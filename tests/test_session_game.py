from dataclasses import replace
from itertools import combinations
from math import comb
from collections import Counter
from pathlib import Path
import random
import tempfile
import unittest

from chinesepoker.ai.model import EMPTY, CARDS, Observation, encode, validate_move
from chinesepoker.ai.evaluation import summary
from chinesepoker.ai.mccfr import OutcomeSampling, ActionLimit, TrajectoryLimit
from chinesepoker.ai.session_game import OFCSession, SessionState, FantasyActions, unrank_combination, can_settle
from chinesepoker.core.card import Card
from chinesepoker.core.player import Player
from chinesepoker.core.game import Game
from tools.evaluate_mccfr import evaluate_sessions


def board(*rows):
    return tuple(tuple(sorted(encode(Card(c[0],c[1:])) for c in row.split())) for row in rows)


ENTRY = board('SQ HQ D2', 'C4 S5 H6 D7 C8', 'S9 H10 DJ CQ SK')
STAY = board('SA HA DA', 'S2 H3 D4 C5 S6', 'S7 H8 D9 C10 SJ')


def no_fl_opponent(other):
    rng = random.Random(91)
    remaining = [c for c in range(52) if c not in {c for row in other for c in row}]
    while True:
        cards = rng.sample(remaining,13)
        b = (tuple(sorted(cards[:3])),tuple(sorted(cards[3:8])),tuple(sorted(cards[8:])))
        if not summary(b)[2] and not summary(b,14)[2]:
            return b


def actual_score(boards, tiers):
    players = [Player('a'),Player('b')]
    for p,b,t in zip(players,boards,tiers):
        p.top,p.mid,p.bot = ([CARDS[c] for c in row] for row in b)
        p.fantasyland, p.fantasyland_cards = bool(t), t
        p.evaluate_board()
    a,b = players
    return Game(players).calculate_matchup(a,b)[0]+a.get_royalties()-b.get_royalties()


