"""Undiscounted OFC sessions: settle only when BOTH next-FL rights vanish.

The transition model has no hand-count terminal and no exit action during FL.
Resource guards belong to the trainer, not to the game's rewards.
"""
from collections.abc import Sequence
from dataclasses import dataclass, replace
import hashlib
import json
from math import comb
import random

from .model import EMPTY, Move, Observation, after_move, validate_move
from .evaluation import terminal_value, summary, continuation_value
from .search import normal_moves
from .training_games import observation_data, move_data
from chinesepoker.core.session_rules import can_settle


def unrank_combination(items, count, index):
    """Lexicographic combination indexing without enumerating the space."""
    result = []
    start = 0
    for remaining in range(count, 0, -1):
        for position in range(start, len(items)-remaining+1):
            block = comb(len(items)-position-1, remaining-1)
            if index < block:
                result.append(items[position])
                start = position+1
                break
            index -= block
    return tuple(result)


class FantasyActions(Sequence):
    """Every 3/5/5 assignment, including fouls, represented lazily."""
    def __init__(self, hand):
        self.hand = tuple(sorted(hand))
        n = len(self.hand)
        if n not in (14, 15, 16, 17) or len(set(hand)) != n:
            raise ValueError('Invalid Fantasyland hand')
        self.bottoms = comb(n-8, 5)
        self.rest = comb(n-3, 5)*self.bottoms
        self.count = comb(n, 3)*self.rest

    def __len__(self):
        return self.count

    def __getitem__(self, index):
        if isinstance(index, slice):
            raise TypeError('Slice materialization is disabled for large action spaces')
        if index < 0:
            index += len(self)
        if not 0 <= index < len(self):
            raise IndexError(index)
        top_id, rest_id = divmod(index, self.rest)
        mid_id, bot_id = divmod(rest_id, self.bottoms)
        top = unrank_combination(self.hand, 3, top_id)
        rest = tuple(c for c in self.hand if c not in top)
        mid = unrank_combination(rest, 5, mid_id)
        rest = tuple(c for c in rest if c not in mid)
        bot = unrank_combination(rest, 5, bot_id)
        used = set(top + mid + bot)
        return Move(tuple((c,r) for r,row in enumerate((top,mid,bot)) for c in row),
                    tuple(c for c in self.hand if c not in used))


def restricted_fantasy_actions(obs, count):
    """A deterministic action abstraction; NEVER described as all FL actions."""
    actions = FantasyActions(obs.hand)
    # Same observable information always produces the same ordered actions.
    digest = hashlib.sha256(json.dumps(observation_data(obs), separators=(',', ':')).encode()).digest()
    rng = random.Random(int.from_bytes(digest, 'big'))
    indices = rng.sample(range(len(actions)), min(len(actions), max(256, count)))
    opponent = obs.opponent if sum(map(len, obs.opponent)) == 13 else None
    candidates = [actions[i] for i in indices]
    candidates.sort(key=lambda m: (terminal_value(after_move(EMPTY,m), opponent, obs.fantasyland_cards),
                                   not summary(after_move(EMPTY,m), obs.fantasyland_cards)[0], move_data(m)), reverse=True)
    return tuple(candidates[:count])


