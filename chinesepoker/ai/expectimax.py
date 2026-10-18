"""Own-decision expectimax with an explicit, approximate opponent model.

Chance is averaged BEFORE a previous decision is maximized. No simulated
actor receives a future deal. Exactness refers only to the finite own-hand
problem with a supplied terminal objective, never to the whole OFC game.
"""
from functools import lru_cache
from itertools import combinations
import math
import random
import time

from .model import CAPACITY, Decision, after_move, validate_move
from .evaluation import complete, heuristic
from .search import normal_moves, rollout, sampled_opponent, SearchConfig
from .action_model import load_model, terminal_score


class SearchTimeout(Exception):
    pass


def exact_value(board, unseen, terminal, *, max_states=100000):
    """Exhaustive E_draw[max_action V] for a reduced, finite own-hand tree.

    terminal(board, remaining_cards) must depend only on those arguments.
    All three drawn cards leave the pool, including the discarded card.
    A resource limit raises instead of returning a purported exact value.
    """
    cards = tuple(c for row in board for c in row)
    unseen = tuple(unseen)
    if (len(board) != 3 or any(len(row)>cap for row,cap in zip(board,CAPACITY))
            or len(cards) not in (5,7,9,11,13)
            or len(set(cards+unseen)) != len(cards+unseen)
            or any(not isinstance(c,int) or not 0<=c<52 for c in cards+unseen)):
        raise ValueError('Exact solver requires a valid post-opening normal board and disjoint unseen cards')
    states = 0

    @lru_cache(maxsize=None)
    def visit(board, pool):
        nonlocal states
        states += 1
        if states > max_states:
            raise ValueError('Exact state budget exceeded')
        if complete(board):
            return terminal(board, pool)
        if len(pool) < 3:
            raise ValueError('Insufficient future cards')
        total = 0.0
        for draw in combinations(pool, 3):
            rest = tuple(c for c in pool if c not in draw)
            total += max(visit(after_move(board, m), rest)
                         for m in normal_moves(board, draw, 2))
        return total / math.comb(len(pool), 3)

    return visit(board, tuple(sorted(unseen)))


class Planner:
    def __init__(self, obs, seed, deadline, opponent_samples=4, rollout_samples=2):
        self.obs, self.seed, self.deadline = obs, seed, deadline
        self.opponent_samples, self.rollout_samples = opponent_samples, rollout_samples
        self.model = load_model()
        self.leaves = 0
        self.used_cutoff = False
        self.opponent_cache = {}
        self.value_cache = {}

    def check(self):
        if time.monotonic() >= self.deadline:
            raise SearchTimeout()

    def rng(self, pool, salt=0):
        # Stable across candidates and Python processes, independent of board
        # placement. Identical information uses identical chance samples.
        mask = sum(1 << c for c in pool)
        return random.Random(mask ^ self.seed ^ salt)

    def opponents(self, pool):
        if complete(self.obs.opponent):
            return (self.obs.opponent,)
        if pool not in self.opponent_cache:
            rng = self.rng(pool, 92837)
            boards = []
            for _ in range(self.opponent_samples):
                self.check()
                draws = rng.sample(pool, len(pool))
                boards.append(sampled_opponent(self.obs, draws, self.model, rng, self.deadline))
            self.opponent_cache[pool] = tuple(boards)
        return self.opponent_cache[pool]

    def terminal(self, board, pool):
        self.check()
        self.leaves += 1
        opponents = self.opponents(pool)
        return sum(terminal_score(board, other, self.obs.fantasyland_cards,
                                  self.obs.opponent_fantasyland_cards, self.model)
                   for other in opponents) / len(opponents)

    def cutoff(self, board, pool):
        """Explicit rollout boundary, not an exact value or a learned oracle."""
        self.used_cutoff = True
        rng = self.rng(pool, 10293)
        count = (13-sum(map(len, board)))//2*3
        total = 0.0
        for _ in range(self.rollout_samples):
            self.check()
            draws = tuple(rng.sample(pool, count))
            end = rollout(board, draws)
            rest = tuple(c for c in pool if c not in draws)
            total += self.terminal(end, rest)
        return total/self.rollout_samples

    def value(self, board, pool, depth):
        self.check()
        key = (board, pool, depth)
        if key in self.value_cache:
            return self.value_cache[key]
        if complete(board):
            result = self.terminal(board, pool)
        elif depth <= 0:
            result = self.cutoff(board, pool)
        else:
            # Nested chance expectation is inside this decision's value.
            # A separate draw is NOT picked to favor each candidate.
            rng = self.rng(pool, 71309 + depth)
            hands = (list(combinations(pool, 3)) if len(pool) <= 5 else
                     [tuple(sorted(rng.sample(pool, 3))) for _ in range(2)])
            result = sum(self.best_draw(board, pool, hand, depth-1) for hand in hands)/len(hands)
        self.value_cache[key] = result
        return result

    def best_draw(self, board, pool, draw, depth):
        rest = tuple(c for c in pool if c not in draw)
        values = []
        for move in normal_moves(board, draw, 2):
            self.check()
            values.append(self.value(after_move(board, move), rest, depth))
        return max(values)


