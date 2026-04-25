from card import Deck
from evaluator import evaluate_hand, compare_hands, get_hand_name

class Game:
    def __init__(self, players):
        self.players = players
        self.deck = Deck()
        self.points = {p.name: 0 for p in players}

    def deal_cards(self, player, count):
        return self.deck.draw(count)

    def calculate_matchup(self, p1, p2):
        if p1.is_foul and p2.is_foul:
            return 0, 0
            
        if p1.is_foul:
            # If p1 busts, p2 gets 1 point per row (3) + scoop (3) = 6 points
            return -6, 6
            
        if p2.is_foul:
            # If p2 busts, p1 gets 6 points
            return 6, -6
            
        # Normal comparison
        p1_wins = 0
        p2_wins = 0
        
        # Top
        top_cmp = compare_hands(evaluate_hand(p1.top), evaluate_hand(p2.top))
        if top_cmp > 0: p1_wins += 1
        elif top_cmp < 0: p2_wins += 1
        
        # Mid
        mid_cmp = compare_hands(evaluate_hand(p1.mid), evaluate_hand(p2.mid))
        if mid_cmp > 0: p1_wins += 1
        elif mid_cmp < 0: p2_wins += 1
        
        # Bot
        bot_cmp = compare_hands(evaluate_hand(p1.bot), evaluate_hand(p2.bot))
        if bot_cmp > 0: p1_wins += 1
        elif bot_cmp < 0: p2_wins += 1
        
        score_diff = p1_wins - p2_wins
        
        # Scoop
        if p1_wins == 3 and p2_wins == 0:
            score_diff += 3
        elif p2_wins == 3 and p1_wins == 0:
            score_diff -= 3
            
        return score_diff, -score_diff

    def resolve_scores(self):
        # Evaluate validities and fantasies
        for p in self.players:
            p.evaluate_board()
            
        results = ""
        # 1-on-1 matchups
        for i in range(len(self.players)):
            for j in range(i + 1, len(self.players)):
                p1 = self.players[i]
                p2 = self.players[j]
                
                # Matchup & Scoop
                p1_score, p2_score = self.calculate_matchup(p1, p2)
                
                # Row calculations for display
                def calc_row(row_name):
                    r1 = p1.get_row_royalty(row_name)
                    r2 = p2.get_row_royalty(row_name)
                    m1, m2 = 0, 0
                    if not p1.is_foul and not p2.is_foul:
                        eval1 = evaluate_hand(getattr(p1, row_name))
                        eval2 = evaluate_hand(getattr(p2, row_name))
                        cmp = compare_hands(eval1, eval2)
                        if cmp > 0: m1, m2 = 1, -1
                        elif cmp < 0: m1, m2 = -1, 1
                    elif not p1.is_foul and p2.is_foul:
                        m1, m2 = 1, -1
                    elif p1.is_foul and not p2.is_foul:
                        m1, m2 = -1, 1
                        
                    # Format e.g., "1pt+2pt"
                    def fmt(m, r):
                        res = f"{m}pt"
                        if r > 0: res += f"+{r}pt"
                        elif r < 0: res += f"{r}pt"
                        return res
                        
                    return fmt(m1, r1), fmt(m2, r2), m1, m2
                
                top1, top2, tm1, tm2 = calc_row('top')
                mid1, mid2, mm1, mm2 = calc_row('mid')
                bot1, bot2, bm1, bm2 = calc_row('bot')
                
                # Scoop
                p1_wins = sum(1 for m in [tm1, mm1, bm1] if m > 0)
                p2_wins = sum(1 for m in [tm2, mm2, bm2] if m > 0)
                s1, s2 = 0, 0
                if p1_wins == 3 and not p1.is_foul: s1, s2 = 3, -3
                if p2_wins == 3 and not p2.is_foul: s1, s2 = -3, 3
                if p1.is_foul and not p2.is_foul: s1, s2 = -3, 3
                if p2.is_foul and not p1.is_foul: s1, s2 = 3, -3
                
                scoop1 = f"{s1}pt" if s1 else "0pt"
                scoop2 = f"{s2}pt" if s2 else "0pt"
                
                r1 = p1.get_royalties()
                r2 = p2.get_royalties()
                
                p1_total = p1_score + (r1 - r2)
                p2_total = p2_score + (r2 - r1)
                
                self.points[p1.name] += p1_total
                self.points[p2.name] += p2_total
                
                results += f"       {p1.name}  vs  {p2.name}\n"
                results += f"top    {top1:<12} {top2}\n"
                results += f"mid    {mid1:<12} {mid2}\n"
                results += f"bot    {bot1:<12} {bot2}\n"
                results += f"scoop  {scoop1:<12} {scoop2}\n"
                results += f"total  {str(p1_total)+'pt':<12} {str(p2_total)+'pt'}\n"
                
                results += "\n"
                for p in [p1, p2]:
                    if p.is_foul:
                        results += f"{p.name}: burst!\n"
                    elif p.next_fantasyland:
                        if p.next_fantasyland_cards == 14:
                            results += f"{p.name}: Q Fantasyland!\n"
                        elif p.next_fantasyland_cards == 15:
                            results += f"{p.name}: K Fantasyland!\n"
                        elif p.next_fantasyland_cards == 16:
                            results += f"{p.name}: A Fantasyland!\n"
                        elif p.next_fantasyland_cards >= 17:
                            results += f"{p.name}: Trips Fantasyland!\n"
                
        return results
