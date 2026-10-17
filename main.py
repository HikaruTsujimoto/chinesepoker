import os
from player import Player
from game import Game

def clear_screen():
    os.system('cls' if os.name == 'nt' else 'clear')

def prompt_placement(player, cards, count_to_place):
    placed_this_turn = []
    print(f"\n{player.name}'s turn. Please place {count_to_place} cards.")
    player.print_board()

    while True:
        cards_str = [str(c) for c in cards]
        print(f"Cards available: {', '.join(cards_str)}")

        if len(placed_this_turn) == count_to_place:
            print("You have placed all required cards. Type 'done' to finish, or '<card> <row>' to move a placed card.")
        else:
            print(f"Format: <card> <row> (e.g. H10 top). {count_to_place - len(placed_this_turn)} more to place.")

        try:
            user_input = input(">> ").strip().split()
            if not user_input:
                continue

            if user_input[0].lower() == 'done' and len(placed_this_turn) == count_to_place:
                break

            if len(user_input) != 2:
                print("Invalid input format. Use '<card> <row>' or 'done'.")
                continue

            card_name = user_input[0]
            row = user_input[1].lower()

            if row not in ('top', 'mid', 'bot'):
                print("Invalid row. Choose 'top', 'mid', or 'bot'.")
                continue

            # Check if card is in hand
            card_idx = -1
            for idx, c in enumerate(cards):
                if str(c).upper() == card_name.upper():
                    card_idx = idx
                    break

            if card_idx != -1:
                # Placing a new card from hand
                if len(placed_this_turn) >= count_to_place:
                    print(f"You can only place {count_to_place} cards. Move an existing card or type 'done'.")
                    continue

                card_to_place = cards[card_idx]
                if player.place_card(row, card_to_place):
                    cards.pop(card_idx)
                    placed_this_turn.append(card_to_place)
                    player.print_board()
                else:
                    print(f"Row '{row}' is full! Try another row.")
            else:
                # Check if card was placed this turn and can be moved
                placed_card = None
                for c in placed_this_turn:
                    if str(c).upper() == card_name.upper():
                        placed_card = c
                        break

                if placed_card:
                    # Find which row it is currently in
                    current_row = None
                    if placed_card in player.top: current_row = player.top
                    elif placed_card in player.mid: current_row = player.mid
                    elif placed_card in player.bot: current_row = player.bot

                    target_row_list = getattr(player, row)
                    max_len = 3 if row == 'top' else 5

                    if current_row != target_row_list and len(target_row_list) >= max_len:
                        print(f"Row '{row}' is full! Cannot move card.")
                        continue

                    if current_row != target_row_list:
                        current_row.remove(placed_card)
                        target_row_list.append(placed_card)
                        player.print_board()
                else:
                    print("Invalid card. Make sure you typed the card name correctly.")

        except EOFError:
            print("\nExiting.")
            exit(0)

    return placed_this_turn

def play_round(game):
    game.deck = Game(game.players).deck # reset deck
    for p in game.players:
        p.top = []
        p.mid = []
        p.bot = []
        p.is_foul = False
        p.fantasyland = p.next_fantasyland
        if p.fantasyland:
            p.fantasyland_cards = p.next_fantasyland_cards
        p.next_fantasyland = False
        p.next_fantasyland_cards = 0

    # 1. Normal players First deal (5 cards to each player)
    for p in game.players:
        if not p.fantasyland:
            clear_screen()
            input(f"Press Enter to start {p.name}'s turn...")
            cards = game.deal_cards(p, 5)
            prompt_placement(p, cards, 5)

    # 2. Normal players Subsequent deals (3 cards dealt, 2 placed, 1 discarded, 4 times)
    for round_num in range(1, 5):
        for p in game.players:
            if not p.fantasyland:
                clear_screen()
                input(f"\n--- Round {round_num}/4 --- Press Enter for {p.name}'s turn...")
                cards = game.deal_cards(p, 3)
                prompt_placement(p, cards, 2)
                # The remaining 1 card in `cards` is discarded.
                print(f"Discarding {cards[0]}")

    # 3. Fantasyland players act after all normal turns
    for p in game.players:
        if p.fantasyland:
            clear_screen()
            input(f"Press Enter to start {p.name}'s turn (FANTASYLAND - {p.fantasyland_cards} cards)...")
            cards = game.deal_cards(p, p.fantasyland_cards)
            prompt_placement(p, cards, 13)
            print(f"Discarding remaining {len(cards)} cards...")

    # Evaluate at end of round
    clear_screen()
    print("=== FINISHED ROUND ===")
    for p in game.players:
        p.print_board()

    results = game.resolve_scores()
    print("\n=== RESULTS ===")
    print(results)
    print("\n=== CURRENT SCORES ===")
    for name, score in game.points.items():
        print(f"{name}: {score}")

def main():
    print("Welcome to Pineapple Open Face Chinese Poker (Terminal Logic Edition)!")
    p1 = Player("Player 1")
    p2 = Player("Player 2")
    game = Game([p1, p2])

    round_number = 1
    while True:
        print(f"\n--- Starting Game Round {round_number} ---")
        play_round(game)

        in_fantasyland = any(p.next_fantasyland for p in game.players)
        if in_fantasyland:
            print("\nA player has entered/stayed in Fantasyland! The game must continue.")
            input("Press Enter to start the next round...")
        else:
            ans = input("\nPlay another round? (y/n): ").strip().lower()
            if ans != 'y':
                break

        round_number += 1

    print("\n=== FINAL SCORES ===")
    for name, score in game.points.items():
        print(f"{name}: {score}")
    print("Thanks for playing!")

if __name__ == "__main__":
    main()
