# Change Records

## 2025-12-30 11:30: Fixed critical infinite loop in re-categorization when LLM returns wrong category
Prevents infinite loop by fetching all items needing re-categorization ONCE before processing, instead of continuously querying database. Modified `recategorize_batch()` to accept optional `items_to_fix` parameter - when provided, processes those specific items instead of querying database. Items are processed once per run; any remaining items with wrong categories will be picked up on next run. Removed unused imports (List, RawNewsItem) from llm_news_processor.py.

## 2025-12-30 10:45: Enhanced project documentation with comprehensive structure guide
Created PROJECT_STRUCTURE.txt with complete directory tree, database schemas, configurations, and workflows. Updated README.md to reference new structure file. Expanded QUICK_API_REFERENCE.md with detailed endpoint documentation, response formats, Python usage examples, and common workflows.

## 2025-11-18 15:00: Refactored news_db from news_agent submodule to standalone repository
Created UV-based environment, removed backend dependencies, implemented standalone modules.

## 2025-11-18 15:30: Created migration scripts for existing stock_news table
Analyzed current schema and generated adjustment queries for LIFO stack compatibility.

## 2025-11-18 16:00: Fixed DROP INDEX error in migration script
Changed from DROP INDEX to ALTER TABLE DROP CONSTRAINT for constraint-backed index.

---

## Session 1: Initial Refactoring (2025-11-18)

### Files Created:
- `.gitignore` - Python project ignore rules
- `pyproject.toml` - UV project configuration
- `db/stock_news.py` - Standalone StockNewsDB class
- `schema_stock_news.sql` - Stock news table schema
- `SETUP.md` - Installation and setup guide

### Files Modified:
- `fetchers/finnhub_fetcher.py` - Removed backend imports, standalone FinnhubClient
- `processors/news_processor.py` - Uses local StockNewsDB
- `storage/raw_news_storage.py` - Absolute imports
- `test_fetch_news.py` - Local imports
- All `__init__.py` files - Absolute imports
- `README.md` - Updated usage examples

### Key Changes:
- Replaced `backend.app.*` imports → standalone implementations
- Relative imports → absolute imports
- Created LIFO stack implementation in StockNewsDB
- Set up UV environment with all dependencies

### Test Result:
✅ Successfully fetched 60 articles from Finnhub and stored in Supabase

---

## Session 2: Schema Migration (2025-11-18)

### Files Created:
- `adjust_stock_news_table.sql` - Migration script for existing table
- `check_stock_news_schema.sql` - Schema inspection queries
- `docs/FIX_Database_Docs.md` - Database fix documentation
- `docs/RECORD_Change.md` - This file

### Schema Analysis:
- Current table has 11 columns, needs 4 more
- Has `position_in_stack` (critical for LIFO)
- Missing: source_id, external_id, metadata, updated_at
- Index issue: UNIQUE on url (should be symbol+url)

### Fix Applied:
- Changed `DROP INDEX` → `ALTER TABLE DROP CONSTRAINT` (line 64)
- Properly handles constraint-backed unique index

## 2025-11-18 16:15: Investigated processing limit and failures
Test script only processes 10 items at a time; created test_process_all.py to handle all pending items.

### Issue Identified:
- `test_fetch_news.py` has `limit=10` on line 120
- Only first 10 pending items (all AAPL) were processed
- TSLA and GOOGL remain unprocessed (pending)
- 10 items failed processing (need to check error_log)

### Files Created:
- `check_failed_items.sql` - Query to check failed processing errors
- `test_process_all.py` - Process all pending items in batches

### Next Steps:
1. Run `check_failed_items.sql` to see why 10 items failed
2. Run `test_process_all.py` to process remaining items

## 2025-11-18 16:30: Added Polygon as second news source
Implemented PolygonNewsFetcher with full integration for fetching, storing, and processing news.

### Files Created:
- `fetchers/polygon_fetcher.py` - Polygon.io API client and fetcher
- `test_multi_source.py` - Test script for both Finnhub and Polygon

### Files Modified:
- `models/raw_news.py` - Added `from_polygon_response()` method
- `processors/news_processor.py` - Added `_process_polygon_json()` method
- `fetchers/__init__.py` - Export PolygonNewsFetcher

### Implementation Details:
- Polygon API endpoint: `/v2/reference/news`
- API key env var: `MASSIVE_API_KEY`
- Response format: ISO 8601 timestamps, different field names than Finnhub
- Rate limit handling: 200ms delay between requests (5 req/min free tier)
- Metadata stored: author, publisher, image_url, amp_url, tickers list

### Usage:
```bash
uv run python test_multi_source.py
```

## 2025-11-18 16:45: Created today's news fetcher with configurable symbols
Added dynamic test script that fetches only today's news with configurable symbol list.

### Files Created:
- `test_today_news.py` - Fetch today's news only (dynamic date)
- `config.py` - Centralized configuration for symbols and fetch settings

### Features:
- **Dynamic date:** Always fetches from today (00:00:00 to current time)
- **Configurable symbols:** Edit `config.py` to change which symbols to fetch
- **Both sources:** Fetches from Finnhub and Polygon
- **Auto-process:** Processes all pending items automatically
- **Summary view:** Shows news stacks with source and publisher info

