"""
Base scraper class for government auction sites.
"""

import asyncio
import logging
from abc import ABC, abstractmethod
from datetime import datetime
from typing import Any, Optional

import aiohttp
from bs4 import BeautifulSoup
from fake_useragent import UserAgent
from tenacity import retry, stop_after_attempt, wait_exponential

from govauc.models import AuctionListing, AuctionSite, AssetCategory

logger = logging.getLogger(__name__)


class BaseScraper(ABC):
    """Base class for all auction site scrapers."""

    def __init__(self, site: AuctionSite):
        self.site = site
        self.ua = UserAgent()
        self.session: Optional[aiohttp.ClientSession] = None
        self.last_request_time = 0.0

    async def __aenter__(self):
        """Async context manager entry."""
        self.session = aiohttp.ClientSession(
            headers=self._get_headers(),
            timeout=aiohttp.ClientTimeout(total=30)
        )
        return self

    async def __aexit__(self, exc_type, exc_val, exc_tb):
        """Async context manager exit."""
        if self.session:
            await self.session.close()

    def _get_headers(self) -> dict[str, str]:
        """Get HTTP headers with rotating user agent."""
        return {
            "User-Agent": self.ua.random,
            "Accept": "text/html,application/xhtml+xml,application/xml;q=0.9,*/*;q=0.8",
            "Accept-Language": "en-US,en;q=0.5",
            "Accept-Encoding": "gzip, deflate",
            "Connection": "keep-alive",
            "Upgrade-Insecure-Requests": "1",
        }

    async def _rate_limit(self):
        """Enforce rate limiting between requests."""
        now = asyncio.get_event_loop().time()
        elapsed = now - self.last_request_time
        if elapsed < self.site.rate_limit_seconds:
            await asyncio.sleep(self.site.rate_limit_seconds - elapsed)
        self.last_request_time = asyncio.get_event_loop().time()

    @retry(
        stop=stop_after_attempt(3),
        wait=wait_exponential(multiplier=1, min=2, max=10)
    )
    async def fetch_page(self, url: str) -> str:
        """Fetch a page with retry logic."""
        await self._rate_limit()

        if not self.session:
            raise RuntimeError("Session not initialized. Use async context manager.")

        logger.debug(f"Fetching: {url}")

        async with self.session.get(url, headers=self._get_headers()) as response:
            response.raise_for_status()
            return await response.text()

    def parse_html(self, html: str) -> BeautifulSoup:
        """Parse HTML content."""
        return BeautifulSoup(html, "lxml")

    @abstractmethod
    async def get_listing_urls(self) -> list[str]:
        """Get all auction listing URLs from the site."""
        pass

    @abstractmethod
    async def parse_listing(self, url: str) -> Optional[AuctionListing]:
        """Parse a single auction listing page."""
        pass

    async def scrape_all_listings(self) -> list[AuctionListing]:
        """Scrape all listings from the site."""
        listings = []

        logger.info(f"Starting scrape of {self.site.name}")

        urls = await self.get_listing_urls()
        logger.info(f"Found {len(urls)} listing URLs")

        for url in urls:
            try:
                listing = await self.parse_listing(url)
                if listing:
                    listings.append(listing)
                    logger.debug(f"Parsed listing: {listing.title}")
            except Exception as e:
                logger.error(f"Failed to parse {url}: {e}")
                continue

        logger.info(f"Scraped {len(listings)} listings from {self.site.name}")
        return listings

    def detect_category(self, text: str) -> AssetCategory:
        """Detect asset category from text."""
        text_lower = text.lower()

        vehicle_keywords = [
            "car", "truck", "van", "suv", "vehicle", "ford", "chevrolet", "toyota",
            "honda", "nissan", "jeep", "dodge", "motorcycle", "boat", "trailer"
        ]
        if any(kw in text_lower for kw in vehicle_keywords):
            return AssetCategory.VEHICLE

        electronics_keywords = [
            "laptop", "computer", "phone", "iphone", "ipad", "tablet", "dell",
            "hp", "lenovo", "apple", "samsung", "monitor", "printer", "server"
        ]
        if any(kw in text_lower for kw in electronics_keywords):
            return AssetCategory.ELECTRONICS

        real_estate_keywords = [
            "house", "property", "land", "acre", "lot", "building", "home",
            "residential", "commercial", "real estate"
        ]
        if any(kw in text_lower for kw in real_estate_keywords):
            return AssetCategory.REAL_ESTATE

        jewelry_keywords = [
            "jewelry", "gold", "silver", "diamond", "ring", "necklace", "watch",
            "rolex", "bracelet"
        ]
        if any(kw in text_lower for kw in jewelry_keywords):
            return AssetCategory.JEWELRY

        equipment_keywords = [
            "equipment", "tool", "machinery", "forklift", "tractor", "generator",
            "compressor", "industrial"
        ]
        if any(kw in text_lower for kw in equipment_keywords):
            return AssetCategory.EQUIPMENT

        return AssetCategory.OTHER

    def clean_price(self, price_text: str) -> float:
        """Clean and parse price text."""
        import re
        # Remove currency symbols and commas
        cleaned = re.sub(r"[^\d.]", "", price_text)
        try:
            return float(cleaned) if cleaned else 0.0
        except ValueError:
            return 0.0

    def parse_datetime(self, date_text: str) -> Optional[datetime]:
        """Parse various date formats."""
        from dateutil import parser
        try:
            return parser.parse(date_text)
        except Exception:
            return None


class GenericScraper(BaseScraper):
    """Generic scraper for simple auction sites."""

    async def get_listing_urls(self) -> list[str]:
        """Get listing URLs - to be customized per site."""
        # Generic implementation - looks for common patterns
        html = await self.fetch_page(self.site.url)
        soup = self.parse_html(html)

        urls = []
        # Look for common auction link patterns
        for link in soup.find_all("a", href=True):
            href = link["href"]
            if any(pattern in href.lower() for pattern in ["auction", "lot", "item", "listing"]):
                if href.startswith("/"):
                    href = f"{self.site.url.rstrip('/')}{href}"
                urls.append(href)

        return list(set(urls))

    async def parse_listing(self, url: str) -> Optional[AuctionListing]:
        """Parse a generic listing page."""
        try:
            html = await self.fetch_page(url)
            soup = self.parse_html(html)

            # Try to extract basic info
            title = soup.find("h1") or soup.find("title")
            title_text = title.get_text().strip() if title else "Unknown"

            description = ""
            desc_elem = soup.find(class_=lambda x: x and "description" in x.lower())
            if desc_elem:
                description = desc_elem.get_text().strip()

            # Extract price info
            price_elem = soup.find(class_=lambda x: x and "price" in x.lower() or "bid" in x.lower())
            current_bid = 0.0
            if price_elem:
                current_bid = self.clean_price(price_elem.get_text())

            listing = AuctionListing(
                id=f"{self.site.name}_{hash(url)}",
                site_name=self.site.name,
                site_url=self.site.url,
                listing_url=url,
                title=title_text,
                description=description,
                category=self.detect_category(f"{title_text} {description}"),
                current_bid=current_bid,
                raw_data={"html_excerpt": str(soup)[:5000]},
            )

            return listing

        except Exception as e:
            logger.error(f"Failed to parse listing {url}: {e}")
            return None
