"""Exercise 14/15/16/17-card Fantasyland searches on fixed independent deals."""
import json
from pathlib import Path
import random
from chinesepoker.ai.model import EMPTY, Observation, validate_move
from chinesepoker.ai.search import choose_move
from chinesepoker.ai.evaluation import summary


def main():
    records = []
    for tier in (14, 15, 16, 17):
        for sample in range(4):
            seed = 20261019 + tier * 100 + sample
            hand = tuple(random.Random(seed).sample(range(52), tier))
            obs = Observation(EMPTY, hand, fantasyland_cards=tier)
            result = choose_move(obs, 'normal', seed=seed)
            foul, royalty, next_tier = summary(validate_move(obs, result.move), tier)
            records.append(dict(seed=seed, tier=tier, foul=foul, royalty=royalty,
                                next_tier=next_tier, seconds=result.seconds,
                                evaluated=result.candidates))
        print(f'{tier}-card cases complete', flush=True)
    path = Path('docs/cpu-benchmark-fantasy.json')
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(dict(difficulty='normal', records=records), indent=2), encoding='utf-8')
    print(json.dumps(dict(cases=len(records), fouls=sum(r['foul'] for r in records),
                         mean_royalty=sum(r['royalty'] for r in records)/len(records),
                         max_seconds=max(r['seconds'] for r in records))))


if __name__ == '__main__':
    main()
