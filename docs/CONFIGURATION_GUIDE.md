# Configuration Guide

All configurable parameters are centralized in `config.py`. Edit this file to adjust system behavior without modifying the code.

---

## Configuration File: `config.py`

### LLM Processing Configuration

```python
LLM_CONFIG = {
    "batch_size": 10,              # Items per LLM API call
    "processing_limit": 20,        # Max items to process per incremental run
    "temperature": 0.3,            # LLM temperature (0.0-1.0)
}
```

**Parameters:**

- **`batch_size`** (default: 10)
  - Number of news items sent to LLM in each API call
  - Lower = more API calls, but less cost per call
  - Higher = fewer API calls, but more tokens per call
  - Recommended: 10-20 for optimal balance
  - Used in: `LLMNewsProcessor.process_unprocessed_batch()`

- **`processing_limit`** (default: 20)
  - Maximum number of items to fetch and process per incremental run
  - Controls how many unprocessed items are pulled from stock_news_raw
  - Lower = faster runs, good for frequent updates
  - Higher = fewer runs needed, better for batch processing
  - Recommended: 20 for frequent updates, 50-100 for batch processing
  - Used in: `fetch_incremental_llm.py` main loop

- **`temperature`** (default: 0.3)
  - LLM randomness/creativity level (0.0 = deterministic, 1.0 = creative)
  - Lower = more consistent categorization (recommended for production)
  - Higher = more diverse categories (useful for testing)
  - Recommended: 0.3 for production, 0.5-0.7 for experimentation
  - Used in: `NewsCategorizer.categorize_batch()` API calls

---

### News Fetching Configuration

```python
FETCH_CONFIG = {
    "polygon_limit": 200,          # Max articles from Polygon per fetch
    "finnhub_limit": 200,          # Finnhub returns ~100 latest articles
    "buffer_minutes": 1,           # Overlap window for incremental fetching
}
```

**Parameters:**

- **`polygon_limit`** (default: 200)
  - Maximum number of articles to fetch from Polygon API per request
  - Polygon free tier: 5 requests/min
  - Higher = more news per fetch, but hits rate limits faster
  - Recommended: 100-200 for daily updates, 500+ for initial backfill
  - Used in: `fetch_incremental_llm.py`, `test_fetch_llm_for_new_databse.py`

