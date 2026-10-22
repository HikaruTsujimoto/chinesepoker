import pygame
import os
import sys
import time
import multiprocessing
import sqlite3
from uuid import uuid4
from concurrent.futures import ProcessPoolExecutor
from chinesepoker.ai.model import Observation, board_of, encode, apply_move
from chinesepoker.ai.search import choose_move
from chinesepoker import features
from chinesepoker.ai.training_games import observation_data, move_data
from chinesepoker.core.player import Player
from chinesepoker.core.game import Game
from chinesepoker.core.session_rules import can_settle
from chinesepoker.profiles import ProfileStore, round_event

# --- Constants & Colors ---
WIDTH, HEIGHT = 1280, 900
FPS = 60
BG_COLOR = (35, 90, 50) # Poker table green
WHITE = (255, 255, 255)
GOLD = (255, 215, 0)
BLACK = (0, 0, 0)
RED = (220, 20, 60)

CARD_W, CARD_H = 70, 96

# --- Pygame Setup ---
pygame.init()
screen = pygame.display.set_mode((WIDTH, HEIGHT))
pygame.display.set_caption("Pineapple OFC")
clock = pygame.time.Clock()
font = pygame.font.SysFont('yugothic,meiryo,notosanscjk,Arial', 24, bold=True)
large_font = pygame.font.SysFont('yugothic,meiryo,notosanscjk,Arial', 36, bold=True)
mono_font = pygame.font.SysFont('Consolas', 24, bold=True)

def resource_path(relative_path):
    """ Get absolute path to resource, works for dev and for PyInstaller """
    try:
        base_path = sys._MEIPASS
    except AttributeError:
        base_path = os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
    return os.path.join(base_path, relative_path)

# --- Asset Loading ---
def load_assets():
    cards = {}
    for suit in ['S', 'H', 'D', 'C']:
        for rank in ['2', '3', '4', '5', '6', '7', '8', '9', '10', 'J', 'Q', 'K', 'A']:
            path = resource_path(os.path.join('assets', f"{rank}{suit}.png"))
            try:
                img = pygame.image.load(path).convert_alpha()
                cards[f"{suit}{rank}"] = pygame.transform.smoothscale(img, (CARD_W, CARD_H))
            except:
                pass # Skip if missing
    try:
        back_img = pygame.image.load(resource_path(os.path.join('assets', 'back.png'))).convert_alpha()
        cards['back'] = pygame.transform.smoothscale(back_img, (CARD_W, CARD_H))
    except:
        pass
    return cards

card_images = load_assets()

# --- Helpers ---
def draw_text(surface, text, font, color, x, y, align="left"):
    img = font.render(text, True, color)
    rect = img.get_rect()
    if align == "center": rect.center = (x, y)
    elif align == "right": rect.topright = (x, y)
    else: rect.topleft = (x, y)
    surface.blit(img, rect)

class Button:
    def __init__(self, x, y, w, h, text, color, hover_color):
        self.rect = pygame.Rect(x, y, w, h)
        self.text = text
        self.color = color
        self.hover_color = hover_color
        
    def draw(self, surface):
        mouse_pos = pygame.mouse.get_pos()
        c = self.hover_color if self.rect.collidepoint(mouse_pos) else self.color
        pygame.draw.rect(surface, c, self.rect, border_radius=8)
        pygame.draw.rect(surface, WHITE, self.rect, 2, border_radius=8)
        draw_text(surface, self.text, font, WHITE, self.rect.centerx, self.rect.centery, align="center")
        
    def is_clicked(self, event):
        if event.type == pygame.MOUSEBUTTONDOWN and event.button == 1:
            if self.rect.collidepoint(event.pos):
                return True
        return False

