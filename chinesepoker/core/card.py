import random

class Card:
    SUITS = ('S', 'H', 'D', 'C')
    RANKS = ('2', '3', '4', '5', '6', '7', '8', '9', '10', 'J', 'Q', 'K', 'A')

    def __init__(self, suit, rank):
        suit = {'♠': 'S', '♥': 'H', '♦': 'D', '♣': 'C'}.get(suit, suit)
        suit = suit.upper()
        rank = rank.upper()
        rank = '10' if rank == 'T' else rank
        if suit not in self.SUITS:
            raise ValueError(f"Invalid suit: {suit}")
        if rank not in self.RANKS:
            raise ValueError(f"Invalid rank: {rank}")
        self.suit = suit
        self.rank = rank

    @property
    def value(self):
        return self.RANKS.index(self.rank) + 2

    def __repr__(self):
        return f"{self.suit}{self.rank}"

    def __eq__(self, other):
        if not isinstance(other, Card):
            return False
        return self.suit == other.suit and self.rank == other.rank

    def __hash__(self):
        return hash((self.suit, self.rank))

class Deck:
    def __init__(self):
        self.cards = [Card(suit, rank) for suit in Card.SUITS for rank in Card.RANKS]
        self.shuffle()

    def shuffle(self):
        random.shuffle(self.cards)

    def draw(self, count=1):
        if count > len(self.cards):
            raise ValueError("Not enough cards in deck")
        drawn = self.cards[:count]
        self.cards = self.cards[count:]
        return drawn

    def __len__(self):
        return len(self.cards)