class SessionTests(unittest.TestCase):
    def test_entry_continuation_switch_sides_and_settle(self):
        state = SessionState()
        total = 0
        rounds = [(ENTRY,no_fl_opponent(ENTRY)), (STAY,no_fl_opponent(STAY)),
                  (no_fl_opponent(ENTRY),ENTRY), (ENTRY,no_fl_opponent(ENTRY))]
        expected = [(14,0),(14,0),(0,14),(14,0)]
        # Enter, retain same tier despite top AAA, then transfer FL to the other
        # player. The chain must not end just because the original player exits.
        for boards,tiers in zip(rounds,expected):
            total += actual_score(boards,state.tiers)
            state = state.finish_hand(boards)
            self.assertEqual(state.tiers,tiers)
            self.assertEqual(state.total,total)
            self.assertEqual(state.player,-1)
            with self.assertRaises(ValueError):
                state.payoff(0)
        # QQ alone cannot retain FL. Other side has no entry/retention condition.
        boards = (ENTRY,no_fl_opponent(ENTRY))
        total += actual_score(boards,state.tiers)
        state = state.finish_hand(boards)
        self.assertTrue(state.settled)
        self.assertTrue(can_settle(state.tiers))
        self.assertEqual(state.completed_hands,5)
        self.assertEqual(state.payoff(0),total)
        self.assertEqual(state.payoff(1),-total)
        self.assertEqual(len(state.histories[0]),5)

    def test_every_tier_is_preserved(self):
        for tier in (14,15,16,17):
            result = SessionState(tiers=(tier,0)).finish_hand((STAY,no_fl_opponent(STAY)))
            self.assertEqual(result.tiers,(tier,0))

    def test_exact_fantasy_actions_are_lazy_and_complete(self):
        items = tuple(range(8))
        self.assertEqual([unrank_combination(items,3,i) for i in range(comb(8,3))],list(combinations(items,3)))
        for tier in (14,15,16,17):
            obs = Observation(EMPTY,tuple(range(tier)),fantasyland_cards=tier)
            actions = FantasyActions(obs.hand)
            self.assertEqual(len(actions),comb(tier,3)*comb(tier-3,5)*comb(tier-8,5))
            indices = {0,1,len(actions)//2,len(actions)-1}
            self.assertEqual(len({actions[i] for i in indices}),len(indices))
            for i in indices:
                validate_move(obs,actions[i])
            with self.assertRaises(IndexError):
                actions[len(actions)]

    def test_normal_first_and_both_fantasy_keep_actions_hidden(self):
        for tiers in ((0,14),(17,0),(14,16)):
            state = OFCSession(8,tiers).start(None).sample_chance(random.Random(3))
            self.assertEqual(len({c for hand in state.deals for c in hand}),sum(map(len,state.deals)))
            if 0 in tiers:
                normal = tiers.index(0)
                self.assertEqual(state.schedule[:5],tuple((normal,s) for s in range(5)))
                for _ in range(5):
                    state = state.child(state.actions()[0])
                self.assertEqual(sum(map(len,state.observation().opponent)),13)
                self.assertNotEqual(state.player,normal)
                self.assertEqual(sum(event[0]=='reveal' for event in state.histories[state.player]),5)
            else:
                actions = state.actions()
                a,b = state.child(actions[0]),state.child(actions[-1])
                self.assertEqual(a.key(),b.key())
                self.assertEqual(a.observation().opponent,EMPTY)

    def test_hidden_deals_and_previous_history_boundaries(self):
        state = OFCSession(8).start(None).sample_chance(random.Random(5))
        deals = list(state.deals)
        deals[1],deals[2] = deals[2],deals[1]
        self.assertEqual(state.key(),replace(state,deals=tuple(deals)).key())
        self.assertNotEqual(state.key(),replace(state,histories=((('old hand',),),())).key())

    def test_limits_roll_back_random_state_and_updates_without_settlement(self):
        solver = OutcomeSampling(OFCSession(0,(14,0)),seed=13,max_actions=10000)
        rng = solver.rng.getstate()
        with self.assertRaises(ActionLimit):
            solver.iteration()
        self.assertEqual(solver.nodes,{})
        self.assertEqual(solver.rng.getstate(),rng)
        self.assertEqual(solver.iterations,0)
        class ContinuedGame:
            def start(self,rng):
                return SessionState(tiers=(14,0),completed_hands=1,total=42)
        solver = OutcomeSampling(ContinuedGame(),max_hands=1)
        with self.assertRaises(TrajectoryLimit):
            solver.iteration()
        self.assertEqual(solver.iterations,0)
        self.assertEqual(solver.nodes,{})
        result = evaluate_sessions(solver,pairs=1)
        self.assertEqual(result['settled_sessions'],0)
        self.assertIsNone(result['mean_points'])
        self.assertTrue(all(r['points'] is None for r in result['records']))

    def test_session_resume_is_identical_and_abstraction_is_identified(self):
        game = OFCSession(8,(14,14))
        solver = OutcomeSampling(game,seed=9)
        solver.iteration()
        with tempfile.TemporaryDirectory(dir='.') as directory:
            path = Path(directory)/'session.json'
            solver.save(path)
            restored = OutcomeSampling.load(path,game)
            solver.iteration()
            restored.iteration()
            self.assertEqual(solver.nodes,restored.nodes)
            self.assertEqual(solver.rng.getstate(),restored.rng.getstate())
            with self.assertRaises(ValueError):
                OutcomeSampling.load(path,OFCSession(16,(14,14)))

    def test_a_deal_can_force_absorption_regardless_of_placement(self):
        # Each player gets only ranks 2..J, at most two of each. Then no top
        # QQ/KK/AA/trips, full house, quads OR straight flush can be formed.
        pools = [[],[]]
        for i,r in enumerate(Card.RANKS[:10]):
            selected = {i%4,(i+1)%4} if i<7 else {i%4}
            for s in selected:
                pools[0].append(encode(Card(Card.SUITS[s],r)))
            for s in [s for s in range(4) if s not in selected][:(2 if i<7 else 1)]:
                pools[1].append(encode(Card(Card.SUITS[s],r)))
        for tiers in ((0,0),(14,0),(0,17),(14,17),(17,17)):
            state = OFCSession(8,tiers).start(None).sample_chance(random.Random(1))
            consumed = [0,0]
            deals = []
            for (p,street),old_hand in zip(state.schedule,state.deals):
                count = len(old_hand)
                deals.append(tuple(sorted(pools[p][consumed[p]:consumed[p]+count])))
                consumed[p] += count
            for p in (0,1):
                values = [c%13+2 for (actor,_),hand in zip(state.schedule,deals) if actor==p for c in hand]
                self.assertLessEqual(max(Counter(values).values()),2)
                self.assertLessEqual(max(values),11)
                cards = [c for (actor,_),hand in zip(state.schedule,deals) if actor==p for c in hand]
                for suit in range(4):
                    ranks = {c%13+2 for c in cards if c//13==suit}
                    self.assertFalse(any(set(range(low,low+5)) <= ranks for low in range(2,11)))
            state = replace(state,deals=tuple(deals))
            while state.player in (0,1):
                state = state.child(state.actions()[0])
            self.assertTrue(state.settled)
            self.assertEqual(state.completed_hands,1)

    def test_long_trajectories_do_not_depend_on_python_recursion(self):
        class State:
            def __init__(self,depth=0):
                self.depth = depth
            @property
            def player(self):
                return None if self.depth == 1500 else self.depth%2
            def actions(self):
                return (0,)
            def key(self):
                return str(self.depth)
            def child(self,action):
                return State(self.depth+1)
            def payoff(self,player):
                return 1 if player == 0 else -1
        class DeepGame:
            def start(self,rng):
                return State()
        solver = OutcomeSampling(DeepGame(),max_steps=1600)
        solver.iteration()
        self.assertEqual(solver.iterations,1)
        self.assertEqual(len(solver.nodes),1500)


if __name__ == '__main__':
    unittest.main()
