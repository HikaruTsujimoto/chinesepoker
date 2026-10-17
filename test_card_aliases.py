import unittest
from card import Card, Deck
from evaluator import evaluate_hand, HandRank


class CardAliasTests(unittest.TestCase):
    def test_aliases_normalize_identity(self):
        for symbol, letter in zip('♠♥♦♣', 'SHDC'):
            for rank in ('T', '10', 't'):
                with self.subTest(suit=symbol, rank=rank):
                    card = Card(symbol, rank)
                    self.assertEqual(card, Card(letter, '10'))
                    self.assertEqual(hash(card), hash(Card(letter, '10')))
                    self.assertEqual(str(card), letter + '10')
                    self.assertEqual(card.value, 10)
        self.assertEqual(len(set(Deck().cards)), 52)

    def test_symbol_hand_can_be_evaluated(self):
        cards = [Card('♠', r) for r in ('A', 'K', 'Q', 'J', 'T')]
        self.assertEqual(evaluate_hand(cards)[0], HandRank.ROYAL_FLUSH)

    def test_invalid_inputs_still_rejected(self):
        for suit, rank in [('X', 'A'), ('S', '1')]:
            with self.assertRaises(ValueError):
                Card(suit, rank)


if __name__ == '__main__':
    unittest.main()
