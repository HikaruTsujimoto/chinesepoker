"""Learn a generalized afterstate value from FULL settled self-play sessions."""
import argparse
from dataclasses import replace
import json
from pathlib import Path
import random
import statistics

from chinesepoker.ai.session_game import SessionState
from chinesepoker.ai.model import after_move
from chinesepoker.ai.search import choose_move, normal_moves, LEVELS
from chinesepoker.ai.value_model import FORMAT, DEFAULT_MODEL, features, fit


def collect(count, seed, max_hands=64):
    rows, sessions, censored = [], [], 0
    for index in range(count):
        chance = random.Random(seed+index)
        policy = random.Random(seed+index+10000000)
        state = SessionState()
        pending = []
        while not state.settled:
            if state.needs_deal:
                if state.completed_hands >= max_hands:
                    censored += 1
                    break
                state = state.sample_chance(chance)
                continue
            obs, seat = state.observation(), state.player
            if not obs.fantasyland_cards and policy.random() < .15:
                move = policy.choice(list(normal_moves(obs.board, obs.hand, obs.place_count)))
            else:
                move = choose_move(obs, seed=policy.randrange(2**32),
                                   config=replace(LEVELS['easy'], seconds=.08, diversified_fantasy=True)).move
            if not obs.fantasyland_cards:
                pending.append((features(after_move(obs.board, move), obs.opponent), seat, state.total))
            state = state.child(move)
        if state.settled:
            rows.extend((x, (state.total-before)*(1 if seat == 0 else -1)) for x,seat,before in pending)
            sessions.append(state.completed_hands)
        if (index+1) % 50 == 0:
            print(f'{index+1}/{count} self-play sessions', flush=True)
    if censored:
        # Dropping long sessions conditions the training distribution on length.
        # Refuse to publish that biased model: rerun with a larger guard.
        raise RuntimeError(f'{censored} censored sessions; increase max_hands')
    return rows, dict(sessions=count, hands=sum(sessions), multi_hand=sum(h>1 for h in sessions))


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--sessions', type=int, default=5000)
    parser.add_argument('--validation', type=int, default=1000)
    parser.add_argument('--seed', type=int, default=20261030)
    parser.add_argument('--max-hands', type=int, default=64)
    parser.add_argument('--output', type=Path, default=DEFAULT_MODEL)
    args = parser.parse_args()
    if min(args.sessions, args.validation, args.max_hands) < 1 or args.sessions >= 1000000:
        parser.error('Positive counts required; training sessions must be < 1000000')
    train, train_info = collect(args.sessions, args.seed, args.max_hands)
    valid, valid_info = collect(args.validation, args.seed+1000000, args.max_hands)
    model = fit(train, seed=args.seed)
    mean = statistics.mean(y for _,y in train)
    mse = statistics.mean((sum(w*v for w,v in zip(model.weights,x))-y)**2 for x,y in valid)
    baseline = statistics.mean((mean-y)**2 for _,y in valid)
    data = dict(format=FORMAT, weights=model.weights, seed=args.seed,
                train=train_info, validation=valid_info, train_rows=len(train), validation_rows=len(valid),
                validation_mse=mse, constant_baseline_mse=baseline,
                target='Undiscounted remaining session points until BOTH FL rights vanish',
                behavior='Easy heuristic + 15% random normal moves; diversified FL search 0.08 seconds',
                limitations='Linear policy evaluation, not optimal value, CFR or a Nash certificate; FL continuation is in returns.')
    args.output.parent.mkdir(parents=True, exist_ok=True)
    args.output.write_text(json.dumps(data, indent=2), encoding='utf-8')
    print(json.dumps({k:v for k,v in data.items() if k != 'weights'}, indent=2))


if __name__ == '__main__':
    main()
