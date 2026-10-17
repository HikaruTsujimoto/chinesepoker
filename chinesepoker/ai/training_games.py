"""Exact, perfect-recall finite games for the MCCFR trainer."""
from dataclasses import dataclass, replace
from itertools import combinations, permutations, product
import json

from .model import EMPTY, Observation, validate_move
from .search import normal_moves
from .evaluation import terminal_value, summary, continuation_value


def observation_data(obs):
    return (obs.board, tuple(sorted(obs.hand)), obs.opponent, tuple(sorted(obs.discards)), obs.fantasyland_cards)


def move_data(move):
    return (tuple(sorted(move.placements)), tuple(sorted(move.discards)))


def information_key(player, history, observation):
    return json.dumps((player, history, observation_data(observation)), separators=(',', ':'))


@dataclass(frozen=True)
class OFCState:
    deck: tuple
    boards: tuple = (EMPTY, EMPTY)
    visible: tuple = (EMPTY, EMPTY)
    discards: tuple = ((), ())
    histories: tuple = ((), ())
    street: int = 0
    actor: int = 0

    @property
    def player(self):
        return None if self.street == 5 else self.actor

    def observation(self):
        count = 5 if self.street == 0 else 3
        offset = self.actor * 5 if self.street == 0 else 10 + (self.street-1)*6 + self.actor*3
        return Observation(self.boards[self.actor], tuple(sorted(self.deck[offset:offset+count])),
                           self.visible[1-self.actor], self.discards[self.actor])

    def key(self):
        return information_key(self.actor, self.histories[self.actor], self.observation())

    def actions(self):
        obs = self.observation()
        return tuple(normal_moves(obs.board, obs.hand, obs.place_count))

    def child(self, action):
        obs = self.observation()
        boards, discards, histories = list(self.boards), list(self.discards), list(self.histories)
        boards[self.actor] = validate_move(obs, action)
        discards[self.actor] += action.discards
        histories[self.actor] += ((observation_data(obs), move_data(action)),)
        return OFCState(self.deck, tuple(boards), tuple(boards) if self.actor else self.visible,
                        tuple(discards), tuple(histories), self.street + self.actor, 1-self.actor)

    def payoff(self, player):
        if self.player is not None:
            raise ValueError('Payoff requested before end of hand')
        # Remove the existing CPU's heuristic next-FL bonus: this finite game's
        # utility is ONLY the actual single-hand score, exactly zero-sum.
        score = terminal_value(self.boards[0], self.boards[1]) - continuation_value(summary(self.boards[0])[2])
        return score if player == 0 else -score


class OFCOneHand:
    identifier = 'pineapple-ofc-normal-one-hand-exact-v1'

    def start(self, rng):
        return OFCState(tuple(rng.sample(range(52), 52)))


@dataclass(frozen=True)
class EndgameState:
    hands: tuple
    boards: tuple
    visible: tuple
    actor: int = 0

    @property
    def player(self):
        return self.actor if self.actor < 2 else None

    def observation(self):
        return Observation(self.boards[self.actor], self.hands[self.actor], self.visible[1-self.actor])

    def key(self):
        return information_key(self.actor, (), self.observation())

    def actions(self):
        obs = self.observation()
        return tuple(normal_moves(obs.board, obs.hand, 2))

    def child(self, action):
        boards = list(self.boards)
        boards[self.actor] = validate_move(self.observation(), action)
        return replace(self, boards=tuple(boards), actor=self.actor+1)

    def payoff(self, player):
        if self.player is not None:
            raise ValueError('Non-terminal endgame')
        return OFCState((), boards=self.boards, street=5).payoff(player)


class OFCEndgame:
    """Controlled finite game: public 11-card boards and a public chance pool.

    Hands of three are drawn without replacement. Only own hand is observable;
    placements are simultaneous. The pool is common knowledge, NOT guessed
    from one player's secret discards. No future FL value is awarded.
    """
    def __init__(self, boards=None, pool=None):
        self.boards = boards or (((37,), (5, 7, 18, 43, 46), (8, 22, 28, 34, 47)),
                                 ((20, 24, 51), (2, 9, 45, 48), (1, 14, 36, 42)))
        self.pool = tuple(sorted(pool if pool is not None else (15, 12, 10, 4, 49, 0, 3, 6)))
        known = [c for b in self.boards for row in b for c in row]
        if (len(self.boards) != 2 or any(sum(map(len,b)) != 11 for b in self.boards)
                or len(self.pool) < 6 or len(set(known + list(self.pool))) != len(known) + len(self.pool)
                or any(not isinstance(c, int) or not 0 <= c < 52 for c in known + list(self.pool))):
            raise ValueError('Invalid public endgame scenario')
        for i in (0, 1):
            Observation(self.boards[i], self.pool[:3], self.boards[1-i])
        self.identifier = 'ofc-public-pool-endgame-v1:' + json.dumps((self.boards, self.pool), separators=(',', ':'))

    def start(self, rng):
        cards = rng.sample(self.pool, 6)
        return self.deal(tuple(sorted(cards[:3])), tuple(sorted(cards[3:])))

    def deal(self, hand0, hand1):
        return EndgameState((hand0, hand1), self.boards, self.boards)


