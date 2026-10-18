"""Diversified anytime FL search, with a legal incumbent at every deadline."""
from itertools import combinations
import time
from .model import Move, Decision, validate_move
from .evaluation import rank, compare_hands, terminal_value, complete


def search(obs, config, rng, start, deadline):
    hand = tuple(sorted(obs.hand))
    opponent = obs.opponent if complete(obs.opponent) else None
    best = (hand[:3], hand[3:8], hand[8:13])
    best_value = terminal_value(best, opponent, obs.fantasyland_cards)
    evaluated = 1
    fives = []
    for cards in combinations(hand, 5):
        if time.monotonic() >= deadline:
            break
        fives.append((rank(cards), sum(1 << c for c in cards), cards))
    fives.sort(reverse=True)
    # Interleave hand categories: do not spend the entire budget on the first
    # strongest bottom while starving full houses, flushes or weaker bottoms.
    groups = {}
    for item in fives:
        groups.setdefault(item[0][0], []).append(item)
    bottoms = []
    for depth in range(max((len(g) for g in groups.values()), default=0)):
        bottoms.extend(g[depth] for g in groups.values() if depth < len(g))
        if len(bottoms) >= config.fantasy_bottoms:
            break
    bottoms = bottoms[:config.fantasy_bottoms]
    # Each bottom receives one compatible middle per pass. This gives diverse
    # legal boards early; cursors avoid rescanning rejected overlapping subsets.
    cursors = [0]*len(bottoms)
    active = list(range(len(bottoms)))
    while active and time.monotonic() < deadline:
        remaining = []
        for i in active:
            if time.monotonic() >= deadline:
                break
            br, bm, bot = bottoms[i]
            while cursors[i] < len(fives):
                if time.monotonic() >= deadline:
                    break
                mr, mm, mid = fives[cursors[i]]
                cursors[i] += 1
                if bm & mm or compare_hands(br, mr) < 0:
                    continue
                rest = tuple(c for c in hand if not (bm | mm) & (1 << c))
                for top in combinations(rest, 3):
                    if time.monotonic() >= deadline:
                        break
                    if compare_hands(mr, rank(top)) < 0:
                        continue
                    board = (top, mid, bot)
                    value = terminal_value(board, opponent, obs.fantasyland_cards)
                    evaluated += 1
                    if value > best_value:
                        best, best_value = board, value
                break
            if cursors[i] < len(fives):
                remaining.append(i)
        active = remaining
    used = {c for row in best for c in row}
    move = Move(tuple((c,r) for r,row in enumerate(best) for c in row),
                tuple(c for c in hand if c not in used))
    validate_move(obs, move)
    return Decision(move, evaluated, 0, time.monotonic()-start, best_value,
                    'diversified Fantasyland subset search')
