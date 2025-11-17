"""
Opportunity scoring engine for identifying high-value auction opportunities.
"""

import logging
from datetime import datetime, timedelta
from typing import Optional

from govauc.models import AuctionListing, OpportunityAlert, MarketValueEstimate

logger = logging.getLogger(__name__)


class OpportunityScorer:
    """
    Scores auction listings based on profit potential, ROI, timing, and risk.

    The score ranges from 0-1, where:
    - 0.0-0.3: Low opportunity (skip)
    - 0.3-0.6: Moderate opportunity (monitor)
    - 0.6-0.8: Good opportunity (consider bidding)
    - 0.8-1.0: Excellent opportunity ("gem" - prioritize)
    """

    def __init__(self, config: Optional[dict] = None):
        """
        Initialize the scorer with configuration.

        Args:
            config: Scoring parameters and thresholds
        """
        self.config = config or {}

        # Default thresholds
        self.min_profit = self.config.get("min_profit", 100)
        self.min_roi_percent = self.config.get("min_roi_percent", 50)
        self.max_risk_tolerance = self.config.get("max_risk_tolerance", 0.7)

        # Weights for different scoring factors
        self.weights = {
            "profit_potential": 0.30,
            "roi": 0.25,
            "confidence": 0.20,
            "timing": 0.15,
            "category_preference": 0.10,
        }

    def score_listing(self, listing: AuctionListing) -> float:
        """
        Calculate opportunity score for a listing.

        Args:
            listing: Auction listing to score

        Returns:
            Score between 0-1
        """
        scores = {
            "profit_potential": self._score_profit_potential(listing),
            "roi": self._score_roi(listing),
            "confidence": self._score_confidence(listing),
            "timing": self._score_timing(listing),
            "category_preference": self._score_category(listing),
        }

        # Weighted sum
        total_score = sum(
            scores[key] * self.weights[key] for key in scores
        )

        # Normalize to 0-1
        opportunity_score = min(1.0, max(0.0, total_score))

        logger.debug(
            f"Scored listing {listing.id}: {opportunity_score:.2f} "
            f"(profit={scores['profit_potential']:.2f}, "
            f"roi={scores['roi']:.2f}, "
            f"confidence={scores['confidence']:.2f})"
        )

        return opportunity_score

    def _score_profit_potential(self, listing: AuctionListing) -> float:
        """Score based on absolute profit potential."""
        if not listing.estimated_market_value or listing.current_bid <= 0:
            return 0.0

        profit = listing.profit_potential

        if profit <= 0:
            return 0.0
        elif profit < self.min_profit:
            return 0.2
        elif profit < self.min_profit * 5:  # 5x min profit
            # Linear scale from 0.2 to 0.7
            return 0.2 + (profit / (self.min_profit * 5)) * 0.5
        elif profit < self.min_profit * 20:  # 20x min profit
            # Scale from 0.7 to 0.9
            return 0.7 + ((profit - self.min_profit * 5) / (self.min_profit * 15)) * 0.2
        else:  # Exceptional profit
            return 1.0

    def _score_roi(self, listing: AuctionListing) -> float:
        """Score based on return on investment percentage."""
        roi = listing.roi_percentage

        if roi <= 0:
            return 0.0
        elif roi < self.min_roi_percent:
            return 0.1
        elif roi < 100:  # 100% ROI
            return 0.3
        elif roi < 200:  # 200% ROI
            return 0.5
        elif roi < 500:  # 500% ROI
            return 0.7
        elif roi < 1000:  # 1000% ROI
            return 0.9
        else:  # Exceptional ROI
            return 1.0

    def _score_confidence(self, listing: AuctionListing) -> float:
        """Score based on confidence in our market value estimate."""
        confidence = listing.confidence_score

        if confidence < 0.3:
            return 0.2  # Too uncertain
        elif confidence < 0.5:
            return 0.4
        elif confidence < 0.7:
            return 0.7
        else:
            return confidence  # Pass through high confidence

    def _score_timing(self, listing: AuctionListing) -> float:
        """
        Score based on auction timing.

        Ending soon = more urgent = higher score
        But too soon might be risky
        """
        remaining = listing.time_remaining_seconds

        if remaining is None:
            return 0.5  # Unknown timing

        hours_remaining = remaining / 3600

        if hours_remaining < 0:
            return 0.0  # Ended
        elif hours_remaining < 0.1:  # Less than 6 minutes
            return 0.95  # Very urgent, great for sniping
        elif hours_remaining < 0.5:  # Less than 30 minutes
            return 0.9
        elif hours_remaining < 1:  # Less than 1 hour
            return 0.85
        elif hours_remaining < 6:  # Less than 6 hours
            return 0.7
        elif hours_remaining < 24:  # Less than 1 day
            return 0.6
        elif hours_remaining < 72:  # Less than 3 days
            return 0.4
        else:  # More than 3 days
            return 0.3  # Monitor, not urgent

    def _score_category(self, listing: AuctionListing) -> float:
        """Score based on category preferences and liquidity."""
        # Categories ranked by ease of resale and market liquidity
        category_scores = {
            "electronics": 0.9,  # Very liquid, easy to flip
            "vehicle": 0.8,  # Good market, predictable pricing
            "jewelry": 0.7,  # Can be profitable but needs expertise
            "equipment": 0.6,  # Niche market
            "furniture": 0.5,  # Bulky, harder to ship
            "real_estate": 0.4,  # High capital, complex
            "industrial": 0.3,  # Very niche
            "other": 0.3,
        }

        return category_scores.get(listing.category.value, 0.3)

    def create_alert(
        self,
        listing: AuctionListing,
        market_estimates: Optional[list[MarketValueEstimate]] = None,
    ) -> Optional[OpportunityAlert]:
        """
        Create an alert for a high-opportunity listing.

        Args:
            listing: The listing to alert on
            market_estimates: Market value estimates

        Returns:
            OpportunityAlert if listing meets threshold, None otherwise
        """
        # Score the listing
        score = self.score_listing(listing)
        listing.opportunity_score = score

        # Determine urgency
        remaining = listing.time_remaining_seconds or float("inf")
        if remaining < 600:  # 10 minutes
            urgency = "critical"
        elif remaining < 3600:  # 1 hour
            urgency = "high"
        elif remaining < 86400:  # 1 day
            urgency = "medium"
        else:
            urgency = "low"

        # Calculate recommended max bid
        if listing.estimated_market_value:
            # Recommend bidding up to 60-70% of market value for good margin
            margin_factor = 0.65 if score > 0.8 else 0.60
            recommended_max = listing.estimated_market_value * margin_factor
        else:
            recommended_max = listing.current_bid * 1.5

        alert = OpportunityAlert(
            listing=listing,
            market_values=market_estimates or [],
            profit_potential=listing.profit_potential,
            roi_percentage=listing.roi_percentage,
            urgency=urgency,
            recommended_max_bid=round(recommended_max, 2),
        )

        return alert

    def find_gems(
        self, listings: list[AuctionListing], min_score: float = 0.8
    ) -> list[OpportunityAlert]:
        """
        Find all gem opportunities from a list of listings.

        Args:
            listings: List of analyzed listings
            min_score: Minimum opportunity score to be considered a gem

        Returns:
            List of alerts for gem opportunities, sorted by score
        """
        gems = []

        for listing in listings:
            score = self.score_listing(listing)
            listing.opportunity_score = score

            if score >= min_score:
                alert = self.create_alert(listing)
                if alert:
                    gems.append(alert)

        # Sort by opportunity score (highest first)
        gems.sort(key=lambda a: a.listing.opportunity_score, reverse=True)

        logger.info(f"Found {len(gems)} gem opportunities from {len(listings)} listings")

        return gems

    def prioritize_auctions(
        self, listings: list[AuctionListing]
    ) -> list[AuctionListing]:
        """
        Prioritize auctions for bidding based on score and timing.

        Args:
            listings: List of listings to prioritize

        Returns:
            Sorted list with highest priority first
        """
        # Score all listings
        for listing in listings:
            listing.opportunity_score = self.score_listing(listing)

        # Sort by:
        # 1. Opportunity score (high to low)
        # 2. Time remaining (soon to late)
        # 3. ROI percentage (high to low)
        sorted_listings = sorted(
            listings,
            key=lambda l: (
                -l.opportunity_score,
                l.time_remaining_seconds or float("inf"),
                -l.roi_percentage,
            ),
        )

        return sorted_listings

    def generate_daily_report(
        self, listings: list[AuctionListing]
    ) -> dict:
        """
        Generate a daily summary report of opportunities.

        Args:
            listings: All analyzed listings

        Returns:
            Summary report dictionary
        """
        # Score all listings
        scored_listings = []
        for listing in listings:
            listing.opportunity_score = self.score_listing(listing)
            scored_listings.append(listing)

        # Categorize by score
        gems = [l for l in scored_listings if l.opportunity_score >= 0.8]
        good = [l for l in scored_listings if 0.6 <= l.opportunity_score < 0.8]
        moderate = [l for l in scored_listings if 0.3 <= l.opportunity_score < 0.6]
        low = [l for l in scored_listings if l.opportunity_score < 0.3]

        # Calculate totals
        total_profit_potential = sum(l.profit_potential for l in gems)
        avg_roi = (
            sum(l.roi_percentage for l in gems) / len(gems) if gems else 0
        )

        # Ending soon (within 24 hours)
        ending_soon = [
            l for l in gems if l.time_remaining_seconds and l.time_remaining_seconds < 86400
        ]

        report = {
            "date": datetime.utcnow().isoformat(),
            "total_listings_analyzed": len(listings),
            "summary": {
                "gems": len(gems),
                "good_opportunities": len(good),
                "moderate_opportunities": len(moderate),
                "low_opportunities": len(low),
            },
            "gems_analysis": {
                "count": len(gems),
                "total_profit_potential": round(total_profit_potential, 2),
                "average_roi_percent": round(avg_roi, 2),
                "ending_soon_count": len(ending_soon),
            },
            "top_opportunities": [
                {
                    "id": l.id,
                    "title": l.title[:50],
                    "category": l.category.value,
                    "current_bid": l.current_bid,
                    "estimated_value": l.estimated_market_value,
                    "profit_potential": l.profit_potential,
                    "roi_percent": round(l.roi_percentage, 2),
                    "score": round(l.opportunity_score, 3),
                    "hours_remaining": (
                        round(l.time_remaining_seconds / 3600, 1)
                        if l.time_remaining_seconds
                        else None
                    ),
                }
                for l in gems[:10]  # Top 10 gems
            ],
            "category_breakdown": {},
        }

        # Category breakdown
        for listing in scored_listings:
            cat = listing.category.value
            if cat not in report["category_breakdown"]:
                report["category_breakdown"][cat] = {
                    "count": 0,
                    "gems": 0,
                    "avg_score": 0,
                    "total_profit": 0,
                }
            report["category_breakdown"][cat]["count"] += 1
            if listing.opportunity_score >= 0.8:
                report["category_breakdown"][cat]["gems"] += 1
            report["category_breakdown"][cat]["total_profit"] += listing.profit_potential

        # Calculate averages
        for cat in report["category_breakdown"]:
            cat_listings = [l for l in scored_listings if l.category.value == cat]
            if cat_listings:
                report["category_breakdown"][cat]["avg_score"] = round(
                    sum(l.opportunity_score for l in cat_listings) / len(cat_listings),
                    3,
                )
                report["category_breakdown"][cat]["total_profit"] = round(
                    report["category_breakdown"][cat]["total_profit"], 2
                )

        return report
