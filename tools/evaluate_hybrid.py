"""Swapped-seat complete-session comparisons and component ablations."""
import argparse
from dataclasses import replace, asdict
import json
import hashlib
import math
from pathlib import Path
import random
import statistics

from chinesepoker.ai.session_game import SessionState
from chinesepoker.ai.search import choose_move, LEVELS
from chinesepoker.ai.evaluation import summary
from chinesepoker.ai.value_model import DEFAULT_MODEL


def evaluate(pairs, seed, seconds, variants, initial_tiers=(0,0), max_hands=64):
    from chinesepoker.ai.action_model import DEFAULT_MODEL as action_path, load_model as load_action
    action_hash=None
    if any(v in ('action','adaptive','expectimax') for v in variants):
        load_action.cache_clear()
        action_hash=hashlib.sha256(action_path.read_bytes()).hexdigest()
    old = replace(LEVELS['normal'], seconds=seconds)
    records = []
    for variant in variants:
        new = replace(old, value_weight=.4 if variant in ('value','hybrid') else 0,
                      diversified_fantasy=variant in ('fantasy','hybrid','adaptive'),
                      action_weight=.35 if variant in ('action','adaptive') else 0,
                      expectimax=variant=='expectimax',
                      shortlist=12 if variant=='expectimax' else old.shortlist)
        for pair in range(pairs):
            for new_seat in (0,1):
                # Same deck stream for swapped seats and all variants; future
                # trajectories can diverge due to FL, so pair entire sessions.
                chance = random.Random(seed+pair)
                state = SessionState(tiers=tuple(initial_tiers))
                decisions, methods, fouls, fl_hands = [[],[]], [[],[]], [0,0], [0,0]
                while not state.settled:
                    if state.needs_deal:
                        if state.completed_hands >= max_hands:
                            break
                        state = state.sample_chance(chance)
                        continue
                    seat = state.player
                    obs = state.observation()
                    decision = choose_move(obs, config=new if seat == new_seat else old,
                                           seed=seed+pair*100000+state.completed_hands*100+state.turn)
                    decisions[seat].append(decision.seconds)
                    methods[seat].append(decision.method)
                    next_state = state.child(decision.move)
                    if next_state.completed_hands != state.completed_hands:
                        boards = next_state.histories[0][-1][2]
                        for p in (0,1):
                            fouls[p] += summary(boards[p],state.tiers[p])[0]
                            fl_hands[p] += bool(state.tiers[p])
                    state = next_state
                records.append(dict(variant=variant,pair=pair,new_seat=new_seat,settled=state.settled,
                                    points=state.payoff(new_seat) if state.settled else None,
                                    hands=state.completed_hands,new_fouls=fouls[new_seat],old_fouls=fouls[1-new_seat],
                                    fl_player_hands=sum(fl_hands),new_seconds=decisions[new_seat],old_seconds=decisions[1-new_seat],
                                    new_methods=methods[new_seat]))
            print(f'{variant}: {pair+1}/{pairs} pairs', flush=True)
    results = {}
    for variant in variants:
        rows = [r for r in records if r['variant'] == variant]
        censored = sum(not r['settled'] for r in rows)
        means = [] if censored else [statistics.mean(r['points'] for r in rows if r['pair'] == p) for p in range(pairs)]
        avg = statistics.mean(means) if means else None
        # Student-t critical values for small numbers of independent pairs.
        t95 = {1:12.706,2:4.303,3:3.182,4:2.776,5:2.571,6:2.447,7:2.365,8:2.306,9:2.262,
               10:2.228,11:2.201,12:2.179,13:2.160,14:2.145,15:2.131,16:2.120,17:2.110,18:2.101,19:2.093}
        margin = t95.get(pairs-1,2.086)*statistics.stdev(means)/math.sqrt(pairs) if len(means)>1 else None
        hands = sum(r['hands'] for r in rows)
        results[variant] = dict(sessions=len(rows),censored=censored,hands=hands,
                               mean_session_points=avg,paired_approx_95_ci=[avg-margin,avg+margin] if margin is not None else None,
                               new_foul_rate=sum(r['new_fouls'] for r in rows)/hands if hands else None,
                               old_foul_rate=sum(r['old_fouls'] for r in rows)/hands if hands else None,
                               fl_player_hands=sum(r['fl_player_hands'] for r in rows),
                               mean_new_seconds=statistics.mean(t for r in rows for t in r['new_seconds']),
                               mean_old_seconds=statistics.mean(t for r in rows for t in r['old_seconds']))
    if action_hash is not None and action_hash!=hashlib.sha256(action_path.read_bytes()).hexdigest():
        raise RuntimeError('Action model changed during evaluation; refusing mixed-model report')
    return dict(seed=seed,pairs=pairs,initial_tiers=initial_tiers,old_config=asdict(old),results=results,records=records,
                action_model_sha256=action_hash,
                model_sha256=hashlib.sha256(DEFAULT_MODEL.read_bytes()).hexdigest(),
                scope='Held-out deck seeds; matched per-decision time caps, paired whole-session returns, no FL bonus at settlement. Small-sample approximate CI, no equilibrium certificate. Wall-clock search is not bit-reproducible.')


if __name__ == '__main__':
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--pairs',type=int,default=12)
    parser.add_argument('--seed',type=int,default=20300000)
    parser.add_argument('--seconds',type=float,default=1.5)
    parser.add_argument('--variants',nargs='+',choices=['value','fantasy','hybrid','action','adaptive','expectimax'],default=['value','fantasy','hybrid'])
    parser.add_argument('--initial-tiers',nargs=2,type=int,choices=[0,14,15,16,17],default=[0,0])
    parser.add_argument('--max-hands',type=int,default=64)
    parser.add_argument('--output',type=Path,default=Path('docs/hybrid-evaluation.json'))
    args = parser.parse_args()
    if args.pairs<2 or not math.isfinite(args.seconds) or args.seconds<=0 or args.max_hands<1:
        parser.error('pairs >=2, seconds >0 and max-hands >=1 required')
    result = evaluate(args.pairs,args.seed,args.seconds,args.variants,args.initial_tiers,args.max_hands)
    args.output.parent.mkdir(parents=True,exist_ok=True)
    args.output.write_text(json.dumps(result,indent=2),encoding='utf-8')
    print(json.dumps(result['results'],indent=2))
