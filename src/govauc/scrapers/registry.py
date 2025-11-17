"""
Registry for auction site scrapers.
"""

import logging
from typing import Type

from govauc.models import AuctionSite
from govauc.scrapers.base import BaseScraper, GenericScraper

logger = logging.getLogger(__name__)


class ScraperRegistry:
    """Registry for managing different auction site scrapers."""

    _scrapers: dict[str, Type[BaseScraper]] = {
        "GenericScraper": GenericScraper,
    }

    @classmethod
    def register(cls, name: str, scraper_class: Type[BaseScraper]):
        """Register a new scraper class."""
        cls._scrapers[name] = scraper_class
        logger.info(f"Registered scraper: {name}")

    @classmethod
    def get_scraper(cls, site: AuctionSite) -> BaseScraper:
        """Get a scraper instance for a site."""
        scraper_class = cls._scrapers.get(site.scraper_class, GenericScraper)
        return scraper_class(site)

    @classmethod
    def list_scrapers(cls) -> list[str]:
        """List all registered scraper classes."""
        return list(cls._scrapers.keys())


# Import specialized scrapers to register them
def load_specialized_scrapers():
    """Load all specialized scraper implementations."""
    try:
        from govauc.scrapers import gsa, govplanet, publicsurplus
        logger.info("Loaded specialized scrapers")
    except ImportError as e:
        logger.debug(f"Some specialized scrapers not loaded: {e}")


load_specialized_scrapers()
