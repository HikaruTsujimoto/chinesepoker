import hashlib
from itertools import combinations
import random
import time
import unittest

from chinesepoker.ai.expectimax import exact_value, choose_move, Planner
from chinesepoker.ai.model import Observation, after_move, validate_move
from chinesepoker.ai.search import normal_moves


class ExpectimaxTests(unittest.TestCase):
    def test_exact_api_rejects_opening_and_overlapping_cards(self):
        with self.assertRaises(ValueError):
            exact_value(((),(),()),tuple(range(10)),lambda b,p:0)
        with self.assertRaises(ValueError):
            exact_value(((0,),(1,2),(3,4)),(4,5,6),lambda b,p:0)

    def test_two_chance_nodes_average_before_choosing(self):
        board = ((0,1), (2,3,4), (5,6,7,8))
        pool = tuple(range(9,16))

        def reward(board, rest):
            # Irregular but deterministic terminal utility makes a clairvoyant
            # optimizer distinguishable from a policy using only current draws.
            return hashlib.sha256(repr((board,rest)).encode()).digest()[0]/255

        expected, clairvoyant = [], []
        for first in combinations(pool,3):
            rest = tuple(c for c in pool if c not in first)
            second_hands = list(combinations(rest,3))
            rows = []
            for move in normal_moves(board,first,2):
                middle = after_move(board,move)
                values = []
                for second in second_hands:
                    left = tuple(c for c in rest if c not in second)
                    values.append(max(reward(after_move(middle,m),left)
                                      for m in normal_moves(middle,second,2)))
                rows.append(values)
            expected.append(max(sum(row)/len(row) for row in rows))
            clairvoyant.append(sum(max(row[i] for row in rows) for i in range(len(second_hands)))/len(second_hands))
        actual = exact_value(board,pool,reward)
        self.assertAlmostEqual(actual,sum(expected)/len(expected))
        self.assertLess(actual,sum(clairvoyant)/len(clairvoyant))

    def test_discard_also_leaves_future_pool(self):
        board = ((0,1,2),(3,4,5,6),(7,8,9,10))
        pool = (11,12,13,14)
        def terminal(end,rest):
            used = {c for row in end for c in row}
            self.assertEqual(len(rest),1)
            self.assertTrue(used.isdisjoint(rest))
            return rest[0]
        self.assertAlmostEqual(exact_value(board,pool,terminal),12.5)

    def test_exact_budget_is_not_silently_approximate(self):
        with self.assertRaisesRegex(ValueError,'budget'):
            exact_value(((0,1,2),(3,4,5,6),(7,8,9,10)),(11,12,13),lambda b,p:0,max_states=1)

    def test_final_known_opponent_matches_complete_enumeration(self):
        cards=random.Random(15).sample(range(52),27)
        own=(tuple(sorted(cards[:3])),tuple(sorted(cards[3:7])),tuple(sorted(cards[7:11])))
        other=(tuple(sorted(cards[14:17])),tuple(sorted(cards[17:22])),tuple(sorted(cards[22:27])))
        obs=Observation(own,tuple(cards[11:14]),other)
        planner=Planner(obs,3,time.monotonic()+30)
        expected=max(planner.terminal(after_move(obs.board,m),obs.unseen())
                     for m in normal_moves(obs.board,obs.hand,2))
        result=choose_move(obs,seed=3,seconds=5)
        self.assertAlmostEqual(result.estimated_value,expected)
        self.assertIn('exact own-hand objective',result.method)
        validate_move(obs,result.move)

    def test_zero_time_has_legal_honest_fallback(self):
        obs=Observation(((),(),()),(0,2,5,17,30))
        result=choose_move(obs,seconds=0,seed=1)
        validate_move(obs,result.move)
        self.assertIn('heuristic fallback',result.method)
        self.assertNotIn('exact own-hand',result.method)

    def test_penultimate_runtime_matches_exact_reduced_pool(self):
        board=((0,1),(2,3,4),(5,6,7,8))
        other=((12,13,14),(15,16,17,18,19),(20,21,22,23,24))
        # Synthetic known-card boundary leaves only four unseen cards.
        obs=Observation(board,(9,10,11),other,tuple(range(29,52)))
        planner=Planner(obs,4,time.monotonic()+30)
        expected=max(exact_value(after_move(board,m),obs.unseen(),planner.terminal)
                     for m in normal_moves(board,obs.hand,2))
        result=choose_move(obs,seed=4,seconds=5)
        self.assertAlmostEqual(result.estimated_value,expected)
        self.assertIn('exact own-hand objective',result.method)
        self.assertIn('(4 complete batches',result.method)

    def test_opponent_samples_exclude_own_future_draw_and_discards(self):
        obs=Observation(((0,1,2),(3,4,5,6),(7,8,9,10)),(11,12,13),discards=(14,15,16))
        planner=Planner(obs,7,time.monotonic()+30)
        for board in planner.opponents(obs.unseen()):
            used={c for row in board for c in row}
            self.assertTrue(used.issubset(set(obs.unseen())))
            self.assertEqual(len(used),13)


if __name__=='__main__':
    unittest.main()
