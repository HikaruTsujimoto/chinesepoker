"""Reduced-deck exact benchmark, NOT a full-game strength estimate."""
import argparse
from functools import lru_cache
from itertools import combinations
import json
import random
from pathlib import Path
from chinesepoker.ai.action_model import load_model, terminal_score
from chinesepoker.ai.evaluation import complete
from chinesepoker.ai.expectimax import exact_value
from chinesepoker.ai.model import EMPTY, after_move
from chinesepoker.ai.search import greedy_move, opponent_completion


def run(cases=12, seed=91000000):
    records=[]
    model=load_model()
    for case in range(cases):
        deck=random.Random(seed+case).sample(range(52),52)
        board=after_move(EMPTY,greedy_move(EMPTY,deck[:5],5))
        for start in (5,8):
            board=after_move(board,greedy_move(board,deck[start:start+3],2))
        pool=tuple(sorted(deck[11:18]))
        other=opponent_completion(EMPTY,deck[18:35])
        def terminal(board,pool):
            return terminal_score(board,other,0,0,model)
        @lru_cache(maxsize=None)
        def greedy_value(board,pool):
            if complete(board):
                return terminal(board,pool)
            draws=list(combinations(pool,3))
            return sum(greedy_value(after_move(board,greedy_move(board,draw,2)),
                       tuple(c for c in pool if c not in draw)) for draw in draws)/len(draws)
        optimal=exact_value(board,pool,terminal)
        baseline=greedy_value(board,pool)
        if optimal+1e-9 < baseline:
            raise AssertionError('Exact optimizer fell below a feasible greedy policy')
        records.append(dict(case=case,board=board,pool=pool,opponent=other,
                            optimal=optimal,greedy=baseline,gain=optimal-baseline))
    return dict(seed=seed,cases=cases,mean_gain=sum(r['gain'] for r in records)/cases,
                records=records,scope='Seven-card remaining pool, two future draws, fixed fully known opponent and fixed FL continuation table. Exact only within this reduced own-hand problem.')


if __name__=='__main__':
    p=argparse.ArgumentParser(description=__doc__)
    p.add_argument('--cases',type=int,default=12)
    p.add_argument('--output',type=Path,default=Path('docs/expectimax-endgame.json'))
    args=p.parse_args()
    if args.cases<1: p.error('Positive cases required')
    result=run(args.cases)
    args.output.parent.mkdir(parents=True,exist_ok=True)
    args.output.write_text(json.dumps(result,indent=2),encoding='utf-8')
    print(json.dumps({k:v for k,v in result.items() if k!='records'},indent=2))
