"""
SQLAlchemy models for the auction database.
"""

from datetime import datetime
from typing import Any, Optional

from sqlalchemy import (
    Boolean,
    Column,
    DateTime,
    Float,
    ForeignKey,
    Integer,
    String,
    Text,
    JSON,
    Enum,
)
from sqlalchemy.orm import declarative_base, relationship

from govauc.models import AssetCategory, AuctionStatus, BidStatus

Base = declarative_base()


class SiteConfigRecord(Base):
    """Auction site configuration."""

    __tablename__ = "site_configs"

    id = Column(Integer, primary_key=True)
    name = Column(String(100), unique=True, nullable=False)
    url = Column(String(500), nullable=False)
    site_type = Column(String(50), nullable=False)
    scraper_class = Column(String(100), default="GenericScraper")
    requires_auth = Column(Boolean, default=False)
    requires_javascript = Column(Boolean, default=False)
    rate_limit_seconds = Column(Float, default=2.0)
    enabled = Column(Boolean, default=True)
    credentials = Column(JSON, default=dict)
    metadata_json = Column(JSON, default=dict)
    last_scraped = Column(DateTime, nullable=True)
    created_at = Column(DateTime, default=datetime.utcnow)
    updated_at = Column(DateTime, default=datetime.utcnow, onupdate=datetime.utcnow)

    # Relationships
    listings = relationship("ListingRecord", back_populates="site")


class ListingRecord(Base):
    """Auction listing database record."""

    __tablename__ = "listings"

    id = Column(Integer, primary_key=True)
    external_id = Column(String(200), unique=True, nullable=False)
    site_id = Column(Integer, ForeignKey("site_configs.id"), nullable=False)
    listing_url = Column(String(1000), nullable=False)

    # Basic info
    title = Column(String(500), nullable=False)
    description = Column(Text)
    category = Column(String(50), nullable=False)

    # Pricing
    current_bid = Column(Float, default=0.0)
    starting_bid = Column(Float, default=0.0)
    min_increment = Column(Float, default=1.0)
    buy_now_price = Column(Float, nullable=True)

    # Timing
    start_time = Column(DateTime, nullable=True)
    end_time = Column(DateTime, nullable=True)
    status = Column(String(20), default="active")

    # Asset details
    location = Column(String(500), nullable=True)
    condition = Column(String(100), nullable=True)
    quantity = Column(Integer, default=1)
    images = Column(JSON, default=list)

    # Parsed data
    parsed_attributes = Column(JSON, default=dict)
    raw_data = Column(JSON, default=dict)

    # Analysis results
    estimated_market_value = Column(Float, nullable=True)
    confidence_score = Column(Float, default=0.0)
    opportunity_score = Column(Float, default=0.0)
    market_estimates = Column(JSON, default=list)

    # Tracking
    is_favorite = Column(Boolean, default=False)
    notes = Column(Text, nullable=True)
    created_at = Column(DateTime, default=datetime.utcnow)
    updated_at = Column(DateTime, default=datetime.utcnow, onupdate=datetime.utcnow)
    last_checked = Column(DateTime, default=datetime.utcnow)

    # Relationships
    site = relationship("SiteConfigRecord", back_populates="listings")
    bids = relationship("BidRecord", back_populates="listing")

    @property
    def profit_potential(self) -> float:
        """Calculate potential profit."""
        if self.estimated_market_value and self.current_bid > 0:
            return self.estimated_market_value - self.current_bid
        return 0.0

    @property
    def roi_percentage(self) -> float:
        """Calculate ROI percentage."""
        if self.estimated_market_value and self.current_bid > 0:
            return ((self.estimated_market_value - self.current_bid) / self.current_bid) * 100
        return 0.0


class BidRecord(Base):
    """Record of placed bids."""

    __tablename__ = "bids"

    id = Column(Integer, primary_key=True)
    listing_id = Column(Integer, ForeignKey("listings.id"), nullable=False)
    amount = Column(Float, nullable=False)
    max_bid = Column(Float, nullable=False)
    status = Column(String(20), default="pending")
    placed_at = Column(DateTime, default=datetime.utcnow)

    # Strategy used
    strategy_name = Column(String(50), nullable=True)
    snipe_seconds = Column(Integer, nullable=True)
    auto_increase = Column(Boolean, default=False)

    # Response
    response_data = Column(JSON, default=dict)

    # Relationships
    listing = relationship("ListingRecord", back_populates="bids")


class AlertRecord(Base):
    """Opportunity alerts."""

    __tablename__ = "alerts"

    id = Column(Integer, primary_key=True)
    listing_id = Column(Integer, ForeignKey("listings.id"), nullable=False)
    alert_type = Column(String(50), nullable=False)  # gem, ending_soon, price_drop
    urgency = Column(String(20), nullable=False)  # low, medium, high, critical
    message = Column(Text, nullable=False)
    recommended_max_bid = Column(Float, nullable=True)
    created_at = Column(DateTime, default=datetime.utcnow)
    acknowledged = Column(Boolean, default=False)
    acknowledged_at = Column(DateTime, nullable=True)


class DailyReport(Base):
    """Daily summary reports."""

    __tablename__ = "daily_reports"

    id = Column(Integer, primary_key=True)
    report_date = Column(DateTime, nullable=False)
    total_listings = Column(Integer, default=0)
    gems_found = Column(Integer, default=0)
    total_profit_potential = Column(Float, default=0.0)
    report_data = Column(JSON, default=dict)
    created_at = Column(DateTime, default=datetime.utcnow)
