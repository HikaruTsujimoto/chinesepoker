"""Train/resume an exact tabular outcome-sampling MCCFR average strategy."""
import argparse
import json
from pathlib import Path
import time

from chinesepoker.ai.mccfr import OutcomeSampling, ResourceLimit
from chinesepoker.ai.session_game import OFCSession
from chinesepoker.ai.training_games import KuhnPoker, OFCOneHand, OFCEndgame, EndgameEvaluator, evaluate_kuhn


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--game', choices=('kuhn', 'ofc', 'endgame', 'session'), default='session')
    parser.add_argument('--fantasy-candidates', type=int, default=0, help='0: all FL actions; 1..256: explicit action abstraction')
    parser.add_argument('--initial-tiers', type=int, nargs=2, default=(0,0), help='Diagnostic FL start; normal session starts 0 0')
    parser.add_argument('--max-actions', type=int, default=10000)
    parser.add_argument('--max-hands', type=int, default=64, help='Resource guard, NOT a terminal game rule')
    parser.add_argument('--max-steps', type=int, default=512)
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
    game = (OFCSession(args.fantasy_candidates, tuple(args.initial_tiers)) if args.game == 'session'
            else {'kuhn': KuhnPoker, 'ofc': OFCOneHand, 'endgame': OFCEndgame}[args.game]())
    evaluator = EndgameEvaluator(game) if args.game == 'endgame' else None
    limits = dict(max_nodes=args.max_nodes, max_actions=args.max_actions, max_hands=args.max_hands, max_steps=args.max_steps)
    solver = (OutcomeSampling.load(args.checkpoint, game, **limits) if args.resume else
              OutcomeSampling(game, args.seed, args.exploration, **limits))
    start, initial = time.monotonic(), solver.iterations
    status = 'iterations_complete'
    curve = []
    episode_hands = []
    stop_reason = None
    try:
        for _ in range(args.iterations):
            if args.seconds and time.monotonic()-start >= args.seconds:
                status = 'time_limit'
                break
            solver.iteration()
            episode_hands.extend(solver.last_episode_hands)
            if solver.iterations % args.save_every == 0:
                solver.save(args.checkpoint)
                row = dict(iterations=solver.iterations, information_sets=len(solver.nodes))
                if args.game == 'kuhn':
                    row.update(evaluate_kuhn(solver))
                elif evaluator:
                    row.update(evaluator.evaluate(solver))
                curve.append(row)
                print(json.dumps(row), flush=True)
    except ResourceLimit as error:
        status = type(error).__name__
        stop_reason = str(error)
    except KeyboardInterrupt:
        print('Interrupted: retaining the last completed on-disk checkpoint.', flush=True)
        return 130
    solver.save(args.checkpoint)
    result = dict(game=game.identifier, algorithm='outcome-sampling MCCFR', status=status,
                  iterations=solver.iterations, additional_iterations=solver.iterations-initial,
                  information_sets=len(solver.nodes), seconds=time.monotonic()-start,
                  exploration=solver.exploration, curve=curve, stop_reason=stop_reason)
    if args.game == 'kuhn':
        result.update(evaluate_kuhn(solver))
    elif evaluator:
        result.update(evaluator.evaluate(solver))
        result.update(scope='Fixed public boards and public 8-card pool; exact restricted endgame, not full-game exploitability.')
    elif args.game == 'session':
        result.update(exploitability=None, equilibrium_certified=False,
                      fantasy_candidates=args.fantasy_candidates, initial_tiers=args.initial_tiers,
                      completed_episodes=len(episode_hands), total_completed_hands=sum(episode_hands),
                      longest_completed_session=max(episode_hands,default=0),
                      multi_hand_sessions=sum(n>1 for n in episode_hands),
                      scope='Undiscounted scores until BOTH next-FL rights vanish. No artificial terminal or cash-out at resource limits. FL action abstraction only if fantasy_candidates > 0. No full-game equilibrium certificate.')
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
