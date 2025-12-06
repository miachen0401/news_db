"""Data models for news fetching system."""
from src.models.raw_news import RawNewsItem, ProcessingStatus
import logging
logger = logging.getLogger(__name__)


__all__ = ["RawNewsItem", "ProcessingStatus"]
