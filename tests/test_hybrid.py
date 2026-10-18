import random
import unittest
from unittest.mock import patch
from chinesepoker.ai.value_model import features, fit, load_model, ValueModel
from chinesepoker.ai.model import EMPTY, Observation, validate_move
from chinesepoker.ai.search import SearchConfig, choose_move


class HybridTests(unittest.TestCase):
    def test_generalization_is_suit_invariant(self):
        board = ((12,25),(0,13,5),(1,14,27))
        opponent = ((3,),(4,17),(6,19))
        def permute(b):
            suits = [2,0,3,1]
            return tuple(tuple(sorted(suits[c//13]*13+c%13 for c in row)) for row in b)
        self.assertEqual(features(board,opponent),features(permute(board),permute(opponent)))
        self.assertAlmostEqual(load_model().predict(board,opponent),load_model().predict(permute(board),permute(opponent)))

    def test_model_rejects_malformed_weights(self):
        with self.assertRaises(ValueError):
            ValueModel([float('nan')]*len(features(EMPTY,EMPTY)))
        with self.assertRaises(ValueError):
            ValueModel([1])

    def test_invalid_search_budget_is_rejected(self):
        obs = Observation(EMPTY,(0,1,2,3,4))
        for config in (SearchConfig(seconds=float('nan')), SearchConfig(value_weight=-1)):
            with self.assertRaises(ValueError):
                choose_move(obs,config=config)

    def test_training_refuses_censored_returns(self):
        from tools.train_value import collect
        # At a chance node with the guard already exhausted, no partial score
        # or rows may be silently accepted as a completed session.
        with self.assertRaisesRegex(RuntimeError, 'censored'):
            collect(1,123,max_hands=0)

    def test_session_labels_wait_for_settlement_and_use_each_seat_sign(self):
        from tools.train_value import collect
        # Two observed actions in an already-running FL chain; only the final
        # payoff may label them, with past hand scores subtracted.
        obs = Observation(EMPTY,(0,1,2,3,4))
        class FakeState:
            needs_deal = False
            completed_hands = 1
            def __init__(self, turn=0):
                self.turn = turn
                self.settled = turn == 2
                self.player = turn
                self.total = 17 if self.settled else 5
            def observation(self):
                return obs
            def child(self, move):
                return FakeState(self.turn+1)
        with patch('tools.train_value.SessionState',FakeState):
            rows,_ = collect(1,123)
        self.assertEqual([y for _,y in rows],[12,-12])

    def test_regression_learns_unseen_numeric_state(self):
        size = len(features(EMPTY,EMPTY))
        def x(v):
            return (1.0,v)+(0.0,)*(size-2)
        rows = [(x(v/20),3+2*v/20) for v in range(-20,21)]
        model = fit(rows,epochs=100)
        self.assertAlmostEqual(sum(w*v for w,v in zip(model.weights,x(.325))),3.65,delta=.15)

    def test_new_search_legal_at_all_fl_tiers_and_zero_deadline(self):
        for tier in (14,15,16,17):
            obs = Observation(EMPTY,tuple(random.Random(tier).sample(range(52),tier)),fantasyland_cards=tier)
            for seconds in (0,.08):
                decision = choose_move(obs,config=SearchConfig(seconds=seconds,diversified_fantasy=True),seed=0)
                board = validate_move(obs,decision.move)
                self.assertEqual(tuple(map(len,board)),(3,5,5))
                self.assertEqual(len(decision.move.discards),tier-13)

    def test_generalized_policy_reaches_all_normal_streets(self):
        cards = random.Random(500).sample(range(52),17)
        board, discards = EMPTY, ()
        config = SearchConfig(seconds=60,samples=1,shortlist=3,value_weight=.4)
        for start,count in ((0,5),(5,3),(8,3),(11,3),(14,3)):
            obs = Observation(board,tuple(cards[start:start+count]),discards=discards)
            a = choose_move(obs,config=config,seed=42)
            b = choose_move(obs,config=config,seed=42)
            self.assertEqual(a.move,b.move)
            board = validate_move(obs,a.move)
            discards += a.move.discards
        self.assertEqual(tuple(map(len,board)),(3,5,5))


if __name__ == '__main__':
    unittest.main()
