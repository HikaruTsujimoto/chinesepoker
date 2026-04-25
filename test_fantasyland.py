import unittest
from player import Player
from card import Card

class TestFantasyland(unittest.TestCase):
    
    def test_no_fantasyland(self):
        player = Player("P1")
        # Top: J high
        player.top = [Card('S', 'J'), Card('H', '2'), Card('D', '3')]
        player.mid = [Card('C', '4'), Card('S', '5'), Card('H', '6'), Card('D', '7'), Card('C', '8')]
        player.bot = [Card('S', '9'), Card('H', '10'), Card('D', 'J'), Card('C', 'Q'), Card('S', 'K')]
        
        player.evaluate_board()
        self.assertFalse(player.is_foul)
        self.assertFalse(player.next_fantasyland)
        self.assertEqual(player.next_fantasyland_cards, 0)
        
    def test_foul_prevents_fantasyland(self):
        player = Player("P1")
        # Top has AAA, but Mid is worse than Top (foul)
        player.top = [Card('S', 'A'), Card('H', 'A'), Card('D', 'A')]
        player.mid = [Card('C', '2'), Card('S', '3'), Card('H', '4'), Card('D', '7'), Card('C', '8')]
        player.bot = [Card('S', '9'), Card('H', '10'), Card('D', 'J'), Card('C', 'Q'), Card('S', 'K')]
        
        player.evaluate_board()
        self.assertTrue(player.is_foul)
        self.assertFalse(player.next_fantasyland)
        self.assertEqual(player.next_fantasyland_cards, 0)

    def test_fantasyland_pair_q(self):
        player = Player("P1")
        # Top: QQ
        player.top = [Card('S', 'Q'), Card('H', 'Q'), Card('D', '2')]
        player.mid = [Card('C', '4'), Card('S', '5'), Card('H', '6'), Card('D', '7'), Card('C', '8')] # 8 high straight
        player.bot = [Card('S', '9'), Card('H', '10'), Card('D', 'J'), Card('C', 'Q'), Card('S', 'K')] # K high straight
        
        player.evaluate_board()
        self.assertFalse(player.is_foul)
        self.assertTrue(player.next_fantasyland)
        self.assertEqual(player.next_fantasyland_cards, 14)

    def test_fantasyland_pair_k(self):
        player = Player("P1")
        # Top: KK
        player.top = [Card('S', 'K'), Card('H', 'K'), Card('D', '2')]
        player.mid = [Card('S', '2'), Card('H', '2'), Card('C', '2'), Card('D', '4'), Card('C', '5')] # Three of a kind
        player.bot = [Card('S', '3'), Card('H', '3'), Card('C', '3'), Card('D', '3'), Card('C', '6')] # Four of a kind
        
        player.evaluate_board()
        self.assertFalse(player.is_foul)
        self.assertTrue(player.next_fantasyland)
        self.assertEqual(player.next_fantasyland_cards, 15)

    def test_fantasyland_pair_a(self):
        player = Player("P1")
        # Top: AA
        player.top = [Card('S', 'A'), Card('H', 'A'), Card('D', '2')]
        player.mid = [Card('S', '2'), Card('H', '2'), Card('C', '2'), Card('D', '4'), Card('C', '5')] # Three of a kind
        player.bot = [Card('S', '3'), Card('H', '3'), Card('C', '3'), Card('D', '3'), Card('C', '6')] # Four of a kind
        
        player.evaluate_board()
        self.assertFalse(player.is_foul)
        self.assertTrue(player.next_fantasyland)
        self.assertEqual(player.next_fantasyland_cards, 16)

    def test_fantasyland_three_of_a_kind(self):
        player = Player("P1")
        # Top: 222
        player.top = [Card('S', '2'), Card('H', '2'), Card('D', '2')]
        player.mid = [Card('S', '4'), Card('H', '4'), Card('C', '4'), Card('D', '5'), Card('C', '5')] # Full house
        player.bot = [Card('S', 'A'), Card('H', 'A'), Card('C', 'A'), Card('D', 'A'), Card('C', '6')] # Four of a kind
        
        player.evaluate_board()
        self.assertFalse(player.is_foul)
        self.assertTrue(player.next_fantasyland)
        self.assertEqual(player.next_fantasyland_cards, 17)

    def test_stay_in_fantasyland_weak_top_strong_bot(self):
        player = Player("P1")
        player.fantasyland = True # Already in fantasyland
        # Top: Pair 2
        player.top = [Card('S', '2'), Card('H', '2'), Card('D', '3')]
        player.mid = [Card('S', '4'), Card('H', '5'), Card('C', '6'), Card('D', '7'), Card('C', '8')] # Straight
        player.bot = [Card('S', 'A'), Card('H', 'A'), Card('C', 'A'), Card('D', 'A'), Card('C', '6')] # Four of a kind (Qualifies to stay)
        
        player.evaluate_board()
        self.assertFalse(player.is_foul)
        self.assertTrue(player.next_fantasyland)
        self.assertEqual(player.next_fantasyland_cards, 14) # Default to 14 if staying via bot but top doesn't give progressive bonus

if __name__ == '__main__':
    unittest.main()
