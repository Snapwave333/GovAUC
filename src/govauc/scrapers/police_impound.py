"""
Police impound lot auction scraper - Local law enforcement seized property.
This is a generic scraper that can be configured for various police auction sites.
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


class PoliceImpoundScraper(BaseScraper):
    """Scraper for police impound and seized property auctions."""

    async def get_listing_urls(self) -> list[str]:
        """Get auction URLs from police impound sites."""
        urls = []

        try:
            html = await self.fetch_page(self.site.url)
            soup = self.parse_html(html)

            # Police sites often list auctions in tables or simple lists
            # Look for links containing typical auction keywords
            link_patterns = [
                r"auction",
                r"seized",
                r"impound",
                r"sale",
                r"item",
                r"lot",
                r"bid",
            ]

            for link in soup.find_all("a", href=True):
                href = link.get("href", "").lower()
                text = link.get_text().lower()

                if any(pattern in href or pattern in text for pattern in link_patterns):
                    full_url = link["href"]
                    if full_url.startswith("/"):
                        full_url = urljoin(self.site.url, full_url)
                    elif not full_url.startswith("http"):
                        full_url = urljoin(self.site.url, full_url)
                    urls.append(full_url)

            # Also check for paginated results
            for page in range(2, 11):  # Check up to 10 pages
                page_url = None

                # Common pagination patterns
                next_link = soup.find("a", text=re.compile(r"Next|Page\s*\d+|>"))
                if next_link:
                    page_url = urljoin(self.site.url, next_link["href"])

                if page_url and page_url not in urls:
                    try:
                        page_html = await self.fetch_page(page_url)
                        page_soup = self.parse_html(page_html)

                        for link in page_soup.find_all("a", href=True):
                            href = link.get("href", "").lower()
                            if any(pattern in href for pattern in link_patterns):
                                full_url = urljoin(self.site.url, link["href"])
                                urls.append(full_url)
                    except Exception:
                        break

        except Exception as e:
            logger.error(f"Error scraping police impound site {self.site.url}: {e}")

        return list(set(urls))

    async def parse_listing(self, url: str) -> Optional[AuctionListing]:
        """Parse a police impound auction listing."""
        try:
            html = await self.fetch_page(url)
            soup = self.parse_html(html)

            # Extract title - police sites often have basic formatting
            title = "Seized Property"
            for tag in ["h1", "h2", "h3", ".title", "#title"]:
                elem = soup.select_one(tag) if tag.startswith((".", "#")) else soup.find(tag)
                if elem:
                    title = elem.get_text().strip()
                    break

            # Extract description
            description = ""
            desc_keywords = ["description", "details", "info", "about"]
            for keyword in desc_keywords:
                desc_elem = soup.find(class_=re.compile(keyword, re.I)) or soup.find(
                    id=re.compile(keyword, re.I)
                )
                if desc_elem:
                    description = desc_elem.get_text().strip()
                    break

            # Police auctions often list vehicles with specific formats
            parsed_attrs = self._parse_seized_property(title + " " + description)

            # Extract bid/price info
            current_bid = 0.0
            price_keywords = ["bid", "price", "amount", "cost"]
            for keyword in price_keywords:
                price_elem = soup.find(class_=re.compile(keyword, re.I)) or soup.find(
                    text=re.compile(rf"{keyword}.*\$", re.I)
                )
                if price_elem:
                    text = price_elem.get_text() if hasattr(price_elem, "get_text") else str(price_elem)
                    current_bid = self.clean_price(text)
                    if current_bid > 0:
                        break

            # Extract auction date/time
            end_time = None
            date_elem = soup.find(text=re.compile(r"(Date|Time|Closes?|Ends?)", re.I))
            if date_elem:
                date_text = date_elem.find_next().get_text() if hasattr(date_elem, "find_next") else str(date_elem)
                end_time = self.parse_datetime(date_text)

            # Extract location
            location = ""
            loc_elem = soup.find(text=re.compile(r"Location|Address|Where", re.I))
            if loc_elem and hasattr(loc_elem, "find_next"):
                location = loc_elem.find_next().get_text().strip()

            # Extract case/lot number
            case_num = ""
            case_match = re.search(r"(?:Case|Lot|Item|#)\s*:?\s*([A-Z0-9\-]+)", html, re.I)
            if case_match:
                case_num = case_match.group(1)

            # Extract images
            images = []
            for img in soup.find_all("img"):
                src = img.get("src") or img.get("data-src", "")
                if src and not src.startswith("data:") and not "logo" in src.lower():
                    images.append(urljoin(self.site.url, src))

            listing_id = case_num or str(hash(url))

            listing = AuctionListing(
                id=f"police_{self.site.name.lower().replace(' ', '_')}_{listing_id}",
                site_name=self.site.name,
                site_url=self.site.url,
                listing_url=url,
                title=title,
                description=description,
                category=self.detect_category(f"{title} {description}"),
                current_bid=current_bid,
                end_time=end_time,
                location=location,
                images=images[:10],
                parsed_attributes=parsed_attrs,
                raw_data={
                    "case_number": case_num,
                    "source": "police_impound",
                },
            )

            return listing

        except Exception as e:
            logger.error(f"Failed to parse police impound listing {url}: {e}")
            return None

    def _parse_seized_property(self, text: str) -> dict:
        """Parse seized property details from text."""
        attrs = {}

        # Extract VIN if present
        vin_match = re.search(r"\b([A-HJ-NPR-Z0-9]{17})\b", text)
        if vin_match:
            attrs["vin"] = vin_match.group(1)

        # Extract year/make/model for vehicles
        year_match = re.search(r"\b(19|20)\d{2}\b", text)
        if year_match:
            attrs["year"] = int(year_match.group())

        # Common vehicle makes
        makes = [
            "Ford", "Chevrolet", "Chevy", "Toyota", "Honda", "Dodge", "Jeep",
            "GMC", "Nissan", "BMW", "Mercedes", "Audi", "Lexus", "Acura",
            "Cadillac", "Buick", "Chrysler", "Infiniti", "Hyundai", "Kia"
        ]
        for make in makes:
            if re.search(rf"\b{make}\b", text, re.I):
                attrs["make"] = make
                break

        # Extract mileage
        miles_match = re.search(r"(\d[\d,]+)\s*(?:miles?|mi)", text, re.I)
        if miles_match:
            attrs["mileage"] = int(miles_match.group(1).replace(",", ""))

        # Extract color
        colors = ["black", "white", "silver", "gray", "grey", "red", "blue", "green", "gold", "tan"]
        for color in colors:
            if re.search(rf"\b{color}\b", text, re.I):
                attrs["color"] = color.capitalize()
                break

        return attrs


# Register the scraper
ScraperRegistry.register("PoliceImpoundScraper", PoliceImpoundScraper)
