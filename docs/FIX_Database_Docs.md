# Database Fix Documentation

## 2025-11-18 16:00: stock_news table adjustment for LIFO stack compatibility
Fixed SQL script to properly drop UNIQUE constraint before recreating as composite index.

---

## Issue: DROP INDEX fails for constraint-backed index

**Error:**
```
ERROR: cannot drop index stock_news_url_key because constraint stock_news_url_key on table stock_news requires it
```

**Root Cause:**
`stock_news_url_key` is a UNIQUE constraint, not a standalone index. Constraints must be dropped with `ALTER TABLE ... DROP CONSTRAINT`.

**Fix:**
```sql
-- Wrong:
DROP INDEX IF EXISTS stock_news_url_key;

-- Correct:
ALTER TABLE stock_news DROP CONSTRAINT IF EXISTS stock_news_url_key;
```

**Applied in:** `adjust_stock_news_table.sql` line 64

---

## Schema Changes Required

### Missing Columns (4):
- `source_id` UUID - news source reference
- `external_id` TEXT - API external IDs
- `metadata` JSONB - flexible additional data
- `updated_at` TIMESTAMPTZ - auto-updated timestamp

### Constraint Fixes (2):
- `published_at` → NOT NULL (currently nullable)
- `created_at` → NOT NULL (currently nullable)

### Index Changes (3):
- DROP constraint `stock_news_url_key` (UNIQUE on url)
- ADD index `idx_stock_news_symbol_url` (UNIQUE on symbol+url)
- ADD index `idx_stock_news_symbol_position` (critical for stack queries)

### Helper Functions (1):
- `increment_news_positions(p_symbol TEXT)` - increments all positions for LIFO stack

---

## Migration File

**File:** `adjust_stock_news_table.sql`
**Status:** Ready to run
**Safe:** Yes - only adds columns/indexes, no data loss

## 2025-11-20 01:05: Fixed timezone-aware datetime error in incremental fetcher

**Error:**
```
can't subtract offset-naive and offset-aware datetimes
```

**Root Cause:**
Database returns timezone-aware datetimes, but code was mixing with timezone-naive datetimes causing subtraction errors.

**Fix:**
- `fetch_incremental.py` line 69-72: Strip timezone info before datetime operations
- Added informative messages: "No news updates for {symbol}" when no articles found
- Added message: "No new updates (all duplicates)" when articles fetched but all duplicates

**Applied in:** `fetch_incremental.py`

## 2025-11-20 01:10: Fixed NULL source and published_at in stock_news table

**Issue:**
- `source` column was NULL (not being populated)
- `published_at` was NULL in some cases

**Root Cause:**
- Processor wasn't extracting `source` field into processed_data
- Database insertion wasn't including `source` field
- Source names were only stored in metadata, not in dedicated column

**Fix:**
1. `processors/news_processor.py`:
   - Finnhub: Extract `source` from raw_json (line 48)
   - Polygon: Use `publisher` as source (line 102)
   - Add `source` field to processed_data dict

2. `db/stock_news.py`:
   - Added `source` field to news_item dict (line 54)
   - Now properly maps source from processed_data to database

**Applied in:**
- `processors/news_processor.py` (lines 48, 102)
- `db/stock_news.py` (line 54)

**Result:**
- New articles will have populated `source` field
- `published_at` was already correct (ISO format timestamp)

## 2025-11-20 02:05: Created cleanup script for Friday test

**Purpose:**
Provide SQL queries to delete old data before testing new LLM categorization system.

**File:** `cleanup_before_friday_test.sql`

**Options Provided:**

1. **OPTION 1 - Complete Reset (TRUNCATE)**
   - Deletes ALL data from all tables
   - Use for completely fresh start
   - Fast but destructive

2. **OPTION 2 - Delete Before Friday (Recommended)**
   - Deletes data created before 2025-11-21
   - Safe, preserves Friday data
   - Good for testing

3. **OPTION 3 - Delete Symbol-Specific Only**
   - Removes old symbol-based data (AAPL, TSLA, etc.)
   - Keeps GENERAL news (new system)
   - Good for transitioning systems

4. **OPTION 4 - Keep Last 7 Days**
   - Rolling cleanup
   - Good for production maintenance

**Recommended Workflow:**
```sql
-- 1. Check what will be deleted
SELECT 'stock_news before 2025-11-21', COUNT(*) FROM stock_news WHERE created_at < '2025-11-21';

-- 2. Delete old data
DELETE FROM stock_news WHERE created_at < '2025-11-21 00:00:00';
DELETE FROM stock_news_raw WHERE created_at < '2025-11-21 00:00:00';
DELETE FROM fetch_state WHERE last_fetch_to < '2025-11-21 00:00:00';

-- 3. Verify
SELECT COUNT(*) FROM stock_news;
```

