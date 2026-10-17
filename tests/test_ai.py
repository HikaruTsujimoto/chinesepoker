import random
import unittest
from chinesepoker.ai.model import Observation, EMPTY, Move, CARDS, board_of, apply_move, validate_move
from chinesepoker.ai.search import choose_move, normal_moves, SearchConfig
from chinesepoker.ai.evaluation import summary, terminal_value
from chinesepoker.core.player import Player
from chinesepoker.core.game import Game


class CpuTests(unittest.TestCase):
    def test_all_opening_and_pineapple_actions(self):
        self.assertEqual(len(list(normal_moves(EMPTY, (0, 1, 2, 3, 4), 5))), 232)
        board = ((0,), (1, 2), (3, 4))
        obs = Observation(board, (5, 6, 7))
        moves = list(normal_moves(board, obs.hand, 2))
        self.assertEqual(len(moves), 27)
        for move in moves:
            validate_move(obs, move)

    def test_card_conservation_over_complete_round(self):
        rng = random.Random(123)
        for _ in range(10):
            cards = rng.sample(range(52), 17)
            board, discards = EMPTY, ()
            for start, count in ((0, 5), (5, 3), (8, 3), (11, 3), (14, 3)):
                obs = Observation(board, tuple(cards[start:start + count]), discards=discards)
                decision = choose_move(obs, 'easy', seed=10)
                board = validate_move(obs, decision.move)
                discards += decision.move.discards
            self.assertEqual(tuple(map(len, board)), (3, 5, 5))
            self.assertEqual(set(c for row in board for c in row) | set(discards), set(cards))

    def test_fixed_budget_is_reproducible_and_does_not_mutate_global_rng(self):
        obs = Observation(EMPTY, (0, 13, 25, 38, 51))
        state = random.getstate()
        config = SearchConfig(seconds=60, samples=2, shortlist=4)
        first = choose_move(obs, seed=42, config=config)
        second = choose_move(obs, seed=42, config=config)
        self.assertEqual(first.move, second.move)
        self.assertEqual(first.estimated_value, second.estimated_value)
        self.assertEqual(random.getstate(), state)

    def test_visible_boundary(self):
        p = Player('opponent')
        p.top = [CARDS[0], CARDS[1]]
        p.mid = [CARDS[2]]
        visible = board_of(p, hidden=[CARDS[1], CARDS[2]])
        p.top[1] = CARDS[30]
        p.mid[0] = CARDS[40]
        self.assertEqual(visible, board_of(p, hidden=[CARDS[30], CARDS[40]]))
        obs = Observation(EMPTY, (3, 4, 5, 6, 7), visible, (8,))
        self.assertTrue(set((0, 3, 4, 5, 6, 7, 8)).isdisjoint(obs.unseen()))
        self.assertIn(30, obs.unseen())
        self.assertIn(40, obs.unseen())
        self.assertNotIn('deck', obs.__dataclass_fields__)

    def test_invalid_move_is_atomic(self):
        p = Player('P')
        hand = list(CARDS[:5])
        with self.assertRaises(ValueError):
            apply_move(p, hand, Move(((0, 0),) * 5, ()))
        self.assertEqual(board_of(p), EMPTY)
        self.assertEqual(hand, list(CARDS[:5]))

    def test_final_street_chooses_non_foul_when_possible(self):
        board = ((12, 25), (0, 13, 26, 1), (2, 15, 28, 41, 3))
        obs = Observation(board, (4, 14, 16))
        result = choose_move(obs, 'normal', seed=0)
        self.assertFalse(summary(validate_move(obs, result.move))[0])
        self.assertTrue(result.method.startswith('final-street enumeration'))

    def test_fantasy_all_tiers_and_zero_budget(self):
        for tier in (14, 15, 16, 17):
            hand = tuple(random.Random(tier).sample(range(52), tier))
            obs = Observation(EMPTY, hand, fantasyland_cards=tier)
            for seconds in (0, 0.05):
                decision = choose_move(obs, seed=3, config=SearchConfig(seconds=seconds))
                board = validate_move(obs, decision.move)
                self.assertEqual(tuple(map(len, board)), (3, 5, 5))
                self.assertEqual(len(decision.move.discards), tier - 13)

    def test_terminal_score_matches_game_when_no_fantasy_bonus(self):
        rng = random.Random(70)
        game = Game([Player('a'), Player('b')])
        for _ in range(30):
            cards = rng.sample(range(52), 26)
            boards = [tuple(tuple(sorted(row)) for row in (cards[i:i+3], cards[i+3:i+8], cards[i+8:i+13])) for i in (0, 13)]
            for p, board in zip(game.players, boards):
                p.top, p.mid, p.bot = ([CARDS[c] for c in row] for row in board)
                p.evaluate_board()
            a, b = game.players
            expected = game.calculate_matchup(a, b)[0] + a.get_royalties() - b.get_royalties()
            if not a.next_fantasyland:
                self.assertEqual(terminal_value(boards[0], boards[1]), expected)


if __name__ == '__main__':
    unittest.main()
