"""Shared settlement boundary for a two-player Fantasyland chain."""


def can_settle(next_tiers):
    """Evaluate at a completed hand, using NEXT rights rather than old tiers."""
    return not any(next_tiers)