### Configuration:
Edit `config.py` to customize:
- `DEFAULT_SYMBOLS` - List of symbols to fetch
- `FETCH_CONFIG` - Fetch and processing settings
- Predefined lists: `TOP_STOCKS`, `TECH_STOCKS`

### Usage:
```bash
uv run python test_today_news.py
```

Runs daily to fetch latest news for configured symbols.

## 2025-11-18 17:00: Implemented incremental fetching with timestamp tracking
Created production-ready incremental fetching system to avoid re-fetching old news.

### Files Created:
- `schema_fetch_state.sql` - Tracks last fetch timestamp per symbol+source
- `storage/fetch_state_manager.py` - Manages fetch state and incremental windows
- `fetch_incremental.py` - Production incremental fetcher

### How It Works:
1. **First run:** Fetches last 7 days of news, stores timestamp
2. **Subsequent runs:** Fetches only from (last_timestamp - 1min) to now
3. **Buffer window:** 1-minute overlap prevents missing news
4. **Duplicate check:** Still active as safety net

### Key Features:
- **Timestamp tracking:** Per symbol+source combination
- **Automatic incremental:** No manual configuration needed
- **Buffer window:** Configurable overlap (default 1 minute)
- **Stale detection:** Find symbols that haven't been fetched recently
- **Reset capability:** Force full refresh when needed

### Database Schema:
- `fetch_state` table: Tracks last_fetch_from, last_fetch_to
- `v_fetch_state_status` view: Shows time since last fetch
- Unique constraint on (symbol, fetch_source)

### Production Benefits:
- **Efficiency:** Only fetch new news, not entire history
- **API savings:** Reduce API calls dramatically
- **Speed:** Faster execution (fewer items to check)
- **Scalability:** Can run frequently (every 5-15 minutes)

### Usage:
```bash
# Run schema first (one time)
cat schema_fetch_state.sql | supabase sql

# Run incremental fetch
uv run python fetch_incremental.py
```

### Performance:
- First run: ~7 days of news
- Subsequent runs: Only last few minutes/hours
- Duplicate checking: Still active but processes fewer items

## 2025-11-18 17:15: Changed first run to fetch last 24 hours instead of 7 days
Modified default fetch window for first run from 7 days to 1 day (yesterday only).

### Change:
- `fetch_state_manager.py` line 49: Changed from `timedelta(days=7)` to `timedelta(days=1)`
- First run now fetches last 24 hours instead of full week
- Reduces initial fetch volume while still getting recent news

## 2025-11-20 01:15: Added fetch_source column to track API source
Added separate column to distinguish between news source (publisher) and fetch source (API).

### Files Created:
- `alter_add_fetch_source.sql` - Adds fetch_source column to stock_news table

### Files Modified:
- `processors/news_processor.py` - Added fetch_source to processed_data (both Finnhub and Polygon)
- `db/stock_news.py` - Added fetch_source to news_item dict

### Column Distinction:
- **source**: News publisher (Reuters, Bloomberg, WSJ, etc.)
- **fetch_source**: API that fetched the news (finnhub, polygon, newsapi, etc.)

### Usage for Data Quality Analysis:
```sql
-- Compare news count by API source
SELECT fetch_source, COUNT(*) FROM stock_news GROUP BY fetch_source;

-- Compare duplicates by source
SELECT fetch_source, COUNT(DISTINCT url) as unique_urls, COUNT(*) as total
FROM stock_news GROUP BY fetch_source;

-- Find overlapping news from different APIs
SELECT url, array_agg(DISTINCT fetch_source) as sources, COUNT(*)
FROM stock_news
GROUP BY url
HAVING COUNT(DISTINCT fetch_source) > 1;
```

### Migration:
Run `alter_add_fetch_source.sql` in Supabase to add the column.

## 2025-11-20 02:00: Complete restructure - LLM categorization instead of symbol-based fetching
Major refactor: Switched from symbol-specific fetching to general news with LLM categorization.

### Files Created:
- `fetchers/general_news_fetcher.py` - Fetches all news without symbol filtering
- `services/llm_categorizer.py` - Zhipu AI GLM-4-flash categorization
- `services/__init__.py` - Services module init
- `processors/llm_news_processor.py` - LLM-based processor (no LIFO stack)
- `alter_add_secondary_category.sql` - Adds secondary_category column
- `test_friday_llm.py` - Friday (2025-11-21) test script

### Files Modified:
- `db/stock_news.py` - Added `insert_news()` method (no stack, direct insert)

### Major Changes:

#### 1. Fetching Strategy:
**Before:** Fetch news per symbol (AAPL, TSLA, etc.)
**After:** Fetch all general news, no symbol filtering

#### 2. Storage Strategy:
**Before:** LIFO stack (top 5 per symbol)
**After:** Direct insert, all news stored (except NON_FINANCIAL)

#### 3. Categorization:
**Before:** Manual category assignment
**After:** LLM categorization with 15 categories

#### 4. Symbol Association:
**Before:** Fetched per symbol
**After:** LLM extracts mentioned stocks in `secondary_category`

### Schema Changes:
- Added `secondary_category` column for stock ticker symbols
- `category` = Primary category (MACRO_ECONOMIC, EARNINGS_FINANCIALS, etc.)
- `secondary_category` = Stock symbols mentioned (AAPL, TSLA) or empty

### LLM Categorization:
- Model: Zhipu AI GLM-4-flash
- API key: ZHIPU_API_KEY
- Batch processing: 10 items per API call
- 15 categories (see news_category.txt)
- NON_FINANCIAL news filtered out automatically

