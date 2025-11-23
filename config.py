"""Configuration for LLM-based news categorization system."""

# LLM Processing Configuration
LLM_CONFIG = {
    "batch_size": 10,              # Items per LLM API call
    "processing_limit": 20,        # Max items to process per incremental run
    "temperature": 0.3,            # LLM temperature (lower = more consistent)
}

# News Fetching Configuration
FETCH_CONFIG = {
    # Finnhub categories to fetch (will fetch from all listed categories)
    "finnhub_categories": ['general', 'merger'],
    "polygon_limit": 200,          # Max articles from Polygon per fetch
    "buffer_minutes": 1,           # Overlap window for incremental fetching (avoid gaps)
}
