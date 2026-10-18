"""Paired, reproducible ordinary-hand benchmark (not an equilibrium test).

Run: python -m tools.benchmark_cpu --pairs 40 --output docs/cpu-benchmark.json
Both policies receive each seat/deal once. Fantasyland admission is recorded;
continued Fantasyland games are not part of this benchmark.
"""
import argparse
import json
import math
from pathlib import Path
import random
import statistics
from chinesepoker.ai.model import EMPTY, Observation, validate_move, CARDS
from chinesepoker.ai.search import choose_move, SearchConfig
from chinesepoker.core.player import Player
from chinesepoker.core.game import Game


def benchmark(pairs=40, seed=20261017, samples=32, shortlist=16, seconds=60):
    records = []
    config = SearchConfig(seconds=seconds, samples=samples, shortlist=shortlist)
    for pair in range(pairs):
        for search_seat in (0, 1):
            deck = random.Random(seed + pair).sample(range(52), 52)
            boards, discards = [EMPTY, EMPTY], [(), ()]
            timings, counts = [], []
            index = 0
            for street in range(5):
                visible = boards[:]
                for seat in (0, 1):
                    count = 5 if street == 0 else 3
                    hand = tuple(deck[index:index + count])
                    index += count
                    obs = Observation(boards[seat], hand, visible[1 - seat], discards[seat])
                    decision = choose_move(obs, 'easy', seed=seed + pair * 100 + street * 2 + seat,
                                           config=config if seat == search_seat else None)
                    boards[seat] = validate_move(obs, decision.move)
                    discards[seat] += decision.move.discards
                    if seat == search_seat:
                        timings.append(decision.seconds)
                        counts.append(decision.simulations)
            players = [Player('search'), Player('greedy')]
            for player, board in zip(players, (boards[search_seat], boards[1 - search_seat])):
                player.top, player.mid, player.bot = ([CARDS[c] for c in row] for row in board)
                player.evaluate_board()
            game = Game(players)
            a, b = players
            points = game.calculate_matchup(a, b)[0] + a.get_royalties() - b.get_royalties()
            records.append(dict(pair=pair, search_seat=search_seat, points=points,
                                search_foul=a.is_foul, greedy_foul=b.is_foul,
                                search_fantasy=a.next_fantasyland, greedy_fantasy=b.next_fantasyland,
                                seconds=timings, simulations=counts))
        if (pair + 1) % 5 == 0:
            print(f'{pair + 1}/{pairs} pairs complete', flush=True)
    pair_means = [(records[2*i]['points'] + records[2*i+1]['points']) / 2 for i in range(pairs)]
    mean = statistics.mean(pair_means)
    margin = 1.96 * statistics.stdev(pair_means) / math.sqrt(pairs) if pairs > 1 else None
    times = [t for row in records for t in row['seconds']]
    result = dict(seed=seed, pairs=pairs, hands=len(records), samples=samples, shortlist=shortlist,
                  seconds_budget=seconds, mean_points=mean,
                  approximate_95_percent_paired_ci=None if margin is None else [mean-margin, mean+margin],
                  win_rate=sum(r['points'] > 0 for r in records)/len(records),
                  tie_rate=sum(r['points'] == 0 for r in records)/len(records),
                  search_foul_rate=statistics.mean(r['search_foul'] for r in records),
                  greedy_foul_rate=statistics.mean(r['greedy_foul'] for r in records),
                  search_fantasy_rate=statistics.mean(r['search_fantasy'] for r in records),
                  greedy_fantasy_rate=statistics.mean(r['greedy_fantasy'] for r in records),
                  mean_decision_seconds=statistics.mean(times), max_decision_seconds=max(times),
                  scope='Independent ordinary hands; same deals with swapped policies; heuristic baseline, no human or equilibrium benchmark.',
                  records=records)
    return result


if __name__ == '__main__':
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--pairs', type=int, default=40)
    parser.add_argument('--seed', type=int, default=20261017)
    parser.add_argument('--samples', type=int, default=32)
    parser.add_argument('--shortlist', type=int, default=16)
    parser.add_argument('--seconds', type=float, default=60)
    parser.add_argument('--output', type=Path, default=Path('docs/cpu-benchmark.json'))
    args = parser.parse_args()
    if args.pairs < 1:
        parser.error('--pairs must be positive')
    result = benchmark(args.pairs, args.seed, args.samples, args.shortlist, args.seconds)
    args.output.parent.mkdir(exist_ok=True, parents=True)
    args.output.write_text(json.dumps(result, indent=2), encoding='utf-8')
    print(json.dumps({k: v for k, v in result.items() if k != 'records'}, indent=2))
