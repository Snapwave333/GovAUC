"""
Bidding strategies for the auction sniper.
"""

from abc import ABC, abstractmethod
from typing import Optional

from govauc.models import AuctionListing, BidStrategy


class BiddingStrategy(ABC):
    """Base class for bidding strategies."""

    @abstractmethod
    def calculate_bid(
        self, listing: AuctionListing, max_budget: float
    ) -> Optional[BidStrategy]:
        """
        Calculate the optimal bid strategy for a listing.

        Args:
            listing: The auction listing
            max_budget: Maximum amount willing to spend

        Returns:
            BidStrategy if we should bid, None otherwise
        """
        pass


class ConservativeStrategy(BiddingStrategy):
    """
    Conservative bidding strategy:
    - Bid at most 50% of estimated market value
    - Snipe in final 30 seconds
    - Don't auto-increase bids
    """

    def calculate_bid(
        self, listing: AuctionListing, max_budget: float
    ) -> Optional[BidStrategy]:
        if not listing.estimated_market_value:
            return None

        # Max bid is 50% of market value
        max_bid = min(
            listing.estimated_market_value * 0.50,
            max_budget
        )

        # Don't bid if current bid is already too high
        if listing.current_bid >= max_bid:
            return None

        # Calculate bid amount (just enough to win)
        bid_amount = min(
            listing.current_bid + listing.min_increment,
            max_bid
        )

        return BidStrategy(
            max_bid=max_bid,
            snipe_seconds_before_end=30,
            bid_increment_percentage=5.0,
            auto_increase_max=False,
            max_attempts=2,
        )


class AggressiveStrategy(BiddingStrategy):
    """
    Aggressive bidding strategy:
    - Bid up to 70% of estimated market value
    - Snipe in final 10 seconds
    - Auto-increase bids if outbid
    """

    def calculate_bid(
        self, listing: AuctionListing, max_budget: float
    ) -> Optional[BidStrategy]:
        if not listing.estimated_market_value:
            return None

        # Max bid is 70% of market value
        max_bid = min(
            listing.estimated_market_value * 0.70,
            max_budget
        )

        # Don't bid if ROI would be too low
        potential_profit = listing.estimated_market_value - max_bid
        if potential_profit / max_bid < 0.3:  # Less than 30% ROI
            return None

        return BidStrategy(
            max_bid=max_bid,
            snipe_seconds_before_end=10,
            bid_increment_percentage=10.0,
            auto_increase_max=True,
            max_attempts=5,
        )


class CalculatedStrategy(BiddingStrategy):
    """
    Calculated strategy based on opportunity score and confidence.
    """

    def calculate_bid(
        self, listing: AuctionListing, max_budget: float
    ) -> Optional[BidStrategy]:
        if not listing.estimated_market_value:
            return None

        # Adjust max bid based on confidence
        confidence_factor = 0.50 + (listing.confidence_score * 0.25)
        max_bid = min(
            listing.estimated_market_value * confidence_factor,
            max_budget
        )

        # Adjust snipe timing based on opportunity score
        if listing.opportunity_score >= 0.9:
            snipe_seconds = 5  # High confidence, late snipe
        elif listing.opportunity_score >= 0.8:
            snipe_seconds = 15
        else:
            snipe_seconds = 30

        # Adjust aggressiveness based on score
        auto_increase = listing.opportunity_score >= 0.85
        max_attempts = 5 if auto_increase else 2

        return BidStrategy(
            max_bid=max_bid,
            snipe_seconds_before_end=snipe_seconds,
            bid_increment_percentage=listing.opportunity_score * 15,
            auto_increase_max=auto_increase,
            max_attempts=max_attempts,
        )
