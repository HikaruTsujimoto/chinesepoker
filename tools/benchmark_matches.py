"""Paired fixed-horizon matches against the previous Normal policy, including FL."""
import argparse
from dataclasses import replace
import json
import math
from pathlib import Path
import random
import statistics

from chinesepoker.ai.model import CARDS, EMPTY, Observation, validate_move
from chinesepoker.ai.search import LEVELS, choose_move
from chinesepoker.core.player import Player
from chinesepoker.core.game import Game


def benchmark(pairs=10, hands=6, seed=20261020):
    records = []
    for pair in range(pairs):
        for new_seat in (0, 1):
            tiers = [0, 0]
            for hand_number in range(hands):
                deck = random.Random(seed + pair * hands + hand_number).sample(range(52), 52)
                boards, discards, held = [EMPTY, EMPTY], [(), ()], [(), ()]
                index = 0
                timings = []

                def decide(seat, hand, visible):
                    obs = Observation(boards[seat], tuple(hand), visible[1-seat],
                                      discards[seat], tiers[seat])
                    config = replace(LEVELS['normal'], opponent_aware_final=seat == new_seat)
                    decision = choose_move(obs, seed=seed + pair*10000 + hand_number*100 + street*2 + seat,
                                           config=config)
                    boards[seat] = validate_move(obs, decision.move)
                    discards[seat] += decision.move.discards
                    timings.append(decision.seconds)

                for street in range(5):
                    visible = boards[:]
                    for seat in (0, 1):
                        if tiers[seat]:
                            if street == 0:
                                held[seat] = tuple(deck[index:index+tiers[seat]])
                                index += tiers[seat]
                            continue
                        count = 5 if street == 0 else 3
                        hand = deck[index:index+count]
                        index += count
                        decide(seat, hand, visible)
                visible = boards[:]
                street = 5
                for seat in (0, 1):
                    if tiers[seat]:
                        decide(seat, held[seat], visible)
                players = [Player('0'), Player('1')]
                for seat, player in enumerate(players):
                    player.top, player.mid, player.bot = ([CARDS[c] for c in row] for row in boards[seat])
                    player.fantasyland = bool(tiers[seat])
                    player.fantasyland_cards = tiers[seat]
                    player.evaluate_board()
                    if tiers[seat] and player.next_fantasyland:
                        assert player.next_fantasyland_cards == tiers[seat]
                a, b = players[new_seat], players[1-new_seat]
                points = Game(players).calculate_matchup(a, b)[0] + a.get_royalties() - b.get_royalties()
                records.append(dict(pair=pair, new_seat=new_seat, hand=hand_number, points=points,
                                    tiers=tiers, next_tiers=[p.next_fantasyland_cards for p in players],
                                    new_foul=a.is_foul, old_foul=b.is_foul, seconds=timings))
                tiers = [p.next_fantasyland_cards for p in players]
        print(f'{pair+1}/{pairs} pairs complete', flush=True)
    means = [statistics.mean(r['points'] for r in records if r['pair'] == p) for p in range(pairs)]
    mean = statistics.mean(means)
    margin = 1.96 * statistics.stdev(means) / math.sqrt(pairs) if pairs > 1 else None
    times = [t for r in records for t in r['seconds']]
    return dict(seed=seed, pairs=pairs, hands_per_match=hands, hands=len(records),
                mean_points=mean, approximate_95_percent_paired_ci=None if margin is None else [mean-margin, mean+margin],
                new_foul_rate=statistics.mean(r['new_foul'] for r in records),
                old_foul_rate=statistics.mean(r['old_foul'] for r in records),
                fantasy_player_hands=sum(bool(t) for r in records for t in r['tiers']),
                fantasy_continuations=sum(bool(t) and bool(n) for r in records for t,n in zip(r['tiers'],r['next_tiers'])),
                mean_decision_seconds=statistics.mean(times), max_decision_seconds=max(times),
                scope='Normal vs previous Normal; swapped seats, fixed horizon, FL continued; no terminal FL bonus. Deals diverge when FL tiers differ. Approximate CI clusters whole paired matches; no equilibrium claim.',
                records=records)


if __name__ == '__main__':
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--pairs', type=int, default=10)
    parser.add_argument('--hands', type=int, default=6)
    parser.add_argument('--seed', type=int, default=20261020)
    parser.add_argument('--output', type=Path, default=Path('docs/cpu-benchmark-matches.json'))
    args = parser.parse_args()
    if args.pairs < 1 or args.hands < 1:
        parser.error('pairs and hands must be positive')
    result = benchmark(args.pairs, args.hands, args.seed)
    args.output.parent.mkdir(parents=True, exist_ok=True)
    args.output.write_text(json.dumps(result, indent=2), encoding='utf-8')
    print(json.dumps({k:v for k,v in result.items() if k != 'records'}, indent=2))