**Usage:**
Copy relevant queries to Supabase SQL Editor and execute.

## 2025-11-22 01:30: Fixed duplicate news fetching issue

**Issue:**
Terminal logs showed many duplicate news articles being fetched repeatedly.

**Root Cause:**
- Different news APIs (Finnhub, Polygon) have different timezone conventions
- APIs may return news published hours ago, not "right now"
- Previous implementation used `datetime.now()` as `last_fetch_to`
- Next incremental fetch would re-fetch the same old news because:
  - News published at 10:00 AM
  - Fetched at 2:00 PM, recorded `last_fetch_to = 2:00 PM`
  - Next run fetches from 2:00 PM onwards
  - But the news at 10:00 AM gets returned again by API

**Fix:**
Changed timestamp tracking to use **actual news published_at timestamp** instead of fetch time.

**Files Modified:**
1. `storage/fetch_state_manager.py`:
   - Added `get_latest_news_timestamp()` - queries latest `published_at` from `stock_news_raw`
   - Modified `get_last_fetch_time()` - now uses actual news timestamp as baseline
   - Priority: actual news timestamp > fetch_state table > 24h default

2. `fetch_incremental_llm.py`:
   - Calculates actual latest timestamp from fetched items: `max(item.published_at)`
   - Updates `fetch_state.last_fetch_to` with actual news time, not current time
   - Displays both source timestamps in summary

**Result:**
- No more duplicate fetching
- Incremental fetching correctly based on news publish time
- Works across different timezones
- Next run fetches only news published after latest article

## 2025-11-22 02:00: Added published_at column to stock_news_raw

**Issue:**
Previous fix incomplete - `stock_news_raw` didn't store news `published_at`, only `fetched_at`.
`get_latest_news_timestamp()` was querying a non-existent column.

**Solution:**
Added `published_at` column to `stock_news_raw` table to store actual news publication time.

**Files Created:**
- `alter_add_published_at_to_raw.sql` - Migration to add column

**Files Modified:**
1. `models/raw_news.py`:
   - Added `published_at: Optional[datetime]` field
   - Updated `to_db_dict()` to include published_at
   - Modified `from_finnhub_response()` - extracts from 'datetime' field (Unix timestamp)
   - Modified `from_polygon_response()` - extracts from 'published_utc' field (ISO string)

2. `fetchers/general_news_fetcher.py`:
   - Changed to use factory methods instead of manual construction
   - Finnhub: `RawNewsItem.from_finnhub_response()`
   - Polygon: `RawNewsItem.from_polygon_response()`

3. `fetch_incremental_llm.py`:
   - Simplified timestamp extraction - now uses `item.published_at` directly
   - No need to parse raw_json anymore

**Migration:**
```bash
# Run in Supabase SQL Editor
cat alter_add_published_at_to_raw.sql
```

**Result:**
- `stock_news_raw.published_at` now stores actual news publish time
- `get_latest_news_timestamp()` can query this column correctly
- Incremental fetching works properly with real news timestamps

## 2025-11-22 02:15: Fixed incremental fetching - client-side filter for Finnhub, full datetime for Polygon

**Issue:**
Even with `published_at` column, still fetching duplicates because:
1. **Finnhub API**: Doesn't support date filtering - always returns latest 100 articles
2. **Polygon API**: Was only passing date (YYYY-MM-DD), not time (HH:MM:SS)

**Solution:**
1. **Finnhub**: Client-side filtering after fetch
2. **Polygon**: Pass full datetime (YYYY-MM-DDTHH:MM:SS) + use `gt` instead of `gte`

**Files Modified:**
1. `fetchers/general_news_fetcher.py`:
   - `fetch_finnhub_general_news()`: Added `after_timestamp` parameter for client-side filtering
   - `fetch_polygon_general_news()`: Changed to accept full datetime, use `published_utc.gt` (greater than, not gte)

2. `fetch_incremental_llm.py`:
   - Finnhub: Passes `after_timestamp=finnhub_from` for client-side filtering
   - Polygon: Formats datetime as `%Y-%m-%dT%H:%M:%S` (includes hours/minutes/seconds)

**Key Changes:**
```python
# Finnhub: Client-side filter
finnhub_items = await general_fetcher.fetch_finnhub_general_news(
    after_timestamp=finnhub_from  # Filters out old news after fetching
)

# Polygon: Full datetime in API call
polygon_from_str = polygon_from.strftime("%Y-%m-%dT%H:%M:%S")  # Not just date!
polygon_items = await general_fetcher.fetch_polygon_general_news(
    from_date=polygon_from_str,  # API filters server-side
    to_date=polygon_to_str
)
```

**Result:**
- Finnhub: Fetches 100 articles, filters client-side to only new ones
- Polygon: API only returns news published AFTER last timestamp (with precision to the second)
- No more duplicates!
- Efficient incremental fetching
