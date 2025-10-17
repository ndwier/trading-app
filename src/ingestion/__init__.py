"""Data ingestion package for collecting trading disclosures."""

from .base import BaseIngester, IngestionError
from .politician_scraper import PoliticianScraper
from .sec_scraper import SECScraper
from .data_normalizer import DataNormalizer

__all__ = [
    "BaseIngester",
    "IngestionError", 
    "PoliticianScraper",
    "SECScraper",
    "DataNormalizer"
]
