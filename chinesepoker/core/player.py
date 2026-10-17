from chinesepoker.core.evaluator import evaluate_hand, check_validity, HandRank

class Player:
    def __init__(self, name):
        self.name = name
        self.top = []     # Max 3
        self.mid = []     # Max 5
        self.bot = []     # Max 5
        self.fantasyland = False
        self.fantasyland_cards = 0
        self.next_fantasyland = False
        self.next_fantasyland_cards = 0
        self.is_foul = False

    def place_card(self, row, card):
        if row == 'top':
            if len(self.top) >= 3: return False
            self.top.append(card)
        elif row == 'mid':
            if len(self.mid) >= 5: return False
            self.mid.append(card)
        elif row == 'bot':
            if len(self.bot) >= 5: return False
            self.bot.append(card)
        else:
            return False
        return True

    def evaluate_board(self):
        if len(self.top) != 3 or len(self.mid) != 5 or len(self.bot) != 5:
            self.is_foul = True
            return

        self.is_foul = not check_validity(self.top, self.mid, self.bot)
        
        self.next_fantasyland = False
        self.next_fantasyland_cards = 0
        
        # Check for fantasyland (not foul)
        if not self.is_foul:
            top_eval = evaluate_hand(self.top)
            mid_eval = evaluate_hand(self.mid)
            bot_eval = evaluate_hand(self.bot)
            
            fl_cards = 0
            if top_eval[0] >= HandRank.THREE_OF_A_KIND:
                fl_cards = 17
            elif top_eval[0] == HandRank.PAIR:
                rank_val = top_eval[1][0]
                if rank_val == 14: # A
                    fl_cards = 16
                elif rank_val == 13: # K
                    fl_cards = 15
                elif rank_val == 12: # Q
                    fl_cards = 14
                    
            if self.fantasyland:
                # To stay in FL: Set on top, Full house on mid, or Quads on bot
                stays = False
                if top_eval[0] >= HandRank.THREE_OF_A_KIND:
                    stays = True
                elif mid_eval[0] >= HandRank.FULL_HOUSE:
                    stays = True
                elif bot_eval[0] >= HandRank.FOUR_OF_A_KIND:
                    stays = True
                    
                if stays:
                    self.next_fantasyland = True
                    # Strictly maintain the current Fantasyland tier; no upgrades
                    self.next_fantasyland_cards = self.fantasyland_cards
            else:
                if fl_cards >= 14:
                    self.next_fantasyland = True
                    self.next_fantasyland_cards = fl_cards

    def get_row_royalty(self, row_name):
        if self.is_foul: return 0
        points = 0
        if row_name == 'bot':
            bot_eval = evaluate_hand(self.bot)
            bot_rank = bot_eval[0]
            if bot_rank == HandRank.STRAIGHT: points += 2
            elif bot_rank == HandRank.FLUSH: points += 4
            elif bot_rank == HandRank.FULL_HOUSE: points += 6
            elif bot_rank == HandRank.FOUR_OF_A_KIND: points += 10
            elif bot_rank == HandRank.STRAIGHT_FLUSH: points += 15
            elif bot_rank == HandRank.ROYAL_FLUSH: points += 25
        elif row_name == 'mid':
            mid_eval = evaluate_hand(self.mid)
            mid_rank = mid_eval[0]
            if mid_rank == HandRank.THREE_OF_A_KIND: points += 2
            elif mid_rank == HandRank.STRAIGHT: points += 4
            elif mid_rank == HandRank.FLUSH: points += 8
            elif mid_rank == HandRank.FULL_HOUSE: points += 12
            elif mid_rank == HandRank.FOUR_OF_A_KIND: points += 20
            elif mid_rank == HandRank.STRAIGHT_FLUSH: points += 30
            elif mid_rank == HandRank.ROYAL_FLUSH: points += 50
        elif row_name == 'top':
            top_eval = evaluate_hand(self.top)
            top_rank = top_eval[0]
            top_val = top_eval[1][0]
            if top_rank == HandRank.PAIR:
                if top_val >= 6: points += (top_val - 5)
            elif top_rank == HandRank.THREE_OF_A_KIND:
                points += (top_val + 8)
        return points

    def get_royalties(self):
        return self.get_row_royalty('top') + self.get_row_royalty('mid') + self.get_row_royalty('bot')

    def count_cards(self):
        return len(self.top) + len(self.mid) + len(self.bot)

    def print_board(self):
        # Format the board
        top_str = " ".join([str(c) for c in self.top]) + "  (3)"
        mid_str = " ".join([str(c) for c in self.mid]) + "  (5)"
        bot_str = " ".join([str(c) for c in self.bot]) + "  (5)"
        print(f"--- {self.name}'s Board ---")
        print(f"Top: {top_str}")
        print(f"Mid: {mid_str}")
        print(f"Bot: {bot_str}")
        print("-----------------------")
