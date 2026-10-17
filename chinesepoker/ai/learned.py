"""Opt-in use of a saved single-hand average policy; explicit Normal fallback."""
from functools import lru_cache
from pathlib import Path
import random
import time

from .mccfr import OutcomeSampling, normalize
from .model import Decision, validate_move
from .search import choose_move, normal_moves
from .training_games import OFCOneHand, information_key


@lru_cache(maxsize=1)
def _load(path, modified, size):
    return OutcomeSampling.load(path, OFCOneHand(), max_nodes=1000000)


def choose_learned(observation, path, history=(), seat=1, supported=True, seed=None):
    start = time.monotonic()
    if supported and not observation.fantasyland_cards:
        file = Path(path).resolve()
        stat = file.stat()
        solver = _load(str(file), stat.st_mtime_ns, stat.st_size)
        key = information_key(seat, history, observation)
        node = solver.nodes.get(key)
        if node is not None and sum(node.average) > 0:
            moves = tuple(normal_moves(observation.board, tuple(sorted(observation.hand)), observation.place_count))
            if len(moves) != len(node.average):
                raise ValueError('Saved strategy has incompatible actions')
            move = random.Random(seed).choices(moves, weights=normalize(node.average), k=1)[0]
            validate_move(observation, move)
            return Decision(move, len(moves), 0, time.monotonic()-start, 0.0,
                            f'MCCFR average ({node.visits} updates; no value estimate)')
        reason = 'unseen information set'
    else:
        reason = 'Fantasyland outside trained game'
    result = choose_move(observation, 'normal', seed=seed)
    return Decision(result.move, result.candidates, result.simulations, time.monotonic()-start,
                    result.estimated_value, f'Normal fallback: {reason}; {result.method}')
