"""Sampled policy iteration with a nonlinear, within-state advantage loss.

Not Deep CFR: these targets are policy rollout values, NOT counterfactual regrets.
Training requires NumPy; exported inference uses only Python's standard library.
"""
import argparse
from dataclasses import replace
import json
from pathlib import Path
import random
import statistics
import numpy as np

from chinesepoker.ai.action_model import ActionModel, FORMAT, TIERS, DEFAULT_MODEL, action_features
from chinesepoker.ai.model import EMPTY
from chinesepoker.ai.search import choose_move, normal_moves, greedy_move, SearchConfig
from chinesepoker.ai.evaluation import heuristic, complete
from chinesepoker.ai.model import after_move
from chinesepoker.ai.session_game import SessionState


class FastModel(ActionModel):
    def __init__(self,data):
        super().__init__(data)
        self.a, self.b, self.v = np.array(self.w1).T, np.array(self.b1), np.array(self.w2)

    def scores(self,obs,moves):
        x = np.array([action_features(obs,m) for m in moves])
        return (self.prior_scale*100*x[:,37]+20*np.tanh(x@self.a+self.b)@self.v).tolist()


def policy(obs, model, rng, explore=0):
    if obs.fantasyland_cards:
        return choose_move(obs,seed=rng.randrange(2**32),config=SearchConfig(
            seconds=.04,samples=0,diversified_fantasy=True)).move
    moves = list(normal_moves(obs.board,obs.hand,obs.place_count))
    if rng.random()<explore:
        return rng.choice(moves)
    if model is None or sum(map(len,obs.board))==11:
        return greedy_move(obs.board,obs.hand,obs.place_count)
    values = model.scores(obs,moves)
    # Keep irreparable-foul protection during bootstrap policy improvement.
    valid = [i for i,m in enumerate(moves) if heuristic(after_move(obs.board,m))>=-90]
    return moves[max(valid or range(len(moves)),key=lambda i:
                     heuristic(after_move(obs.board,moves[i]))+.35*values[i])]


def finish_session(state,model,chance,actions,max_hands):
    while not state.settled:
        if state.needs_deal:
            if state.completed_hands>=max_hands:
                raise RuntimeError('Censored FL session: raise --max-hands; no partial payoff accepted')
            state = state.sample_chance(chance)
        else:
            state = state.child(policy(state.observation(),model,actions))
    return state


def continuation_table(model,pairs,seed,max_hands):
    table = [[0.0]*5 for _ in range(5)]
    records = []
    for i in range(5):
        for j in range(i+1,5):
            differences=[]
            hands=0
            for pair in range(pairs):
                returns=[]
                for tiers in ((TIERS[i],TIERS[j]),(TIERS[j],TIERS[i])):
                    state=finish_session(SessionState(tiers=tiers),model,
                        random.Random(seed+1000*i+100*j+pair),random.Random(seed+90000+pair),max_hands)
                    returns.append(state.total)
                    hands += state.completed_hands
                differences.append((returns[0]-returns[1])/2)
            table[i][j]=statistics.mean(differences)
            table[j][i]=-table[i][j]
            records.append(dict(tiers=[TIERS[i],TIERS[j]],pairs=pairs,hands=hands,
                                value=table[i][j],paired_values=differences))
            print(f'FL continuation {TIERS[i]}/{TIERS[j]}: {table[i][j]:.2f}',flush=True)
    # Same-policy symmetric states have zero EXPECTED score, not zero pathwise
    # payoff. All (0,0) states are settled at this boundary.
    return table,records


def sampled_remainder(obs,seed):
    """Uniform hidden-card approximation conditional only on known cards.

    Each simulated actor observes only their own draws and the correct street's
    public boards. No rollout actor sees future cards stored in deals.
    """
    if obs.fantasyland_cards:
        raise ValueError('Normal-turn teacher only')
    street = 0 if not sum(map(len,obs.board)) else (sum(map(len,obs.board))-3)//2
    other_done = complete(obs.opponent)
    schedule=[]
    for s in range(street,5):
        schedule.append((0,s))
        if not obs.opponent_fantasyland_cards and not other_done:
            schedule.append((1,s))
    if obs.opponent_fantasyland_cards and not other_done:
        schedule.append((1,5))
    unseen=list(obs.unseen())
    random.Random(seed).shuffle(unseen)
    deals=[obs.hand]
    index=0
    for p,s in schedule[1:]:
        count=obs.opponent_fantasyland_cards if s==5 else 5 if s==0 else 3
        deals.append(tuple(sorted(unseen[index:index+count])))
        index += count
    if index>len(unseen):
        raise ValueError('Insufficient unseen cards')
    return SessionState(tiers=(0,obs.opponent_fantasyland_cards),boards=(obs.board,obs.opponent),
                        visible=(obs.board,obs.opponent),discards=(obs.discards,()),
                        deals=tuple(deals),schedule=tuple(schedule),needs_deal=False)


