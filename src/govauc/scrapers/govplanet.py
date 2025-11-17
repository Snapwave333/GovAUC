"""
GovPlanet scraper - Government surplus heavy equipment and vehicles.
https://www.govplanet.com
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


class GovPlanetScraper(BaseScraper):
    """Scraper for GovPlanet auctions."""

    BASE_URL = "https://www.govplanet.com"

    async def get_listing_urls(self) -> list[str]:
        """Get all active auction URLs from GovPlanet."""
        urls = []

        # GovPlanet category pages
        category_paths = [
            "/for-sale/Cars",
            "/for-sale/Trucks",
            "/for-sale/Heavy-Equipment",
            "/for-sale/Construction-Equipment",
            "/for-sale/Electronics",
            "/for-sale/Office-Equipment",
        ]

        for category_path in category_paths:
            try:
                search_url = urljoin(self.BASE_URL, category_path)
                html = await self.fetch_page(search_url)
                soup = self.parse_html(html)

                # Find item links
                for link in soup.find_all("a", href=re.compile(r"/for-sale/.*-\d+$")):
                    href = link.get("href")
                    if href:
                        full_url = urljoin(self.BASE_URL, href)
                        urls.append(full_url)

            except Exception as e:
                logger.error(f"Error scraping GovPlanet category {category_path}: {e}")
                continue

        return list(set(urls))

    async def parse_listing(self, url: str) -> Optional[AuctionListing]:
        """Parse a GovPlanet listing page."""
        try:
            html = await self.fetch_page(url)
            soup = self.parse_html(html)

            # Extract title
            title_elem = soup.find("h1", class_="listing-title") or soup.find("h1")
            title = title_elem.get_text().strip() if title_elem else "Unknown Item"

            # Extract description
            desc_elem = soup.find(class_="item-description") or soup.find(id="description")
            description = desc_elem.get_text().strip() if desc_elem else ""

            # Parse vehicle/equipment details from title
            parsed_attrs = self._parse_equipment_title(title)

            # Extract current bid/price
            bid_elem = soup.find(class_="current-bid") or soup.find(class_="price")
            current_bid = 0.0
            if bid_elem:
                current_bid = self.clean_price(bid_elem.get_text())

            # Extract end time
            end_time = None
            time_elem = soup.find(class_="time-remaining") or soup.find(class_="countdown")
            if time_elem:
                end_time = self.parse_datetime(time_elem.get_text())

            # Extract location
            location = ""
            loc_elem = soup.find(class_="item-location")
            if loc_elem:
                location = loc_elem.get_text().strip()

            # Extract condition
            condition = ""
            cond_elem = soup.find(text=re.compile(r"Condition:"))
            if cond_elem:
                condition = cond_elem.find_next().get_text().strip()

            # Extract images
            images = []
            for img in soup.find_all("img", class_=re.compile(r"(gallery|main-image)", re.I)):
                src = img.get("src") or img.get("data-src")
                if src and not src.startswith("data:"):
                    images.append(urljoin(self.BASE_URL, src))

            # Extract listing ID
            listing_id = ""
            id_match = re.search(r"-(\d+)$", url)
            if id_match:
                listing_id = id_match.group(1)
            else:
                listing_id = str(hash(url))

            listing = AuctionListing(
                id=f"govplanet_{listing_id}",
                site_name="GovPlanet",
                site_url=self.BASE_URL,
                listing_url=url,
                title=title,
                description=description,
                category=self.detect_category(f"{title} {description}"),
                current_bid=current_bid,
                end_time=end_time,
                location=location,
                condition=condition,
                images=images[:10],
                parsed_attributes=parsed_attrs,
                raw_data={
                    "listing_id": listing_id,
                    "source": "govplanet",
                },
            )

            return listing

        except Exception as e:
            logger.error(f"Failed to parse GovPlanet listing {url}: {e}")
            return None

    def _parse_equipment_title(self, title: str) -> dict:
        """Parse equipment details from title string."""
        attrs = {}

        # Extract year
        year_match = re.search(r"\b(19|20)\d{2}\b", title)
        if year_match:
            attrs["year"] = int(year_match.group())

        # Extract make/model for vehicles
        vehicle_makes = [
            "Ford", "Chevrolet", "Chevy", "Toyota", "Honda", "Dodge", "Jeep",
            "GMC", "Nissan", "RAM", "Caterpillar", "CAT", "John Deere", "JD",
            "Komatsu", "Bobcat", "Case", "New Holland"
        ]
        for make in vehicle_makes:
            if make.lower() in title.lower():
                attrs["make"] = make
                break

        # Extract mileage/hours
        miles_match = re.search(r"(\d[\d,]+)\s*(?:miles?|mi)", title, re.I)
        if miles_match:
            attrs["mileage"] = int(miles_match.group(1).replace(",", ""))

        hours_match = re.search(r"(\d[\d,]+)\s*(?:hours?|hrs?)", title, re.I)
        if hours_match:
            attrs["hours"] = int(hours_match.group(1).replace(",", ""))

        return attrs


# Register the scraper
ScraperRegistry.register("GovPlanetScraper", GovPlanetScraper)
