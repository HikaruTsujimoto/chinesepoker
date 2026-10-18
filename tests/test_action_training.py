import importlib.util
import random
import unittest
from chinesepoker.ai.model import EMPTY, Observation, validate_move
from chinesepoker.ai.search import greedy_move
from chinesepoker.ai.action_model import ActionModel, FORMAT, action_features


@unittest.skipUnless(importlib.util.find_spec('numpy'),'Install requirements/training.txt for trainer tests')
class TrainingTests(unittest.TestCase):
    def test_sampled_deal_conserves_known_cards_and_hides_first_action(self):
        from tools.train_action_model import sampled_remainder
        obs=Observation(((0,),(1,2),(3,4)),(5,6,7),((8,),(9,10),(11,12)),(13,))
        state=sampled_remainder(obs,12)
        dealt=[c for hand in state.deals for c in hand]
        self.assertEqual(len(dealt),len(set(dealt)))
        self.assertTrue(set(dealt[3:]).issubset(set(obs.unseen())))
        nxt=state.child(greedy_move(obs.board,obs.hand,2))
        self.assertEqual(nxt.player,1)
        self.assertEqual(nxt.observation().opponent,obs.board)
        while state.completed_hands==0:
            o=state.observation()
            state=state.child(greedy_move(o.board,o.hand,o.place_count))
        self.assertEqual(state.completed_hands,1)

    def test_waiting_fantasy_player_receives_correct_number(self):
        from tools.train_action_model import sampled_remainder
        obs=Observation(EMPTY,(0,1,2,3,4),opponent_fantasyland_cards=17)
        state=sampled_remainder(obs,0)
        self.assertEqual(state.schedule,((0,0),(0,1),(0,2),(0,3),(0,4),(1,5)))
        self.assertEqual(len(state.deals[-1]),17)

    def test_numpy_and_standalone_predictions_agree(self):
        from tools.train_action_model import FastModel
        obs=Observation(EMPTY,(0,1,2,3,4))
        move=greedy_move(obs.board,obs.hand,5)
        width=len(action_features(obs,move))
        rng=random.Random(5)
        data=dict(format=FORMAT,w1=[[rng.uniform(-1,1) for _ in range(width)] for _ in range(3)],
                  b1=[.1,.2,.3],w2=[.1,-.2,.3],continuation=[[0.0]*5 for _ in range(5)])
        self.assertAlmostEqual(ActionModel(data).scores(obs,[move])[0],FastModel(data).scores(obs,[move])[0],places=10)

    def test_censored_continuation_has_no_payoff(self):
        from tools.train_action_model import finish_session
        from chinesepoker.ai.session_game import SessionState
        with self.assertRaisesRegex(RuntimeError,'Censored'):
            finish_session(SessionState(tiers=(14,17)),None,random.Random(0),random.Random(1),0)


if __name__=='__main__':
    unittest.main()
