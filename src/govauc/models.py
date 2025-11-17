"""
Core data models for the auction sniper system.
"""

from datetime import datetime
from enum import Enum
from typing import Any, Optional

from pydantic import BaseModel, Field, field_validator


class AssetCategory(str, Enum):
    """Categories of assets found at government auctions."""
    VEHICLE = "vehicle"
    ELECTRONICS = "electronics"
    REAL_ESTATE = "real_estate"
    JEWELRY = "jewelry"
    EQUIPMENT = "equipment"
    FURNITURE = "furniture"
    INDUSTRIAL = "industrial"
    OTHER = "other"


class AuctionStatus(str, Enum):
    """Status of an auction."""
    UPCOMING = "upcoming"
    ACTIVE = "active"
    ENDING_SOON = "ending_soon"
    ENDED = "ended"
    CANCELLED = "cancelled"


class BidStatus(str, Enum):
    """Status of a placed bid."""
    PENDING = "pending"
    PLACED = "placed"
    WINNING = "winning"
    OUTBID = "outbid"
    WON = "won"
    LOST = "lost"
    FAILED = "failed"


class AuctionSite(BaseModel):
    """Configuration for a government auction site."""
    name: str
    url: str
    site_type: str  # gsa, county, police, federal, state
    requires_auth: bool = False
    requires_javascript: bool = False
    scraper_class: str = "GenericScraper"
    rate_limit_seconds: float = 2.0
    enabled: bool = True
    metadata: dict[str, Any] = Field(default_factory=dict)


class AuctionListing(BaseModel):
    """A single auction listing."""
    id: str
    site_name: str
    site_url: str
    listing_url: str
    title: str
    description: str
    category: AssetCategory

    # Pricing
    current_bid: float = 0.0
    starting_bid: float = 0.0
    min_increment: float = 1.0
    buy_now_price: Optional[float] = None

    # Timing
    start_time: Optional[datetime] = None
    end_time: Optional[datetime] = None
    status: AuctionStatus = AuctionStatus.ACTIVE

    # Asset details
    location: Optional[str] = None
    condition: Optional[str] = None
    quantity: int = 1
    images: list[str] = Field(default_factory=list)

    # Extracted metadata
    raw_data: dict[str, Any] = Field(default_factory=dict)
    parsed_attributes: dict[str, Any] = Field(default_factory=dict)

    # Analysis
    estimated_market_value: Optional[float] = None
    confidence_score: float = 0.0
    opportunity_score: float = 0.0

    # Tracking
    created_at: datetime = Field(default_factory=datetime.utcnow)
    updated_at: datetime = Field(default_factory=datetime.utcnow)

    @property
    def profit_potential(self) -> float:
        """Calculate potential profit."""
        if self.estimated_market_value and self.current_bid > 0:
            return self.estimated_market_value - self.current_bid
        return 0.0

    @property
    def roi_percentage(self) -> float:
        """Calculate potential ROI percentage."""
        if self.estimated_market_value and self.current_bid > 0:
            return ((self.estimated_market_value - self.current_bid) / self.current_bid) * 100
        return 0.0

    @property
    def time_remaining_seconds(self) -> Optional[int]:
        """Get seconds remaining in auction."""
        if self.end_time:
            delta = self.end_time - datetime.utcnow()
            return max(0, int(delta.total_seconds()))
        return None

    @property
    def is_gem(self) -> bool:
        """Check if this is a high-opportunity 'gem'."""
        return (
            self.opportunity_score >= 0.8
            and self.roi_percentage >= 200
            and self.confidence_score >= 0.7
        )


class BidStrategy(BaseModel):
    """Strategy for placing bids."""
    max_bid: float
    snipe_seconds_before_end: int = 30
    bid_increment_percentage: float = 5.0
    auto_increase_max: bool = False
    max_attempts: int = 3


class PlacedBid(BaseModel):
    """Record of a placed bid."""
    id: str
    listing_id: str
    amount: float
    placed_at: datetime
    status: BidStatus = BidStatus.PENDING
    strategy: BidStrategy
    response_data: dict[str, Any] = Field(default_factory=dict)


class MarketValueEstimate(BaseModel):
    """Estimated market value from various sources."""
    source: str  # kbb, ebay, amazon, etc.
    value: float
    confidence: float  # 0-1
    data_points: int = 1
    retrieved_at: datetime = Field(default_factory=datetime.utcnow)
    metadata: dict[str, Any] = Field(default_factory=dict)


class OpportunityAlert(BaseModel):
    """Alert for a high-value opportunity."""
    listing: AuctionListing
    market_values: list[MarketValueEstimate]
    profit_potential: float
    roi_percentage: float
    urgency: str  # low, medium, high, critical
    recommended_max_bid: float
    created_at: datetime = Field(default_factory=datetime.utcnow)
