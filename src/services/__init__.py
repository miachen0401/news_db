"""Services for news processing."""
from src.services.llm_categorizer import NewsCategorizer
import logging
logger = logging.getLogger(__name__)


__all__ = ["NewsCategorizer"]
