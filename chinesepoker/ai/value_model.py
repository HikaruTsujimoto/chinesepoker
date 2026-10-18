"""Suit-invariant linear session value model; no equilibrium guarantee."""
from collections import Counter
from functools import lru_cache
import json
import math
from pathlib import Path

from .evaluation import row_potential, heuristic
from .model import CAPACITY

FORMAT = 'ofc-session-value-v1'
DEFAULT_MODEL = Path(__file__).with_name('session_value.json')


@lru_cache(maxsize=65536)
def _row_features(row,i):
    ranks = [c % 13 + 2 for c in row]
    counts = Counter(ranks)
    suits = Counter(c // 13 for c in row)
    unique = set(ranks)
    if 14 in unique:
        unique.add(1)
    connected = max(len(unique.intersection(range(low, low+5))) for low in range(1, 11))
    strength, potential = row_potential(row,i)
    return (len(row)/CAPACITY[i],strength/9,potential/20,
            sum(ranks)/70,max(ranks,default=0)/14,
            sum(n==2 for n in counts.values())/2,
            float(any(n>=3 for n in counts.values())),float(any(n==4 for n in counts.values())),
            max(suits.values(),default=0)/5,connected/5,
            float(any(r>=12 and n>=2 for r,n in counts.items())))


def _board_features(board):
    rows=[_row_features(row,i) for i,row in enumerate(board)]
    # Use the original unscaled strengths to preserve floating-point results.
    strengths=[row_potential(row,i)[0] for i,row in enumerate(board)]
    return tuple(v for row in rows for v in row)+(max(0,strengths[0]-strengths[1])/9,
            max(0,strengths[1]-strengths[2])/9,max(-100,min(100,heuristic(board)))/100)


def features(board, opponent, tier=0):
    """Only public opponent cards and own afterstate; no deck or hidden hand."""
    return (1.0,tier/17)+_board_features(board)+_board_features(opponent)


class ValueModel:
    def __init__(self, weights):
        self.weights = tuple(weights)
        if len(self.weights) != len(features(((),(),()), ((),(),()))) or not all(math.isfinite(x) for x in weights):
            raise ValueError('Invalid value model weights')

    def predict(self, board, opponent, tier=0):
        return sum(w*x for w,x in zip(self.weights, features(board, opponent, tier)))


@lru_cache(maxsize=8)
def load_model(path=DEFAULT_MODEL):
    data = json.loads(Path(path).read_text(encoding='utf-8'))
    if data.get('format') != FORMAT:
        raise ValueError('Unsupported value model format')
    return ValueModel(data['weights'])


def fit(rows, epochs=40, rate=.015, ridge=.002, seed=0):
    """Regularized SGD; training needs no additional runtime dependencies."""
    import random
    rng = random.Random(seed)
    rows = list(rows)
    if not rows:
        raise ValueError('No completed training sessions')
    weights = [0.0]*len(rows[0][0])
    for epoch in range(epochs):
        rng.shuffle(rows)
        step = rate / (1+epoch/10)
        for x,y in rows:
            error = sum(w*v for w,v in zip(weights,x))-y
            for i,v in enumerate(x):
                weights[i] -= step*(error*v + (ridge*weights[i] if i else 0))
    return ValueModel(weights)