### Test Workflow:
1. Fetch Friday (2025-11-21) news only
2. Store all in stock_news_raw
3. LLM categorizes each article
4. Store in stock_news (except NON_FINANCIAL)
5. Record timestamp for incremental fetching

### Usage:
```bash
# Run schema changes
cat alter_add_secondary_category.sql | supabase sql

# Test with Friday news
uv run python test_friday_llm.py
```

### Next Steps:
- Incremental fetching will work with GENERAL symbol
- LLM will categorize all new news
- Can query by primary category or secondary_category (stocks)

## 2025-11-22 01:00: Created incremental fetcher for LLM categorization system
Adapted fetch_incremental.py to work with new general news + LLM categorization system.

### Files Created:
- `fetch_incremental_llm.py` - Production incremental fetcher with LLM categorization

### Key Changes:
- Uses "GENERAL" symbol instead of specific stock symbols (AAPL, TSLA, etc.)
- Fetches all general news from both Finnhub and Polygon
- Processes incrementally based on last fetch_state timestamp
- LLM categorizes in batches (limit=20 per cycle)
- Automatically filters NON_FINANCIAL news
- Updates fetch_state after successful run for next incremental fetch

### Workflow:
1. Get last fetch time from fetch_state (with 1-min buffer)
2. Fetch incremental general news from Finnhub and Polygon
3. Store in stock_news_raw
4. Update fetch_state with new timestamps
5. Process with LLM categorization in batches
6. Store financial news in stock_news (skip NON_FINANCIAL)
7. Show recent categorized news sample

### Usage:
```bash
# Run incremental fetch (fetches news after last timestamp)
uv run python fetch_incremental_llm.py
```

### Integration with Friday Test:
- `test_friday_llm.py` establishes baseline (Friday 2025-11-21)
- `fetch_incremental_llm.py` fetches news after that timestamp
- Each run updates timestamp for next incremental fetch

## 2025-11-22 01:30: Fixed duplicate news issue - use actual news timestamp instead of fetch time
Fixed timestamp tracking to use actual latest news published_at instead of current time to avoid duplicates.

### Issue:
- Different news APIs return news with different timezone conventions
- Using `datetime.now()` as fetch window endpoint caused duplicates
- Same news fetched multiple times because publish time != fetch time

### Root Cause:
- Finnhub/Polygon may return news published hours ago
- `fetch_state.last_fetch_to` was set to current time, not actual news time
- Next run would re-fetch the same old news

### Fix:
**`storage/fetch_state_manager.py`:**
- Added `get_latest_news_timestamp()` method
- Queries `stock_news_raw` for latest `published_at` by source
- `get_last_fetch_time()` now uses actual news timestamp as baseline
- Fallback: uses `fetch_state` table, then 24h default

**`fetch_incremental_llm.py`:**
- Calculates actual latest news timestamp from fetched items:
  ```python
  finnhub_latest = max(item.published_at for item in finnhub_items)
  ```
- Updates `fetch_state` with actual news timestamp, not current time
- Shows both timestamps in summary for transparency

### Result:
- No more duplicate fetching of old news
- Incremental fetching based on actual news publish time
- Works correctly across different timezones
- Next run fetches only news published after latest fetched article

## 2025-11-24 23:00: Fixed processor source matching bug and added pending news processing
Fixed fetch_source matching for finnhub_{category} naming and added pending news processing before new fetches.

### Bug Fix in `src/processors/llm_news_processor.py`:
**Issue:** Changed source naming from `"finnhub"` to `"finnhub_general"`, `"finnhub_merger"` but processor still checked exact match `fetch_source == "finnhub"`, causing 0 items to be categorized.

**Fix:**
- Changed `if fetch_source == "finnhub":` to `if fetch_source and fetch_source.startswith("finnhub"):`
- Applied to both `_extract_content()` and `_build_processed_data()` methods
- Now handles all Finnhub category sources correctly

### New Feature - Process Pending Before Fetching:
**`src/storage/raw_news_storage.py`:**
- Added `count_pending()` method to quickly check pending items count

**`fetch_incremental_llm.py`:**
- Added STEP 1: Check for pending raw news and process them first
- If pending items exist, process all before fetching new news
- Prevents accumulation of unprocessed raw news
- Shows summary of pending processing results

**Workflow:**
1. Check pending count
2. If pending > 0: Process all pending items with LLM
3. Then proceed with normal incremental fetch flow

### Result:
- LLM categorization now works correctly with category-specific sources
- Pending news processed automatically before new fetches
- No accumulation of unprocessed raw news

## 2025-11-24 23:30: Added LLM concurrency control and centralized model configuration
Implemented concurrency limiting and retry logic to prevent 429 rate limit errors, moved model config to config.py.

### Issue:
GLM-4-flash free tier has 2 concurrent request limit, causing 429 errors:
```
❌ Zhipu API error: 429
Response: {"error":{"code":"1302","message":"您当前使用该API的并发数过高，请降低并发，或联系客服增加限额。"}}
```

### Changes in `src/config.py`:
**Added `LLM_MODELS` configuration:**
- `categorization`: Model settings for news categorization
  - `model`: "glm-4-flash" (changeable to other models)
  - `concurrency_limit`: 1 (limits concurrent API calls)
  - `delay_between_batches`: 2.0s (delay between batches)
  - `max_retries`: 2 (retry failed requests)
  - `timeout`: 60.0s
