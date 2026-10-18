"""Shared-observation diagnostics, including a prior-only neural ablation."""
import argparse
from dataclasses import replace
import json
from pathlib import Path
import random
from unittest.mock import patch
from chinesepoker.ai.action_model import DEFAULT_MODEL, ActionModel
from chinesepoker.ai.search import LEVELS, choose_move
from chinesepoker.ai.session_game import SessionState


def run(hands=10,samples=64):
    old_config=replace(LEVELS['normal'],seconds=60,samples=samples)
    new_config=replace(LEVELS['adaptive'],seconds=60,samples=samples)
    data=json.loads(DEFAULT_MODEL.read_text(encoding='utf-8'))
    data['w2']=[0.0]*len(data['w2'])
    prior_only=ActionModel(data)
    records=[]
    for game in range(hands):
        state=SessionState().sample_chance(random.Random(20400000+game))
        while state.completed_hands==0:
            obs=state.observation()
            seed=20410000+game*100+state.turn
            old=choose_move(obs,config=old_config,seed=seed)
            new=choose_move(obs,config=new_config,seed=seed)
            with patch('chinesepoker.ai.action_model.load_model',return_value=prior_only):
                prior=choose_move(obs,config=new_config,seed=seed)
            if sum(map(len,obs.board))!=11:
                for decision in (old,new,prior):
                    assert f'({samples} complete batches)' in decision.method
            records.append(dict(hand=game,street=state.schedule[state.turn][1],
                                same_as_old=old.move==new.move,same_as_prior=prior.move==new.move))
            state=state.child(old.move)
        print(f'{game+1}/{hands} shared-observation hands',flush=True)
    return dict(hands=hands,samples=samples,decisions=len(records),
                changed_vs_old=sum(not r['same_as_old'] for r in records),
                changed_vs_prior_only=sum(not r['same_as_prior'] for r in records),
                by_street={str(s):dict(decisions=sum(r['street']==s for r in records),
                    changed_vs_old=sum(r['street']==s and not r['same_as_old'] for r in records),
                    changed_vs_prior_only=sum(r['street']==s and not r['same_as_prior'] for r in records)) for s in range(5)},
                scope='Matched observations and completed sample budgets; action changes do not establish greater strength.',records=records)


if __name__=='__main__':
    p=argparse.ArgumentParser(description=__doc__)
    p.add_argument('--hands',type=int,default=10)
    p.add_argument('--samples',type=int,default=64)
    p.add_argument('--output',type=Path,default=Path('docs/action-diagnostics.json'))
    args=p.parse_args()
    if min(args.hands,args.samples)<1: p.error('Positive counts required')
    result=run(args.hands,args.samples)
    args.output.parent.mkdir(parents=True,exist_ok=True)
    args.output.write_text(json.dumps(result,indent=2),encoding='utf-8')
    print(json.dumps({k:v for k,v in result.items() if k!='records'},indent=2))
