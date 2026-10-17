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
        player.fantasyland_cards = 14
        # Top: Pair 2
        player.top = [Card('S', '2'), Card('H', '2'), Card('D', '3')]
        player.mid = [Card('S', '4'), Card('H', '5'), Card('C', '6'), Card('D', '7'), Card('C', '8')] # Straight
        player.bot = [Card('S', 'A'), Card('H', 'A'), Card('C', 'A'), Card('D', 'A'), Card('C', '6')] # Four of a kind (Qualifies to stay)
        
        player.evaluate_board()
        self.assertFalse(player.is_foul)
        self.assertTrue(player.next_fantasyland)
        self.assertEqual(player.next_fantasyland_cards, 14) # Preserve the current tier

    def test_continuation_preserves_every_tier(self):
        for tier in (14, 15, 16, 17):
            for reason in ('top', 'mid', 'bot'):
                with self.subTest(tier=tier, reason=reason):
                    p = Player('P1')
                    p.fantasyland = True
                    p.fantasyland_cards = tier
                    if reason == 'top':
                        p.top = [Card(s, 'A') for s in 'SHD']
                        p.mid = [Card(s, r) for s, r in [('S','2'),('H','3'),('D','4'),('C','5'),('S','6')]]
                        p.bot = [Card(s, r) for s, r in [('S','7'),('H','8'),('D','9'),('C','10'),('S','J')]]
                    else:
                        p.top = [Card(s, r) for s, r in [('S','2'),('H','2'),('D','3')]]
                        p.mid = ([Card(s, r) for s, r in [('S','4'),('H','4'),('C','4'),('D','5'),('C','5')]]
                                 if reason == 'mid' else
                                 [Card(s, r) for s, r in [('S','4'),('H','5'),('C','6'),('D','7'),('C','8')]])
                        p.bot = [Card(s, r) for s, r in [('S','A'),('H','A'),('C','A'),('D','A'),('C','9')]]
                    p.evaluate_board()
                    self.assertFalse(p.is_foul)
                    self.assertTrue(p.next_fantasyland)
                    self.assertEqual(p.next_fantasyland_cards, tier)

if __name__ == '__main__':
    unittest.main()