- `summarization`: Model settings for daily summaries
  - Same structure, longer timeout (120s)
- Reduced `batch_size` from 10 to 5 to avoid overwhelming API

### Changes in `src/services/llm_categorizer.py`:
**Added concurrency control:**
- Created `asyncio.Semaphore` to limit concurrent API calls
- New `_call_llm_api()` method with:
  - Semaphore-based concurrency control
  - Automatic retry with exponential backoff (5s, 10s, 15s)
  - Handles 429 rate limit errors gracefully
  - Returns None if failed after max_retries
- Updated `categorize_batch()`:
  - Uses new `_call_llm_api()` method
  - Adds delay between batches (`delay_between_batches`)
  - Falls back to UNCATEGORIZED if API fails
- Reads all settings from `LLM_MODELS['categorization']`

### Changes in `src/services/daily_summarizer.py`:
**Updated to use model config:**
- Reads model, temperature, timeout from `LLM_MODELS['summarization']`
- `generate_daily_summary()` uses config temperature by default
- Ready for future model changes

### Benefits:
- **No more 429 errors**: Concurrency limited to safe level
- **Automatic retry**: Transient failures handled automatically
- **Easy model switching**: Change model in one place (config.py)
- **Better rate limiting**: 2s delay between batches + concurrency control
- **Flexible configuration**: Different settings for categorization vs summarization

### Usage:
To change models in the future, just edit `src/config.py`:
```python
LLM_MODELS = {
    "categorization": {
        "model": "glm-4-plus",  # Change model here
        ...
    }
}
```

## 2025-11-25 00:00: Added UNCATEGORIZED re-processing and ACTION_PRIORITY system
Implemented re-categorization of UNCATEGORIZED news and priority-based processing order for future distributed systems.

### New Features:

**1. UNCATEGORIZED Re-processing (`src/db/stock_news.py`):**
- Added `count_uncategorized()` - Count UNCATEGORIZED items in stock_news
- Added `get_uncategorized()` - Fetch UNCATEGORIZED items for re-processing
- Added `update_category()` - Update category and secondary_category

**2. Re-categorization Method (`src/processors/llm_news_processor.py`):**
- New `recategorize_uncategorized_batch()` method:
  - Fetches UNCATEGORIZED news from stock_news table
  - Sends to LLM for re-categorization
  - Updates categories in place (no deletion)
  - Marks NON_FINANCIAL items but keeps them in database
  - Shows detailed progress logging

**3. ACTION_PRIORITY System (`src/config.py`):**
Added priority configuration for distributed processing:
```python
ACTION_PRIORITY = {
    "process_pending_raw": 1,          # Highest priority
    "recategorize_uncategorized": 2,   # High priority
    "fetch_and_process": 3,            # Normal priority
    "generate_summary": 4,             # Lower priority
}
```

**4. Updated Fetch Script (`fetch_incremental_llm_new.py`):**
- **STEP 1** (Priority 1): Process pending items in stock_news_raw
- **STEP 1.5** (Priority 2): Re-categorize UNCATEGORIZED in stock_news
- **STEP 2-3** (Priority 3): Regular fetch and process
- Steps numbered 1, 1.5, 2, 3, 4, 5, 6, 7, 8

### Processing Order:
1. **Pending raw news** (stock_news_raw with status='pending')
2. **UNCATEGORIZED news** (stock_news with category='UNCATEGORIZED')
3. **New news fetching** (incremental fetch from APIs)
4. **Daily summary** (separate script, priority 4)

### Benefits:
- **No data loss**: Failed categorizations get retried automatically
- **Clean database**: UNCATEGORIZED items eventually get proper categories
- **Priority-based**: Critical tasks (pending, uncategorized) processed first
- **Future-ready**: ACTION_PRIORITY enables distributed task scheduling
- **Flexible**: Can adjust priority order in config.py

### Example Usage:
When running `fetch_incremental_llm_new.py`:
1. First clears any pending items from stock_news_raw
2. Then re-processes any UNCATEGORIZED items in stock_news
3. Finally fetches and processes new news

This ensures clean data and no accumulation of unprocessed/uncategorized items.

## 2025-11-25 00:30: Added ERROR category and error_log to prevent infinite retry loops
Implemented error handling for permanent API failures to avoid infinite retry loops on broken items.

### Problem:
When LLM API returns permanent errors (400, invalid input, etc.), items stay UNCATEGORIZED and get retried infinitely, wasting API calls and processing time.

### Solution:

**1. Database Migration (`migrations/alter_add_error_log_to_stock_news.sql`):**
- Added `error_log` column to stock_news table
- Stores error details (API error code, message, exception info)
- Added index for ERROR category items

**2. ERROR Category Handling:**
- New category: `ERROR` - For items with permanent API failures
- Items marked as ERROR will NOT be retried to prevent infinite loops
- Error details stored in `error_log` column for manual review

**3. Updated LLM Categorizer (`src/services/llm_categorizer.py`):**
- `_call_llm_api()` now returns tuple: `(content, error_msg)`
- Returns error details on permanent failures (400, 500, exceptions)
- `categorize_batch()` marks failed items as ERROR with `api_error` field
- Error types captured:
  - API errors (400, 500, etc.): "API Error {code}: {response}"
  - JSON parse errors: "JSON parse error: {details}"
  - Exceptions: "Batch processing exception: {exception}"

