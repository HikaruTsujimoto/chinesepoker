"""Tabular outcome-sampling MCCFR for two-player zero-sum finite games.

Games sample uniform root chance with start(rng). States expose player, key(),
actions(), child(action), and payoff(player). No action or information abstraction
is performed here. Returned policies are reach-weighted AVERAGE strategies.
"""
from dataclasses import dataclass
import json
import math
from pathlib import Path
import random


def normalize(weights):
    total = sum(weights)
    return [x / total for x in weights] if total > 0 else [1 / len(weights)] * len(weights)


@dataclass
class Node:
    regrets: list
    average: list
    visits: int = 0

    def policy(self):
        return normalize([max(0.0, r) for r in self.regrets])


class NodeLimit(RuntimeError):
    pass


class OutcomeSampling:
    def __init__(self, game, seed=0, exploration=0.6, max_nodes=100000):
        if not 0 < exploration <= 1 or max_nodes < 1:
            raise ValueError('Invalid exploration or node limit')
        self.game = game
        self.rng = random.Random(seed)
        self.exploration = exploration
        self.max_nodes = max_nodes
        self.nodes = {}
        self.iterations = 0

    def iteration(self):
        # Freeze policies during both episodes; commit all updates together.
        updates = []
        for target in (0, 1):
            self._episode(self.game.start(self.rng), target, 1.0, 1.0, 1.0, updates)
        for key, regrets, average in updates:
            node = self.nodes[key]
            node.regrets = [a+b for a,b in zip(node.regrets, regrets)]
            node.average = [a+b for a,b in zip(node.average, average)]
            node.visits += 1
        self.iterations += 1

    def _episode(self, state, target, own_reach, other_reach, sampling_reach, updates):
        if state.player is None:
            return state.payoff(target)
        actions = state.actions()
        key = state.key()
        node = self.nodes.get(key)
        if node is None:
            if len(self.nodes) >= self.max_nodes:
                raise NodeLimit('Information-set limit reached; no abstraction or eviction applied')
            node = self.nodes[key] = Node([0.0]*len(actions), [0.0]*len(actions))
        if len(node.regrets) != len(actions):
            raise ValueError('Information set has inconsistent legal actions')
        policy = node.policy()
        updating = state.player == target
        sampling = [(1-self.exploration)*p + self.exploration/len(actions) for p in policy] if updating else policy
        selected = self.rng.choices(range(len(actions)), weights=sampling, k=1)[0]
        child_value = self._episode(state.child(actions[selected]), target,
                                    own_reach * (policy[selected] if updating else 1),
                                    other_reach * (1 if updating else policy[selected]),
                                    sampling_reach * sampling[selected], updates)
        # Importance correction for the sampled continuation. Unsampled action
        # values have zero estimates; in expectation all legal actions contribute.
        action_value = child_value / sampling[selected]
        value = policy[selected] * action_value
        if updating:
            counterfactual_weight = other_reach / sampling_reach
            regrets = [counterfactual_weight * ((action_value if a == selected else 0)-value)
                       for a in range(len(actions))]
            average = [own_reach * p / sampling_reach for p in policy]
            updates.append((key, regrets, average))
        return value

    def policy(self, state):
        actions = state.actions()
        node = self.nodes.get(state.key())
        if node is None:
            return [1 / len(actions)] * len(actions)
        if len(node.average) != len(actions):
            raise ValueError('Strategy/action mismatch')
        return normalize(node.average)

    def save(self, path):
        path = Path(path)
        path.parent.mkdir(parents=True, exist_ok=True)
        data = dict(format='ofc-mccfr-v1', game=self.game.identifier, iterations=self.iterations,
                    exploration=self.exploration, rng=self.rng.getstate(),
                    nodes={k:dict(regrets=n.regrets, average=n.average, visits=n.visits)
                           for k,n in self.nodes.items()})
        temporary = path.with_suffix(path.suffix + '.tmp')
        temporary.write_text(json.dumps(data, separators=(',', ':'), allow_nan=False), encoding='utf-8')
        temporary.replace(path)

    @classmethod
    def load(cls, path, game, max_nodes=100000):
        data = json.loads(Path(path).read_text(encoding='utf-8'))
        if data['format'] != 'ofc-mccfr-v1' or data['game'] != game.identifier:
            raise ValueError('Checkpoint belongs to a different game or format')
        solver = cls(game, exploration=data['exploration'], max_nodes=max_nodes)
        if len(data['nodes']) > max_nodes or data['iterations'] < 0:
            raise ValueError('Invalid checkpoint size or iteration count')
        for key, value in data['nodes'].items():
            regrets, average = value['regrets'], value['average']
            if (not regrets or len(regrets) != len(average) or value['visits'] < 0 or
                    any(not math.isfinite(x) for x in regrets + average) or any(x < 0 for x in average)):
                raise ValueError('Invalid checkpoint node')
            solver.nodes[key] = Node(regrets, average, value['visits'])
        solver.iterations = data['iterations']
        def tuples(value):
            return tuple(tuples(x) for x in value) if isinstance(value, list) else value
        solver.rng.setstate(tuples(data['rng']))
        return solver
