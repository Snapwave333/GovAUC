"""
Repository pattern for database operations.
"""

import logging
from datetime import datetime, timedelta
from typing import List, Optional

from sqlalchemy import create_engine, desc, and_
from sqlalchemy.orm import sessionmaker, Session

from govauc.database.models import (
    Base,
    ListingRecord,
    BidRecord,
    SiteConfigRecord,
    AlertRecord,
    DailyReport,
)
from govauc.models import AuctionListing, AuctionSite, PlacedBid

logger = logging.getLogger(__name__)


class AuctionRepository:
    """Repository for auction database operations."""

    def __init__(self, database_url: str = "sqlite:///govauc.db"):
        """
        Initialize the repository.

        Args:
            database_url: SQLAlchemy database URL
        """
        self.engine = create_engine(database_url, echo=False)
        self.SessionLocal = sessionmaker(bind=self.engine)

        # Create tables
        Base.metadata.create_all(self.engine)
        logger.info(f"Database initialized: {database_url}")

    def get_session(self) -> Session:
        """Get a new database session."""
        return self.SessionLocal()

    # Site Configuration
    def add_site(self, site: AuctionSite) -> SiteConfigRecord:
        """Add a new auction site configuration."""
        with self.get_session() as session:
            record = SiteConfigRecord(
                name=site.name,
                url=site.url,
                site_type=site.site_type,
                scraper_class=site.scraper_class,
                requires_auth=site.requires_auth,
                requires_javascript=site.requires_javascript,
                rate_limit_seconds=site.rate_limit_seconds,
                enabled=site.enabled,
                metadata_json=site.metadata,
            )
            session.add(record)
            session.commit()
            session.refresh(record)
            logger.info(f"Added site: {site.name}")
            return record

    def get_enabled_sites(self) -> List[SiteConfigRecord]:
        """Get all enabled auction sites."""
        with self.get_session() as session:
            return session.query(SiteConfigRecord).filter_by(enabled=True).all()

    def update_site_last_scraped(self, site_id: int):
        """Update the last scraped timestamp for a site."""
        with self.get_session() as session:
            site = session.query(SiteConfigRecord).get(site_id)
            if site:
                site.last_scraped = datetime.utcnow()
                session.commit()

    # Listings
    def save_listing(self, listing: AuctionListing, site_id: int) -> ListingRecord:
        """Save or update an auction listing."""
        with self.get_session() as session:
            # Check if listing exists
            existing = (
                session.query(ListingRecord)
                .filter_by(external_id=listing.id)
                .first()
            )

            if existing:
                # Update existing
                existing.current_bid = listing.current_bid
                existing.end_time = listing.end_time
                existing.status = listing.status.value
                existing.estimated_market_value = listing.estimated_market_value
                existing.confidence_score = listing.confidence_score
                existing.opportunity_score = listing.opportunity_score
                existing.parsed_attributes = listing.parsed_attributes
                existing.last_checked = datetime.utcnow()
                existing.updated_at = datetime.utcnow()
                session.commit()
                logger.debug(f"Updated listing: {listing.id}")
                return existing
            else:
                # Create new
                record = ListingRecord(
                    external_id=listing.id,
                    site_id=site_id,
                    listing_url=listing.listing_url,
                    title=listing.title,
                    description=listing.description,
                    category=listing.category.value,
                    current_bid=listing.current_bid,
                    starting_bid=listing.starting_bid,
                    min_increment=listing.min_increment,
                    buy_now_price=listing.buy_now_price,
                    start_time=listing.start_time,
                    end_time=listing.end_time,
                    status=listing.status.value,
                    location=listing.location,
                    condition=listing.condition,
                    quantity=listing.quantity,
                    images=listing.images,
                    parsed_attributes=listing.parsed_attributes,
                    raw_data=listing.raw_data,
                    estimated_market_value=listing.estimated_market_value,
                    confidence_score=listing.confidence_score,
                    opportunity_score=listing.opportunity_score,
                )
                session.add(record)
                session.commit()
                session.refresh(record)
                logger.debug(f"Saved new listing: {listing.id}")
                return record

    def save_listings_batch(
        self, listings: List[AuctionListing], site_id: int
    ) -> int:
        """Save multiple listings efficiently."""
        count = 0
        for listing in listings:
            self.save_listing(listing, site_id)
            count += 1
        logger.info(f"Saved {count} listings for site {site_id}")
        return count

    def get_gems(self, min_score: float = 0.8) -> List[ListingRecord]:
        """Get all gem opportunities."""
        with self.get_session() as session:
            return (
                session.query(ListingRecord)
                .filter(
                    and_(
                        ListingRecord.opportunity_score >= min_score,
                        ListingRecord.status == "active",
                    )
                )
                .order_by(desc(ListingRecord.opportunity_score))
                .all()
            )

    def get_ending_soon(self, hours: int = 24) -> List[ListingRecord]:
        """Get listings ending soon."""
        with self.get_session() as session:
            cutoff = datetime.utcnow() + timedelta(hours=hours)
            return (
                session.query(ListingRecord)
                .filter(
                    and_(
                        ListingRecord.end_time <= cutoff,
                        ListingRecord.end_time > datetime.utcnow(),
                        ListingRecord.status == "active",
                    )
                )
                .order_by(ListingRecord.end_time)
                .all()
            )

    def get_listings_by_category(self, category: str) -> List[ListingRecord]:
        """Get listings by category."""
        with self.get_session() as session:
            return (
                session.query(ListingRecord)
                .filter_by(category=category, status="active")
                .order_by(desc(ListingRecord.opportunity_score))
                .all()
            )

    def search_listings(self, query: str) -> List[ListingRecord]:
        """Search listings by title or description."""
        with self.get_session() as session:
            search_term = f"%{query}%"
            return (
                session.query(ListingRecord)
                .filter(
                    and_(
                        ListingRecord.title.ilike(search_term)
                        | ListingRecord.description.ilike(search_term),
                        ListingRecord.status == "active",
                    )
                )
                .all()
            )

    def get_favorite_listings(self) -> List[ListingRecord]:
        """Get favorited listings."""
        with self.get_session() as session:
            return (
                session.query(ListingRecord)
                .filter_by(is_favorite=True)
                .order_by(ListingRecord.end_time)
                .all()
            )

    def toggle_favorite(self, listing_id: int) -> bool:
        """Toggle favorite status for a listing."""
        with self.get_session() as session:
            listing = session.query(ListingRecord).get(listing_id)
            if listing:
                listing.is_favorite = not listing.is_favorite
                session.commit()
                return listing.is_favorite
        return False

    # Bids
    def save_bid(self, bid: PlacedBid, listing_db_id: int) -> BidRecord:
        """Save a bid record."""
        with self.get_session() as session:
            record = BidRecord(
                listing_id=listing_db_id,
                amount=bid.amount,
                max_bid=bid.strategy.max_bid,
                status=bid.status.value,
                placed_at=bid.placed_at,
                strategy_name=bid.strategy.__class__.__name__
                if hasattr(bid.strategy, "__class__")
                else "custom",
                snipe_seconds=bid.strategy.snipe_seconds_before_end,
                auto_increase=bid.strategy.auto_increase_max,
                response_data=bid.response_data,
            )
            session.add(record)
            session.commit()
            session.refresh(record)
            logger.info(f"Saved bid: ${bid.amount:.2f} on listing {listing_db_id}")
            return record

    def get_bid_history(self, limit: int = 100) -> List[BidRecord]:
        """Get recent bid history."""
        with self.get_session() as session:
            return (
                session.query(BidRecord)
                .order_by(desc(BidRecord.placed_at))
                .limit(limit)
                .all()
            )

    def get_winning_bids(self) -> List[BidRecord]:
        """Get all winning bids."""
        with self.get_session() as session:
            return (
                session.query(BidRecord)
                .filter(BidRecord.status.in_(["winning", "won"]))
                .all()
            )

    # Alerts
    def create_alert(
        self,
        listing_id: int,
        alert_type: str,
        urgency: str,
        message: str,
        recommended_bid: Optional[float] = None,
    ) -> AlertRecord:
        """Create an opportunity alert."""
        with self.get_session() as session:
            alert = AlertRecord(
                listing_id=listing_id,
                alert_type=alert_type,
                urgency=urgency,
                message=message,
                recommended_max_bid=recommended_bid,
            )
            session.add(alert)
            session.commit()
            session.refresh(alert)
            return alert

    def get_unacknowledged_alerts(self) -> List[AlertRecord]:
        """Get all unacknowledged alerts."""
        with self.get_session() as session:
            return (
                session.query(AlertRecord)
                .filter_by(acknowledged=False)
                .order_by(desc(AlertRecord.created_at))
                .all()
            )

    def acknowledge_alert(self, alert_id: int):
        """Acknowledge an alert."""
        with self.get_session() as session:
            alert = session.query(AlertRecord).get(alert_id)
            if alert:
                alert.acknowledged = True
                alert.acknowledged_at = datetime.utcnow()
                session.commit()

    # Reports
    def save_daily_report(self, report_data: dict) -> DailyReport:
        """Save a daily summary report."""
        with self.get_session() as session:
            report = DailyReport(
                report_date=datetime.utcnow(),
                total_listings=report_data.get("total_listings_analyzed", 0),
                gems_found=report_data.get("summary", {}).get("gems", 0),
                total_profit_potential=report_data.get("gems_analysis", {}).get(
                    "total_profit_potential", 0
                ),
                report_data=report_data,
            )
            session.add(report)
            session.commit()
            session.refresh(report)
            logger.info(f"Saved daily report: {report.id}")
            return report

    def get_statistics(self) -> dict:
        """Get overall statistics."""
        with self.get_session() as session:
            total_listings = session.query(ListingRecord).count()
            active_listings = (
                session.query(ListingRecord).filter_by(status="active").count()
            )
            gems = (
                session.query(ListingRecord)
                .filter(ListingRecord.opportunity_score >= 0.8)
                .count()
            )
            total_bids = session.query(BidRecord).count()
            winning_bids = (
                session.query(BidRecord)
                .filter(BidRecord.status.in_(["winning", "won"]))
                .count()
            )

            # Calculate total profit potential
            gem_listings = self.get_gems(0.8)
            total_profit = sum(l.profit_potential for l in gem_listings)

            return {
                "total_listings": total_listings,
                "active_listings": active_listings,
                "gems_found": gems,
                "total_bids_placed": total_bids,
                "winning_bids": winning_bids,
                "total_profit_potential": round(total_profit, 2),
                "sites_configured": session.query(SiteConfigRecord).count(),
                "enabled_sites": (
                    session.query(SiteConfigRecord).filter_by(enabled=True).count()
                ),
            }