@dataclass(frozen=True)
class SessionState:
    tiers: tuple = (0, 0)
    histories: tuple = ((), ())
    total: float = 0.0
    completed_hands: int = 0
    fantasy_candidates: int = 0
    boards: tuple = (EMPTY, EMPTY)
    visible: tuple = (EMPTY, EMPTY)
    discards: tuple = ((), ())
    deals: tuple = ()  # Per-action private hands; never included in an info key.
    schedule: tuple = ()  # (player, street); FL street is 5.
    turn: int = 0
    needs_deal: bool = True
    settled: bool = False

    @property
    def player(self):
        return None if self.settled else -1 if self.needs_deal else self.schedule[self.turn][0]

    def sample_chance(self, rng):
        if not self.needs_deal or self.settled:
            raise ValueError('Not a deal node')
        deck = rng.sample(range(52), 52)
        normal = [p for p in (0,1) if not self.tiers[p]]
        fantasy = [p for p in (0,1) if self.tiers[p]]
        schedule = [(p,s) for s in range(5) for p in normal] + [(p,5) for p in fantasy]
        index, deals = 0, []
        for p, street in schedule:
            count = self.tiers[p] if street == 5 else 5 if street == 0 else 3
            deals.append(tuple(sorted(deck[index:index+count])))
            index += count
        return replace(self, deals=tuple(deals), schedule=tuple(schedule), needs_deal=False)

    def observation(self):
        p = self.player
        if p not in (0,1):
            raise ValueError('Not a player node')
        return Observation(self.boards[p], self.deals[self.turn], self.visible[1-p], self.discards[p], self.tiers[p], self.tiers[1-p])

    def key(self):
        p = self.player
        return json.dumps(('session-v1',p,self.completed_hands,self.total,self.tiers,
                           self.histories[p],observation_data(self.observation())), separators=(',', ':'))

    def actions(self):
        obs = self.observation()
        if obs.fantasyland_cards:
            return (restricted_fantasy_actions(obs, self.fantasy_candidates) if self.fantasy_candidates
                    else FantasyActions(obs.hand))
        return tuple(normal_moves(obs.board, obs.hand, obs.place_count))

    def child(self, action):
        p = self.player
        obs = self.observation()
        boards, discards, histories = list(self.boards), list(self.discards), list(self.histories)
        boards[p] = validate_move(obs, action)
        discards[p] += action.discards
        histories[p] += (('move',observation_data(obs),move_data(action)),)
        if self.turn+1 < len(self.schedule):
            reveal = self.schedule[self.turn][1] != self.schedule[self.turn+1][1]
            if reveal:
                # FL players also observe the normal player's earlier public
                # placements while waiting. Preserve that public sequence.
                event = ('reveal',self.schedule[self.turn][1],tuple(boards))
                histories = [h+(event,) for h in histories]
            return replace(self, boards=tuple(boards), discards=tuple(discards), histories=tuple(histories),
                           visible=tuple(boards) if reveal else self.visible, turn=self.turn+1)
        return self.finish_hand(tuple(boards), tuple(histories))

    def finish_hand(self, boards, histories=None):
        if len(boards) != 2 or any(tuple(map(len,b)) != (3,5,5) for b in boards):
            raise ValueError('Both boards must be complete before resolving a hand')
        # Rule engine evaluates continuation with the CURRENT 14/15/16/17 tier.
        evaluations = [summary(b,t) for b,t in zip(boards,self.tiers)]
        next_tiers = tuple(e[2] for e in evaluations)
        score = terminal_value(boards[0],boards[1],self.tiers[0]) - continuation_value(next_tiers[0])
        event = ('result',self.tiers,boards,score,next_tiers)
        histories = tuple(h+(event,) for h in (self.histories if histories is None else histories))
        terminal = can_settle(next_tiers)
        return SessionState(next_tiers,histories,self.total+score,self.completed_hands+1,
                            self.fantasy_candidates,needs_deal=not terminal,settled=terminal)

    def payoff(self, player):
        if not self.settled:
            raise ValueError('Cannot cash out while either player has Fantasyland rights')
        return self.total if player == 0 else -self.total


class OFCSession:
    def __init__(self, fantasy_candidates=0, initial_tiers=(0,0)):
        if fantasy_candidates < 0 or fantasy_candidates > 256:
            raise ValueError('Use 0 (exact) or 1..256 FL candidates')
        if len(initial_tiers) != 2 or any(t not in (0,14,15,16,17) for t in initial_tiers):
            raise ValueError('Invalid initial Fantasyland tiers')
        self.fantasy_candidates = fantasy_candidates
        self.initial_tiers = tuple(initial_tiers)
        self.identifier = 'ofc-until-both-fl-end-v1:' + json.dumps((fantasy_candidates,initial_tiers), separators=(',', ':'))

    def start(self, rng):
        return SessionState(tiers=self.initial_tiers, fantasy_candidates=self.fantasy_candidates)
