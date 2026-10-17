"""Time-bounded Monte Carlo rollout policy, not an equilibrium solver."""
from dataclasses import dataclass
from itertools import combinations, product
import random
import time
from .model import CAPACITY, EMPTY, Move, Decision, after_move, validate_move
from .evaluation import heuristic, terminal_value, complete, rank, compare_hands, summary


@dataclass(frozen=True)
class SearchConfig:
    seconds: float = 1.5
    samples: int = 64
    shortlist: int = 16
    fantasy_bottoms: int = 384


LEVELS = {
    'easy': SearchConfig(0.25, 0, 1, 48),
    'normal': SearchConfig(1.5, 64, 16, 384),
    'hard': SearchConfig(5.0, 256, 32, 2048),
}


def normal_moves(board, hand, place):
    """Enumerate ALL current-street assignments and discard choices."""
    for selected in combinations(range(len(hand)), place):
        for rows in product(range(3), repeat=place):
            if any(len(board[r]) + rows.count(r) > CAPACITY[r] for r in range(3)):
                continue
            yield Move(tuple((hand[i], r) for i, r in zip(selected, rows)),
                       tuple(c for i, c in enumerate(hand) if i not in selected))


def greedy_move(board, hand, place):
    return max(normal_moves(board, hand, place), key=lambda m: heuristic(after_move(board, m)))


def rollout(board, draws):
    """Only the current sampled draw is visible to the continuation policy."""
    index = 0
    while not complete(board):
        place = min(2, 13 - sum(map(len, board)))
        hand = draws[index:index + 3]
        if len(hand) < place:
            raise ValueError('Not enough sampled future cards')
        board = after_move(board, greedy_move(board, hand, place))
        index += 3
    return board


def opponent_completion(board, draws):
    """Approximate unknown opponent placement; no real hidden cards are read."""
    index = 0
    if board == EMPTY:
        board = after_move(board, greedy_move(board, draws[:5], 5))
        index = 5
    return rollout(board, draws[index:])


def choose_move(observation, difficulty='normal', seed=None, config=None):
    config = config or LEVELS[difficulty]
    if config.seconds < 0 or config.samples < 0 or config.shortlist < 1 or config.fantasy_bottoms < 1:
        raise ValueError('Invalid search configuration')
    start = time.monotonic()
    deadline = start + config.seconds
    rng = random.Random(seed)
    if observation.fantasyland_cards:
        return fantasy_move(observation, config, rng, start, deadline)
    moves = list(normal_moves(observation.board, observation.hand, observation.place_count))
    ranked = sorted(moves, key=lambda m: heuristic(after_move(observation.board, m)), reverse=True)
    best = ranked[0]
    # Final-street placements are all evaluated, without pruning.
    if complete(after_move(observation.board, best)):
        opponent = observation.opponent if complete(observation.opponent) else None
        best = max(moves, key=lambda m: (terminal_value(after_move(observation.board, m), opponent),
                                         not summary(after_move(observation.board, m))[0]))
        value = terminal_value(after_move(observation.board, best), opponent)
        return Decision(best, len(moves), 0, time.monotonic() - start, value, 'final-street enumeration')
    candidates = ranked[:config.shortlist]
    totals = [0.0] * len(candidates)
    simulations = 0
    batches = 0
    unseen = list(observation.unseen())
    remaining = (13 - sum(map(len, observation.board)) - observation.place_count) // 2
    for _ in range(config.samples):
        if time.monotonic() >= deadline:
            break
        rng.shuffle(unseen)
        own_draws = tuple(unseen[:remaining * 3])
        other_draws = tuple(unseen[remaining * 3:])
        opponent = opponent_completion(observation.opponent, other_draws)
        values = []
        # Common random numbers make comparisons less noisy. Incomplete batches
        # are discarded so a deadline cannot favor earlier candidates.
        for move in candidates:
            if time.monotonic() >= deadline:
                break
            board = rollout(after_move(observation.board, move), own_draws)
            values.append(terminal_value(board, opponent))
            simulations += 1
        if len(values) != len(candidates):
            break
        totals = [a + b for a, b in zip(totals, values)]
        batches += 1
    if batches:
        index = max(range(len(candidates)), key=lambda i: totals[i])
        best, value = candidates[index], totals[index] / batches
    else:
        value = heuristic(after_move(observation.board, best))
    validate_move(observation, best)
    return Decision(best, len(moves), simulations, time.monotonic() - start, value,
                    f'rollouts ({batches} complete batches)' if batches else 'heuristic fallback')


def fantasy_move(obs, config, rng, start, deadline):
    hand = tuple(sorted(obs.hand))
    opponent = obs.opponent if complete(obs.opponent) else None
    best_board = (hand[:3], hand[3:8], hand[8:13])
    best_value = terminal_value(best_board, opponent, obs.fantasyland_cards)
    evaluated = 1
    # Establish an anytime incumbent before the more expensive subset search.
    for _ in range(128):
        if time.monotonic() >= deadline:
            break
        shuffled = rng.sample(hand, len(hand))
        board = tuple(tuple(sorted(row)) for row in (shuffled[:3], shuffled[3:8], shuffled[8:13]))
        value = terminal_value(board, opponent, obs.fantasyland_cards)
        evaluated += 1
        if (value, not summary(board, obs.fantasyland_cards)[0]) > (best_value, not summary(best_board, obs.fantasyland_cards)[0]):
            best_board, best_value = board, value
    fives = []
    for cards in combinations(hand, 5):
        if time.monotonic() >= deadline:
            break
        fives.append((rank(cards), sum(1 << c for c in cards), cards))
    fives.sort(reverse=True)
    stop = False
    for bot_rank, bot_mask, bot in fives[:config.fantasy_bottoms]:
        if stop or time.monotonic() >= deadline:
            break
        for mid_rank, mid_mask, mid in fives:
            if time.monotonic() >= deadline:
                stop = True
                break
            if bot_mask & mid_mask or compare_hands(bot_rank, mid_rank) < 0:
                continue
            rest = tuple(c for c in hand if not ((bot_mask | mid_mask) & (1 << c)))
            for top in combinations(rest, 3):
                if compare_hands(mid_rank, rank(top)) < 0:
                    continue
                board = (top, mid, bot)
                value = terminal_value(board, opponent, obs.fantasyland_cards)
                evaluated += 1
                if (value, not summary(board, obs.fantasyland_cards)[0]) > (best_value, not summary(best_board, obs.fantasyland_cards)[0]):
                    best_board, best_value = board, value
    used = {c for row in best_board for c in row}
    move = Move(tuple((c, i) for i, row in enumerate(best_board) for c in row),
                tuple(c for c in hand if c not in used))
    validate_move(obs, move)
    return Decision(move, evaluated, 0, time.monotonic() - start, best_value, 'bounded Fantasyland subset search')
