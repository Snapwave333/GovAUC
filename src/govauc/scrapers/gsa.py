"""
GSA Auctions scraper - Federal government surplus property.
https://gsaauctions.gov
"""

import logging
import re
from datetime import datetime
from typing import Optional
from urllib.parse import urljoin

from govauc.models import AuctionListing, AuctionSite, AuctionStatus
from govauc.scrapers.base import BaseScraper
from govauc.scrapers.registry import ScraperRegistry

logger = logging.getLogger(__name__)


class GSAScraper(BaseScraper):
    """Scraper for GSA Auctions (gsaauctions.gov)."""

    BASE_URL = "https://gsaauctions.gov"

    async def get_listing_urls(self) -> list[str]:
        """Get all active auction URLs from GSA Auctions."""
        urls = []

        # GSA uses different categories for browsing
        categories = [
            "/gsaauctions/aucitsrh/?sl=71QSCI",  # Vehicles
            "/gsaauctions/aucitsrh/?sl=71QSCA",  # Computer Equipment
            "/gsaauctions/aucitsrh/?sl=71QSCM",  # Office Machines
            "/gsaauctions/aucitsrh/?sl=71QSCF",  # Furniture
            "/gsaauctions/aucitsrh/?sl=71QSCE",  # Electrical Equipment
        ]

        for category_path in categories:
            try:
                search_url = urljoin(self.BASE_URL, category_path)
                html = await self.fetch_page(search_url)
                soup = self.parse_html(html)

                # Find auction links
                for link in soup.find_all("a", href=re.compile(r"aucitsrh/\?.*aession")):
                    href = link.get("href")
                    if href:
                        full_url = urljoin(self.BASE_URL, href)
                        urls.append(full_url)

                logger.debug(f"Found {len(urls)} URLs from {category_path}")

            except Exception as e:
                logger.error(f"Error scraping category {category_path}: {e}")
                continue

        return list(set(urls))

    async def parse_listing(self, url: str) -> Optional[AuctionListing]:
        """Parse a GSA Auctions listing page."""
        try:
            html = await self.fetch_page(url)
            soup = self.parse_html(html)

            # Extract title
            title_elem = soup.find("h1") or soup.find(class_="item-title")
            title = title_elem.get_text().strip() if title_elem else "Unknown GSA Item"

            # Extract description
            desc_elem = soup.find(id="item-description") or soup.find(class_="description")
            description = desc_elem.get_text().strip() if desc_elem else ""

            # Extract current bid
            bid_elem = soup.find(class_="current-bid") or soup.find(text=re.compile(r"Current Bid"))
            current_bid = 0.0
            if bid_elem:
                bid_text = bid_elem.get_text() if hasattr(bid_elem, "get_text") else str(bid_elem)
                current_bid = self.clean_price(bid_text)

            # Extract end time
            end_elem = soup.find(class_="end-time") or soup.find(text=re.compile(r"Closes?:"))
            end_time = None
            if end_elem:
                time_text = end_elem.get_text() if hasattr(end_elem, "get_text") else str(end_elem)
                end_time = self.parse_datetime(time_text)

            # Extract location
            location = ""
            loc_elem = soup.find(class_="location") or soup.find(text=re.compile(r"Location:"))
            if loc_elem:
                location = loc_elem.get_text().strip() if hasattr(loc_elem, "get_text") else str(loc_elem)

            # Extract images
            images = []
            for img in soup.find_all("img", src=re.compile(r"(auction|image|photo)", re.I)):
                src = img.get("src")
                if src:
                    images.append(urljoin(self.BASE_URL, src))

            # Extract sale number/ID
            sale_id = ""
            id_match = re.search(r"aession=(\w+)", url)
            if id_match:
                sale_id = id_match.group(1)
            else:
                sale_id = str(hash(url))

            listing = AuctionListing(
                id=f"gsa_{sale_id}",
                site_name="GSA Auctions",
                site_url=self.BASE_URL,
                listing_url=url,
                title=title,
                description=description,
                category=self.detect_category(f"{title} {description}"),
                current_bid=current_bid,
                end_time=end_time,
                location=location,
                images=images[:10],  # Limit to 10 images
                raw_data={
                    "sale_id": sale_id,
                    "source": "gsa",
                },
            )

            # Determine status based on end time
            if end_time:
                now = datetime.utcnow()
                if end_time < now:
                    listing.status = AuctionStatus.ENDED
                elif (end_time - now).total_seconds() < 3600:  # Less than 1 hour
                    listing.status = AuctionStatus.ENDING_SOON

            return listing

        except Exception as e:
            logger.error(f"Failed to parse GSA listing {url}: {e}")
            return None


# Register the scraper
ScraperRegistry.register("GSAScraper", GSAScraper)
