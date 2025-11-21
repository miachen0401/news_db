"""Configuration for LLM-based news categorization system."""

# LLM Processing Configuration
LLM_CONFIG = {
    "batch_size": 10,              # Items per LLM API call
    "processing_limit": 20,        # Max items to process per incremental run
    "temperature": 0.3,            # LLM temperature (lower = more consistent)
}

# News Fetching Configuration
FETCH_CONFIG = {
    "polygon_limit": 100,          # Max articles from Polygon per fetch
    "finnhub_limit": 100,          # Finnhub returns ~100 latest articles
    "buffer_minutes": 1,           # Overlap window for incremental fetching (avoid gaps)
}
