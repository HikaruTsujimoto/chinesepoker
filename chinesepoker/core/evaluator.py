from collections import Counter

class HandRank:
    HIGH_CARD = 0
    PAIR = 1
    TWO_PAIR = 2
    THREE_OF_A_KIND = 3
    STRAIGHT = 4
    FLUSH = 5
    FULL_HOUSE = 6
    FOUR_OF_A_KIND = 7
    STRAIGHT_FLUSH = 8
    ROYAL_FLUSH = 9

def evaluate_hand(cards):
    """
    Evaluates a poker hand (3 or 5 cards) and returns a tuple for comparison:
    (HandRank, [primary_values], [kicker_values])
    This allows easy comparison handling e.g. hand1 > hand2
    """
    if len(cards) not in (3, 5):
        raise ValueError(f"Hand must have exactly 3 or 5 cards. Got {len(cards)}")

    values = sorted([card.value for card in cards], reverse=True)
    suits = [card.suit for card in cards]
    
    value_counts = Counter(values)
    counts = sorted(value_counts.items(), key=lambda x: (x[1], x[0]), reverse=True)
    
    is_flush = len(cards) == 5 and len(set(suits)) == 1
    is_straight = False
    
    if len(cards) == 5:
        # Check normal straight
        if len(set(values)) == 5 and values[0] - values[4] == 4:
            is_straight = True
        # Check A, 5, 4, 3, 2 straight (values: 14, 5, 4, 3, 2)
        elif values == [14, 5, 4, 3, 2]:
            is_straight = True
            values = [5, 4, 3, 2, 1] # A acts as 1

    if is_flush and is_straight:
        if values[0] == 14:
            return (HandRank.ROYAL_FLUSH, [14], [])
        return (HandRank.STRAIGHT_FLUSH, [values[0]], [])
    
    if counts[0][1] == 4:
        return (HandRank.FOUR_OF_A_KIND, [counts[0][0]], [counts[1][0]])
        
    if counts[0][1] == 3 and len(counts) > 1 and counts[1][1] >= 2:
        return (HandRank.FULL_HOUSE, [counts[0][0], counts[1][0]], [])
        
    if is_flush:
        return (HandRank.FLUSH, values, [])
        
    if is_straight:
        return (HandRank.STRAIGHT, [values[0]], [])
        
    if counts[0][1] == 3:
        kickers = [val for val, count in counts[1:]]
        return (HandRank.THREE_OF_A_KIND, [counts[0][0]], kickers)
        
    if counts[0][1] == 2 and len(counts) > 1 and counts[1][1] == 2:
        kicker = counts[2][0] if len(counts) > 2 else 0
        return (HandRank.TWO_PAIR, [counts[0][0], counts[1][0]], [kicker])
        
    if counts[0][1] == 2:
        kickers = [val for val, count in counts[1:]]
        return (HandRank.PAIR, [counts[0][0]], kickers)
        
    return (HandRank.HIGH_CARD, values, [])

def compare_hands(hand1_eval, hand2_eval):
    """
    Compare two hand evaluations. 
    Returns:
    1 if hand1 > hand2
    -1 if hand1 < hand2
    0 if hand1 == hand2
    """
    if hand1_eval[0] > hand2_eval[0]: return 1
    if hand1_eval[0] < hand2_eval[0]: return -1
    
    # Same rank, compare primary values
    for v1, v2 in zip(hand1_eval[1], hand2_eval[1]):
        if v1 > v2: return 1
        if v1 < v2: return -1
        
    # Same primary values, compare kickers
    for v1, v2 in zip(hand1_eval[2], hand2_eval[2]):
        if v1 > v2: return 1
        if v1 < v2: return -1
        
    return 0

def check_validity(top_cards, mid_cards, bot_cards):
    """
    Check if the placement is valid (not a foul/bust).
    bot >= mid >= top
    Returns True if valid, False if foul.
    """
    top_eval = evaluate_hand(top_cards)
    mid_eval = evaluate_hand(mid_cards)
    bot_eval = evaluate_hand(bot_cards)
    
    cmp_bot_mid = compare_hands(bot_eval, mid_eval)
    cmp_mid_top = compare_hands(mid_eval, top_eval)
    
    if cmp_bot_mid < 0 or cmp_mid_top < 0:
        return False
    return True

def get_hand_name(hand_eval):
    names = {
        0: "High Card",
        1: "Pair",
        2: "Two Pair",
        3: "Three of a Kind",
        4: "Straight",
        5: "Flush",
        6: "Full House",
        7: "Four of a Kind",
        8: "Straight Flush",
        9: "Royal Flush"
    }
    return names.get(hand_eval[0], "Unknown")
