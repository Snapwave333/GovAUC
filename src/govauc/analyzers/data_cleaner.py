"""
AI-powered data cleaning engine for parsing messy government auction listings.
"""

import json
import logging
import re
from typing import Any, Optional

from govauc.models import AuctionListing, AssetCategory

logger = logging.getLogger(__name__)


class DataCleaner:
    """
    AI-powered data cleaning engine that:
    1. Extracts structured data from messy listing descriptions
    2. Normalizes inconsistent formats
    3. Identifies key asset attributes
    4. Enhances listings with parsed metadata
    """

    def __init__(self, llm_client: Optional[Any] = None):
        """
        Initialize the data cleaner.

        Args:
            llm_client: Optional LLM client (OpenAI/Anthropic) for advanced parsing
        """
        self.llm_client = llm_client

    def clean_listing(self, listing: AuctionListing) -> AuctionListing:
        """
        Clean and enhance a single listing with parsed attributes.

        Args:
            listing: Raw auction listing

        Returns:
            Enhanced listing with parsed attributes
        """
        # Parse the title and description
        combined_text = f"{listing.title} {listing.description}"

        # Extract attributes based on category
        if listing.category == AssetCategory.VEHICLE:
            attributes = self._parse_vehicle(combined_text)
        elif listing.category == AssetCategory.ELECTRONICS:
            attributes = self._parse_electronics(combined_text)
        elif listing.category == AssetCategory.REAL_ESTATE:
            attributes = self._parse_real_estate(combined_text)
        elif listing.category == AssetCategory.JEWELRY:
            attributes = self._parse_jewelry(combined_text)
        elif listing.category == AssetCategory.EQUIPMENT:
            attributes = self._parse_equipment(combined_text)
        else:
            attributes = self._parse_generic(combined_text)

        # Merge with existing parsed attributes
        listing.parsed_attributes.update(attributes)

        # Clean and normalize text fields
        listing.title = self._normalize_text(listing.title)
        listing.description = self._normalize_text(listing.description)

        # Update category if we got more info
        if "type" in attributes:
            listing.category = self._refine_category(listing.category, attributes)

        logger.debug(f"Cleaned listing {listing.id}: {attributes}")
        return listing

    def clean_listings_batch(self, listings: list[AuctionListing]) -> list[AuctionListing]:
        """Clean a batch of listings."""
        return [self.clean_listing(listing) for listing in listings]

    def _normalize_text(self, text: str) -> str:
        """Normalize text by removing extra whitespace and cleaning up."""
        # Remove multiple spaces
        text = re.sub(r"\s+", " ", text)
        # Remove special characters that don't add meaning
        text = re.sub(r"[^\w\s\-\.\,\'\"\$\#\&\(\)]", " ", text)
        # Clean up multiple spaces again
        text = re.sub(r"\s+", " ", text)
        return text.strip()

    def _parse_vehicle(self, text: str) -> dict[str, Any]:
        """Parse vehicle-specific attributes."""
        attrs = {}

        # Year
        year_match = re.search(r"\b(19[5-9]\d|20[0-2]\d)\b", text)
        if year_match:
            attrs["year"] = int(year_match.group(1))

        # Make - extensive list
        makes = {
            "Ford": ["ford", "f-150", "f150", "f-250", "mustang", "explorer"],
            "Chevrolet": ["chevrolet", "chevy", "silverado", "tahoe", "corvette"],
            "Toyota": ["toyota", "camry", "corolla", "tacoma", "4runner"],
            "Honda": ["honda", "civic", "accord", "cr-v", "pilot"],
            "Dodge": ["dodge", "ram", "charger", "challenger", "durango"],
            "Jeep": ["jeep", "wrangler", "cherokee", "grand cherokee"],
            "GMC": ["gmc", "sierra", "yukon", "acadia"],
            "Nissan": ["nissan", "altima", "rogue", "frontier", "titan"],
            "BMW": ["bmw", "beamer", "bimmer"],
            "Mercedes": ["mercedes", "mercedes-benz", "benz", "mb"],
            "Audi": ["audi"],
            "Lexus": ["lexus"],
            "Tesla": ["tesla", "model s", "model 3", "model x", "model y"],
            "Harley-Davidson": ["harley", "harley-davidson", "hd"],
            "Kawasaki": ["kawasaki"],
            "Yamaha": ["yamaha"],
        }

        text_lower = text.lower()
        for make, keywords in makes.items():
            if any(kw in text_lower for kw in keywords):
                attrs["make"] = make
                break

        # Model - common patterns
        model_patterns = [
            r"(?:ford\s+)(f-?\d{3}|explorer|mustang|escape|edge|ranger)",
            r"(?:chevy|chevrolet\s+)(silverado|tahoe|suburban|impala|camaro)",
            r"(?:toyota\s+)(camry|corolla|tacoma|tundra|4runner|rav4|highlander)",
            r"(?:honda\s+)(civic|accord|cr-v|pilot|odyssey|ridgeline)",
            r"(?:dodge\s+)(ram|charger|challenger|durango|caravan)",
        ]

        for pattern in model_patterns:
            model_match = re.search(pattern, text_lower)
            if model_match:
                attrs["model"] = model_match.group(1).upper()
                break

        # VIN
        vin_match = re.search(r"\b([A-HJ-NPR-Z0-9]{17})\b", text.upper())
        if vin_match:
            attrs["vin"] = vin_match.group(1)

        # Mileage
        mile_patterns = [
            r"(\d{1,3}(?:,\d{3})*|\d+)\s*(?:miles?|mi\b)",
            r"odometer[:\s]+(\d{1,3}(?:,\d{3})*|\d+)",
            r"mileage[:\s]+(\d{1,3}(?:,\d{3})*|\d+)",
        ]
        for pattern in mile_patterns:
            miles_match = re.search(pattern, text, re.I)
            if miles_match:
                attrs["mileage"] = int(miles_match.group(1).replace(",", ""))
                break

        # Condition keywords
        condition_map = {
            "excellent": ["excellent", "pristine", "mint", "perfect"],
            "good": ["good", "great", "nice", "clean"],
            "fair": ["fair", "average", "moderate"],
            "poor": ["poor", "rough", "damaged", "salvage", "parts only"],
            "unknown": ["as-is", "as is", "unknown"],
        }

        for condition, keywords in condition_map.items():
            if any(kw in text_lower for kw in keywords):
                attrs["condition"] = condition
                break

        # Color
        colors = [
            "black", "white", "silver", "gray", "grey", "red", "blue",
            "green", "gold", "tan", "brown", "orange", "yellow", "purple"
        ]
        for color in colors:
            if re.search(rf"\b{color}\b", text_lower):
                attrs["color"] = color.capitalize()
                break

        # Vehicle type
        types = {
            "sedan": ["sedan", "4dr", "4-door", "four door"],
            "suv": ["suv", "sport utility", "crossover"],
            "truck": ["truck", "pickup", "pick-up"],
            "van": ["van", "minivan", "mini-van"],
            "coupe": ["coupe", "2dr", "2-door", "two door"],
            "motorcycle": ["motorcycle", "bike", "cruiser"],
            "boat": ["boat", "vessel", "watercraft"],
        }

        for vtype, keywords in types.items():
            if any(kw in text_lower for kw in keywords):
                attrs["vehicle_type"] = vtype
                break

        # Engine info
        engine_match = re.search(r"(\d\.\d)\s*(?:L|liter)|V-?(\d)", text, re.I)
        if engine_match:
            if engine_match.group(1):
                attrs["engine"] = f"{engine_match.group(1)}L"
            elif engine_match.group(2):
                attrs["engine"] = f"V{engine_match.group(2)}"

        # Transmission
        if any(kw in text_lower for kw in ["automatic", "auto trans", "at"]):
            attrs["transmission"] = "automatic"
        elif any(kw in text_lower for kw in ["manual", "stick", "mt", "5-speed", "6-speed"]):
            attrs["transmission"] = "manual"

        return attrs

    def _parse_electronics(self, text: str) -> dict[str, Any]:
        """Parse electronics-specific attributes."""
        attrs = {}
        text_lower = text.lower()

        # Brand
        brands = {
            "Dell": ["dell", "optiplex", "latitude", "precision"],
            "HP": ["hp", "hewlett", "packard", "elitebook", "probook"],
            "Lenovo": ["lenovo", "thinkpad", "ideapad"],
            "Apple": ["apple", "mac", "macbook", "imac", "iphone", "ipad"],
            "Samsung": ["samsung", "galaxy"],
            "Microsoft": ["microsoft", "surface"],
            "Cisco": ["cisco"],
            "Intel": ["intel", "nuc"],
        }

        for brand, keywords in brands.items():
            if any(kw in text_lower for kw in keywords):
                attrs["brand"] = brand
                break

        # Type of electronic
        types = {
            "laptop": ["laptop", "notebook", "portable computer"],
            "desktop": ["desktop", "tower", "pc", "workstation"],
            "server": ["server", "rack", "blade"],
            "monitor": ["monitor", "display", "lcd", "led"],
            "printer": ["printer", "copier", "scanner", "mfp"],
            "phone": ["phone", "iphone", "smartphone", "mobile"],
            "tablet": ["tablet", "ipad"],
            "network": ["router", "switch", "firewall", "network"],
        }

        for etype, keywords in types.items():
            if any(kw in text_lower for kw in keywords):
                attrs["type"] = etype
                break

        # Quantity (lot size)
        qty_match = re.search(r"(?:lot\s+of\s+|qty[:\s]+|quantity[:\s]+)(\d+)", text, re.I)
        if qty_match:
            attrs["quantity"] = int(qty_match.group(1))
        else:
            # Look for patterns like "50 Dell Laptops"
            qty_match = re.search(r"(\d+)\s+(?:dell|hp|lenovo|apple|samsung)", text, re.I)
            if qty_match:
                attrs["quantity"] = int(qty_match.group(1))

        # Model numbers
        model_match = re.search(r"(?:model|part|#)[:\s]+([A-Z0-9\-]+)", text, re.I)
        if model_match:
            attrs["model_number"] = model_match.group(1)

        # Specs
        ram_match = re.search(r"(\d+)\s*(?:GB|G)\s*(?:RAM|memory)", text, re.I)
        if ram_match:
            attrs["ram_gb"] = int(ram_match.group(1))

        storage_match = re.search(r"(\d+)\s*(?:GB|TB)\s*(?:SSD|HDD|hard drive|storage)", text, re.I)
        if storage_match:
            attrs["storage"] = storage_match.group(0).strip()

        # Condition
        if "refurbished" in text_lower:
            attrs["condition"] = "refurbished"
        elif any(kw in text_lower for kw in ["new", "sealed", "unopened"]):
            attrs["condition"] = "new"
        elif any(kw in text_lower for kw in ["used", "pre-owned"]):
            attrs["condition"] = "used"
        elif any(kw in text_lower for kw in ["parts", "salvage", "for parts"]):
            attrs["condition"] = "for_parts"

        return attrs

    def _parse_real_estate(self, text: str) -> dict[str, Any]:
        """Parse real estate attributes."""
        attrs = {}
        text_lower = text.lower()

        # Square footage
        sqft_match = re.search(r"(\d{1,3}(?:,\d{3})*)\s*(?:sq\.?\s*ft|square\s*feet)", text, re.I)
        if sqft_match:
            attrs["square_feet"] = int(sqft_match.group(1).replace(",", ""))

        # Acreage
        acre_match = re.search(r"(\d+(?:\.\d+)?)\s*(?:acres?|ac)", text, re.I)
        if acre_match:
            attrs["acres"] = float(acre_match.group(1))

        # Bedrooms/Bathrooms
        bed_match = re.search(r"(\d+)\s*(?:bed|br|bedroom)", text, re.I)
        if bed_match:
            attrs["bedrooms"] = int(bed_match.group(1))

        bath_match = re.search(r"(\d+(?:\.\d)?)\s*(?:bath|ba|bathroom)", text, re.I)
        if bath_match:
            attrs["bathrooms"] = float(bath_match.group(1))

        # Property type
        if any(kw in text_lower for kw in ["single family", "house", "home", "residential"]):
            attrs["property_type"] = "single_family"
        elif any(kw in text_lower for kw in ["condo", "condominium", "unit"]):
            attrs["property_type"] = "condo"
        elif any(kw in text_lower for kw in ["land", "lot", "vacant"]):
            attrs["property_type"] = "land"
        elif any(kw in text_lower for kw in ["commercial", "office", "retail"]):
            attrs["property_type"] = "commercial"

        # Year built
        year_match = re.search(r"(?:built|year)[:\s]+(\d{4})", text, re.I)
        if year_match:
            attrs["year_built"] = int(year_match.group(1))

        return attrs

    def _parse_jewelry(self, text: str) -> dict[str, Any]:
        """Parse jewelry attributes."""
        attrs = {}
        text_lower = text.lower()

        # Metal type
        metals = {
            "gold": ["gold", "kt", "karat", "14k", "18k", "24k"],
            "silver": ["silver", "sterling", ".925"],
            "platinum": ["platinum", "plat"],
        }

        for metal, keywords in metals.items():
            if any(kw in text_lower for kw in keywords):
                attrs["metal"] = metal
                break

        # Gold karat
        karat_match = re.search(r"(\d{1,2})\s*(?:k|kt|karat)", text, re.I)
        if karat_match:
            attrs["karat"] = int(karat_match.group(1))

        # Weight
        weight_match = re.search(r"(\d+(?:\.\d+)?)\s*(?:grams?|g\b|oz|ounces?)", text, re.I)
        if weight_match:
            attrs["weight"] = weight_match.group(0).strip()

        # Gemstones
        gems = ["diamond", "ruby", "emerald", "sapphire", "pearl", "opal"]
        for gem in gems:
            if gem in text_lower:
                attrs["gemstone"] = gem.capitalize()
                break

        # Carat weight for diamonds
        ct_match = re.search(r"(\d+(?:\.\d+)?)\s*(?:ct|carat|carats)", text, re.I)
        if ct_match:
            attrs["carat_weight"] = float(ct_match.group(1))

        # Brand
        brands = ["rolex", "cartier", "tiffany", "bulgari", "omega", "tag heuer"]
        for brand in brands:
            if brand in text_lower:
                attrs["brand"] = brand.title()
                break

        return attrs

    def _parse_equipment(self, text: str) -> dict[str, Any]:
        """Parse equipment and machinery attributes."""
        attrs = {}
        text_lower = text.lower()

        # Equipment type
        types = {
            "forklift": ["forklift", "fork lift", "lift truck"],
            "tractor": ["tractor", "backhoe", "loader"],
            "generator": ["generator", "genset"],
            "compressor": ["compressor", "air compressor"],
            "pump": ["pump", "water pump"],
            "welder": ["welder", "welding"],
        }

        for etype, keywords in types.items():
            if any(kw in text_lower for kw in keywords):
                attrs["type"] = etype
                break

        # Brand
        brands = ["caterpillar", "cat", "john deere", "komatsu", "bobcat", "case", "kubota"]
        for brand in brands:
            if brand in text_lower:
                attrs["brand"] = brand.title()
                break

        # Hours of operation
        hours_match = re.search(r"(\d{1,3}(?:,\d{3})*)\s*(?:hours?|hrs?)", text, re.I)
        if hours_match:
            attrs["hours"] = int(hours_match.group(1).replace(",", ""))

        # Capacity/size
        capacity_match = re.search(r"(\d+(?:,\d+)?)\s*(?:lb|lbs?|ton|hp|kw)", text, re.I)
        if capacity_match:
            attrs["capacity"] = capacity_match.group(0).strip()

        return attrs

    def _parse_generic(self, text: str) -> dict[str, Any]:
        """Parse generic attributes for unknown categories."""
        attrs = {}

        # Quantity
        qty_match = re.search(r"(?:lot\s+of\s+|qty|quantity)[:\s]+(\d+)", text, re.I)
        if qty_match:
            attrs["quantity"] = int(qty_match.group(1))

        # Brand (generic)
        brand_match = re.search(r"(?:brand|make|manufacturer)[:\s]+([A-Za-z]+)", text, re.I)
        if brand_match:
            attrs["brand"] = brand_match.group(1)

        # Model
        model_match = re.search(r"(?:model|part)[:\s#]+([A-Z0-9\-]+)", text, re.I)
        if model_match:
            attrs["model"] = model_match.group(1)

        # Condition
        text_lower = text.lower()
        if "new" in text_lower:
            attrs["condition"] = "new"
        elif "used" in text_lower:
            attrs["condition"] = "used"
        elif any(kw in text_lower for kw in ["damaged", "broken", "salvage"]):
            attrs["condition"] = "damaged"

        return attrs

    def _refine_category(
        self, current_category: AssetCategory, attributes: dict[str, Any]
    ) -> AssetCategory:
        """Refine category based on parsed attributes."""
        # If we found vehicle-specific attributes, it's likely a vehicle
        if any(key in attributes for key in ["vin", "mileage", "vehicle_type"]):
            return AssetCategory.VEHICLE

        # Electronics
        if attributes.get("type") in ["laptop", "desktop", "server", "phone", "tablet"]:
            return AssetCategory.ELECTRONICS

        # Real estate
        if any(key in attributes for key in ["square_feet", "acres", "bedrooms"]):
            return AssetCategory.REAL_ESTATE

        # Jewelry
        if any(key in attributes for key in ["karat", "gemstone", "carat_weight"]):
            return AssetCategory.JEWELRY

        # Equipment
        if attributes.get("hours") or attributes.get("type") in ["forklift", "tractor", "generator"]:
            return AssetCategory.EQUIPMENT

        return current_category

    async def clean_with_llm(self, listing: AuctionListing) -> AuctionListing:
        """
        Use LLM to extract structured data from messy listing text.
        This is the advanced AI-powered parsing method.
        """
        if not self.llm_client:
            return self.clean_listing(listing)

        prompt = f"""
        Extract structured information from this government auction listing:

        Title: {listing.title}
        Description: {listing.description}
        Category: {listing.category.value}

        Extract and return a JSON object with relevant attributes such as:
        - For vehicles: year, make, model, vin, mileage, condition, color, engine, transmission
        - For electronics: brand, type, model_number, quantity, condition, specs
        - For real estate: square_feet, acres, bedrooms, bathrooms, property_type
        - For jewelry: metal, karat, weight, gemstone, brand
        - For equipment: type, brand, hours, capacity

        Only include fields where you have high confidence in the value.
        Return only the JSON object, no other text.
        """

        try:
            # This would call the actual LLM
            # response = await self.llm_client.chat.completions.create(...)
            # For now, fall back to rule-based parsing
            logger.info("LLM parsing not implemented, using rule-based parsing")
            return self.clean_listing(listing)

        except Exception as e:
            logger.error(f"LLM parsing failed: {e}, falling back to rule-based")
            return self.clean_listing(listing)