**4. Updated Processor (`src/processors/llm_news_processor.py`):**
- `process_raw_item()`: Stores ERROR items with error_log in metadata
- `recategorize_uncategorized_batch()`:
  - Marks ERROR items and saves to error_log
  - ERROR items excluded from future re-processing
  - Clears error_log when successfully re-categorized

**5. Updated StockNewsDB (`src/db/stock_news.py`):**
- `update_category()` now accepts optional `error_log` parameter
- `get_uncategorized()` excludes ERROR items (only gets UNCATEGORIZED)

### Error Flow:
1. **Initial categorization**: API fails → mark as ERROR, save error_log
2. **Re-categorization check**: ERROR items skipped (not fetched by `get_uncategorized()`)
3. **Manual review**: Users can query `category='ERROR'` to review failed items

### Benefits:
- **No infinite loops**: ERROR items marked and skipped
- **API efficiency**: Don't waste calls on permanently broken items
- **Debuggability**: Error details saved for manual review
- **Clean separation**:
  - UNCATEGORIZED = Temporary failure, will retry
  - ERROR = Permanent failure, won't retry

### Example Error Messages:
```sql
-- API Error example
error_log: "API Error 400: {\"error\":{\"code\":\"invalid_input\",\"message\":\"...\"}}"

-- JSON Parse Error example
error_log: "JSON parse error: Expecting ',' delimiter: line 5 column 10 (char 145)"

-- Exception example
error_log: "Exception after 2 retries: Connection timeout"
```

### Usage:
```sql
-- Find all ERROR items for manual review
SELECT title, error_log, created_at
FROM stock_news
WHERE category = 'ERROR'
ORDER BY created_at DESC;

-- Count ERROR vs UNCATEGORIZED
SELECT category, COUNT(*)
FROM stock_news
WHERE category IN ('ERROR', 'UNCATEGORIZED')
GROUP BY category;
```

## 2025-11-25 00:45: Changed to INCLUDED_CATEGORIES whitelist approach for daily summaries
Replaced exclusion list with explicit whitelist (INCLUDED_CATEGORIES) for better control and clarity.

### Changes:

**1. Added INCLUDED_CATEGORIES to config (`src/config.py`):**
```python
INCLUDED_CATEGORIES = [
    "MACRO_ECONOMIC",           # Macroeconomic indicators
    "CENTRAL_BANK_POLICY",      # Monetary policy, interest rates
    "GEOPOLITICAL_SPECIFIC",    # Geopolitical news with named entities
    "INDUSTRY_REGULATION",      # Regulatory news for specific sectors
    "EARNINGS_FINANCIALS",      # Earnings, revenue, financial statements
    "CORPORATE_ACTIONS",        # M&A, stock splits, buybacks
    "MANAGEMENT_CHANGES",       # CEO, CFO, board changes
    "PRODUCT_TECH_UPDATE",      # New products, R&D, launches
    "BUSINESS_OPERATIONS",      # Supply chain, contracts, partnerships
    "ACCIDENT_INCIDENT",        # Breaches, accidents, recalls, lawsuits
    "ANALYST_RATING",           # Analyst upgrades/downgrades
    "MARKET_SENTIMENT",         # Investor sentiment, market flows
    "COMMODITY_FOREX_CRYPTO",   # Commodities, forex, crypto
]
# 13 valid categories total

# Automatically excludes: MACRO_NOBODY, UNCATEGORIZED, ERROR, NON_FINANCIAL
```

**2. Updated Daily Summary (`generate_daily_summary.py`):**
- Changed from `EXCLUDED_CATEGORIES` to `INCLUDED_CATEGORIES`
- Changed filter from `.not_.in_()` to `.in_()`
- Whitelist approach: Only explicitly listed categories included
- Automatically excludes any new invalid categories

**3. Updated Documentation (`README.md`):**
- Replaced EXCLUDED_CATEGORIES with INCLUDED_CATEGORIES
- Shows all 13 valid categories

### Blacklist vs Whitelist Approach:

**Before (Blacklist):**
```python
.not_.in_("category", ["MACRO_NOBODY", "UNCATEGORIZED", "ERROR", "NON_FINANCIAL"])
# Problem: Any new category automatically included
```

**After (Whitelist):**
```python
.in_("category", INCLUDED_CATEGORIES)  # 13 explicit categories
# Benefit: Only explicitly approved categories included
```

### Benefits:
- **Explicit control**: Must explicitly add new categories to whitelist
- **Safety**: New categories (valid or invalid) don't accidentally appear in summaries
- **Clarity**: Clear list of what IS included vs what ISN'T
- **Self-documenting**: Config shows exactly which categories are used
- **Future-proof**: Adding new error categories doesn't affect summaries

### Automatically Excluded:
- MACRO_NOBODY (geopolitical commentary)
- UNCATEGORIZED (temporary failures)
- ERROR (permanent failures)
- NON_FINANCIAL (non-market news)
- Any future invalid categories added to the system

## 2025-12-27 14:00: Created FastAPI server with APScheduler for Render deployment
Converted fetch_incremental_llm_new.py and generate_daily_summary.py to scheduled FastAPI service for Render cloud deployment.

