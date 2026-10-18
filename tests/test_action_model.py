import random
import unittest
from unittest.mock import patch
from chinesepoker.ai.action_model import ActionModel, FORMAT, action_features, terminal_score
from chinesepoker.ai.model import EMPTY, Observation, Move, after_move, validate_move
from chinesepoker.ai.search import normal_moves, choose_move, SearchConfig
from chinesepoker.ai.session_game import SessionState
from chinesepoker.ai.evaluation import terminal_value, summary, continuation_value


class ActionModelTests(unittest.TestCase):
    def model(self):
        obs=Observation(EMPTY,(0,13,1,2,3))
        move=next(normal_moves(obs.board,obs.hand,5))
        width=len(action_features(obs,move))
        return dict(format=FORMAT,w1=[[0.0]*width],b1=[0.0],w2=[1.0],continuation=[[0.0]*5 for _ in range(5)])

    def test_opponent_can_change_relative_candidate_scores(self):
        data=self.model()
        data['w1'][0][74]=1
        data['w1'][0][74+39+5]=1
        model=ActionModel(data)
        hand=(0,13,1,2,3)
        a=Move(((0,0),(13,2),(1,2),(2,2),(3,2)),())
        b=Move(tuple((c,2) for c in hand),())
        old=model.scores(Observation(EMPTY,hand),[a,b])
        new=model.scores(Observation(EMPTY,hand,((5,),(),())),[a,b])
        self.assertNotAlmostEqual(old[0]-old[1],new[0]-new[1])

    def test_known_discards_and_opponent_tier_are_features(self):
        obs=Observation(((0,),(1,2),(3,4)),(5,6,7),discards=(8,))
        move=next(normal_moves(obs.board,obs.hand,2))
        other=Observation(obs.board,obs.hand,discards=(9,),opponent_fantasyland_cards=17)
        self.assertNotEqual(action_features(obs,move),action_features(other,move))

    def test_suit_permutation_preserves_features(self):
        obs=Observation(((0,),(1,14),(2,15)),(3,16,29),((4,),(5,),(6,)),(7,),0,14)
        move=next(normal_moves(obs.board,obs.hand,2))
        suits=(2,0,3,1)
        def card(c): return suits[c//13]*13+c%13
        def board(b): return tuple(tuple(sorted(map(card,row))) for row in b)
        changed=Observation(board(obs.board),tuple(map(card,obs.hand)),board(obs.opponent),tuple(map(card,obs.discards)),0,14)
        changed_move=Move(tuple((card(c),r) for c,r in move.placements),tuple(map(card,move.discards)))
        self.assertEqual(action_features(obs,move),action_features(changed,changed_move))

    def test_model_changes_final_normal_action_not_just_shortlist(self):
        obs=Observation(EMPTY,(0,13,25,38,51))
        moves=list(normal_moves(obs.board,obs.hand,5))
        old=choose_move(obs,seed=7,config=SearchConfig(seconds=60,samples=1,shortlist=232))
        target=next(m for m in moves if m!=old.move)
        class ForcedModel:
            def scores(self,obs,moves): return [100 if m==target else 0 for m in moves]
            def tail(self,a,b): return 0
        with patch('chinesepoker.ai.action_model.load_model',return_value=ForcedModel()):
            new=choose_move(obs,seed=7,config=SearchConfig(seconds=60,samples=1,shortlist=232,action_weight=1))
        self.assertEqual(new.move,target)
        validate_move(obs,new.move)

    def test_continuation_replaces_bonus_without_double_counting(self):
        cards=random.Random(25).sample(range(52),26)
        boards=[tuple(tuple(sorted(r)) for r in (cards[i:i+3],cards[i+3:i+8],cards[i+8:i+13])) for i in (0,13)]
        model=ActionModel(self.model())
        expected=terminal_value(boards[0],boards[1])-continuation_value(summary(boards[0])[2])
        self.assertEqual(terminal_score(*boards,0,0,model),expected)

    def test_model_rejects_asymmetric_or_nonfinite_matrix(self):
        data=self.model(); data['continuation'][0][1]=1
        with self.assertRaises(ValueError): ActionModel(data)
        data=self.model(); data['w1'][0][0]=float('nan')
        with self.assertRaises(ValueError): ActionModel(data)

    def test_session_exposes_public_opponent_fl_tier(self):
        state=SessionState(tiers=(0,17)).sample_chance(random.Random(1))
        self.assertEqual(state.observation().opponent_fantasyland_cards,17)


if __name__=='__main__':
    unittest.main()
