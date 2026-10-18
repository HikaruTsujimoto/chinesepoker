"""Time-bounded Monte Carlo rollout policy, not an equilibrium solver."""
from dataclasses import dataclass
from itertools import combinations, product
import random
import time
import math
from .model import CAPACITY, EMPTY, Move, Decision, after_move, validate_move
from .evaluation import heuristic, terminal_value, complete, rank, compare_hands, summary


@dataclass(frozen=True)
class SearchConfig:
    seconds: float = 1.5
    samples: int = 64
    shortlist: int = 16
    fantasy_bottoms: int = 384
    opponent_aware_final: bool = True
    value_weight: float = 0.0
    diversified_fantasy: bool = False
    action_weight: float = 0.0


LEVELS = {
    'easy': SearchConfig(0.25, 0, 1, 48),
    'normal': SearchConfig(1.5, 64, 16, 384),
    'hard': SearchConfig(5.0, 256, 32, 2048),
    'hybrid': SearchConfig(1.5, 64, 16, 384, True, 0.4, True),
    'adaptive': SearchConfig(1.5, 64, 16, 384, True, 0.0, True, 0.35),
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
    if (not math.isfinite(config.seconds) or config.seconds < 0 or config.samples < 0
            or config.shortlist < 1 or config.fantasy_bottoms < 1
            or not math.isfinite(config.value_weight) or config.value_weight < 0):
        raise ValueError('Invalid search configuration')
    if not math.isfinite(config.action_weight) or not 0 <= config.action_weight <= 1:
        raise ValueError('Invalid action-model mixing weight')
    start = time.monotonic()
    deadline = start + config.seconds
    rng = random.Random(seed)
    if observation.fantasyland_cards:
        if config.diversified_fantasy:
            from .fantasy_search import search
            return search(observation, config, rng, start, deadline)
        return fantasy_move(observation, config, rng, start, deadline)
    moves = list(normal_moves(observation.board, observation.hand, observation.place_count))
    action_model, advantages = None, {}
    if config.action_weight:
        from .action_model import load_model as load_action_model
        action_model = load_action_model()
        advantages = dict(zip(moves,action_model.scores(observation,moves)))
    model = None
    if config.value_weight:
        from .value_model import load_model
        model = load_model()
    def priority(move):
        board = after_move(observation.board, move)
        base = heuristic(board)
        if action_model is not None and base >= -90 and not complete(board):
            return base+config.action_weight*advantages[move]
        # Keep irreparable foul protection and final-street exact evaluation.
        if model is None or base < -90 or complete(board):
            return base
        return base + config.value_weight*max(-20, min(20, model.predict(board, observation.opponent)))
    ranked = sorted(moves, key=priority, reverse=True)
    best = ranked[0]
    # Final-street placements are all evaluated, without pruning.
    if complete(after_move(observation.board, best)):
        return final_street(observation, moves, config, rng, start, deadline, action_model)
    candidates = ranked[:config.shortlist]
    if action_model is not None:
        candidates = ([m for m in ranked if heuristic(after_move(observation.board,m))>=-90] or ranked)[:config.shortlist]
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
        opponent = sampled_opponent(observation, other_draws, action_model, rng, deadline)
        values = []
        # Common random numbers make comparisons less noisy. Incomplete batches
        # are discarded so a deadline cannot favor earlier candidates.
        for move in candidates:
            if time.monotonic() >= deadline:
                break
            board = rollout(after_move(observation.board, move), own_draws)
            values.append(search_value(board, opponent, observation, action_model))
            simulations += 1
        if len(values) != len(candidates):
            break
        totals = [a + b for a, b in zip(totals, values)]
        batches += 1
    if batches:
        index = max(range(len(candidates)), key=lambda i:
                    (1-config.action_weight)*totals[i]/batches + config.action_weight*advantages[candidates[i]]
                    if action_model is not None else totals[i])
        best, value = candidates[index], totals[index] / batches
    else:
        value = heuristic(after_move(observation.board, best))
    validate_move(observation, best)
    method = f'rollouts ({batches} complete batches)' if batches else 'heuristic fallback'
    if model is not None:
        method += ' + generalized session-value shortlist'
    if action_model is not None:
        method += ' + learned action advantages and FL continuation'
    return Decision(best, len(moves), simulations, time.monotonic() - start, value, method)


def search_value(board, opponent, obs, model):
    if model is None:
        return terminal_value(board,opponent,obs.fantasyland_cards)
    from .action_model import terminal_score
    return terminal_score(board,opponent,obs.fantasyland_cards,obs.opponent_fantasyland_cards,model)


def sampled_opponent(obs, draws, model, rng, deadline):
    if complete(obs.opponent):
        return obs.opponent
    if model is not None and obs.opponent_fantasyland_cards:
        from .model import Observation
        opponent_obs = Observation(EMPTY,tuple(draws[:obs.opponent_fantasyland_cards]),
                                   fantasyland_cards=obs.opponent_fantasyland_cards)
        decision = choose_move(opponent_obs,seed=rng.randrange(2**32),
                               config=SearchConfig(seconds=max(0,min(.04,deadline-time.monotonic())),
                                                   samples=0,diversified_fantasy=True))
        return after_move(EMPTY,decision.move)
    return opponent_completion(obs.opponent,draws)


def final_street(obs, moves, config, rng, start, deadline, action_model=None):
    """Score every own placement against the same sampled opponent outcomes."""
    boards = [after_move(obs.board, move) for move in moves]
    known_opponent = obs.opponent if complete(obs.opponent) else None
    values = [terminal_value(board, known_opponent) for board in boards]
    if known_opponent is not None and action_model is not None:
        values = [search_value(board,known_opponent,obs,action_model) for board in boards]
    totals = [0.0] * len(boards)
    batches = 0
    if known_opponent is None and config.opponent_aware_final:
        unseen = list(obs.unseen())
        for _ in range(config.samples):
            if time.monotonic() >= deadline:
                break
            rng.shuffle(unseen)
            opponent = sampled_opponent(obs,tuple(unseen),action_model,rng,deadline)
            batch = []
            for board in boards:
                if time.monotonic() >= deadline:
                    break
                batch.append(search_value(board, opponent, obs, action_model))
            # Only compare equally sampled alternatives; retain a legal fallback.
            if len(batch) != len(boards):
                break
            totals = [a + b for a, b in zip(totals, batch)]
            batches += 1
    if batches:
        values = [total / batches for total in totals]
    index = max(range(len(moves)), key=lambda i: (values[i], not summary(boards[i])[0]))
    validate_move(obs, moves[index])
    method = 'final-street enumeration'
    if batches:
        method += f' + opponent sampling ({batches} batches)'
    if action_model is not None:
        method += ' + learned FL continuation'
    return Decision(moves[index], len(moves), batches * len(moves),
                    time.monotonic() - start, values[index], method)


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
