"""
Core orchestrator for the GovAUC auction bot.
"""

import asyncio
import logging
from typing import Any, Optional

from govauc.analyzers import DataCleaner, MarketValueAnalyzer, OpportunityScorer
from govauc.database import AuctionRepository
from govauc.models import AuctionListing, AuctionSite
from govauc.scrapers import ScraperRegistry
from govauc.snipers import SnipeEngine, SnipeScheduler

logger = logging.getLogger(__name__)


class AuctionBot:
    """
    Main orchestrator for the Government Auction Sniper Bot.

    Coordinates:
    - Web scraping of auction sites
    - Data cleaning and parsing
    - Market value analysis
    - Opportunity scoring
    - Automated sniping
    """

    def __init__(self, config: dict[str, Any]):
        """
        Initialize the auction bot.

        Args:
            config: Application configuration
        """
        self.config = config
        self.repo = AuctionRepository(config["database"]["url"])
        self.data_cleaner = DataCleaner()
        self.market_analyzer: Optional[MarketValueAnalyzer] = None
        self.opportunity_scorer = OpportunityScorer(config.get("analysis", {}))
        self.snipe_engine: Optional[SnipeEngine] = None
        self.snipe_scheduler: Optional[SnipeScheduler] = None

        self._initialized = False

    async def initialize(self):
        """Initialize async components."""
        if self._initialized:
            return

        self.market_analyzer = MarketValueAnalyzer(self.config.get("api_keys", {}))
        await self.market_analyzer.__aenter__()

        self.snipe_engine = SnipeEngine(self.config)
        await self.snipe_engine.__aenter__()

        self.snipe_scheduler = SnipeScheduler(
            self.snipe_engine,
            total_budget=self.config.get("budget", {}).get("total_budget", 10000),
            max_concurrent_snipes=self.config.get("sniping", {}).get("max_concurrent_snipes", 5),
        )

        self._initialized = True
        logger.info("AuctionBot initialized")

    async def cleanup(self):
        """Clean up async resources."""
        if self.market_analyzer:
            await self.market_analyzer.__aexit__(None, None, None)
        if self.snipe_engine:
            await self.snipe_engine.__aexit__(None, None, None)
        self._initialized = False

    async def scrape_site(self, site: AuctionSite) -> list[AuctionListing]:
        """
        Scrape a single auction site.

        Args:
            site: Site configuration to scrape

        Returns:
            List of found listings
        """
        logger.info(f"Scraping site: {site.name}")

        scraper = ScraperRegistry.get_scraper(site)
        async with scraper:
            listings = await scraper.scrape_all_listings()

        logger.info(f"Found {len(listings)} listings from {site.name}")
        return listings

    async def scrape_all_sites(self) -> dict[str, Any]:
        """
        Scrape all enabled auction sites.

        Returns:
            Summary of scraping results
        """
        enabled_sites = self.repo.get_enabled_sites()
        all_listings = []

        for site_record in enabled_sites:
            site = AuctionSite(
                name=site_record.name,
                url=site_record.url,
                site_type=site_record.site_type,
                scraper_class=site_record.scraper_class,
                requires_auth=site_record.requires_auth,
                requires_javascript=site_record.requires_javascript,
                rate_limit_seconds=site_record.rate_limit_seconds,
            )

            try:
                listings = await self.scrape_site(site)

                # Clean and analyze each listing
                for listing in listings:
                    listing = self.data_cleaner.clean_listing(listing)
                    listing = await self.market_analyzer.analyze_listing(listing)
                    listing.opportunity_score = self.opportunity_scorer.score_listing(listing)

                    # Save to database
                    self.repo.save_listing(listing, site_record.id)
                    all_listings.append(listing)

                # Update last scraped
                self.repo.update_site_last_scraped(site_record.id)

            except Exception as e:
                logger.error(f"Failed to scrape {site.name}: {e}")
                continue

        # Calculate summary
        gems = [l for l in all_listings if l.opportunity_score >= 0.8]
        total_profit = sum(l.profit_potential for l in gems)

        return {
            "total_listings": len(all_listings),
            "gems_found": len(gems),
            "total_profit_potential": total_profit,
            "sites_scraped": len(enabled_sites),
        }

    async def scrape_sites(self, site_names: list[str]) -> dict[str, Any]:
        """
        Scrape specific sites by name.

        Args:
            site_names: List of site names to scrape

        Returns:
            Summary of scraping results
        """
        enabled_sites = self.repo.get_enabled_sites()
        all_listings = []

        for site_record in enabled_sites:
            if site_record.name not in site_names:
                continue

            site = AuctionSite(
                name=site_record.name,
                url=site_record.url,
                site_type=site_record.site_type,
                scraper_class=site_record.scraper_class,
            )

            try:
                listings = await self.scrape_site(site)

                for listing in listings:
                    listing = self.data_cleaner.clean_listing(listing)
                    listing = await self.market_analyzer.analyze_listing(listing)
                    listing.opportunity_score = self.opportunity_scorer.score_listing(listing)
                    self.repo.save_listing(listing, site_record.id)
                    all_listings.append(listing)

                self.repo.update_site_last_scraped(site_record.id)

            except Exception as e:
                logger.error(f"Failed to scrape {site.name}: {e}")

        gems = [l for l in all_listings if l.opportunity_score >= 0.8]
        return {
            "total_listings": len(all_listings),
            "gems_found": len(gems),
            "total_profit_potential": sum(l.profit_potential for l in gems),
        }

    async def run_full_analysis(self) -> dict[str, Any]:
        """
        Run full analysis on all listings in database.

        Returns:
            Analysis report
        """
        # Get all active listings from database
        gem_records = self.repo.get_gems(0.0)  # Get all scored listings

        # Convert to AuctionListing objects for analysis
        listings = []
        for record in gem_records:
            listing = AuctionListing(
                id=record.external_id,
                site_name="",  # Will be set from site relationship
                site_url="",
                listing_url=record.listing_url,
                title=record.title,
                description=record.description or "",
                category=record.category,
                current_bid=record.current_bid,
                estimated_market_value=record.estimated_market_value,
                confidence_score=record.confidence_score,
                opportunity_score=record.opportunity_score,
                parsed_attributes=record.parsed_attributes or {},
            )
            listings.append(listing)

        # Generate report
        report = self.opportunity_scorer.generate_daily_report(listings)

        return report

    async def generate_daily_report(self) -> dict[str, Any]:
        """Generate and save a daily report."""
        report = await self.run_full_analysis()
        self.repo.save_daily_report(report)
        return report

    def set_sniping_budget(self, total_budget: float, max_per_item: float):
        """Set the sniping budget."""
        if self.snipe_scheduler:
            self.snipe_scheduler.total_budget = total_budget
            self.snipe_scheduler.remaining_budget = total_budget

        self.config["budget"]["total_budget"] = total_budget
        self.config["budget"]["max_per_item"] = max_per_item

    async def auto_schedule_snipes(self) -> int:
        """
        Automatically schedule snipes for gem opportunities.

        Returns:
            Number of snipes scheduled
        """
        if not self.snipe_scheduler:
            logger.error("Snipe scheduler not initialized")
            return 0

        # Get gem listings from database
        gem_records = self.repo.get_gems(0.8)

        # Convert to AuctionListing objects
        listings = []
        for record in gem_records:
            listing = AuctionListing(
                id=record.external_id,
                site_name=record.site.name if record.site else "",
                site_url=record.site.url if record.site else "",
                listing_url=record.listing_url,
                title=record.title,
                description=record.description or "",
                category=record.category,
                current_bid=record.current_bid,
                end_time=record.end_time,
                estimated_market_value=record.estimated_market_value,
                confidence_score=record.confidence_score,
                opportunity_score=record.opportunity_score,
            )
            listings.append(listing)

        # Schedule snipes
        max_per_item = self.config.get("budget", {}).get("max_per_item", 1000)
        return self.snipe_scheduler.auto_schedule_gems(listings, max_per_item)

    def get_snipe_schedule(self) -> dict:
        """Get current snipe schedule summary."""
        if self.snipe_scheduler:
            return self.snipe_scheduler.get_schedule_summary()
        return {}

    async def run_snipe_scheduler(self):
        """Run the snipe scheduler."""
        if self.snipe_scheduler:
            await self.snipe_scheduler.run_scheduler()

    def find_opportunities(
        self, min_score: float = 0.6, max_results: int = 50
    ) -> list[AuctionListing]:
        """
        Find high-value opportunities.

        Args:
            min_score: Minimum opportunity score
            max_results: Maximum results to return

        Returns:
            List of opportunities sorted by score
        """
        records = self.repo.get_gems(min_score)[:max_results]

        opportunities = []
        for record in records:
            listing = AuctionListing(
                id=record.external_id,
                site_name=record.site.name if record.site else "",
                site_url=record.site.url if record.site else "",
                listing_url=record.listing_url,
                title=record.title,
                description=record.description or "",
                category=record.category,
                current_bid=record.current_bid,
                end_time=record.end_time,
                location=record.location,
                estimated_market_value=record.estimated_market_value,
                confidence_score=record.confidence_score,
                opportunity_score=record.opportunity_score,
            )
            opportunities.append(listing)

        return opportunities
