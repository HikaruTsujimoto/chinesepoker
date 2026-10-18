import random
import unittest
from unittest.mock import patch

from chinesepoker.ai.model import Observation, after_move, validate_move
from chinesepoker.ai.search import SearchConfig, choose_move, normal_moves
from chinesepoker.ai.evaluation import terminal_value


class EndgameTests(unittest.TestCase):
    def test_opponent_model_changes_choice_to_gain_five_points(self):
        # Same own royalty: the opponent's top row makes the kicker relevant.
        board = ((37,), (5, 7, 18, 43, 46), (8, 22, 28, 34, 47))
        visible = ((20, 24, 51), (2, 9, 45, 48), (1, 14, 36, 42))
        finished = ((20, 24, 51), (2, 4, 9, 45, 48), (1, 14, 36, 42, 49))
        obs = Observation(board, (15, 12, 10), visible)
        old = choose_move(obs, config=SearchConfig(opponent_aware_final=False))
        with patch('chinesepoker.ai.search.opponent_completion', return_value=finished):
            new = choose_move(obs, config=SearchConfig(seconds=60, samples=3))
        old_score = terminal_value(validate_move(obs, old.move), finished)
        new_score = terminal_value(validate_move(obs, new.move), finished)
        self.assertEqual(new_score - old_score, 5)

    def setUp(self):
        deck = random.Random(61).sample(range(52), 40)
        self.board = (tuple(sorted(deck[:2])), tuple(sorted(deck[2:6])), tuple(sorted(deck[6:11])))
        self.hand = tuple(deck[11:14])
        self.other = (tuple(sorted(deck[14:17])), tuple(sorted(deck[17:22])), tuple(sorted(deck[22:27])))

    def test_known_opponent_is_scored_exactly_without_sampling(self):
        obs = Observation(self.board, self.hand, self.other)
        with patch('chinesepoker.ai.search.opponent_completion', side_effect=AssertionError('No unknown cards')):
            decision = choose_move(obs, seed=1)
        expected = max(terminal_value(after_move(obs.board, m), self.other)
                       for m in normal_moves(obs.board, obs.hand, 2))
        self.assertEqual(decision.estimated_value, expected)
        self.assertEqual(decision.simulations, 0)

    def test_same_sampled_opponent_is_used_for_every_candidate(self):
        visible = (self.other[0][:2], self.other[1][:4], self.other[2])
        obs = Observation(self.board, self.hand, visible)
        with patch('chinesepoker.ai.search.opponent_completion', return_value=self.other) as completion:
            decision = choose_move(obs, seed=1, config=SearchConfig(seconds=60, samples=3))
        self.assertEqual(completion.call_count, 3)
        expected = max(terminal_value(after_move(obs.board, m), self.other)
                       for m in normal_moves(obs.board, obs.hand, 2))
        self.assertEqual(decision.estimated_value, expected)
        self.assertEqual(decision.simulations, decision.candidates * 3)
        validate_move(obs, decision.move)

    def test_previous_policy_switch_and_zero_budget_are_legal(self):
        obs = Observation(self.board, self.hand)
        for config in (SearchConfig(seconds=0), SearchConfig(opponent_aware_final=False)):
            with patch('chinesepoker.ai.search.opponent_completion', side_effect=AssertionError('No budget')):
                result = choose_move(obs, seed=10, config=config)
            validate_move(obs, result.move)
            self.assertEqual(result.simulations, 0)

    def test_sampling_never_uses_known_cards_as_unknown(self):
        obs = Observation(self.board, self.hand, (self.other[0][:2], self.other[1][:4], self.other[2]))
        def sample(board, draws):
            self.assertEqual(set(draws), set(obs.unseen()))
            return self.other
        with patch('chinesepoker.ai.search.opponent_completion', side_effect=sample):
            choose_move(obs, seed=7, config=SearchConfig(seconds=60, samples=2))
