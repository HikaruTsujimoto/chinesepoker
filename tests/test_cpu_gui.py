import os
os.environ.setdefault('SDL_VIDEODRIVER', 'dummy')
os.environ.setdefault('SDL_AUDIODRIVER', 'dummy')

from concurrent.futures import Future
import unittest
try:
    import pygame
except ImportError:
    pygame = None

from chinesepoker.ai.model import Observation, board_of, encode, apply_move
from chinesepoker.ai.search import choose_move, SearchConfig


class InlineExecutor:
    def submit(self, fn, observation, difficulty):
        future = Future()
        try:
            future.set_result(fn(observation, difficulty, seed=1,
                                 config=SearchConfig(seconds=0.03, samples=1, shortlist=2)))
        except Exception as error:
            future.set_exception(error)
        return future

    def shutdown(self, **kwargs):
        pass


@unittest.skipIf(pygame is None, 'Install requirements/runtime.txt for GUI tests')
class CpuGuiTests(unittest.TestCase):
    def test_normal_and_fantasy_rounds_finish_and_reset(self):
        from chinesepoker.ui.gui import GameGUI, screen
        for tiers in ((0, 0), (14, 0), (0, 17), (15, 16)):
            with self.subTest(tiers=tiers):
                gui = GameGUI('easy', executor=InlineExecutor())
                for p, tier in zip((gui.p1, gui.p2), tiers):
                    p.next_fantasyland = bool(tier)
                    p.next_fantasyland_cards = tier
                gui.build_round_actions()
                gui.next_action()
                for _ in range(15):
                    if gui.show_results:
                        break
                    if gui.is_cpu_turn():
                        gui.update_cpu()
                        self.assertIsNone(gui.cpu_error)
                    else:
                        obs = Observation(board_of(gui.p1), tuple(encode(c) for c in gui.cards_in_hand),
                                          fantasyland_cards=gui.p1.fantasyland_cards if gui.p1.fantasyland else 0)
                        move = choose_move(obs, seed=1, config=SearchConfig(seconds=0.03, samples=0)).move
                        cards = {encode(c): c for c in gui.cards_in_hand}
                        apply_move(gui.p1, gui.cards_in_hand, move)
                        gui.hidden_cards[gui.p1.name].extend(cards[c] for c, _ in move.placements)
                        gui.next_action()
                    gui.draw(screen)
                self.assertTrue(gui.show_results)
                self.assertEqual(gui.p1.count_cards(), 13)
                self.assertEqual(gui.p2.count_cards(), 13)
                self.assertEqual(sum(gui.game.points.values()), 0)
                gui.build_round_actions()
                self.assertEqual(gui.discards, [])
                self.assertTrue(all(not v for v in gui.hidden_cards.values()))
                gui.close()

    def test_worker_failure_leaves_live_board_unchanged(self):
        from chinesepoker.ui.gui import GameGUI
        gui = GameGUI('easy', executor=InlineExecutor())
        gui.current_action = {'type': 'turn', 'player': gui.p2}
        gui.cpu_future = Future()
        gui.cpu_future.set_exception(RuntimeError('test worker failure'))
        previous = board_of(gui.p2)
        gui.update_cpu()
        self.assertEqual(board_of(gui.p2), previous)
        self.assertIn('test worker failure', gui.cpu_error)
        gui.close()

    def test_gui_snapshot_excludes_current_hidden_cards_and_deck(self):
        from chinesepoker.ui.gui import GameGUI
        from chinesepoker.ai.model import CARDS
        gui = GameGUI('easy', executor=InlineExecutor())
        gui.current_action = {'type': 'turn', 'player': gui.p2}
        gui.cards_in_hand = list(CARDS[10:15])
        gui.p1.top = [CARDS[0], CARDS[1]]
        gui.hidden_cards[gui.p1.name] = [CARDS[1]]
        before = gui.cpu_observation()
        gui.p1.top[1] = CARDS[40]
        gui.hidden_cards[gui.p1.name] = [CARDS[40]]
        gui.game.deck.cards.reverse()
        self.assertEqual(before, gui.cpu_observation())
        gui.handle_click((720, 480))
        self.assertIsNone(gui.selected_card)
        gui.close()
