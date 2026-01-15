"""News processing modules."""
from .extractor import NewsExtractor
from .classifier import EventClassifier

__all__ = ["NewsExtractor", "EventClassifier"]
