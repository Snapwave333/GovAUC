"""
Auction sniping engine for automated bidding.
"""

from .engine import SnipeEngine
from .scheduler import SnipeScheduler
from .strategies import BiddingStrategy, ConservativeStrategy, AggressiveStrategy

__all__ = [
    "SnipeEngine",
    "SnipeScheduler",
    "BiddingStrategy",
    "ConservativeStrategy",
    "AggressiveStrategy",
]
