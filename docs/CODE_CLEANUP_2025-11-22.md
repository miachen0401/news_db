# Code Cleanup: Migration to LLM Categorization System

**Date:** 2025-11-22
**Reason:** Migrated from symbol-specific fetching with LIFO stack to general news with LLM categorization

---

## System Architecture Change

### OLD System (Removed):
- **Fetching:** Symbol-specific news (AAPL, TSLA, etc.)
- **Storage:** LIFO stack (top 5 per symbol, position_in_stack)
- **Categorization:** Manual category assignment
- **Production Script:** `fetch_incremental.py`

### NEW System (Current):
- **Fetching:** General market news (no symbol filtering)
- **Storage:** All news stored (except NON_FINANCIAL)
- **Categorization:** LLM-based with 15 categories (Zhipu AI GLM-4-flash)
- **Production Script:** `fetch_incremental_llm.py`

---

## Files Deleted (8 files)

### 1. Old Production Script
- `fetch_incremental.py` - Old incremental fetcher using symbol-specific approach

### 2. Obsolete Test Scripts (Directory: test_archive/)
- `test_fetch_news.py` - Tested symbol-specific fetching and LIFO stack
- `test_process_all.py` - Tested old NewsProcessor
- `test_today_news.py` - Tested symbol-specific daily fetching
- `test_multi_source.py` - Tested multi-source symbol-specific fetching

### 3. Obsolete Fetcher Classes
- `fetchers/finnhub_fetcher.py` - Symbol-specific Finnhub fetching (FinnhubClient, FinnhubNewsFetcher)
- `fetchers/polygon_fetcher.py` - Symbol-specific Polygon fetching (PolygonClient, PolygonNewsFetcher)

### 4. Obsolete Processor
- `processors/news_processor.py` - Old NewsProcessor with manual categorization and LIFO stack logic

**Total Lines Removed:** ~1,500+ lines

---

## Functions Removed from db/stock_news.py

### Removed LIFO Stack Methods (200+ lines):

1. **`push_news_to_stack()`** - Lines 87-189
   - Implemented LIFO stack with position_in_stack
   - Incremented positions of existing news
   - Archived news beyond position 5
   - **Replaced by:** `insert_news()` (direct insertion, no stack)

2. **`get_news_stack()`** - Lines 191-223
   - Retrieved news ordered by position_in_stack
   - **Replaced by:** Direct queries on stock_news table

3. **`check_duplicate_url()`** - Lines 225-253
   - Checked duplicates per symbol
   - **Replaced by:** Global duplicate check in `insert_news()`

4. **`_archive_old_news()`** - Lines 255-287
   - Deleted news beyond max_position
   - **No longer needed:** All news stored (no position limit)

### Kept Methods:

- `insert_news()` - NEW method for direct insertion (no LIFO stack)
- `get_stats()` - Statistics reporting (still used in fetch_incremental_llm.py)

---

## Configuration Changes (config.py)

### Removed:
- `DEFAULT_SYMBOLS` - List of stock symbols (AAPL, TSLA, NVDA)
- `TOP_STOCKS` - Top market cap stocks list
- `TECH_STOCKS` - Tech stocks list
- Old `FETCH_CONFIG` - Symbol-specific settings

### Added:
- `LLM_CONFIG` - LLM processing configuration
  - `batch_size`: Items per LLM API call (10)
  - `processing_limit`: Max items per incremental run (20)
  - `temperature`: LLM consistency setting (0.3)

- `FETCH_CONFIG` - General news fetching settings
  - `polygon_limit`: Max articles from Polygon (100)
  - `finnhub_limit`: Finnhub article limit (100)
  - `buffer_minutes`: Overlap window for incremental fetching (1)

---

## Current File Structure

### Active Production Files:

**Main Script:**
- `fetch_incremental_llm.py` - Production incremental fetcher with LLM categorization

**Fetchers:**
- `fetchers/general_news_fetcher.py` - General news fetching (Finnhub + Polygon)

**Processors:**
- `processors/llm_news_processor.py` - LLM-based categorization and processing

**Services:**
- `services/llm_categorizer.py` - Zhipu AI GLM-4-flash categorization (15 categories)

**Database:**
- `db/stock_news.py` - Database operations (insert_news, get_stats)

**Storage:**
- `storage/raw_news_storage.py` - Raw news staging
- `storage/fetch_state_manager.py` - Incremental fetch timestamp tracking

**Models:**
- `models/raw_news.py` - RawNewsItem data model

**Test Scripts:**
- `test_friday_llm.py` - Tests new LLM categorization system

---

## Database Schema Notes

### Columns Still in Schema (from old system):
- `position_in_stack` - No longer used, can be dropped in future migration
- Database still has LIFO stack indexes and helper functions (can be cleaned up later)

### Columns Now Used:
- `category` - Primary LLM category (15 types)
- `secondary_category` - Stock symbols mentioned in news (LLM extracted)
- `published_at` - Actual news publication time (for incremental fetching)
- `fetch_source` - API source (finnhub, polygon)
- `source` - News publisher (Reuters, Bloomberg, etc.)

---

## Impact Summary

### Before Cleanup:
- **Files:** 20+ files (including 8 obsolete ones)
- **Lines of Code:** ~3,500+ lines
- **Complexity:** Mixed old/new systems, confusing codebase

### After Cleanup:
- **Files:** 12 active production files
- **Lines of Code:** ~2,000 lines
- **Complexity:** Single clear production path (LLM-based)

### Benefits:
- ✅ Removed ~1,500 lines of obsolete code
- ✅ Eliminated confusion between old/new systems
- ✅ Clear production workflow: fetch_incremental_llm.py
- ✅ No more symbol-specific configuration needed
- ✅ Simplified codebase for easier maintenance

---

## Future Cleanup Opportunities

1. **Database Schema Cleanup:**
   - Drop `position_in_stack` column from stock_news table
   - Remove LIFO stack indexes (`idx_stock_news_symbol_position`)
   - Drop `increment_news_positions()` stored procedure

2. **Old Test Data:**
   - Clean up old symbol-specific data (AAPL, TSLA, NVDA) if desired
   - Can use cleanup_before_friday_test.sql queries

3. **Dependencies:**
   - Review if any unused Python packages can be removed from pyproject.toml

---

## Migration Checklist

- [x] Delete old production script (fetch_incremental.py)
- [x] Delete obsolete test scripts (test_archive/)
- [x] Delete obsolete fetchers (finnhub_fetcher.py, polygon_fetcher.py)
- [x] Delete obsolete processor (news_processor.py)
- [x] Remove LIFO stack methods from db/stock_news.py
- [x] Clean up config.py (remove symbol lists)
- [x] Update documentation
- [ ] Optional: Clean up database schema (position_in_stack, indexes, stored procedures)
- [ ] Optional: Archive old symbol-specific data

---

## Production Usage

Current production command:
```bash
uv run python fetch_incremental_llm.py
```

This script:
1. Fetches general news from Finnhub and Polygon (after last timestamp)
2. Stores in stock_news_raw
3. Categorizes with LLM (15 categories)
4. Stores financial news in stock_news (filters NON_FINANCIAL)
5. Updates fetch_state for next incremental run

Run frequency: Every 15-30 minutes or hourly for continuous news updates.
