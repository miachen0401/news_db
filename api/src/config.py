import logging
logger = logging.getLogger(__name__)

"""Configuration for LLM-based news categorization system."""

# LLM Model Configuration
LLM_MODELS = {
    "categorization": {
        "model": "glm-4-flash",           # Zhipu AI model for categorization (reliable, use glm-4.5-flash in fallback for testing)
        "fallback_model": "glm-4.5-flash",  # Fallback to newer model if primary fails (swapped for reliability)
        "temperature": 0.3,               # Lower = more consistent
        "timeout": 60.0,                  # Request timeout in seconds
        "max_retries": 2,                 # Retry on failure
        "concurrency_limit": 2,           # Max concurrent API calls (glm-4-flash limit: 2, use 1 for safety)
        "delay_between_batches": 2.0,     # Seconds to wait between batches
    },
    "summarization": {
        "model": "glm-4-flash",           # Zhipu AI model for daily summaries
        "temperature": 0.3,               # Lower = more consistent
        "timeout": 120.0,                 # Longer timeout for summaries
        "max_retries": 2,                 # Retry on failure
    }
}

# LLM Processing Configuration
LLM_CONFIG = {
    "batch_size": 5,               # Items per LLM API call (reduced from 10 to avoid rate limits)
    "processing_limit": 20,        # Max items to process per incremental run
    "temperature": 0.3,            # LLM temperature (lower = more consistent) - DEPRECATED, use LLM_MODELS
}

# News Fetching Configuration
FETCH_CONFIG = {
    # Finnhub categories to fetch (will fetch from all listed categories)
    "finnhub_categories": ['general', 'merger'],
    "polygon_limit": 300,          # Max articles from Polygon per fetch
    "buffer_minutes": 0,           # Overlap window for incremental fetching (avoid gaps)
}

COMPANY_NEWS_CONFIG = {
    "enabled": True,               # Enable/disable company news fetching
    "limit": 50,                   # Max news per company per fetch (Finnhub returns up to 50)
    "buffer_minutes": 0,           # Overlap window for incremental fetching
}

ALLOWED_CATEGORIES = [
    "CENTRAL_BANK_POLICY",  # Interest rates, monetary policy decisions
    "GEOPOLITICAL_EVENT",   # Geopolitical news with named governments/leaders
    "INDUSTRY_REGULATION",  # Regulatory/policy actions on specific industries
    "CORPORATE_EARNINGS",   # Earnings, guidance, financial statements
    "CORPORATE_ACTIONS",    # M&A, buybacks, splits, spinoffs, bankruptcies
    "MANAGEMENT_CHANGE",    # CEO/CFO/board-level leadership changes
    "PRODUCT_TECH_UPDATE",  # Product launches, R&D, technology updates
    "BUSINESS_OPERATIONS",  # Supply chain, contracts, partnerships, expansions
    "INCIDENT_LEGAL",       # Lawsuits, investigations, accidents, breaches
    "MACRO_NOBODY",
    "MACRO_ECONOMY",
    "ANALYST_OPINION",
    "NON_FINANCIAL",
    "MARKET_SENTIMENT",
]

# Categories to include in daily summaries and analysis (whitelist approach)
INCLUDED_CATEGORIES = [
    "CENTRAL_BANK_POLICY",  # Interest rates, monetary policy decisions
    "GEOPOLITICAL_EVENT",   # Geopolitical news with named governments/leaders
    "INDUSTRY_REGULATION",  # Regulatory/policy actions on specific industries
    "CORPORATE_EARNINGS",   # Earnings, guidance, financial statements
    "CORPORATE_ACTIONS",    # M&A, buybacks, splits, spinoffs, bankruptcies
    "MANAGEMENT_CHANGE",    # CEO/CFO/board-level leadership changes
    "PRODUCT_TECH_UPDATE",  # Product launches, R&D, technology updates
    "BUSINESS_OPERATIONS",  # Supply chain, contracts, partnerships, expansions
    "INCIDENT_LEGAL",       # Lawsuits, investigations, accidents, breaches
]

# Categories stay in the news database, but not in the daily summary
#    "MACRO_ECONOMY",        # Macroeconomic indicators and official data
#    "ANALYST_OPINION",      # Analyst rating changes, price targets
#    "MARKET_SENTIMENT",     # Investor sentiment, flows, surveys

# Categories that should be filtered out/removed from stock_news table
# These are invalid or unwanted categories that should be excluded from all operations
# MACRO_NOBODY - Geopolitical commentary without specific leaders (too generic)
# NON_FINANCIAL - Non-market news (filtered during processing)
# UNCATEGORIZED - Failed categorization (will be retried, not truly excluded)
# ERROR - Permanent categorization errors (won't retry)
EXCLUDED_CATEGORIES = [
    "MACRO_NOBODY",
    "NON_FINANCIAL",
    "ANALYST_OPINION",
]


# Action Priority Configuration (for distributed processing)
# Lower number = higher priority (processed first)
ACTION_PRIORITY = {
    "process_pending_raw": 1,          # Highest priority: Process pending items in stock_news_raw
    "recategorize_uncategorized": 2,   # High priority: Re-process UNCATEGORIZED in stock_news
    "fetch_and_process": 3,            # Normal priority: Regular incremental fetch + process
    "generate_summary": 4,             # Lower priority: Daily summary generation
}

# Legacy config (deprecated, use ACTION_PRIORITY instead)
PROCESSING_CONFIG = {
    "FETCH_NEWS": 1,
    "PROCESS_NEWS": 2,
    "SUMMARIZE_NEWS": 3,
}