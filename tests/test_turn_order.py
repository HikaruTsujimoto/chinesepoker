import unittest
from unittest.mock import patch
from chinesepoker.core.game import Game
from chinesepoker.core.player import Player
from chinesepoker.ui.cli import play_round


class TurnOrderTests(unittest.TestCase):
    def test_normal_players_finish_before_fantasyland(self):
        for tiers in ((0, 0), (14, 0), (0, 17), (14, 17)):
            with self.subTest(tiers=tiers):
                players = [Player('P1'), Player('P2')]
                for player, tier in zip(players, tiers):
                    player.next_fantasyland = bool(tier)
                    player.next_fantasyland_cards = tier
                game = Game(players)
                calls = []

                def place(player, cards, count):
                    calls.append((player.name, len(cards), count))
                    del cards[:count]

                normal = [p.name for p, tier in zip(players, tiers) if not tier]
                expected = [(name, 5, 5) for name in normal]
                expected += [(name, 3, 2) for _ in range(4) for name in normal]
                expected += [(p.name, tier, 13) for p, tier in zip(players, tiers) if tier]
                with patch('chinesepoker.ui.cli.clear_screen'), patch('builtins.input', return_value=''), patch('builtins.print'), patch('chinesepoker.ui.cli.prompt_placement', side_effect=place), patch.object(game, 'resolve_scores', return_value=''):
                    play_round(game)
                self.assertEqual(calls, expected)


if __name__ == '__main__':
    unittest.main()
