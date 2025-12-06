"""Storage layer for news data."""
from src.storage.raw_news_storage import RawNewsStorage
from src.storage.fetch_state_manager import FetchStateManager
import logging
logger = logging.getLogger(__name__)


__all__ = ["RawNewsStorage", "FetchStateManager"]