def teacher_group(obs,model,table,samples,cap,seed):
    moves=list(normal_moves(obs.board,obs.hand,obs.place_count))
    ranked=sorted(moves,key=lambda m:heuristic(after_move(obs.board,m)),reverse=True)
    rng=random.Random(seed)
    selected=ranked[:max(1,cap//3)]
    if model:
        scores=model.scores(obs,moves)
        for i in sorted(range(len(moves)),key=scores.__getitem__,reverse=True)[:max(1,cap//3)]:
            if moves[i] not in selected:
                selected.append(moves[i])
    rest=[m for m in moves if m not in selected]
    selected += rng.sample(rest,min(len(rest),max(0,cap-len(selected))))
    targets=[0.0]*len(selected)
    for sample in range(samples):
        start=sampled_remainder(obs,seed+sample+100000)
        for i,move in enumerate(selected):
            state=start.child(move)
            action_rng=random.Random(seed+sample+200000)
            while state.completed_hands==0:
                state=state.child(policy(state.observation(),model,action_rng))
            targets[i] += state.total+table[TIERS.index(state.tiers[0])][TIERS.index(state.tiers[1])]
    return dict(x=[action_features(obs,m) for m in selected],y=[v/samples for v in targets],
                legal=len(moves),sampled=len(selected),street=sum(map(len,obs.board)),
                heuristic=[heuristic(after_move(obs.board,m)) for m in selected])


def collect(count,model,table,samples,cap,seed,max_hands):
    groups=[]
    session=0
    while len(groups)<count:
        chance=random.Random(seed+session)
        actions=random.Random(seed+session+500000)
        state=SessionState()
        # Retain old-policy opposition as well as current-policy self-play.
        seats=[model if actions.random()<.5 else None for _ in range(2)]
        while not state.settled:
            if state.needs_deal:
                if state.completed_hands>=max_hands:
                    raise RuntimeError('Censored data collection session')
                state=state.sample_chance(chance)
                continue
            obs=state.observation()
            if not obs.fantasyland_cards and sum(map(len,obs.board))!=11 and len(groups)<count:
                groups.append(teacher_group(obs,model,table,samples,cap,seed+len(groups)*1000))
                if len(groups)%20==0:
                    print(f'{len(groups)}/{count} candidate groups',flush=True)
            state=state.child(policy(obs,seats[state.player],actions,explore=.1))
        session+=1
    return groups,session


def fit(groups,table,seed,steps=1000,hidden=16,validation=None):
    rng=np.random.default_rng(seed)
    width=len(groups[0]['x'][0])
    cap=max(len(g['x']) for g in groups)
    x=np.zeros((len(groups),cap,width))
    y=np.zeros((len(groups),cap))
    mask=np.zeros_like(y)
    for i,g in enumerate(groups):
        n=len(g['x'])
        x[i,:n]=g['x']; y[i,:n]=np.array(g['y'])/20; mask[i,:n]=1
    base=x[:,:,37]*5
    n=mask.sum(axis=1,keepdims=True)
    centered_base=(base-(base*mask).sum(axis=1,keepdims=True)/n)*mask
    centered_y=(y-(y*mask).sum(axis=1,keepdims=True)/n)*mask
    prior=float(np.clip((centered_base*centered_y).sum()/max(1e-8,(centered_base**2).sum()),.05,5))
    y=y-prior*base
    params=[rng.normal(0,.12,(width,hidden)),np.zeros(hidden),rng.normal(0,.05,hidden)]
    params[2][:]=0
    def exported():
        return dict(format=FORMAT,w1=params[0].T.tolist(),b1=params[1].tolist(),w2=params[2].tolist(),continuation=table,prior_scale=prior)
    best=exported()
    best_error=metrics(best,validation or groups)['learned_sample_regret']
    first=[np.zeros_like(p) for p in params]; second=[p.copy() for p in first]
    for step in range(1,steps+1):
        ids=rng.integers(len(groups),size=min(32,len(groups)))
        xx,yy,mm=x[ids],y[ids],mask[ids]
        nn=mm.sum(axis=1,keepdims=True)
        h=np.tanh(xx@params[0]+params[1])
        pred=h@params[2]
        error=pred-yy
        # Per-information-state centering learns candidate differences, not
        # luck/common score offsets shared by all candidates in that state.
        error=(error-(error*mm).sum(axis=1,keepdims=True)/nn)*mm
        grad=2*error/nn/len(ids)
        dh=grad[:,:,None]*params[2]*(1-h*h)
        grads=[np.einsum('bki,bkj->ij',xx,dh),dh.sum(axis=(0,1)),np.einsum('bk,bkh->h',grad,h)]
        for i in range(3):
            g=np.clip(grads[i]+.0001*params[i],-1,1)
            first[i]=.9*first[i]+.1*g; second[i]=.999*second[i]+.001*g*g
            params[i]-=.003*(first[i]/(1-.9**step))/(np.sqrt(second[i]/(1-.999**step))+1e-8)
        if step%50==0:
            candidate=exported()
            error=metrics(candidate,validation or groups)['learned_sample_regret']
            if error<best_error:
                best,best_error=candidate,error
                best['selected_step']=step
    return best


def metrics(data,groups):
    model=FastModel(data)
    learned,baseline,errors=[],[],[]
    for g in groups:
        x=np.array(g['x']); y=np.array(g['y'])
        scores=model.prior_scale*100*x[:,37]+20*np.tanh(x@model.a+model.b)@model.v
        learned.append(float(y.max()-y[scores.argmax()]))
        baseline.append(float(y.max()-y[np.argmax(g['heuristic'])]))
        error=scores-y; errors.extend((error-error.mean()).tolist())
    return dict(groups=len(groups),learned_sample_regret=statistics.mean(learned),
                heuristic_sample_regret=statistics.mean(baseline),centered_mse=statistics.mean(e*e for e in errors),
                note='Regret versus noisy sampled candidate teacher, not game-theoretic exploitability')


def main():
    p=argparse.ArgumentParser(description=__doc__)
    p.add_argument('--generations',type=int,default=2)
    p.add_argument('--groups',type=int,default=160)
    p.add_argument('--validation',type=int,default=40)
    p.add_argument('--samples',type=int,default=4)
    p.add_argument('--candidates',type=int,default=12)
    p.add_argument('--fl-pairs',type=int,default=8)
    p.add_argument('--max-hands',type=int,default=128)
    p.add_argument('--seed',type=int,default=40000000)
    p.add_argument('--output',type=Path,default=DEFAULT_MODEL)
    p.add_argument('--report',type=Path,default=Path('docs/action-training.json'))
    p.add_argument('--initial-model',type=Path)
    p.add_argument('--data-dir',type=Path,default=Path('training-data'))
    args=p.parse_args()
    if min(args.generations,args.groups,args.validation,args.samples,args.candidates,args.fl_pairs,args.max_hands)<1:
        p.error('All counts must be positive')
    model=FastModel(json.loads(args.initial_model.read_text(encoding='utf-8'))) if args.initial_model else None
    history=[]
    for generation in range(args.generations):
        seed=args.seed+generation*10000000
        print(f'Generation {generation+1}',flush=True)
        table,fl=continuation_table(model,args.fl_pairs,seed,args.max_hands)
        groups,sessions=collect(args.groups,model,table,args.samples,args.candidates,seed+1000000,args.max_hands)
        valid,_=collect(args.validation,model,table,args.samples,args.candidates,seed+5000000,args.max_hands)
        args.data_dir.mkdir(parents=True,exist_ok=True)
        (args.data_dir/f'g{generation+1}-seed{seed}.json').write_text(
            json.dumps(dict(groups=groups,validation=valid,continuation=table)),encoding='utf-8')
        # Train on current-policy labels; previous frozen policies are recorded
        # rather than treating their old Q targets as current-policy returns.
        data=fit(groups,table,seed,validation=valid)
        info=dict(generation=generation+1,seed=seed,sessions=sessions,continuation=fl,
                  train=metrics(data,groups),validation=metrics(data,valid))
        history.append(info)
        data['training']=dict(generation=generation+1,seed=seed,groups=args.groups,samples=args.samples,
                              candidates=args.candidates,fl_pairs=args.fl_pairs,
                              target='Centered candidate rollout values plus undiscounted FL-chain continuation',
                              limitations='Approximate policy iteration, not Deep CFR or a Nash certificate. Uniform hidden-state approximation. Restricted sampled candidate labels.')
        args.output.parent.mkdir(parents=True,exist_ok=True)
        checkpoint=args.data_dir/f'model-seed{seed}-g{generation+1}.json'
        checkpoint.write_text(json.dumps(data,indent=2),encoding='utf-8')
        model=FastModel(data)
        print(json.dumps(info['validation']),flush=True)
    args.output.write_text(json.dumps(data,indent=2),encoding='utf-8')
    args.report.parent.mkdir(parents=True,exist_ok=True)
    args.report.write_text(json.dumps(dict(arguments={k:str(v) if isinstance(v,Path) else v for k,v in vars(args).items()},generations=history),indent=2),encoding='utf-8')


if __name__=='__main__':
    main()
