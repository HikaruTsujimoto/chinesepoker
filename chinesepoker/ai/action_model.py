"""Nonlinear candidate advantage model. Pure-Python deployment, no NumPy."""
from collections import Counter
from functools import lru_cache
import json
import math
from pathlib import Path
from .model import after_move, EMPTY
from .value_model import features

FORMAT = 'ofc-action-advantage-v1'
DEFAULT_MODEL = Path(__file__).with_name('action_advantage.json')
TIERS = (0,14,15,16,17)


@lru_cache(maxsize=65536)
def _counts(row):
    ranks=Counter(c%13 for c in row)
    suits=Counter(c//13 for c in row)
    return tuple(ranks[r]/4 for r in range(13)),tuple(suits[s] for s in range(4))


@lru_cache(maxsize=4096)
def _unseen(obs):
    cards=obs.unseen()
    return cards,_counts(cards)[1]


def action_features(obs, move):
    board = after_move(obs.board, move)
    x = list(features(board, obs.opponent, obs.fantasyland_cards))
    # Exact rank multiplicities, including known unavailable cards. No hidden
    # opponent cards or future draws are available to this function.
    unseen,unseen_suits=_unseen(obs)
    for row in (*board, *obs.opponent, obs.discards+move.discards, unseen):
        x.extend(_counts(row)[0])
    for row in board:
        # Match suit availability to the suit being collected in THIS row.
        counts=_counts(row)[1]
        x.append(max((n*unseen_suits[s]/65 for s,n in enumerate(counts)),default=0))
    x.extend((obs.opponent_fantasyland_cards/17, sum(map(len,obs.board))/13))
    return tuple(x)


class ActionModel:
    def __init__(self, data):
        if data.get('format') != FORMAT:
            raise ValueError('Unsupported action model')
        self.w1, self.b1, self.w2 = data['w1'], data['b1'], data['w2']
        self.prior_scale = data.get('prior_scale',0.0)
        from .model import Observation, Move
        sample = Observation(EMPTY,(0,1,2,3,4))
        width = len(action_features(sample,Move(tuple((c,2) for c in sample.hand),())))
        if (not self.w1 or len(self.w1)!=len(self.b1) or len(self.w2)!=len(self.b1)
                or any(len(row)!=width for row in self.w1)):
            raise ValueError('Invalid network shape')
        self.continuation = data['continuation']
        if len(self.continuation)!=5 or any(len(row)!=5 for row in self.continuation):
            raise ValueError('Invalid continuation matrix')
        numbers = [self.prior_scale]+[v for row in self.w1 for v in row]+self.b1+self.w2+[v for row in self.continuation for v in row]
        if not all(math.isfinite(v) for v in numbers):
            raise ValueError('Non-finite model parameter')
        if any(abs(self.continuation[i][j]+self.continuation[j][i])>1e-8 for i in range(5) for j in range(5)):
            raise ValueError('Continuation must be antisymmetric')

    def predict_features(self, x):
        return self.prior_scale*100*x[37]+20*sum(v*math.tanh(b+sum(w*z for w,z in zip(row,x)))
                      for row,b,v in zip(self.w1,self.b1,self.w2))

    def scores(self, obs, moves):
        return [self.predict_features(action_features(obs,m)) for m in moves]

    def tail(self, own, other):
        return self.continuation[TIERS.index(own)][TIERS.index(other)]


@lru_cache(maxsize=4)
def load_model(path=DEFAULT_MODEL):
    return ActionModel(json.loads(Path(path).read_text(encoding='utf-8')))


def terminal_score(board, opponent, own_tier, other_tier, model):
    from .evaluation import terminal_value, summary, continuation_value
    own_next = summary(board,own_tier)[2]
    other_next = summary(opponent,other_tier)[2]
    actual = terminal_value(board,opponent,own_tier)-continuation_value(own_next)
    return actual+model.tail(own_next,other_next)