### Files Created:
- `api_server.py` - FastAPI app with APScheduler for automatic task scheduling
- `requirements.txt` - Python dependencies for Render deployment (exported from pyproject.toml)
- `render.yaml` - Render.com deployment configuration

### Files Modified:
- `pyproject.toml` - Added fastapi, uvicorn, apscheduler dependencies

### Implementation Details:

**1. FastAPI Server (`api_server.py`):**
- **Scheduled Tasks:**
  - `fetch_incremental`: Runs every 4 hours
  - `daily_summary_morning`: Runs at 7 AM EST (12 PM UTC)
  - `daily_summary_evening`: Runs at 5 PM EST (10 PM UTC)
- **HTTP Endpoints:**
  - `GET /` - Health check with scheduler status
  - `GET /health` - Simple health check for Render
  - `GET /status` - Detailed scheduler and job status
  - `POST /trigger/fetch` - Manually trigger incremental fetch
  - `POST /trigger/summary` - Manually trigger daily summary
  - `POST /trigger/all` - Trigger all jobs
- **Job Tracking:**
  - Tracks last run time, status, and errors for each job
  - Background task execution to avoid blocking API responses

**2. Dependencies (`pyproject.toml` and `requirements.txt`):**
- `fastapi>=0.115.0` - Web framework
- `uvicorn[standard]>=0.32.0` - ASGI server
- `apscheduler>=3.10.4` - Task scheduler

**3. Render Configuration (`render.yaml`):**
- **Web Service (Recommended):**
  - Always-on service with in-app APScheduler
  - Requires Render Starter plan ($7/month)
  - All scheduling handled automatically
- **Alternative: Cron Jobs (Commented out):**
  - Use Render's Cron Jobs feature to run scripts
  - Can use free tier
  - Requires separate cron job services

### Deployment Options:

**Option 1: In-App Scheduler (Recommended) ✅**
- Deploy as single Web Service on Render
- APScheduler runs inside FastAPI app
- Pros: Simple, everything in one service
- Cons: Requires paid plan (always-on), uses compute even when idle

**Option 2: Render Cron Jobs**
- Deploy Web Service + separate Cron Jobs
- Cron jobs trigger HTTP endpoints on schedule
- Pros: Only runs when needed, can use free tier
- Cons: More complex setup (multiple services)

### Automatic Scheduling:

**Yes, automatic scheduling works on Render!** The APScheduler runs inside the FastAPI app and executes tasks automatically:
- **Every 4 hours**: Incremental news fetch
- **7 AM EST**: Morning summary
- **5 PM EST**: Evening summary

No external triggers needed - the scheduler handles everything once deployed.

### Usage:

**Deploy to Render:**
1. Push code to GitHub
2. Connect repository to Render
3. Render auto-detects `render.yaml`
4. Set environment variables in Render dashboard
5. Deploy and monitor via `/status` endpoint

**Local Testing:**
```bash
# Install dependencies
uv sync

# Run server
uv run python api_server.py

# Check status
curl http://localhost:8000/status

# Manually trigger jobs
curl -X POST http://localhost:8000/trigger/fetch
curl -X POST http://localhost:8000/trigger/summary
```

### Benefits:
- **Automated execution**: No manual intervention needed
- **Cloud deployment**: Runs 24/7 on Render infrastructure
- **Monitoring**: HTTP endpoints for health checks and status
- **Manual triggers**: Can manually run jobs via API
- **Error tracking**: Job history with error logs
- **Scalable**: Easy to add more scheduled tasks

## 2025-12-27 15:00: Unified category validation with single query
Refactored category validation to use single unified query instead of separate UNCATEGORIZED and invalid category checks.

### Files Modified:
- `src/db/stock_news.py` - Replaced 4 methods with 2 unified methods
- `src/processors/llm_news_processor.py` - Replaced 2 methods with 1 unified method
- `fetch_incremental_llm_new.py` - Simplified to use single validation call

### Key Insight:

**Before:** Separate queries for UNCATEGORIZED and invalid categories
**After:** Single query for all items needing re-categorization

Since UNCATEGORIZED is NOT in INCLUDED_CATEGORIES, a single query `category NOT IN (valid list)` catches both:
- UNCATEGORIZED items (failed initial categorization)
- Invalid categories (hallucinations, typos, old schema)

### Implementation:

**1. Unified Database Methods (`src/db/stock_news.py`):**

Removed (4 methods):
- ~~`count_uncategorized()`~~
- ~~`get_uncategorized()`~~
- ~~`count_invalid_categories()`~~
- ~~`get_invalid_categories()`~~

Added (2 methods):
- `count_items_needing_recategorization()` - Single count query
- `get_items_needing_recategorization(limit)` - Single fetch query

Query logic:
```python
# Categories to skip (don't need re-categorization)
CATEGORIES_TO_SKIP = INCLUDED_CATEGORIES + ["ERROR", "NON_FINANCIAL"]

# Get items where category NOT IN skip list
# This catches: UNCATEGORIZED + invalid categories
.not_.in_("category", CATEGORIES_TO_SKIP)
```

**2. Unified Processor Method (`src/processors/llm_news_processor.py`):**

Removed (2 methods):
- ~~`recategorize_uncategorized_batch()`~~
- ~~`recategorize_invalid_categories_batch()`~~

Added (1 method):
- `recategorize_batch()` - Handles all items needing re-categorization

