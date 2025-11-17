"""
Market value analysis module for estimating real market prices.
Integrates with KBB, eBay, and other pricing sources.
"""

import asyncio
import json
import logging
import re
from datetime import datetime
from typing import Any, Optional

import aiohttp
from tenacity import retry, stop_after_attempt, wait_exponential

from govauc.models import AuctionListing, AssetCategory, MarketValueEstimate

logger = logging.getLogger(__name__)


class MarketValueAnalyzer:
    """
    Analyzes market values from multiple sources:
    - Kelley Blue Book (vehicles)
    - eBay completed sales
    - Amazon prices
    - Specialized databases
    """

    def __init__(self, config: Optional[dict[str, Any]] = None):
        """
        Initialize the market value analyzer.

        Args:
            config: Configuration with API keys and preferences
        """
        self.config = config or {}
        self.session: Optional[aiohttp.ClientSession] = None

        # API endpoints (would be configured with real keys)
        self.ebay_app_id = self.config.get("ebay_app_id", "")
        self.kbb_api_key = self.config.get("kbb_api_key", "")

    async def __aenter__(self):
        """Async context manager entry."""
        self.session = aiohttp.ClientSession(
            timeout=aiohttp.ClientTimeout(total=30)
        )
        return self

    async def __aexit__(self, exc_type, exc_val, exc_tb):
        """Async context manager exit."""
        if self.session:
            await self.session.close()

    async def estimate_market_value(
        self, listing: AuctionListing
    ) -> list[MarketValueEstimate]:
        """
        Get market value estimates from multiple sources.

        Args:
            listing: The auction listing to analyze

        Returns:
            List of market value estimates from different sources
        """
        estimates = []

        # Choose estimation methods based on category
        if listing.category == AssetCategory.VEHICLE:
            kbb_estimate = await self.estimate_vehicle_kbb(listing)
            if kbb_estimate:
                estimates.append(kbb_estimate)

            ebay_estimate = await self.estimate_from_ebay(listing)
            if ebay_estimate:
                estimates.append(ebay_estimate)

        elif listing.category == AssetCategory.ELECTRONICS:
            ebay_estimate = await self.estimate_from_ebay(listing)
            if ebay_estimate:
                estimates.append(ebay_estimate)

            amazon_estimate = await self.estimate_from_amazon(listing)
            if amazon_estimate:
                estimates.append(amazon_estimate)

        elif listing.category == AssetCategory.JEWELRY:
            ebay_estimate = await self.estimate_from_ebay(listing)
            if ebay_estimate:
                estimates.append(ebay_estimate)

            metal_estimate = await self.estimate_jewelry_metal_value(listing)
            if metal_estimate:
                estimates.append(metal_estimate)

        else:
            # Generic eBay search for other categories
            ebay_estimate = await self.estimate_from_ebay(listing)
            if ebay_estimate:
                estimates.append(ebay_estimate)

        # If no estimates found, use heuristic pricing
        if not estimates:
            heuristic = self.estimate_heuristic(listing)
            if heuristic:
                estimates.append(heuristic)

        return estimates

    async def estimate_vehicle_kbb(
        self, listing: AuctionListing
    ) -> Optional[MarketValueEstimate]:
        """
        Estimate vehicle value using Kelley Blue Book methodology.

        Note: In production, this would call the actual KBB API.
        This implementation uses heuristic pricing based on known patterns.
        """
        attrs = listing.parsed_attributes

        # Check if we have enough info
        year = attrs.get("year")
        make = attrs.get("make")

        if not year or not make:
            logger.debug(f"Insufficient vehicle info for KBB estimate")
            return None

        # Base prices by make (average used car prices)
        base_prices = {
            "Ford": 18000,
            "Chevrolet": 17500,
            "Toyota": 20000,
            "Honda": 19500,
            "Dodge": 16000,
            "Jeep": 22000,
            "GMC": 21000,
            "Nissan": 16500,
            "BMW": 25000,
            "Mercedes": 28000,
            "Audi": 26000,
            "Lexus": 27000,
            "Tesla": 35000,
        }

        base_price = base_prices.get(make, 15000)

        # Adjust for year (depreciation)
        current_year = datetime.now().year
        age = current_year - year

        if age <= 0:
            depreciation = 0.0
        elif age == 1:
            depreciation = 0.15  # 15% first year
        elif age == 2:
            depreciation = 0.30
        elif age == 3:
            depreciation = 0.42
        elif age == 4:
            depreciation = 0.52
        elif age == 5:
            depreciation = 0.60
        else:
            # After 5 years, roughly 10% per year additional
            depreciation = min(0.95, 0.60 + (age - 5) * 0.08)

        estimated_value = base_price * (1 - depreciation)

        # Adjust for mileage
        mileage = attrs.get("mileage", 0)
        if mileage:
            avg_miles_per_year = 12000
            expected_miles = age * avg_miles_per_year

            if mileage > expected_miles * 1.5:  # High mileage
                estimated_value *= 0.85
            elif mileage < expected_miles * 0.5:  # Low mileage
                estimated_value *= 1.10

        # Adjust for condition
        condition = attrs.get("condition", "unknown")
        condition_multipliers = {
            "excellent": 1.15,
            "good": 1.05,
            "fair": 0.95,
            "poor": 0.70,
            "unknown": 0.90,  # Assume worst case for unknowns
        }
        estimated_value *= condition_multipliers.get(condition, 0.90)

        # Confidence based on available info
        confidence = 0.5
        if year and make:
            confidence += 0.2
        if mileage:
            confidence += 0.15
        if condition != "unknown":
            confidence += 0.15

        return MarketValueEstimate(
            source="KBB_estimate",
            value=round(estimated_value, 2),
            confidence=min(1.0, confidence),
            data_points=1,
            metadata={
                "year": year,
                "make": make,
                "mileage": mileage,
                "condition": condition,
                "depreciation_rate": depreciation,
            },
        )

    async def estimate_from_ebay(
        self, listing: AuctionListing
    ) -> Optional[MarketValueEstimate]:
        """
        Estimate value based on eBay sold listings.

        In production, this would use the eBay Finding API.
        This implementation uses heuristic-based estimation.
        """
        attrs = listing.parsed_attributes

        # Build search query from listing attributes
        search_terms = []

        if listing.category == AssetCategory.ELECTRONICS:
            brand = attrs.get("brand", "")
            model = attrs.get("model_number", "")
            etype = attrs.get("type", "")

            if brand:
                search_terms.append(brand)
            if model:
                search_terms.append(model)
            if etype:
                search_terms.append(etype)

            # Price per unit estimates
            unit_prices = {
                "laptop": {
                    "Dell": 150,
                    "HP": 140,
                    "Lenovo": 160,
                    "Apple": 450,
                },
                "desktop": {
                    "Dell": 120,
                    "HP": 115,
                    "Lenovo": 125,
                },
                "monitor": {
                    "Dell": 80,
                    "HP": 75,
                    "Samsung": 90,
                },
                "phone": {
                    "Apple": 350,
                    "Samsung": 250,
                },
            }

            etype = attrs.get("type", "laptop")
            brand = attrs.get("brand", "Dell")

            base_price = unit_prices.get(etype, {}).get(brand, 100)

            # Adjust for condition
            condition = attrs.get("condition", "used")
            if condition == "refurbished":
                base_price *= 1.2
            elif condition == "new":
                base_price *= 1.8
            elif condition == "for_parts":
                base_price *= 0.3

            # Multiply by quantity
            quantity = attrs.get("quantity", listing.quantity)
            total_value = base_price * quantity

            confidence = 0.6
            if brand and etype:
                confidence += 0.2
            if quantity > 1:
                confidence -= 0.1  # Less certain about bulk pricing

            return MarketValueEstimate(
                source="eBay_estimate",
                value=round(total_value, 2),
                confidence=min(1.0, confidence),
                data_points=quantity,
                metadata={
                    "search_terms": search_terms,
                    "unit_price": base_price,
                    "quantity": quantity,
                    "condition": condition,
                },
            )

        elif listing.category == AssetCategory.VEHICLE:
            # eBay vehicle estimates
            year = attrs.get("year", 2015)
            make = attrs.get("make", "")

            if not make:
                return None

            # Average eBay sold prices by make
            ebay_prices = {
                "Ford": 16000,
                "Chevrolet": 15500,
                "Toyota": 18500,
                "Honda": 18000,
                "Dodge": 14500,
                "Jeep": 20000,
            }

            base_price = ebay_prices.get(make, 14000)

            # Age adjustment
            current_year = datetime.now().year
            age = max(0, current_year - year)
            depreciation = min(0.90, age * 0.10)

            value = base_price * (1 - depreciation)

            return MarketValueEstimate(
                source="eBay_estimate",
                value=round(value, 2),
                confidence=0.55,
                data_points=1,
                metadata={
                    "year": year,
                    "make": make,
                    "age": age,
                },
            )

        # Generic item estimation
        base_value = max(listing.current_bid * 3, 100)

        return MarketValueEstimate(
            source="eBay_estimate",
            value=round(base_value, 2),
            confidence=0.4,
            data_points=1,
            metadata={"method": "generic_estimate"},
        )

    async def estimate_from_amazon(
        self, listing: AuctionListing
    ) -> Optional[MarketValueEstimate]:
        """
        Estimate electronics value based on Amazon new prices.
        Uses heuristic pricing for common electronics.
        """
        if listing.category != AssetCategory.ELECTRONICS:
            return None

        attrs = listing.parsed_attributes

        # New prices on Amazon (then depreciate for used)
        new_prices = {
            "laptop": {
                "Dell": 600,
                "HP": 550,
                "Lenovo": 650,
                "Apple": 1200,
                "Microsoft": 900,
            },
            "desktop": {
                "Dell": 500,
                "HP": 480,
                "Lenovo": 520,
            },
            "tablet": {
                "Apple": 400,
                "Samsung": 350,
                "Microsoft": 500,
            },
        }

        etype = attrs.get("type", "laptop")
        brand = attrs.get("brand", "Dell")

        new_price = new_prices.get(etype, {}).get(brand, 400)

        # Depreciation for used goods
        condition = attrs.get("condition", "used")
        if condition == "new":
            value = new_price
        elif condition == "refurbished":
            value = new_price * 0.70
        elif condition == "used":
            value = new_price * 0.50
        else:  # for_parts
            value = new_price * 0.20

        quantity = attrs.get("quantity", listing.quantity)
        total_value = value * quantity

        return MarketValueEstimate(
            source="Amazon_estimate",
            value=round(total_value, 2),
            confidence=0.5,
            data_points=quantity,
            metadata={
                "new_price": new_price,
                "condition": condition,
                "quantity": quantity,
            },
        )

    async def estimate_jewelry_metal_value(
        self, listing: AuctionListing
    ) -> Optional[MarketValueEstimate]:
        """
        Estimate jewelry value based on metal content.
        Uses spot prices for gold/silver.
        """
        attrs = listing.parsed_attributes

        metal = attrs.get("metal")
        if not metal:
            return None

        # Spot prices (USD per gram) - these would be fetched in production
        spot_prices = {
            "gold": 60.0,  # Approximate
            "silver": 0.75,
            "platinum": 32.0,
        }

        spot_price = spot_prices.get(metal.lower(), 0)
        if not spot_price:
            return None

        # Parse weight
        weight_str = attrs.get("weight", "")
        weight_grams = 0.0

        if weight_str:
            if "oz" in weight_str.lower() or "ounce" in weight_str.lower():
                oz_match = re.search(r"(\d+(?:\.\d+)?)", weight_str)
                if oz_match:
                    weight_grams = float(oz_match.group(1)) * 31.1  # Troy ounce
            else:
                g_match = re.search(r"(\d+(?:\.\d+)?)", weight_str)
                if g_match:
                    weight_grams = float(g_match.group(1))

        if not weight_grams:
            # Estimate weight if not provided
            weight_grams = 10.0  # Conservative estimate

        # Adjust for karat (gold purity)
        karat = attrs.get("karat", 14)
        purity = karat / 24.0

        metal_value = weight_grams * spot_price * purity

        # Add premium for craftsmanship (typically 30-100% above melt value)
        craftsmanship_premium = 1.5
        total_value = metal_value * craftsmanship_premium

        # Add value for gemstones
        carat_weight = attrs.get("carat_weight", 0)
        if carat_weight > 0:
            # Diamond pricing is complex, use rough estimate
            diamond_value = carat_weight * 2000  # Very rough estimate
            total_value += diamond_value

        return MarketValueEstimate(
            source="metal_value_estimate",
            value=round(total_value, 2),
            confidence=0.45,
            data_points=1,
            metadata={
                "metal": metal,
                "weight_grams": weight_grams,
                "karat": karat,
                "spot_price": spot_price,
                "carat_weight": carat_weight,
            },
        )

    def estimate_heuristic(
        self, listing: AuctionListing
    ) -> Optional[MarketValueEstimate]:
        """
        Fallback heuristic estimation when other methods fail.
        Uses category-based multipliers on current bid.
        """
        # Category-based typical markup from auction to retail
        category_multipliers = {
            AssetCategory.VEHICLE: 2.5,
            AssetCategory.ELECTRONICS: 3.0,
            AssetCategory.REAL_ESTATE: 1.5,
            AssetCategory.JEWELRY: 4.0,
            AssetCategory.EQUIPMENT: 2.0,
            AssetCategory.FURNITURE: 2.5,
            AssetCategory.INDUSTRIAL: 2.0,
            AssetCategory.OTHER: 2.0,
        }

        multiplier = category_multipliers.get(listing.category, 2.0)

        # Use current bid as base, but ensure minimum
        base = max(listing.current_bid, listing.starting_bid, 50)
        estimated_value = base * multiplier

        # Very low confidence for heuristic
        return MarketValueEstimate(
            source="heuristic",
            value=round(estimated_value, 2),
            confidence=0.25,
            data_points=1,
            metadata={
                "multiplier": multiplier,
                "base_price": base,
                "method": "category_multiplier",
            },
        )

    def combine_estimates(
        self, estimates: list[MarketValueEstimate]
    ) -> Optional[float]:
        """
        Combine multiple estimates into a single weighted value.

        Args:
            estimates: List of market value estimates

        Returns:
            Weighted average market value
        """
        if not estimates:
            return None

        # Weight by confidence
        total_weight = sum(e.confidence * e.data_points for e in estimates)
        if total_weight == 0:
            return None

        weighted_sum = sum(
            e.value * e.confidence * e.data_points for e in estimates
        )

        return round(weighted_sum / total_weight, 2)

    async def analyze_listing(self, listing: AuctionListing) -> AuctionListing:
        """
        Fully analyze a listing and update its market value estimates.

        Args:
            listing: Listing to analyze

        Returns:
            Updated listing with market value data
        """
        estimates = await self.estimate_market_value(listing)

        if estimates:
            listing.estimated_market_value = self.combine_estimates(estimates)

            # Calculate confidence as average of estimates
            listing.confidence_score = sum(e.confidence for e in estimates) / len(
                estimates
            )

            # Store estimates in raw_data for reference
            listing.raw_data["market_estimates"] = [
                {
                    "source": e.source,
                    "value": e.value,
                    "confidence": e.confidence,
                    "metadata": e.metadata,
                }
                for e in estimates
            ]

        listing.updated_at = datetime.utcnow()
        return listing
