"""
Web scraping framework for government auction sites.
"""

from .base import BaseScraper
from .registry import ScraperRegistry

__all__ = ["BaseScraper", "ScraperRegistry"]
