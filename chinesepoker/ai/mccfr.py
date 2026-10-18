"""Tabular outcome-sampling MCCFR, including experimental absorbing sessions.

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


class ResourceLimit(RuntimeError):
    pass


class NodeLimit(ResourceLimit):
    pass


class ActionLimit(ResourceLimit):
    pass


class TrajectoryLimit(ResourceLimit):
    pass


class OutcomeSampling:
    def __init__(self, game, seed=0, exploration=0.6, max_nodes=100000,
                 max_actions=10000, max_steps=512, max_hands=64):
        if not 0 < exploration <= 1 or min(max_nodes,max_actions,max_steps,max_hands) < 1:
            raise ValueError('Invalid exploration or node limit')
        self.game = game
        self.rng = random.Random(seed)
        self.exploration = exploration
        self.max_nodes = max_nodes
        self.max_actions, self.max_steps, self.max_hands = max_actions, max_steps, max_hands
        self.nodes = {}
        self.iterations = 0
        self.last_episode_hands = []

    def iteration(self):
        # Freeze policies during both episodes; commit all updates together.
        updates = []
        created, completed = [], []
        rng_state = self.rng.getstate()
        try:
            for target in (0, 1):
                self._episode(self.game.start(self.rng), target, 1.0, 1.0, 1.0, updates,
                              created, completed, 0)
        except (ResourceLimit, KeyboardInterrupt):
            # Do not skip difficult FL trajectories on resume: retry exactly
            # the same episode after the user raises the resource limit.
            for key in created:
                del self.nodes[key]
            self.rng.setstate(rng_state)
            raise
        for key, regrets, average in updates:
            node = self.nodes[key]
            node.regrets = [a+b for a,b in zip(node.regrets, regrets)]
            node.average = [a+b for a,b in zip(node.average, average)]
            node.visits += 1
        self.iterations += 1
        self.last_episode_hands = completed

    def _episode(self, state, target, own_reach, other_reach, sampling_reach, updates,
                 created, completed, depth):
        # Explicit trajectory stack avoids Python recursion limits on long FL chains.
        path = []
        while state.player is not None:
            if depth >= self.max_steps or sampling_reach < 1e-200:
                raise TrajectoryLimit('Trajectory/importance-weight limit reached; no cash-out value assigned')
            depth += 1
            if state.player == -1:
                if getattr(state, 'completed_hands', 0) >= self.max_hands:
                    raise TrajectoryLimit('FL still active at hand resource limit; no settlement or reward update')
                # Uniform deck chance cancels in opponent/sampling reach. The
                # omitted average factor is constant at a perfect-recall set.
                state = state.sample_chance(self.rng)
                continue
            actions = state.actions()
            if len(actions) > self.max_actions:
                raise ActionLimit(f'{len(actions)} legal actions exceed table limit {self.max_actions}; no pruning applied')
            key = state.key()
            node = self.nodes.get(key)
            if node is None:
                if len(self.nodes) >= self.max_nodes:
                    raise NodeLimit('Information-set limit reached; no abstraction or eviction applied')
                node = self.nodes[key] = Node([0.0]*len(actions), [0.0]*len(actions))
                created.append(key)
            if len(node.regrets) != len(actions):
                raise ValueError('Information set has inconsistent legal actions')
            policy = node.policy()
            updating = state.player == target
            sampling = [(1-self.exploration)*p + self.exploration/len(actions) for p in policy] if updating else policy
            selected = self.rng.choices(range(len(actions)), weights=sampling, k=1)[0]
            path.append((key,policy,updating,selected,sampling[selected],own_reach,other_reach,sampling_reach))
            own_reach *= policy[selected] if updating else 1
            other_reach *= 1 if updating else policy[selected]
            sampling_reach *= sampling[selected]
            state = state.child(actions[selected])
        completed.append(getattr(state, 'completed_hands', 1))
        value = state.payoff(target)
        for key,policy,updating,selected,sample_prob,own_reach,other_reach,sampling_reach in reversed(path):
            # Unsampled actions have zero value estimates, not zero regrets.
            action_value = value / sample_prob
            value = policy[selected] * action_value
            if updating:
                counterfactual_weight = other_reach / sampling_reach
                regrets = [counterfactual_weight * ((action_value if a == selected else 0)-value)
                           for a in range(len(policy))]
                average = [own_reach * p / sampling_reach for p in policy]
                updates.append((key, regrets, average))
        return value

    def policy(self, state):
        actions = state.actions()
        if len(actions) > self.max_actions:
            raise ActionLimit('Policy too large to materialize')
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
    def load(cls, path, game, max_nodes=100000, max_actions=10000, max_steps=512, max_hands=64):
        data = json.loads(Path(path).read_text(encoding='utf-8'))
        if data['format'] != 'ofc-mccfr-v1' or data['game'] != game.identifier:
            raise ValueError('Checkpoint belongs to a different game or format')
        solver = cls(game, exploration=data['exploration'], max_nodes=max_nodes,
                     max_actions=max_actions,max_steps=max_steps,max_hands=max_hands)
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