def choose_move(obs, seed=None, seconds=5.0, samples=64, shortlist=12):
    if not math.isfinite(seconds) or seconds < 0 or samples < 1 or shortlist < 1:
        raise ValueError('Invalid expectimax budget')
    start = time.monotonic()
    deadline = start+seconds
    rng = random.Random(seed)
    if obs.fantasyland_cards:
        from .search import choose_move as search_move
        decision = search_move(obs, seed=seed, config=SearchConfig(
            seconds=seconds, samples=0, diversified_fantasy=True))
        return Decision(decision.move, decision.candidates, decision.simulations,
                        decision.seconds, decision.estimated_value,
                        'expectimax FL: existing bounded placement search')
    all_moves = list(normal_moves(obs.board, obs.hand, obs.place_count))
    ranked = sorted(all_moves, key=lambda m: heuristic(after_move(obs.board, m)), reverse=True)
    placed = sum(map(len, obs.board))
    # All late-game assignments remain available, including fouls. Early-game
    # pruning is a declared approximation rather than a global-optimum claim.
    candidates = ranked if placed >= 9 else ranked[:shortlist]
    best = ranked[0]
    fallback = heuristic(after_move(obs.board, best))
    pool = obs.unseen()
    planner = Planner(obs, rng.randrange(2**63), deadline)
    totals = [0.0]*len(candidates)
    batches = 0
    total_hands = math.comb(len(pool), 3) if placed < 11 else 1
    if placed == 9:
        # Randomized, without-replacement enumeration is still a uniform
        # estimate if interrupted; full completion exhausts the chance node.
        draws = list(combinations(pool, 3))
        rng.shuffle(draws)
    elif placed == 11:
        draws = [None]
    else:
        draws = [tuple(sorted(rng.sample(pool, 3))) for _ in range(samples)]
    try:
        for draw in draws:
            values = []
            for move in candidates:
                planner.check()
                board = after_move(obs.board, move)
                if draw is None:
                    value = planner.value(board, pool, 0)
                else:
                    # At seven placed cards, optimize BOTH remaining future
                    # decisions; earlier streets retain a rollout boundary.
                    value = planner.best_draw(board, pool, draw, 1 if placed == 7 else 0)
                values.append(value)
            # Never favor early candidates with extra or incomplete samples.
            totals = [a+b for a,b in zip(totals, values)]
            batches += 1
    except SearchTimeout:
        pass
    exact = (placed >= 9 and batches == total_hands and complete(obs.opponent))
    if batches:
        index = max(range(len(candidates)), key=lambda i: totals[i])
        best, estimate = candidates[index], totals[index]/batches
    else:
        estimate = fallback
    validate_move(obs, best)
    method = ('expectimax exact own-hand objective' if exact else 'expectimax approximate')
    method += f' ({batches} complete batches; {len(candidates)}/{len(all_moves)} candidates)'
    if not batches:
        method += '; heuristic fallback'
    if planner.used_cutoff:
        method += '; greedy rollout boundary'
    if not complete(obs.opponent):
        method += '; sampled opponent, public board held fixed'
    return Decision(best, len(all_moves), planner.leaves, time.monotonic()-start, estimate, method)