class EndgameEvaluator:
    """Exact BR for this one-decision-per-player game, grouped by private hand.

    Cache payoff matrices once. Maximization happens AFTER summing over all
    hidden hands sharing an information set, avoiding clairvoyant responses.
    """
    def __init__(self, game):
        if len(game.pool) > 8:
            raise ValueError('Exact evaluator limited to pools of at most 8 cards')
        self.deals = []
        for h0 in combinations(game.pool, 3):
            for h1 in combinations([c for c in game.pool if c not in h0], 3):
                s0 = game.deal(h0, h1)
                actions0 = s0.actions()
                s1 = s0.child(actions0[0])
                actions1 = s1.actions()
                matrix = [[s0.child(a).child(b).payoff(0) for b in actions1] for a in actions0]
                self.deals.append((s0, s1, matrix))

    def evaluate(self, solver):
        value, response0, response1 = 0.0, {}, {}
        for s0, s1, matrix in self.deals:
            p0, p1 = solver.policy(s0), solver.policy(s1)
            v0 = [sum(v*p for v,p in zip(row,p1)) for row in matrix]
            v1 = [-sum(matrix[i][j]*p0[i] for i in range(len(p0))) for j in range(len(p1))]
            value += sum(p*v for p,v in zip(p0,v0))
            for table, state, values in ((response0,s0,v0), (response1,s1,v1)):
                key = state.key()
                table[key] = [a+b for a,b in zip(table.get(key, [0.0]*len(values)), values)]
        count = len(self.deals)
        best0, best1 = (sum(max(v) for v in table.values())/count for table in (response0,response1))
        return dict(value_player0=value/count, best_response_player0=best0,
                    best_response_player1=best1, nash_conv=best0+best1,
                    exploitability=(best0+best1)/2, chance_outcomes=count)


@dataclass(frozen=True)
class KuhnState:
    cards: tuple
    history: str = ''

    @property
    def player(self):
        return None if self.history in ('pp', 'bp', 'bb', 'pbp', 'pbb') else len(self.history) % 2

    def key(self):
        return f'{self.player}:{self.cards[self.player]}:{self.history}'

    def actions(self):
        return ('p', 'b')

    def child(self, action):
        return replace(self, history=self.history + action)

    def payoff(self, player):
        if self.player is not None:
            raise ValueError('Non-terminal Kuhn state')
        winner = 1 if self.cards[0] > self.cards[1] else -1
        value = 1 if self.history == 'bp' else -1 if self.history == 'pbp' else winner * (2 if self.history.endswith('bb') else 1)
        return value if player == 0 else -value


class KuhnPoker:
    identifier = 'kuhn-poker-v1'

    def start(self, rng):
        return KuhnState(tuple(rng.sample(range(3), 2)))


def evaluate_kuhn(solver):
    """Exact best responses over information-set-consistent pure policies.

    This does NOT maximize separately for each hidden opponent card.
    """
    deals = list(permutations(range(3), 2))
    def value(state, responder=None, choices=None):
        if state.player is None:
            return state.payoff(0)
        if state.player == responder:
            return value(state.child(choices[state.key()]), responder, choices)
        return sum(p * value(state.child(a), responder, choices)
                   for a,p in zip(state.actions(), solver.policy(state)))
    profile = sum(value(KuhnState(d)) for d in deals) / 6
    best = []
    for player, histories in ((0, ('', 'pb')), (1, ('p', 'b'))):
        keys = [f'{player}:{card}:{h}' for card in range(3) for h in histories]
        responses = []
        for actions in product(('p', 'b'), repeat=len(keys)):
            choices = dict(zip(keys, actions))
            responses.append(sum(value(KuhnState(d), player, choices) for d in deals) / 6)
        best.append(max(responses) if player == 0 else min(responses))
    return dict(value_player0=profile, best_response_player0=best[0],
                best_response_player1=-best[1], nash_conv=best[0]-best[1],
                exploitability=(best[0]-best[1])/2)
