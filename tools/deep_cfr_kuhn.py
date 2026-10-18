"""Small-game Deep CFR validation, intentionally NOT an OFC equilibrium claim.

External sampling, iteration-weighted reservoir regression, fresh advantage
networks per update, and a separately fitted average-policy network follow
Brown et al. (2019): https://proceedings.mlr.press/v97/brown19b.html
Only 12 Kuhn information sets are supported by this diagnostic implementation.
"""
import argparse
import json
from pathlib import Path
import random
import numpy as np
from chinesepoker.ai.training_games import KuhnPoker, evaluate_kuhn

KEYS=[f'{p}:{c}:{h}' for p,hs in ((0,('','pb')),(1,('p','b'))) for c in range(3) for h in hs]


def encode_key(key):
    p,c,h=key.split(':')
    return [float(int(p)==i) for i in range(2)]+[float(int(c)==i) for i in range(3)]+[float(h==x) for x in ('','p','b','pb')]


class Reservoir:
    def __init__(self,capacity,rng):
        self.capacity,self.rng,self.seen,self.data=capacity,rng,0,[]

    def add(self,key,target,iteration):
        self.seen+=1
        row=(KEYS.index(key),tuple(target),iteration)
        if len(self.data)<self.capacity:
            self.data.append(row)
        else:
            i=self.rng.randrange(self.seen)
            if i<self.capacity:
                self.data[i]=row

    def aggregate(self):
        sums=np.zeros((12,2)); weights=np.zeros(12)
        for i,y,t in self.data:
            weights[i]+=t
            sums[i]+=np.asarray(y)*t
        return sums/np.maximum(weights[:,None],1),weights


class Network:
    def __init__(self,rng):
        self.p=[rng.normal(0,.2,(9,32)),np.zeros(32),rng.normal(0,.05,(32,2)),np.zeros(2)]

    def outputs(self):
        x=np.asarray([encode_key(k) for k in KEYS])
        return np.tanh(x@self.p[0]+self.p[1])@self.p[2]+self.p[3]

    def train(self,targets,weights,steps,classification=False):
        x=np.asarray([encode_key(k) for k in KEYS])
        w=weights[:,None]/max(1,weights.sum())
        m=[np.zeros_like(p) for p in self.p]; v=[p.copy() for p in m]
        for step in range(1,steps+1):
            h=np.tanh(x@self.p[0]+self.p[1]); pred=h@self.p[2]+self.p[3]
            if classification:
                pred=np.exp(pred-pred.max(axis=1,keepdims=True)); pred/=pred.sum(axis=1,keepdims=True)
            grad=(pred-targets)*w*(1 if classification else 2)
            dh=(grad@self.p[2].T)*(1-h*h)
            grads=[x.T@dh,dh.sum(axis=0),h.T@grad,grad.sum(axis=0)]
            for i,g in enumerate(grads):
                g=np.clip(g,-2,2)
                m[i]=.9*m[i]+.1*g; v[i]=.999*v[i]+.001*g*g
                self.p[i]-=.01*(m[i]/(1-.9**step))/(np.sqrt(v[i]/(1-.999**step))+1e-8)


class DeepCFRKuhn:
    def __init__(self,seed=7,capacity=30000):
        self.rng=random.Random(seed); self.np_rng=np.random.default_rng(seed)
        self.regrets=[Reservoir(capacity,random.Random(seed+10+p)) for p in (0,1)]
        self.average=Reservoir(capacity,random.Random(seed+20))
        self.strategies=[np.full((12,2),.5),np.full((12,2),.5)]
        self.iterations=0
        self.average_network=None

    def traverse(self,state,target):
        if state.player is None:
            return state.payoff(target)
        key=state.key(); i=KEYS.index(key)
        strategy=self.strategies[state.player][i]
        actions=state.actions()
        if state.player==target:
            values=np.array([self.traverse(state.child(a),target) for a in actions])
            value=float(values@strategy)
            self.regrets[target].add(key,values-value,self.iterations)
            return value
        self.average.add(key,strategy,self.iterations)
        action=self.rng.choices(actions,weights=strategy)[0]
        return self.traverse(state.child(action),target)

    def iteration(self,traversals=100,steps=200):
        self.iterations+=1
        for target in (0,1):
            for _ in range(traversals):
                self.traverse(KuhnPoker().start(self.rng),target)
            y,w=self.regrets[target].aggregate()
            network=Network(self.np_rng)  # Retrain from scratch, as in Deep CFR.
            network.train(y,w,steps)
            r=np.maximum(network.outputs(),0)
            totals=r.sum(axis=1,keepdims=True)
            self.strategies[target]=np.divide(r,totals,out=np.full_like(r,.5),where=totals>0)

    def fit_average(self,steps=2000):
        y,w=self.average.aggregate()
        self.average_network=Network(self.np_rng)
        self.average_network.train(y,w,steps,classification=True)
        logits=self.average_network.outputs()
        self.probabilities=np.exp(logits-logits.max(axis=1,keepdims=True))
        self.probabilities/=self.probabilities.sum(axis=1,keepdims=True)

    def policy(self,state):
        if self.average_network is None:
            return [.5,.5]
        return self.probabilities[KEYS.index(state.key())].tolist()


def main():
    p=argparse.ArgumentParser(description=__doc__)
    p.add_argument('--iterations',type=int,default=200)
    p.add_argument('--traversals',type=int,default=100)
    p.add_argument('--seed',type=int,default=7)
    p.add_argument('--output',type=Path,default=Path('docs/deep-cfr-kuhn.json'))
    args=p.parse_args()
    if min(args.iterations,args.traversals)<1:
        p.error('Counts must be positive')
    solver=DeepCFRKuhn(args.seed)
    initial=evaluate_kuhn(solver)
    for i in range(args.iterations):
        solver.iteration(args.traversals)
        if (i+1)%25==0: print(f'Deep CFR {i+1}/{args.iterations}',flush=True)
    solver.fit_average()
    result=dict(seed=args.seed,iterations=args.iterations,traversals=args.traversals,
                initial=initial,final=evaluate_kuhn(solver),
                policies={k:solver.probabilities[i].tolist() for i,k in enumerate(KEYS)},
                average_network=[p.tolist() for p in solver.average_network.p],
                memory_seen=[m.seen for m in solver.regrets]+[solver.average.seen],
                scope='Kuhn only, exact best-response evaluation; independent of deployed OFC policy-iteration model.')
    args.output.parent.mkdir(parents=True,exist_ok=True)
    args.output.write_text(json.dumps(result,indent=2),encoding='utf-8')
    print(json.dumps(result['final'],indent=2))


if __name__=='__main__':
    main()