class GameGUI:
    def __init__(self, difficulty='expectimax', executor=None, strategy_path=None,
                 profile_store=None, profile_ids=(None, None)):
        if not features.LEGACY_CPUS_ENABLED and (difficulty not in (None, 'expectimax') or strategy_path):
            raise ValueError('Legacy CPUs are disabled; use Expectimax')
        self.difficulty = difficulty
        self.strategy_path = strategy_path
        self.profile_store = profile_store
        self.profile_ids = (profile_ids[0], None if difficulty else profile_ids[1])
        active = [p for p in self.profile_ids if p is not None]
        if len(set(active)) != len(active):
            raise ValueError('Select different profiles for each player')
        known = {p['id']:p['name'] for p in profile_store.profiles()} if profile_store else {}
        if any(p not in known for p in active):
            raise ValueError('Unknown profile')
        self.display_names = (known.get(self.profile_ids[0], 'Player 1 (Guest)'),
                              'CPU' if difficulty else known.get(self.profile_ids[1], 'Player 2 (Guest)'))
        self.session_id = uuid4().hex
        self.session_settled = False
        self.target_reached = False
        self.pending_result = None
        self.save_error = None
        self.cpu_history = ()
        self.executor = executor
        self.cpu_future = None
        self.cpu_error = None
        self.cpu_started = 0
        self.last_cpu_decision = None
        self.discards = []
        self.p1 = Player("Player 1")
        self.p2 = Player("CPU" if difficulty else "Player 2")
        self.game = Game([self.p1, self.p2])
        self.game_round = 1
        
        self.actions = []
        self.current_action = None
        self.cards_in_hand = [] # Unplaced cards
        self.placed_this_turn = [] # Track cards placed this turn to allow moving
        self.hidden_cards = {self.p1.name: [], self.p2.name: []}
        self.current_round_num = 1
        
        self.selected_card = None
        self.hand_sort_descending = None
        self.hand_sort_mode = None
        self.btn_sort = Button(50, 432, 190, 38, 'Rank: 2 -> A', (0, 110, 160), (0, 145, 200))
        self.btn_sort_suit = Button(250, 432, 190, 38, 'Suit: S H D C', (0, 110, 160), (0, 145, 200))
        self.waiting_for_turn_start = False
        self.btn_confirm = Button(WIDTH // 2 - 75, HEIGHT - 80, 150, 50, "Confirm", (0, 120, 200), (0, 150, 250))
        self.btn_next = Button(WIDTH // 2 - 100, HEIGHT - 100, 200, 50, "Next Round", (0, 150, 50), (0, 180, 80))
        
        self.show_results = False
        self.results_text = ""
        
        self.build_round_actions()
        self.next_action()

    def build_round_actions(self):
        if self.pending_result is not None:
            raise RuntimeError('Save the previous hand before dealing again')
        if self.session_settled:
            self.session_id = uuid4().hex
            self.session_settled = False
            self.target_reached = False
            self.game.points = {p.name: 0 for p in self.game.players}
        self.round_id = uuid4().hex
        self.cpu_history = ()
        self.discards = []
        self.hidden_cards = {self.p1.name: [], self.p2.name: []}
        self.current_round_num = 1
        # Reset players for new round
        self.game.deck = Game(self.game.players).deck # New deck
        for p in self.game.players:
            p.top, p.mid, p.bot = [], [], []
            p.is_foul = False
            p.fantasyland = p.next_fantasyland
            if p.fantasyland:
                p.fantasyland_cards = p.next_fantasyland_cards
            p.next_fantasyland, p.next_fantasyland_cards = False, 0
            
        self.actions = []
        normal_players = [p for p in self.game.players if not p.fantasyland]
        fl_players = [p for p in self.game.players if p.fantasyland]
        
        # Normal turns
        if normal_players:
            for p in normal_players:
                self.actions.append({'type':'turn', 'player':p, 'deal':5, 'place':5, 'round': 1})
                
            for r in range(2, 6):
                for p in normal_players:
                    self.actions.append({'type':'turn', 'player':p, 'deal':3, 'place':2, 'round': r})
                    
        # Fantasyland turns play last
        for p in fl_players:
            self.actions.append({'type':'turn', 'player':p, 'deal':p.fantasyland_cards, 'place':13, 'round': 6})
                    
        self.actions.append({'type':'eval'})

    def next_action(self):
        if not self.actions:
            return
        
        self.current_action = self.actions.pop(0)
        self.placed_this_turn = []
        self.selected_card = None
        self.hand_sort_descending = None
        self.hand_sort_mode = None
        self.btn_sort.text = 'Rank: 2 -> A'
        
        if self.current_action['type'] == 'turn':
            action_round = self.current_action.get('round', 1)
            if action_round != self.current_round_num:
                self.current_round_num = action_round
                # Round changed! Sort boards so cards group properly now that they are revealed
                from collections import Counter
                for p in self.game.players:
                    for row in [p.top, p.mid, p.bot]:
                        counts = Counter(c.value for c in row)
                        row.sort(key=lambda c: (counts[c.value], c.value), reverse=True)
                
                # Reveal all cards
                for name in self.hidden_cards:
                    self.hidden_cards[name] = []
                    
            player = self.current_action['player']
            deal_count = self.current_action['deal']
            self.cards_in_hand = self.game.deal_cards(player, deal_count)
            self.waiting_for_turn_start = not self.is_cpu_turn()
            if self.is_cpu_turn():
                self.start_cpu()
        elif self.current_action['type'] == 'eval':
            # Final sort before showing results
            from collections import Counter
            for p in self.game.players:
                for row in [p.top, p.mid, p.bot]:
                    counts = Counter(c.value for c in row)
                    row.sort(key=lambda c: (counts[c.value], c.value), reverse=True)
                    
            self.show_results = True
            before = [self.game.points[p.name] for p in self.game.players]
            self.results_text = self.game.resolve_scores()
            self.target_reached = self.target_reached or any(abs(v) >= 100 for v in self.game.points.values())
            self.session_settled = self.target_reached and can_settle([p.next_fantasyland for p in self.game.players])
            self.btn_next.text = 'メニューへ' if self.session_settled else '次のハンド'
            if self.profile_store is not None and any(self.profile_ids):
                points = [self.game.points[p.name]-previous for p,previous in zip(self.game.players,before)]
                self.pending_result = round_event(self.round_id, self.session_id,
                    'cpu' if self.difficulty else 'pvp', self.profile_ids,
                    self.game.players, points, self.session_settled)
                self.pending_result['coin_match'] = True
                self.save_result()

    def save_result(self):
        if self.pending_result is None:
            return
        try:
            self.profile_store.record_round(self.pending_result)
        except (sqlite3.Error, OSError) as error:
            self.save_error = str(error)
            return
        self.pending_result = None
        self.save_error = None

    def is_cpu_turn(self):
        return bool(self.difficulty and self.current_action and
                    self.current_action.get('type') == 'turn' and
                    self.current_action['player'] is self.p2)

    def cpu_observation(self):
        return Observation(
            board_of(self.p2), tuple(encode(c) for c in self.cards_in_hand),
            board_of(self.p1, self.hidden_cards[self.p1.name]), tuple(self.discards),
            self.p2.fantasyland_cards if self.p2.fantasyland else 0,
            self.p1.fantasyland_cards if self.p1.fantasyland else 0)

    def start_cpu(self):
        self.cpu_error = None
        self.cpu_started = time.monotonic()
        try:
            if self.executor is None:
                self.executor = ProcessPoolExecutor(max_workers=1, mp_context=multiprocessing.get_context('spawn'))
            if self.difficulty == 'learned':
                from chinesepoker.ai.learned import choose_learned
                self.cpu_future = self.executor.submit(choose_learned, self.cpu_observation(),
                    self.strategy_path, self.cpu_history, 1,
                    not (self.p1.fantasyland or self.p2.fantasyland))
            else:
                self.cpu_future = self.executor.submit(choose_move, self.cpu_observation(), self.difficulty)
        except Exception as error:
            self.cpu_error = str(error)

    def update_cpu(self):
        if not self.cpu_future or not self.cpu_future.done():
            return
        future, self.cpu_future = self.cpu_future, None
        try:
            decision = future.result()
            observation = self.cpu_observation()
            hand = {encode(c): c for c in self.cards_in_hand}
            apply_move(self.p2, self.cards_in_hand, decision.move)
            self.cpu_history += ((observation_data(observation), move_data(decision.move)),)
            self.hidden_cards[self.p2.name].extend(hand[c] for c, _ in decision.move.placements)
            self.discards.extend(decision.move.discards)
            self.last_cpu_decision = decision
        except Exception as error:
            self.cpu_error = str(error)
            return
        self.next_action()

    def close(self):
        if self.executor is not None:
            self.executor.shutdown(wait=False, cancel_futures=True)
            self.executor = None

    def can_return_to_menu(self):
        if self.pending_result is not None:
            return False
        rights = [p.next_fantasyland if self.show_results else p.fantasyland for p in (self.p1,self.p2)]
        return can_settle(rights)

    def get_row_rects(self, player_idx):
        # Returns dict of rects for top, mid, bot for a player
        # p1 (left), p2 (right)
        base_x = 50 if player_idx == 0 else 700
        base_y = 100
        
        rects = {}
        # Top (3 cards), offset by 1 card width
        rects['top'] = [pygame.Rect(base_x + (i+1)*(CARD_W+10), base_y, CARD_W, CARD_H) for i in range(3)]
        # Mid (5 cards)
        rects['mid'] = [pygame.Rect(base_x + i*(CARD_W+10), base_y + CARD_H + 10, CARD_W, CARD_H) for i in range(5)]
        # Bot (5 cards)
        rects['bot'] = [pygame.Rect(base_x + i*(CARD_W+10), base_y + 2*(CARD_H + 10), CARD_W, CARD_H) for i in range(5)]
        return rects

    def handle_click(self, pos):
        if self.show_results or self.waiting_for_turn_start or self.is_cpu_turn():
            return

        if self.current_action['type'] != 'turn':
            return
            
        player = self.current_action['player']
        place_req = self.current_action['place']
        self.btn_sort.rect.x = 50 if player is self.p1 else 700
        self.btn_sort_suit.rect.x = self.btn_sort.rect.x + 200
        if player.fantasyland and self.btn_sort.rect.collidepoint(pos):
            self.hand_sort_descending = not self.hand_sort_descending if self.hand_sort_mode == 'rank' else False
            self.hand_sort_mode = 'rank'
            self.sort_hand()
            self.btn_sort.text = 'Rank: 2 -> A' if self.hand_sort_descending else 'Rank: A -> 2'
            return
        if player.fantasyland and self.btn_sort_suit.rect.collidepoint(pos):
            self.hand_sort_mode = 'suit'
            self.hand_sort_descending = None
            self.btn_sort.text = 'Rank: 2 -> A'
            self.sort_hand()
            return
        
        # Check clicking cards in hand
        p_idx = 0 if player == self.p1 else 1
        hand_start_x = 50 if p_idx == 0 else 700
        hand_start_y = 480
        for i, card in enumerate(self.cards_in_hand):
            row_offset = i // 5
            col_offset = i % 5
            rect = pygame.Rect(hand_start_x + col_offset*(CARD_W+10), hand_start_y + row_offset*(CARD_H+10), CARD_W, CARD_H)
            if rect.collidepoint(pos):
                if self.selected_card == card:
                    self.selected_card = None # deselect
                else:
                    self.selected_card = card
                return

        # Check clicking cards placed THIS turn to move them back or select them
        # Actually easier: click a placed_this_turn card to pick it up back to hand
        p_idx = 0 if player == self.p1 else 1
        row_rects = self.get_row_rects(p_idx)
        
        # Check placing selected card or picking up
        for row_name, rect_list in row_rects.items():
            row_cards = getattr(player, row_name)
            for i, rect in enumerate(rect_list):
                if rect.collidepoint(pos):
                    # If clicking an existing card placed this turn, select it (pick up)
                    if i < len(row_cards):
                        clicked_card = row_cards[i]
                        if clicked_card in self.placed_this_turn:
                            # Pick it up
                            row_cards.remove(clicked_card)
                            self.placed_this_turn.remove(clicked_card)
                            self.cards_in_hand.append(clicked_card)
                            self.sort_hand()
                            self.selected_card = clicked_card
                    else:
                        # Empty slot, try to place selected card
                        if self.selected_card:
                            # Must place in the next available slot of that row, which is len(row_cards)
                            if len(row_cards) < (3 if row_name == 'top' else 5):
                                if len(self.placed_this_turn) < place_req:
                                    if self.selected_card in self.cards_in_hand:
                                        self.cards_in_hand.remove(self.selected_card)
                                    row_cards.append(self.selected_card)
                                    self.placed_this_turn.append(self.selected_card)
                                    self.selected_card = None
                    return

    def sort_hand(self):
        if self.hand_sort_mode == 'suit':
            self.cards_in_hand.sort(key=lambda c: (c.SUITS.index(c.suit), c.value))
        elif self.hand_sort_mode == 'rank':
            self.cards_in_hand.sort(key=lambda c: (
                -c.value if self.hand_sort_descending else c.value, c.SUITS.index(c.suit)))

    def draw(self, surface):
        surface.fill(BG_COLOR)
        
        # Draw boards
        for idx, p in enumerate(self.game.players):
            row_rects = self.get_row_rects(idx)
            base_x = 50 if idx == 0 else 700
            
            # Draw player name and score
            name = self.display_names[idx]
            while font.size(name)[0] > 290:
                name = name[:-2] + '…'
            draw_text(surface, f"{name}  {self.game.points[p.name]:+d}pt", font, WHITE, base_x, 60)
            if p.fantasyland:
                draw_text(surface, "FANTASYLAND", font, GOLD, base_x, 30)
                
            for row_name in ['top', 'mid', 'bot']:
                rects = row_rects[row_name]
                cards = getattr(p, row_name)
                for i, rect in enumerate(rects):
                    # Outline
                    pygame.draw.rect(surface, (50, 120, 70), rect, 2, border_radius=5)
                    if i < len(cards):
                        c = cards[i]
                        
                        # Hide cards placed in current round if it's not this player's turn
                        is_active_player = (self.current_action and self.current_action.get('type') == 'turn' and self.current_action['player'] == p)
                        
                        if not self.show_results and not is_active_player and c in self.hidden_cards[p.name]:
                            # Transparent (do not draw the card or its back) to completely hide placement position
                            pass
                        else:
                            img_key = f"{c.suit}{c.rank}"
                            if img_key in card_images:
                                surface.blit(card_images[img_key], rect)
                        # Highlight if placed this turn
                        if c in self.placed_this_turn:
                            pygame.draw.rect(surface, GOLD, rect, 3, border_radius=5)

        if self.show_results:
            # Draw results overlay
            overlay = pygame.Surface((WIDTH, HEIGHT))
            overlay.set_alpha(200)
            overlay.fill(BLACK)
            surface.blit(overlay, (0,0))
            
            draw_text(surface, f"End of Round {self.game_round}", large_font, WHITE, WIDTH//2, 100, align="center")
            
            # Split results by newline
            y = 160
            for line in self.results_text.split('\n'):
                draw_text(surface, line, mono_font, WHITE, WIDTH//2 - 180, y, align="left")
                y += 35
                    
            score = self.game.points[self.p1.name]
            status = ('対局終了：勝ち +100コイン' if score > 0 else '対局終了：負け -100コイン' if score < 0 else '対局終了：引分 0コイン') if self.session_settled else ('100点到達：両者のFL終了まで継続' if self.target_reached else '累計 +100 / -100点で終了（FL中は継続）')
            draw_text(surface, status, font, GOLD, WIDTH//2, 640, align='center')
            if self.save_error:
                draw_text(surface, '成績を保存できません。Rキーで再試行してください。', font, RED,
                          WIDTH//2, 715, align='center')
            else:
                if any(self.profile_ids):
                    draw_text(surface, 'アカウントに成績を保存しました', font, GOLD, WIDTH//2, 715, align='center')
                self.btn_next.draw(surface)
            return

        if self.is_cpu_turn():
            message = ("CPU error: press R to retry or Esc for menu" if self.cpu_error else
                       "CPU thinking...")
            draw_text(surface, message, font, GOLD, WIDTH // 2, 500, align="center")
            draw_text(surface, "Your opponent's hand stays hidden", font, WHITE, WIDTH // 2, 550, align="center")
            return

        # Draw current turn info
        if self.current_action and self.current_action['type'] == 'turn':
            player = self.current_action['player']
            req = self.current_action['place']
            
            if self.waiting_for_turn_start:
                overlay = pygame.Surface((WIDTH, HEIGHT))
                overlay.set_alpha(200)
                overlay.fill(BLACK)
                surface.blit(overlay, (0,0))
                
                msg = f"{player.name}'s Turn"
                if player.fantasyland:
                    msg += " (FANTASYLAND)"
                draw_text(surface, msg, large_font, GOLD, WIDTH//2, HEIGHT//2 - 30, align="center")
                draw_text(surface, "Click anywhere to start and reveal your cards", font, WHITE, WIDTH//2, HEIGHT//2 + 30, align="center")
                return

            # Display Turn Info in top center to avoid overlapping with Player 2's Fantasyland text
            draw_text(surface, f"Turn: {player.name} | Need to place: {req - len(self.placed_this_turn)} more", font, GOLD, WIDTH // 2, 20, align="center")
            
            # Draw hand
            p_idx = 0 if player == self.p1 else 1
            hand_start_x = 50 if p_idx == 0 else 700
            hand_start_y = 480
            if player.fantasyland:
                self.btn_sort.rect.x = hand_start_x
                self.btn_sort_suit.rect.x = hand_start_x + 200
                self.btn_sort.draw(surface)
                self.btn_sort_suit.draw(surface)
            for i, card in enumerate(self.cards_in_hand):
                row_offset = i // 5
                col_offset = i % 5
                rect = pygame.Rect(hand_start_x + col_offset*(CARD_W+10), hand_start_y + row_offset*(CARD_H+10), CARD_W, CARD_H)
                img_key = f"{card.suit}{card.rank}"
                if img_key in card_images:
                    surface.blit(card_images[img_key], rect)
                if card == self.selected_card:
                    pygame.draw.rect(surface, RED, rect, 4, border_radius=5)
                    
            if len(self.placed_this_turn) == req:
                self.btn_confirm.draw(surface)

def menu_buttons(strategy_path=None, other_cpus=False):
    if other_cpus and features.LEGACY_CPUS_ENABLED:
        choices = [('CPU - Easy', 'easy'), ('CPU - Normal', 'normal'),
                   ('CPU - Hard', 'hard'), ('CPU - Hybrid (test)', 'hybrid'),
                   ('CPU - Adaptive (test)', 'adaptive')]
        if strategy_path:
            choices.append(('CPU - Learned (test)', 'learned'))
        choices.append(('Back', 'back'))
    else:
        choices = [('Play vs CPU', 'expectimax'), ('Two players', None)]
        if features.LEGACY_CPUS_ENABLED:
            choices.append(('Other CPUs', 'other_cpus'))
    return [(Button(WIDTH // 2 - 165, 300 + i * 75, 330, 60, label,
                       (0, 110, 160), (0, 145, 200)), level) for i, (label, level) in enumerate(choices)]


def draw_menu(surface, buttons, other_cpus=False):
    surface.fill(BG_COLOR)
    draw_text(surface, "Pineapple OFC", large_font, GOLD, WIDTH // 2, 180, align="center")
    draw_text(surface, 'Other CPUs' if other_cpus else 'CPU: Expectimax', font, WHITE, WIDTH // 2, 240, align="center")
    for button, _ in buttons:
        button.draw(surface)


def main(strategy_path=None):
    from chinesepoker.ui.accounts import AccountMenu
    store, storage_error = None, None
    try:
        store = ProfileStore()
        store.ensure_test_profiles()
    except (sqlite3.Error, OSError) as error:
        storage_error = str(error)
        if store:
            store.close()
            store = None
    accounts = AccountMenu(store, storage_error)
    gui = None
    other_cpus = False
    buttons = menu_buttons(strategy_path)
    running = True
    try:
        while running:
            for event in pygame.event.get():
                if event.type == pygame.QUIT:
                    running = False
                    continue
                if gui is None and (accounts.page != 'home' or not other_cpus) and accounts.handle_event(event):
                    continue
                if event.type == pygame.KEYDOWN and event.key == pygame.K_ESCAPE and gui:
                    if gui.can_return_to_menu():
                        gui.close()
                        gui = None
                        accounts.refresh_wallets()
                        other_cpus = False
                        buttons = menu_buttons(strategy_path)
                    continue
                if event.type == pygame.KEYDOWN and event.key == pygame.K_ESCAPE and gui is None:
                    other_cpus = False
                    buttons = menu_buttons(strategy_path)
                if gui and event.type == pygame.KEYDOWN and event.key == pygame.K_r and gui.cpu_error:
                    gui.close()
                    gui.start_cpu()
                if gui and event.type == pygame.KEYDOWN and event.key == pygame.K_r and gui.save_error:
                    gui.save_result()
                if event.type != pygame.MOUSEBUTTONDOWN or event.button != 1:
                    continue
                if gui is None:
                    for button, level in buttons:
                        if button.is_clicked(event):
                            if level in ('other_cpus', 'back'):
                                other_cpus = level == 'other_cpus'
                                buttons = menu_buttons(strategy_path, other_cpus)
                            else:
                                seats = (0,) if level else (0,1)
                                try:
                                    if store is None or any(accounts.selected[i] is None for i in seats):
                                        accounts.message = 'アカウントを選んでから開始してください。'
                                        if store:
                                            accounts.open_profiles(next(i for i in seats if accounts.selected[i] is None))
                                        break
                                    if any(store.balance(accounts.selected[i]) < 100 for i in seats):
                                        accounts.message = '開始には各アカウント100コイン以上が必要です。'
                                        break
                                    gui = GameGUI(level, strategy_path=strategy_path,
                                                  profile_store=store, profile_ids=accounts.selected)
                                except (sqlite3.Error, OSError) as error:
                                    accounts.message = '保存データを読み込めません。再度お試しください。' 
                            break
                elif gui.is_cpu_turn():
                    continue
                elif gui.show_results:
                    if not gui.save_error and gui.btn_next.is_clicked(event):
                        if gui.session_settled:
                            gui.close()
                            gui = None
                            accounts.refresh_wallets()
                            continue
                        gui.show_results = False
                        gui.game_round += 1
                        gui.build_round_actions()
                        gui.next_action()
                elif gui.current_action and gui.current_action['type'] == 'turn':
                    if gui.waiting_for_turn_start:
                        gui.waiting_for_turn_start = False
                    else:
                        req = gui.current_action['place']
                        if len(gui.placed_this_turn) == req and gui.btn_confirm.is_clicked(event):
                            player = gui.current_action['player']
                            gui.hidden_cards[player.name].extend(gui.placed_this_turn)
                            gui.next_action()
                        else:
                            gui.handle_click(event.pos)
            if not running:
                break
            if gui:
                gui.update_cpu()
                gui.draw(screen)
                help_text = ('R: retry saving results' if gui.save_error else
                             'Esc: menu' if gui.can_return_to_menu() else 'FL active: continue until both players leave Fantasyland')
                draw_text(screen, help_text, font, WHITE, 15, HEIGHT - 40)
            else:
                if accounts.page == 'home':
                    draw_menu(screen, buttons, other_cpus)
                    if not other_cpus:
                        accounts.draw_home(screen)
                else:
                    accounts.draw(screen)
            pygame.display.flip()
            clock.tick(FPS)
    finally:
        if gui:
            gui.close()
        if store:
            store.close()
        pygame.quit()


def smoke_test():
    """Verify bundled assets and initial drawing without a game loop."""
    if len(card_images) != 53:
        raise RuntimeError(f'Expected 53 bundled images, loaded {len(card_images)}')
    gui = GameGUI()
    gui.waiting_for_turn_start = False
    gui.draw(screen)
    pygame.quit()


def cpu_smoke_test(strategy_path=None, difficulty='expectimax', profile_store=None, profile_ids=(None,None)):
    """Exercise the real spawned worker, turn transitions and bundled images."""
    if len(card_images) != 53:
        raise RuntimeError('Missing bundled images')
    gui = GameGUI('learned' if strategy_path else difficulty, strategy_path=strategy_path,
                  profile_store=profile_store, profile_ids=profile_ids)
    deadline = time.monotonic() + 120
    hybrid_used = False
    adaptive_used = False
    try:
        while not gui.show_results:
            if time.monotonic() > deadline:
                raise RuntimeError('CPU smoke test timed out')
            if gui.cpu_error:
                raise RuntimeError(gui.cpu_error)
            if gui.is_cpu_turn():
                gui.update_cpu()
                if gui.last_cpu_decision and 'generalized session-value' in gui.last_cpu_decision.method:
                    hybrid_used = True
                if gui.last_cpu_decision and 'learned action advantages' in gui.last_cpu_decision.method:
                    adaptive_used = True
            else:
                observation = Observation(board_of(gui.p1), tuple(encode(c) for c in gui.cards_in_hand))
                decision = choose_move(observation, 'easy', seed=0)
                cards = {encode(c): c for c in gui.cards_in_hand}
                apply_move(gui.p1, gui.cards_in_hand, decision.move)
                gui.hidden_cards[gui.p1.name].extend(cards[c] for c, _ in decision.move.placements)
                gui.next_action()
            gui.draw(screen)
            pygame.event.pump()
            time.sleep(0.005)
        if gui.p1.count_cards() != 13 or gui.p2.count_cards() != 13:
            raise RuntimeError('Incomplete CPU round')
        if not gui.last_cpu_decision:
            raise RuntimeError('CPU did not act')
        if gui.save_error:
            raise RuntimeError('Profile save failed: '+gui.save_error)
        if len(gui.cpu_history) != 5:
            raise RuntimeError('Incomplete CPU observation history')
        if strategy_path and not gui.last_cpu_decision.method.startswith(('MCCFR average', 'Normal fallback')):
            raise RuntimeError('Saved-policy adapter was not used')
        if difficulty == 'hybrid' and not strategy_path and not hybrid_used:
            raise RuntimeError('Bundled generalized value model was not used')
        if difficulty == 'adaptive' and not strategy_path and not adaptive_used:
            raise RuntimeError('Bundled nonlinear action model was not used')
        if difficulty == 'expectimax' and not strategy_path and not gui.last_cpu_decision.method.startswith('expectimax'):
            raise RuntimeError('Expectimax planner was not used')
    finally:
        if gui.executor:
            gui.executor.shutdown(wait=True, cancel_futures=True)
            gui.executor = None
        pygame.quit()


def profile_smoke_test():
    """Exercise bundled SQLite, profile screens, worker and persistence in a temporary DB."""
    import tempfile
    from pathlib import Path
    from chinesepoker.ui.accounts import AccountMenu
    with tempfile.TemporaryDirectory() as folder:
        path = Path(folder)/'profiles.sqlite3'
        store = ProfileStore(path)
        try:
            store.ensure_test_profiles()
            ident = 'starter-1'
            store.select(0,ident)
            menu = AccountMenu(store)
            if store.balance(ident) != 1050:
                raise RuntimeError('Starter wallet or daily bonus failed')
            menu.draw_home(screen)
            menu.open_profiles(0)
            menu.draw(screen)
            menu.open_stats(0)
            menu.draw(screen)
            cpu_smoke_test(profile_store=store,profile_ids=(ident,None))
            if store.stats(ident,'cpu')['hands'] != 1:
                raise RuntimeError('Completed hand was not saved')
        finally:
            store.close()
        reopened = ProfileStore(path)
        try:
            if reopened.selected()[0] != ident or reopened.stats(ident,'cpu')['hands'] != 1:
                raise RuntimeError('Profile persistence failed')
        finally:
            reopened.close()


if __name__ == "__main__":
    if '--smoke-test' in sys.argv:
        smoke_test()
    else:
        main()
