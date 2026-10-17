"""Evaluate a saved profile without training or Normal-policy fallback."""
import argparse
import json
import math
from pathlib import Path
import random
import statistics

from chinesepoker.ai.mccfr import OutcomeSampling
from chinesepoker.ai.training_games import KuhnPoker, OFCOneHand, OFCEndgame, EndgameEvaluator, evaluate_kuhn
from chinesepoker.ai.search import choose_move


def evaluate_ofc(solver, pairs=20, seed=20261021):
    records = []
    hits = decisions = 0
    for pair in range(pairs):
        for seat in (0, 1):
            state = solver.game.start(random.Random(seed+pair))
            rng = random.Random(seed+100000+pair*2+seat)
            while state.player is not None:
                if state.player == seat:
                    node = solver.nodes.get(state.key())
                    hits += int(node is not None and sum(node.average) > 0)
                    decisions += 1
                    move = rng.choices(state.actions(), weights=solver.policy(state), k=1)[0]
                else:
                    move = choose_move(state.observation(), 'easy', seed=seed+pair).move
                state = state.child(move)
            records.append(dict(pair=pair, learned_seat=seat, points=state.payoff(seat)))
    means = [statistics.mean(r['points'] for r in records if r['pair'] == p) for p in range(pairs)]
    mean = statistics.mean(means)
    margin = 1.96*statistics.stdev(means)/math.sqrt(pairs) if pairs > 1 else None
    return dict(pairs=pairs, seed=seed, hands=len(records), mean_points=mean,
                approximate_95_percent_paired_ci=None if margin is None else [mean-margin,mean+margin],
                trained_information_set_hits=hits, decisions=decisions, coverage=hits/decisions,
                exploitability=None, equilibrium_certified=False,
                scope='Single ordinary hand vs Easy; average strategy, UNIFORM on unseen sets. This is NOT GUI Normal fallback and NOT a best-response evaluation.',
                records=records)


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--game', choices=('kuhn', 'ofc', 'endgame'), default='ofc')
    parser.add_argument('--checkpoint', type=Path, required=True)
    parser.add_argument('--pairs', type=int, default=20)
    parser.add_argument('--seed', type=int, default=20261021)
    parser.add_argument('--output', type=Path, required=True)
    args = parser.parse_args()
    if args.pairs < 1:
        parser.error('--pairs must be positive')
    game = {'kuhn': KuhnPoker, 'ofc': OFCOneHand, 'endgame': OFCEndgame}[args.game]()
    solver = OutcomeSampling.load(args.checkpoint, game, max_nodes=1000000)
    result = (evaluate_kuhn(solver) if args.game == 'kuhn' else EndgameEvaluator(game).evaluate(solver)
              if args.game == 'endgame' else evaluate_ofc(solver, args.pairs, args.seed))
    result.update(game=game.identifier, iterations=solver.iterations)
    args.output.parent.mkdir(parents=True, exist_ok=True)
    args.output.write_text(json.dumps(result, indent=2), encoding='utf-8')
    print(json.dumps({k:v for k,v in result.items() if k != 'records'}, indent=2))


if __name__ == '__main__':
    main()
