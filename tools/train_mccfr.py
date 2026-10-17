"""Train/resume an exact tabular outcome-sampling MCCFR average strategy."""
import argparse
import json
from pathlib import Path
import time

from chinesepoker.ai.mccfr import OutcomeSampling, NodeLimit
from chinesepoker.ai.training_games import KuhnPoker, OFCOneHand, OFCEndgame, EndgameEvaluator, evaluate_kuhn


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--game', choices=('kuhn', 'ofc', 'endgame'), default='ofc')
    parser.add_argument('--iterations', type=int, default=1000, help='Additional iterations (two episodes each)')
    parser.add_argument('--seed', type=int, default=20261018)
    parser.add_argument('--exploration', type=float, default=0.6)
    parser.add_argument('--max-nodes', type=int, default=100000)
    parser.add_argument('--checkpoint', type=Path, required=True)
    parser.add_argument('--resume', action='store_true')
    parser.add_argument('--save-every', type=int, default=1000)
    parser.add_argument('--seconds', type=float, default=0, help='Stop at an iteration boundary; 0 means unlimited')
    parser.add_argument('--report', type=Path)
    args = parser.parse_args()
    if args.iterations < 1 or args.save_every < 1 or args.seconds < 0:
        parser.error('iterations/save-every must be positive; seconds must be nonnegative')
    if args.checkpoint.exists() and not args.resume:
        parser.error('Checkpoint exists; use --resume or a new path')
    game = {'kuhn': KuhnPoker, 'ofc': OFCOneHand, 'endgame': OFCEndgame}[args.game]()
    evaluator = EndgameEvaluator(game) if args.game == 'endgame' else None
    solver = (OutcomeSampling.load(args.checkpoint, game, args.max_nodes) if args.resume else
              OutcomeSampling(game, args.seed, args.exploration, args.max_nodes))
    start, initial = time.monotonic(), solver.iterations
    status = 'iterations_complete'
    curve = []
    try:
        for _ in range(args.iterations):
            if args.seconds and time.monotonic()-start >= args.seconds:
                status = 'time_limit'
                break
            solver.iteration()
            if solver.iterations % args.save_every == 0:
                solver.save(args.checkpoint)
                row = dict(iterations=solver.iterations, information_sets=len(solver.nodes))
                if args.game == 'kuhn':
                    row.update(evaluate_kuhn(solver))
                elif evaluator:
                    row.update(evaluator.evaluate(solver))
                curve.append(row)
                print(json.dumps(row), flush=True)
    except NodeLimit:
        # No updates from the aborted iteration are applied. New zero nodes
        # and consumed RNG draws are harmless; resume with a larger limit.
        status = 'node_limit'
    except KeyboardInterrupt:
        print('Interrupted: retaining the last completed on-disk checkpoint.', flush=True)
        return 130
    solver.save(args.checkpoint)
    result = dict(game=game.identifier, algorithm='outcome-sampling MCCFR', status=status,
                  iterations=solver.iterations, additional_iterations=solver.iterations-initial,
                  information_sets=len(solver.nodes), seconds=time.monotonic()-start,
                  exploration=solver.exploration, curve=curve)
    if args.game == 'kuhn':
        result.update(evaluate_kuhn(solver))
    elif evaluator:
        result.update(evaluator.evaluate(solver))
        result.update(scope='Fixed public boards and public 8-card pool; exact restricted endgame, not full-game exploitability.')
    else:
        result.update(exploitability=None, equilibrium_certified=False,
                      scope='Exact 52-card normal single hand; no next-hand FL value. Full private/public recall and all legal actions. Training is not a convergence certificate.')
    if args.report:
        args.report.parent.mkdir(parents=True, exist_ok=True)
        args.report.write_text(json.dumps(result, indent=2), encoding='utf-8')
    print(json.dumps(result, indent=2), flush=True)
    return 0


if __name__ == '__main__':
    raise SystemExit(main())
