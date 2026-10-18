"""Cached rule evaluations and explicitly heuristic incomplete-board estimates."""
from collections import Counter
from functools import lru_cache
from chinesepoker.core.evaluator import evaluate_hand, compare_hands
from chinesepoker.core.player import Player
from .model import CARDS, ROWS, CAPACITY


@lru_cache(maxsize=65536)
def rank(row):
    value = evaluate_hand([CARDS[c] for c in row])
    return value[0], tuple(value[1]), tuple(value[2])


def complete(board):
    return tuple(map(len, board)) == CAPACITY


@lru_cache(maxsize=32768)
def summary(board, fantasy=0):
    """Reuse the game's actual royalty and Fantasyland rules."""
    player = Player('simulation')
    for name, cards in zip(ROWS, board):
        setattr(player, name, [CARDS[c] for c in cards])
    player.fantasyland = bool(fantasy)
    player.fantasyland_cards = fantasy
    player.evaluate_board()
    return player.is_foul, player.get_royalties(), player.next_fantasyland_cards


def continuation_value(tier):
    # A tunable heuristic, NOT a solved long-run value or a Nash guarantee.
    return {0: 0, 14: 7, 15: 9, 16: 11, 17: 13}[tier]


def terminal_value(board, opponent=None, fantasy=0):
    foul, royalties, tier = summary(board, fantasy)
    if opponent is not None and complete(opponent):
        other_foul, other_royalties, _ = summary(opponent)
        if foul and other_foul:
            return 0.0
        if foul:
            return -6.0 - other_royalties
        if other_foul:
            return 6.0 + royalties + continuation_value(tier)
        wins = [compare_hands(rank(a), rank(b)) for a, b in zip(board, opponent)]
        points = sum(wins) + (3 if wins == [1, 1, 1] else -3 if wins == [-1, -1, -1] else 0)
        return points + royalties - other_royalties + continuation_value(tier)
    if foul:
        return -16.0
    # Proxy against an unspecified opponent; reward strength as a tie breaker.
    strength = sum(rank(row)[0] + rank(row)[1][0] / 20 for row in board)
    return royalties + continuation_value(tier) + strength * 0.4


@lru_cache(maxsize=65536)
def row_potential(row, row_index):
    n = len(row)
    if not n:
        return 0.0, 0.0
    values = [c % 13 + 2 for c in row]
    counts = sorted(Counter(values).values(), reverse=True)
    high = max(values) / 100
    if n == CAPACITY[row_index]:
        ev = rank(row)
        return ev[0] + ev[1][0] / 100, ev[0] * 2 + high
    pairs = counts.count(2)
    strength = 7 if counts[0] == 4 else 3 if counts[0] == 3 else 2 if pairs == 2 else 1 if pairs else 0
    synergy = strength * 2.8 + sum(values) * 0.012
    if row_index == 0:
        if counts[0] >= 2 and max(v for v in values if values.count(v) >= 2) >= 12:
            synergy += 4
        elif n == 1 and values[0] >= 12:
            synergy += 0.7
    else:
        suited = max(Counter(c // 13 for c in row).values())
        if suited == n and n >= 2:
            synergy += {2: 1.2, 3: 3.0, 4: 5.2}[n]
            strength = max(strength, {2: 0.45, 3: 1.3, 4: 2.8}[n])
        unique = set(values)
        if 14 in unique:
            unique.add(1)
        connected = max(len(unique.intersection(range(low, low + 5))) for low in range(1, 11))
        if connected == n and n >= 3:
            synergy += {3: 1.1, 4: 2.6}[n]
            strength = max(strength, {3: 0.65, 4: 1.5}[n])
        if counts[0] >= 2:
            synergy += (5 - n) * 0.35
    return strength + high, synergy


def heuristic(board, fantasy=0):
    if complete(board):
        return terminal_value(board, fantasy=fantasy)
    strengths, scores = zip(*(row_potential(row, i) for i, row in enumerate(board)))
    score = sum(scores)
    # A completed inverted pair of rows can never be repaired.
    for low, high in ((0, 1), (1, 2)):
        if len(board[low]) == CAPACITY[low] and len(board[high]) == CAPACITY[high]:
            if compare_hands(rank(board[low]), rank(board[high])) > 0:
                return -100.0 + score * 0.01
        score -= max(0, strengths[low] - strengths[high]) * 3.5
    # Avoid filling top too soon; preserve flexible slots in the early streets.
    total = sum(map(len, board))
    if total <= 7:
        score -= len(board[0]) * 0.65
        score += len(board[2]) * 0.25
    return score
