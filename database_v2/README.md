# Database V2: Event-Based News Classification Pipeline

Clean, modular pipeline for extracting and classifying financial news events.

## Quick Start

```bash
# Process news: extract + classify
uv run python process.py test
```

That's it! One command does everything.

## Directory Structure

```
database_v2/
├── process.py               ⭐ Main script (extract → classify)
│
├── db/                      📁 Database layer
│   ├── __init__.py
│   └── stock_process_db.py  # All Supabase queries
│
├── processors/              📁 Processing modules
│   ├── __init__.py
│   ├── extractor.py         # NewsExtractor class
│   └── classifier.py        # EventClassifier class
│
├── config.py               ⚙️ Configuration
├── 1_event_prompt.txt      📝 LLM prompt
└── README.md               📖 This file
```

## How It Works

`process.py` orchestrates the entire pipeline:

### Step 1: Extract
- Reads from `stock_news_raw` table
- Extracts `title`, `source`, `summary` from `raw_json` JSONB field
- Saves to `stock_process_v1` with `event_based = NULL`
- Skips duplicates and news without summaries
- **Logs skipped news** to `logs/no_summary_*.json` for investigation

### Step 2: Classify
- Fetches all unclassified news (`event_based IS NULL`)
- Classifies with GLM 4.5 Flash (5 news per batch)
- Updates `event_based`, `llm_reasoning`, `model_used`
- Waits 2s between batches (rate limiting)

## Usage

```bash
# Test mode: process last 100 news
uv run python process.py test

# Production mode: process all after 2024-12-20
uv run python process.py production

# Interactive (asks for mode)
uv run python process.py
```

**Output:**
```
======================================================================
STEP 1: EXTRACTING DATA FROM RAW NEWS
======================================================================
Extracting data from 100 news articles...

Extraction Summary:
  Total fetched: 100
  Extracted: 92
  Skipped (no summary): 5
  Skipped (duplicate): 3
  Failed: 0

======================================================================
STEP 2: CLASSIFYING WITH LLM
======================================================================
Classifying 92 unclassified news articles...

Classification Summary:
  Total unclassified: 92
  Successfully classified: 92
    - Event-based: 65
    - Not event-based: 27
  Failed: 0

======================================================================
PIPELINE COMPLETE
======================================================================
Extracted: 92 news
Classified: 92 news
  Event-based: 65
  Not event-based: 27
```

## Module Overview

### db/stock_process_db.py
**All database operations:**
- `fetch_raw_news()` - Get from stock_news_raw
- `fetch_unclassified_news()` - Get NULL event_based
- `insert_extracted_news()` - Save extracted data
- `update_classification()` - Save LLM results
- `check_existing()` - Duplicate detection

### processors/extractor.py
**Data extraction from raw_json:**
- `extract_title()` - Handles `title` or `headline`
- `extract_source()` - Handles `publisher.name` or `source`
- `extract_summary()` - Handles `description` or `summary`
- `extract_and_save()` - Main extraction workflow

### processors/classifier.py
**LLM-based event classification:**
- `classify_news_batch()` - Batch classification (5 at a time)
- `_parse_batch_response()` - Parse LLM output
- Handles GLM quirks (`</arg_value>` → `</think>`)
- Retry logic for empty/incomplete responses

## Database Flow

```
stock_news_raw (input)
  ↓ extract (process.py Step 1)
stock_process_v1 (event_based = NULL)
  ↓ classify (process.py Step 2)
stock_process_v1 (event_based = true/false)
```

## Event Classification

**Event-Based (true):**
- Earnings reports, guidance
- Corporate actions (M&A, buybacks, dividends)
- Product launches
- Leadership changes
- Regulatory/legal events
- Economic data releases

**Not Event-Based (false):**
- Investment advice ("Should you buy...")
- Market commentary ("Stock rallies...")
- Opinion pieces
- General analysis
- Predictions without concrete events

See [1_event_prompt.txt](1_event_prompt.txt) for full classification rules.

## Configuration

Edit [config.py](config.py):

```python
LLM_MODELS = {
    "categorization": {
        "model": "glm-4.5-flash",
        "temperature": 0.3,
        "concurrency_limit": 1,        # Avoid rate limits
        "delay_between_batches": 2.0,  # Seconds between batches
        "max_retries": 2
    }
}
```

## Benefits

1. **One command** - Extract and classify in one run
2. **Clean modules** - Logic separated in processors/
3. **Database layer** - All queries isolated in db/
4. **Robust** - Handles duplicates, retries, errors
5. **Fast** - Only processes what's needed