Features:
- Single LLM batch call for all problematic items
- Logs category breakdown before processing
- Shows old→new category mappings
- Unified statistics

**3. Simplified Fetch Script (`fetch_incremental_llm_new.py`):**
- **STEP 1.5** (Priority 2): Validate & Fix Categories
- Single count query: `count_items_needing_recategorization()`
- Single processing loop: `recategorize_batch()`
- Processing order:
  1. STEP 1: Process pending raw news (Priority 1)
  2. **STEP 1.5: Validate & fix all categories (Priority 2)** ← UNIFIED
     - Single query gets all items needing fixes
     - Single loop processes them all
     - Shows combined statistics
  3. STEP 2-3: Fetch and process new news (Priority 3)

### Common Causes of Invalid Categories:

1. **LLM Hallucination:**
   - LLM returns category names not in our schema
   - Example: "TECH_INNOVATION" instead of "PRODUCT_TECH_UPDATE"

2. **Schema Changes:**
   - INCLUDED_CATEGORIES list updated
   - Old news has categories removed from whitelist

3. **Manual Edits:**
   - Database edited manually with typos
   - Example: "COPORATE_EARNINGS" instead of "CORPORATE_EARNINGS"

4. **API Errors:**
   - LLM returns partial/corrupted responses
   - JSON parsing issues creating invalid categories

### Validation Workflow:

```
1. Check stock_news table for invalid categories
   ↓
2. If found, log which invalid categories exist
   ↓
3. Re-categorize with LLM in batches
   ↓
4. Update with corrected categories or mark as:
   - UNCATEGORIZED (if LLM still can't categorize)
   - ERROR (if API fails permanently)
   - NON_FINANCIAL (if non-market news)
```

### Example Log Output:

```
STEP 1.5: Validate & Fix Categories (Priority 2)
Items needing re-categorization: 23

Re-categorizing 23 items with category issues...

Categories needing fixes:
   UNCATEGORIZED: 8
   TECH_NEWS: 8
   COPORATE_EARNINGS: 5
   MACRO_NOBODY: 2

Sending 23 items to LLM for re-categorization...
Updated [CORPORATE_EARNINGS] Tesla Q4 earnings report... (TSLA)
Fixed [TECH_NEWS→PRODUCT_TECH_UPDATE] Apple launches new MacBook...
Fixed [COPORATE_EARNINGS→CORPORATE_EARNINGS] Tesla earnings beat...
Fixed [MACRO_NOBODY→GEOPOLITICAL_EVENT] Fed announces rate hike...

Category Validation Summary:
   Total updated: 20
   NON_FINANCIAL marked: 1
   Failed: 2
```

### Benefits:

- **Simpler Code**: Eliminated duplicate methods (6 methods → 3 methods)
- **Single Query**: More efficient database access
- **Unified Processing**: One loop instead of two sequential loops
- **Better Logging**: Category breakdown shows all issues at once
- **Data Quality**: Ensures all categories are valid
- **Schema Evolution**: Handles category list changes gracefully
- **Error Recovery**: Fixes LLM hallucination issues automatically

### Code Reduction:

**Before:**
- 4 database methods
- 2 processor methods
- 2 separate processing loops in fetch script
- ~200 lines of duplicate code

**After:**
- 2 database methods
- 1 processor method
- 1 unified processing loop
- ~100 lines of clean code

**Result:** 50% code reduction, same functionality, better maintainability

### Pre-Filter Optimization:

Added intelligent pre-filtering to avoid unnecessary LLM calls:

**"Nobody" Category Filter:**
- Before sending items to LLM, check if category contains "nobody" (case-insensitive)
- Examples: `MACRO_NOBODY`, `Geopolitical_Nobody`, `NOBODY_SPECIFIC`
- These are too generic/non-specific → auto-mark as `NON_FINANCIAL`
- Skip LLM call to save API costs
- Matches filtering logic from raw → cleaned stock flow

**Benefits:**
- Saves LLM API calls for obvious non-financial items
- Reduces processing time
- Maintains consistency with raw news filtering
- Audit trail preserved in error_log field

**Processing Flow:**
```
1. Count all items needing re-categorization: 244
2. Pre-filter ALL "nobody" categories ONCE: 10 filtered → NON_FINANCIAL
3. Re-count remaining items: 234
4. Batch remaining 234 items:
   - Batch 1: 20 items → LLM
   - Batch 2: 20 items → LLM
   - ...
   - Batch 12: 14 items → LLM
```

**Example Output:**
```
STEP 1.5: Validate & Fix Categories (Priority 2)
Items needing re-categorization: 244

Pre-filtering 'nobody' categories...
Pre-filtered 10 'nobody' categories → NON_FINANCIAL

Re-categorizing 234 remaining items with LLM...

Categories needing fixes:
   UNCATEGORIZED: 120
   TECH_NEWS: 80
   COPORATE_EARNINGS: 34

Sending 20 items to LLM...
[Batch 1 processing...]
Sending 20 items to LLM...
[Batch 2 processing...]
...

LLM Re-categorization Summary:
   LLM processed: 220
   NON_FINANCIAL (from LLM): 8
   Failed: 6

Category Validation Summary:
   Pre-filtered (nobody): 10  ← Filtered BEFORE batching
   LLM updated: 220
   Total fixed: 230
```

