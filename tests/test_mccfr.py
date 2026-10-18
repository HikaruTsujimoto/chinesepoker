import json
from pathlib import Path
import random
import tempfile
import unittest
from unittest.mock import patch

from chinesepoker.ai.mccfr import OutcomeSampling, NodeLimit, Node
from chinesepoker.ai.training_games import KuhnPoker, OFCOneHand, OFCState, OFCEndgame, EndgameEvaluator, evaluate_kuhn
from chinesepoker.ai.learned import choose_learned
from chinesepoker.ai.model import CARDS
from chinesepoker.core.player import Player
from chinesepoker.core.game import Game


class MCCFRTests(unittest.TestCase):
    def test_kuhn_exact_exploitability_reduces(self):
        solver = OutcomeSampling(KuhnPoker(), seed=7)
        initial = evaluate_kuhn(solver)['exploitability']
        for _ in range(30000):
            solver.iteration()
        result = evaluate_kuhn(solver)
        self.assertLess(result['exploitability'], 0.04)
        self.assertLess(result['exploitability'], initial / 5)
        self.assertAlmostEqual(result['value_player0'], -1/18, delta=0.02)

    def test_resume_preserves_rng_regrets_and_average(self):
        solver = OutcomeSampling(KuhnPoker(), seed=11)
        for _ in range(100):
            solver.iteration()
        with tempfile.TemporaryDirectory(dir='.') as directory:
            path = Path(directory) / 'checkpoint.json'
            solver.save(path)
            resumed = OutcomeSampling.load(path, KuhnPoker())
            for _ in range(100):
                solver.iteration()
                resumed.iteration()
            self.assertEqual(solver.nodes, resumed.nodes)
            self.assertEqual(solver.rng.getstate(), resumed.rng.getstate())
            with self.assertRaises(ValueError):
                OutcomeSampling.load(path, OFCOneHand())
            data = json.loads(path.read_text())
            next(iter(data['nodes'].values()))['average'][0] = -1
            path.write_text(json.dumps(data))
            with self.assertRaises(ValueError):
                OutcomeSampling.load(path, KuhnPoker())

    def test_ofc_information_boundary_and_perfect_recall(self):
        state = OFCOneHand().start(random.Random(3))
        deck = list(state.deck)
        deck[5], deck[40] = deck[40], deck[5]
        changed_hidden = OFCState(tuple(deck))
        self.assertEqual(state.key(), changed_hidden.key())
        self.assertEqual(state.actions(), changed_hidden.actions())
        first, last = state.child(state.actions()[0]), state.child(state.actions()[-1])
        self.assertEqual(first.key(), last.key())  # Player 1 cannot see current placement.
        next_street = first.child(first.actions()[0])
        self.assertEqual(next_street.visible, next_street.boards)
        forgotten = OFCState(next_street.deck, next_street.boards, next_street.visible,
                             next_street.discards, ((), ()), next_street.street, next_street.actor)
        self.assertNotEqual(next_street.key(), forgotten.key())

    def test_ofc_payoff_matches_real_game_and_is_zero_sum(self):
        for seed in range(12):
            rng = random.Random(seed)
            state = OFCOneHand().start(rng)
            while state.player is not None:
                state = state.child(rng.choice(state.actions()))
            players = [Player('a'), Player('b')]
            for p, board in zip(players, state.boards):
                p.top, p.mid, p.bot = ([CARDS[c] for c in row] for row in board)
                p.evaluate_board()
            a,b = players
            score = Game(players).calculate_matchup(a,b)[0] + a.get_royalties()-b.get_royalties()
            self.assertEqual(state.payoff(0), score)
            self.assertEqual(state.payoff(0), -state.payoff(1))

    def test_node_limit_does_not_apply_partial_regret_updates(self):
        solver = OutcomeSampling(OFCOneHand(), seed=4, max_nodes=2)
        with self.assertRaises(NodeLimit):
            solver.iteration()
        self.assertEqual(solver.iterations, 0)
        self.assertTrue(all(not any(n.regrets) and not any(n.average) for n in solver.nodes.values()))

    def test_ofc_endgame_exact_best_response_improves(self):
        game = OFCEndgame()
        evaluator = EndgameEvaluator(game)
        solver = OutcomeSampling(game, seed=19)
        initial = evaluator.evaluate(solver)['exploitability']
        for _ in range(20000):
            solver.iteration()
        result = evaluator.evaluate(solver)
        self.assertEqual(result['chance_outcomes'], 560)
        self.assertGreaterEqual(result['exploitability'], -1e-10)
        self.assertLess(result['exploitability'], initial / 3)
        # Current opponent placement remains hidden, even in this small game.
        state = game.start(random.Random(1))
        self.assertEqual(state.child(state.actions()[0]).key(), state.child(state.actions()[-1]).key())

    def test_saved_average_is_used_and_misses_fall_back(self):
        game = OFCOneHand()
        solver = OutcomeSampling(game)
        state = game.start(random.Random(9))
        moves = state.actions()
        average = [0.0]*len(moves)
        average[-1] = 5.0
        solver.nodes[state.key()] = Node([0.0]*len(moves), average, 1)
        with tempfile.TemporaryDirectory(dir='.') as directory:
            path = Path(directory) / 'ofc.json'
            solver.save(path)
            result = choose_learned(state.observation(), path, seat=0, seed=1)
            self.assertEqual(result.move, moves[-1])
            self.assertIn('MCCFR average', result.method)
            with patch('chinesepoker.ai.learned.choose_move', return_value=result) as fallback:
                missing = choose_learned(state.observation(), path, seat=1)
                self.assertIn('unseen', missing.method)
                self.assertEqual(fallback.call_count, 1)
                unsupported = choose_learned(state.observation(), path, supported=False)
                self.assertIn('Fantasyland', unsupported.method)

    def test_best_response_respects_hidden_information(self):
        # Uniform Kuhn's exact exploitability is 11/24, not a clairvoyant BR.
        result = evaluate_kuhn(OutcomeSampling(KuhnPoker()))
        self.assertAlmostEqual(result['exploitability'], 11/24)


if __name__ == '__main__':
    unittest.main()
