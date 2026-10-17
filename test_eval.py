from card import Card
from evaluator import check_validity, evaluate_hand, HandRank
import unittest

class EvaluationTests(unittest.TestCase):
    def test_legacy_symbol_hands(self):
        # Test valid placement (Same hand type, but distinct strength)
        # Bot: Two Pair (A, K)
        bot = [Card('♠', 'A'), Card('♥', 'A'), Card('♣', 'K'), Card('♦', 'K'), Card('♠', '5')]
        # Mid: Two Pair (Q, J)
        mid = [Card('♠', 'Q'), Card('♥', 'Q'), Card('♣', 'J'), Card('♦', 'J'), Card('♠', '9')]
        # Top: Pair (T)
        top = [Card('♠', 'T'), Card('♥', 'T'), Card('♣', '2')]

        self.assertTrue(check_validity(top, mid, bot))

        # Test foul (Mid stronger than Bot)
        # Bot: Two Pair (Q, J)
        bot2 = [Card('♠', 'Q'), Card('♥', 'Q'), Card('♣', 'J'), Card('♦', 'J'), Card('♠', '9')]
        # Mid: Two Pair (A, K)
        mid2 = [Card('♠', 'A'), Card('♥', 'A'), Card('♣', 'K'), Card('♦', 'K'), Card('♠', '5')]

        self.assertFalse(check_validity(top, mid2, bot2))

        # Test straight behavior
        bot_str = [Card('♠', 'A'), Card('♥', 'K'), Card('♣', 'Q'), Card('♦', 'J'), Card('♠', 'T')]
        bot_str_low = [Card('♠', '5'), Card('♥', '4'), Card('♣', '3'), Card('♦', '2'), Card('♠', 'A')]

        self.assertEqual(evaluate_hand(bot_str), (HandRank.STRAIGHT, [14], []))
        self.assertEqual(evaluate_hand(bot_str_low), (HandRank.STRAIGHT, [5], []))

if __name__ == '__main__':
    unittest.main()