- **`finnhub_limit`** (default: 200)
  - **Note:** This is NOT used by Finnhub API (they always return ~100 latest)
  - Kept for consistency and future potential pagination
  - Finnhub API does not support date filtering or custom limits
  - Used in: Documentation only (Finnhub API doesn't respect this parameter)

- **`buffer_minutes`** (default: 1)
  - Overlap window when fetching incremental news
  - Prevents missing news due to timing issues
  - Example: If last fetch was at 10:00, next fetch starts at 9:59 (1-min buffer)
  - Lower = less overlap, faster fetches (risk missing news)
  - Higher = more overlap, more duplicates caught by dedup (safer)
  - Recommended: 1-2 minutes for production
  - Used in: `FetchStateManager.get_last_fetch_time()`

---

## How Configuration is Used

### In `fetch_incremental_llm.py`:

```python
from config import LLM_CONFIG, FETCH_CONFIG

# 1. Fetch window with buffer
finnhub_from, finnhub_to = await fetch_state.get_last_fetch_time(
    symbol="GENERAL",
    fetch_source="finnhub",
    buffer_minutes=FETCH_CONFIG['buffer_minutes']  # ← Uses config
)

# 2. Polygon fetch limit
polygon_items = await general_fetcher.fetch_polygon_general_news(
    from_date=polygon_from_str,
    to_date=polygon_to_str,
    limit=FETCH_CONFIG['polygon_limit']  # ← Uses config
)

# 3. LLM processing limit
batch_stats = await llm_processor.process_unprocessed_batch(
    limit=LLM_CONFIG['processing_limit']  # ← Uses config
)
```

### In `LLMNewsProcessor`:

```python
from config import LLM_CONFIG

# LLM batch size
categorized = await self.categorizer.categorize_batch(
    news_for_llm,
    batch_size=LLM_CONFIG['batch_size']  # ← Uses config
)
```

### In `NewsCategorizer`:

```python
from config import LLM_CONFIG

# LLM API call
response = await self.client.post(
    self.base_url,
    json={
        "model": self.model,
        "messages": [...],
        "temperature": LLM_CONFIG['temperature']  # ← Uses config
    }
)
```

---

## Configuration Scenarios

### Scenario 1: High-Frequency Updates (Every 15 minutes)

```python
LLM_CONFIG = {
    "batch_size": 10,              # Small batches for quick processing
    "processing_limit": 20,        # Process fewer items per run
    "temperature": 0.3,            # Consistent categorization
}

FETCH_CONFIG = {
    "polygon_limit": 100,          # Moderate fetch size
    "buffer_minutes": 1,           # Minimal overlap
}
```

**Pros:** Fast execution, frequent updates
**Cons:** More API calls, may miss large news bursts

---

### Scenario 2: Hourly/Daily Batch Processing

```python
LLM_CONFIG = {
    "batch_size": 20,              # Larger batches for efficiency
    "processing_limit": 100,       # Process many items per run
    "temperature": 0.3,            # Consistent categorization
}

FETCH_CONFIG = {
    "polygon_limit": 500,          # Fetch many articles at once
    "buffer_minutes": 5,           # Larger buffer for safety
}
```

**Pros:** Fewer runs, efficient API usage
**Cons:** Slower execution, less frequent updates

---

### Scenario 3: Initial Database Backfill

```python
LLM_CONFIG = {
    "batch_size": 20,              # Efficient batch processing
    "processing_limit": 100,       # Process many at once
    "temperature": 0.3,            # Consistent categorization
}

FETCH_CONFIG = {
    "polygon_limit": 1000,         # Fetch maximum articles
    "buffer_minutes": 0,           # No buffer needed for historical data
}
```

**Pros:** Fast backfill of historical data
**Cons:** May hit API rate limits, requires monitoring

---

### Scenario 4: Testing/Experimentation

```python
LLM_CONFIG = {
    "batch_size": 5,               # Small batches for easier debugging
    "processing_limit": 10,        # Process few items for quick tests
    "temperature": 0.5,            # More variety for testing categories
}

FETCH_CONFIG = {
    "polygon_limit": 50,           # Small fetch size for testing
    "buffer_minutes": 2,           # Larger buffer for safety
}
```

**Pros:** Easy debugging, varied results
**Cons:** Inefficient for production

---

## Monitoring Configuration Impact

### Check Processing Speed:

```sql
-- Average processing time per batch
SELECT
    processing_status,
    COUNT(*) as count,
    AVG(EXTRACT(EPOCH FROM (processed_at - created_at))) as avg_seconds
FROM stock_news_raw
WHERE processing_status IN ('completed', 'failed')
GROUP BY processing_status;
```

### Check Fetch Efficiency:

```sql
-- Articles fetched vs stored (duplicate rate)
SELECT
    fetch_source,
    SUM(articles_fetched) as total_fetched,
    SUM(articles_stored) as total_stored,
    ROUND(100.0 * SUM(articles_stored) / NULLIF(SUM(articles_fetched), 0), 2) as storage_rate
FROM fetch_state
GROUP BY fetch_source;
```

### Check LLM Categorization Distribution:

```sql
-- Category distribution (quality check)
SELECT
    category,
    COUNT(*) as count,
    ROUND(100.0 * COUNT(*) / SUM(COUNT(*)) OVER (), 2) as percentage
FROM stock_news
GROUP BY category
ORDER BY count DESC;
```

---

## Best Practices

1. **Start Conservative:**
   - Use default values (batch_size=10, processing_limit=20)
   - Monitor performance and adjust gradually

2. **Match Your Update Frequency:**
   - Frequent updates (15-30 min): Lower limits (10-20)
   - Hourly updates: Medium limits (50-100)
   - Daily updates: Higher limits (100-500)

3. **Consider API Rate Limits:**
   - Polygon free tier: 5 requests/min
   - Zhipu AI: Monitor your quota
   - Adjust `polygon_limit` and `batch_size` to stay within limits

4. **Monitor Cost:**
   - LLM API charges per token
   - Larger `batch_size` = more tokens per call
   - Balance efficiency vs. cost

5. **Temperature Settings:**
   - Production: 0.3 (consistent)
   - Testing new categories: 0.5-0.7 (variety)
   - Never use 0.0 (too rigid) or 1.0 (too random)

---

## Quick Reference Table

| Parameter | Location | Default | Min | Max | Impact |
|-----------|----------|---------|-----|-----|--------|
| `batch_size` | LLM_CONFIG | 10 | 1 | 50 | LLM API calls |
| `processing_limit` | LLM_CONFIG | 20 | 1 | 500 | Items per run |
| `temperature` | LLM_CONFIG | 0.3 | 0.0 | 1.0 | Category consistency |
| `polygon_limit` | FETCH_CONFIG | 200 | 10 | 1000 | Articles per fetch |
| `buffer_minutes` | FETCH_CONFIG | 1 | 0 | 10 | Overlap window |

---

## Troubleshooting

**Issue: Too many duplicates**
→ Increase `buffer_minutes` from 1 to 2-3

**Issue: Missing news between runs**
→ Increase `buffer_minutes` or check fetch_state timestamps

**Issue: LLM API quota exceeded**
→ Decrease `batch_size` or `processing_limit`

**Issue: Slow processing**
→ Increase `batch_size` (up to 20) for fewer API calls

**Issue: Inconsistent categories**
→ Lower `temperature` (to 0.2) for more consistency

**Issue: Rate limit errors from Polygon**
→ Decrease `polygon_limit` (to 100 or less)
