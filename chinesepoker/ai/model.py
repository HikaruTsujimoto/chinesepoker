"""Immutable, serializable information boundary between the game and CPU."""
from dataclasses import dataclass
from chinesepoker.core.card import Card

ROWS = ('top', 'mid', 'bot')
CAPACITY = (3, 5, 5)
EMPTY = ((), (), ())
CARDS = tuple(Card(s, r) for s in Card.SUITS for r in Card.RANKS)


def encode(card):
    return Card.SUITS.index(card.suit) * 13 + card.value - 2


def board_of(player, hidden=()):
    hidden = set(hidden)
    return tuple(tuple(sorted(encode(c) for c in getattr(player, row) if c not in hidden))
                 for row in ROWS)


@dataclass(frozen=True)
class Observation:
    board: tuple
    hand: tuple
    opponent: tuple = EMPTY
    discards: tuple = ()
    fantasyland_cards: int = 0

    def __post_init__(self):
        for board in (self.board, self.opponent):
            if len(board) != 3 or any(len(row) > cap for row, cap in zip(board, CAPACITY)):
                raise ValueError('Invalid board capacity')
        known = self.hand + self.discards + tuple(c for b in (self.board, self.opponent) for row in b for c in row)
        if any(not isinstance(c, int) or not 0 <= c < 52 for c in known) or len(known) != len(set(known)):
            raise ValueError('Duplicate or invalid visible cards')
        count = sum(map(len, self.board))
        if self.fantasyland_cards:
            if count or len(self.hand) != self.fantasyland_cards or self.fantasyland_cards not in (14, 15, 16, 17):
                raise ValueError('Invalid Fantasyland observation')
        elif not ((count == 0 and len(self.hand) == 5) or
                  (count in (5, 7, 9, 11) and len(self.hand) == 3)):
            raise ValueError('Invalid normal turn')

    @property
    def place_count(self):
        return 13 if self.fantasyland_cards else (5 if len(self.hand) == 5 else 2)

    def unseen(self):
        known = set(self.hand + self.discards)
        known.update(c for b in (self.board, self.opponent) for row in b for c in row)
        return tuple(c for c in range(52) if c not in known)


@dataclass(frozen=True)
class Move:
    placements: tuple  # (encoded card, row index)
    discards: tuple


@dataclass(frozen=True)
class Decision:
    move: Move
    candidates: int
    simulations: int
    seconds: float
    estimated_value: float
    method: str


def after_move(board, move):
    rows = [list(row) for row in board]
    for card, row in move.placements:
        rows[row].append(card)
    return tuple(tuple(sorted(row)) for row in rows)


def validate_move(observation, move):
    played = tuple(c for c, _ in move.placements)
    all_cards = played + move.discards
    if len(played) != observation.place_count or len(all_cards) != len(set(all_cards)) or set(all_cards) != set(observation.hand):
        raise ValueError('Move must place and discard exactly the dealt cards')
    if any(row not in (0, 1, 2) for _, row in move.placements):
        raise ValueError('Invalid row')
    board = after_move(observation.board, move)
    if any(len(row) > cap for row, cap in zip(board, CAPACITY)):
        raise ValueError('Move exceeds row capacity')
    return board


def apply_move(player, hand, move):
    """Validate everything before mutating any live game state."""
    observation = Observation(board_of(player), tuple(encode(c) for c in hand),
                              fantasyland_cards=player.fantasyland_cards if player.fantasyland else 0)
    validate_move(observation, move)
    cards = {encode(c): c for c in hand}
    for card, row in move.placements:
        getattr(player, ROWS[row]).append(cards[card])
    hand[:] = [cards[c] for c in move.discards]
