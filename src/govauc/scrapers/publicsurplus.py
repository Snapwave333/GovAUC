"""
PublicSurplus scraper - State and local government surplus.
https://www.publicsurplus.com
"""

import logging
import re
from datetime import datetime
from typing import Optional
from urllib.parse import urljoin, urlparse, parse_qs

from govauc.models import AuctionListing, AuctionSite, AuctionStatus
from govauc.scrapers.base import BaseScraper
from govauc.scrapers.registry import ScraperRegistry

logger = logging.getLogger(__name__)


class PublicSurplusScraper(BaseScraper):
    """Scraper for PublicSurplus.com auctions."""

    BASE_URL = "https://www.publicsurplus.com"

    async def get_listing_urls(self) -> list[str]:
        """Get all active auction URLs from PublicSurplus."""
        urls = []

        # Browse by category
        category_ids = [
            "1",   # Vehicles
            "2",   # Computer & Office Equipment
            "3",   # Industrial & Manufacturing
            "4",   # Electronics
            "5",   # Tools & Shop Equipment
            "10",  # Miscellaneous
        ]

        for cat_id in category_ids:
            try:
                search_url = f"{self.BASE_URL}/list/list?catId={cat_id}&aession=open"
                html = await self.fetch_page(search_url)
                soup = self.parse_html(html)

                # Find auction links
                for link in soup.find_all("a", href=re.compile(r"sms/auction/view\?aession=")):
                    href = link.get("href")
                    if href:
                        full_url = urljoin(self.BASE_URL, href)
                        urls.append(full_url)

            except Exception as e:
                logger.error(f"Error scraping PublicSurplus category {cat_id}: {e}")
                continue

        return list(set(urls))

    async def parse_listing(self, url: str) -> Optional[AuctionListing]:
        """Parse a PublicSurplus listing page."""
        try:
            html = await self.fetch_page(url)
            soup = self.parse_html(html)

            # Extract title
            title_elem = soup.find("h1") or soup.find(class_="item-name")
            title = title_elem.get_text().strip() if title_elem else "Unknown Item"

            # Extract description - PublicSurplus often has detailed descriptions
            description = ""
            desc_div = soup.find(id="itemDescription") or soup.find(class_="description")
            if desc_div:
                description = desc_div.get_text().strip()

            # Extract current bid
            current_bid = 0.0
            bid_elem = soup.find(class_="current-bid") or soup.find(id="currentBid")
            if bid_elem:
                current_bid = self.clean_price(bid_elem.get_text())

            # Extract minimum bid/starting bid
            starting_bid = 0.0
            start_elem = soup.find(text=re.compile(r"Starting Bid|Minimum"))
            if start_elem:
                starting_bid = self.clean_price(start_elem.find_next().get_text())

            # Extract bid increment
            min_increment = 1.0
            inc_elem = soup.find(text=re.compile(r"Bid Increment"))
            if inc_elem:
                min_increment = self.clean_price(inc_elem.find_next().get_text())

            # Extract end time
            end_time = None
            close_elem = soup.find(text=re.compile(r"Closes?:|End Time"))
            if close_elem:
                time_text = close_elem.find_next().get_text()
                end_time = self.parse_datetime(time_text)

            # Extract location
            location = ""
            loc_elem = soup.find(class_="seller-location") or soup.find(text=re.compile(r"Location:"))
            if loc_elem:
                if hasattr(loc_elem, "find_next"):
                    location = loc_elem.find_next().get_text().strip()
                else:
                    location = loc_elem.get_text().strip()

            # Extract seller info (government agency)
            seller = ""
            seller_elem = soup.find(class_="seller-name")
            if seller_elem:
                seller = seller_elem.get_text().strip()

            # Extract quantity
            quantity = 1
            qty_elem = soup.find(text=re.compile(r"Quantity:"))
            if qty_elem:
                qty_text = qty_elem.find_next().get_text()
                qty_match = re.search(r"(\d+)", qty_text)
                if qty_match:
                    quantity = int(qty_match.group(1))

            # Extract images
            images = []
            gallery = soup.find(class_="image-gallery") or soup.find(id="photos")
            if gallery:
                for img in gallery.find_all("img"):
                    src = img.get("src") or img.get("data-src")
                    if src and not src.startswith("data:"):
                        images.append(urljoin(self.BASE_URL, src))

            # Extract auction ID
            parsed_url = urlparse(url)
            params = parse_qs(parsed_url.query)
            auction_id = params.get("aession", [str(hash(url))])[0]

            listing = AuctionListing(
                id=f"publicsurplus_{auction_id}",
                site_name="PublicSurplus",
                site_url=self.BASE_URL,
                listing_url=url,
                title=title,
                description=description,
                category=self.detect_category(f"{title} {description}"),
                current_bid=current_bid,
                starting_bid=starting_bid,
                min_increment=min_increment,
                end_time=end_time,
                location=location,
                quantity=quantity,
                images=images[:10],
                raw_data={
                    "auction_id": auction_id,
                    "seller": seller,
                    "source": "publicsurplus",
                },
            )

            return listing

        except Exception as e:
            logger.error(f"Failed to parse PublicSurplus listing {url}: {e}")
            return None


# Register the scraper
ScraperRegistry.register("PublicSurplusScraper", PublicSurplusScraper)