## 2025-12-27 16:00: Separated validation logic into standalone recategorization script
Decoupled validation/re-categorization from news fetching for cleaner architecture and independent scheduling.

### Files Created:
- `api/recategorize.py` - Standalone script for validation and re-categorization
  - STEP 1: Process pending raw news
  - STEP 2: Validate & fix categories (with pre-filter and LLM batching)

### Files Modified:
- `api/fetch_incremental_llm_new.py` - Removed validation steps, now focused on fetching only
  - Removed STEP 1 (pending raw news processing)
  - Removed STEP 1.5 (category validation)
  - Renumbered remaining steps (STEP 1-9)
  - Now handles: fetch → store → process new items → statistics
- `api_server.py` - Updated scheduler with two separate jobs
  - Added `run_recategorize_existing()` wrapper function
  - Added "recategorize_existing" to job_status tracking
  - **New schedule**: Recategorization every 4 hours
  - **Updated schedule**: Fetch every 1 hour (was 4 hours)
  - Daily summary: 7 AM and 5 PM EST (unchanged)
  - Added manual trigger endpoint: `POST /trigger/recategorize`
  - Updated `/trigger/all` to include all three jobs

### Documentation Updated:
- `docs/API_USAGE.md` - Added recategorization endpoint documentation
  - Added `/trigger/recategorize` to endpoint table
  - Updated scheduled jobs to show correct intervals
  - Added section 5 for re-categorization trigger
  - Updated Python script example with `trigger_recategorize()` function
  - Updated all job status examples to include recategorize_existing
- `QUICK_API_REFERENCE.md` - Added quick reference commands
  - Added recategorize trigger commands (local and production)
  - Added Python one-liner for recategorization
  - Added description of what recategorize job does

### Scheduling Changes:

**Before:**
- Fetch + Validation: Every 4 hours (combined)
- Daily Summary: 7 AM and 5 PM EST

**After:**
- **Fetch**: Every 1 hour (faster news updates)
- **Recategorize**: Every 4 hours (independent validation)
- **Daily Summary**: 7 AM and 5 PM EST (unchanged)

### Architecture Benefits:

1. **Separation of Concerns:**
   - News fetching script focuses only on fetching new news
   - Recategorization script handles validation and fixing
   - Each script has single responsibility

2. **Independent Scheduling:**
   - Fetch runs more frequently (hourly) for fresher news
   - Validation runs less frequently (4 hours) as needed
   - Can adjust schedules independently

3. **Cleaner Code:**
   - `api/fetch_incremental_llm_new.py` simplified (removed 2 steps)
   - `api/recategorize.py` handles all validation logic
   - No mixed concerns in single script

4. **Better Monitoring:**
   - Separate job status tracking for each task
   - Can see last run time for fetch vs recategorization
   - Independent error tracking

5. **Flexibility:**
   - Can manually trigger validation without re-fetching
   - Can manually fetch without re-validating
   - Can run both together or separately

### API Endpoints:

**Manual Triggers:**
- `POST /trigger/fetch` - Fetch incremental news
- `POST /trigger/recategorize` - Re-categorize existing news
- `POST /trigger/summary` - Generate daily summary
- `POST /trigger/all` - Run all three jobs

**Example Usage:**
```bash
# Trigger re-categorization only
curl -X POST http://localhost:8000/trigger/recategorize

# Trigger all jobs
curl -X POST http://localhost:8000/trigger/all

# Check status
curl http://localhost:8000/status
```

### Benefits:
- **Faster News Updates**: Hourly fetching instead of every 4 hours
- **Efficient Validation**: Runs every 4 hours as needed
- **Independent Jobs**: Each job can be monitored/debugged separately
- **Cleaner Architecture**: Single responsibility per script
- **Flexible Execution**: Can trigger any job independently

## 2025-12-27 16:30: Reorganized API scripts into dedicated folder
Moved scheduled task scripts to `api/` folder and renamed recategorization script for consistency.

### File Changes:

**Renamed:**
- `recategorize_existing.py` → `api/recategorize.py`

**Moved to `api/` folder:**
- `fetch_incremental_llm_new.py` → `api/fetch_incremental_llm_new.py`
- `generate_daily_summary.py` → `api/generate_daily_summary.py`

### Files Modified:
- `api_server.py` - Updated import statements
  - Changed: `from recategorize_existing import main` → `from api.recategorize import main`
  - Changed: `from fetch_incremental_llm_new import main` → `from api.fetch_incremental_llm_new import main`
  - Changed: `from generate_daily_summary import main` → `from api.generate_daily_summary import main`
  - Updated dynamic import: `import generate_daily_summary` → `from api import generate_daily_summary`

### Module Path Fix:
Added parent directory to `sys.path` in all three scripts to ensure `src` module can be found:
```python
import sys
sys.path.insert(0, str(Path(__file__).parent.parent))
```

This allows scripts to be run directly from any location:
```bash
uv run api/recategorize.py
uv run api/fetch_incremental_llm_new.py
uv run api/generate_daily_summary.py
```

### Benefits:
- **Better Organization**: All API-related scripts in dedicated `api/` folder
- **Cleaner Root**: Root directory less cluttered
- **Consistent Naming**: `recategorize.py` matches endpoint name `/trigger/recategorize`
- **Clear Separation**: Core logic separated from API execution scripts
- **Portable Execution**: Scripts can be run from any location
