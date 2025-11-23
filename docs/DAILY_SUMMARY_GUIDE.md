# Daily Summary Guide

This guide explains how to use the daily news summary feature.

## Overview

The daily summary feature generates LLM-powered highlights from the `stock_news` table and stores them in the `daily_highlights` table for historical tracking.

## Features

- **Time Window**: Summarizes news from 6PM EST (previous day) to the specified time on the target date
- **Category Filtering**: Automatically excludes `MACRO_NOBODY` category
- **LLM-Powered**: Uses Zhipu AI GLM-4-flash for intelligent summarization
- **Historical Storage**: Saves all summaries to `daily_highlights` table
- **EST Timezone**: All timestamps are in EST for consistency

## Database Setup

### 1. Create the `daily_highlights` Table

Run the migration:

```bash
# Connect to your Supabase database and run:
psql $DATABASE_URL -f migrations/create_daily_highlights_table.sql
```

Or execute via Supabase SQL Editor:
```sql
-- See: migrations/create_daily_highlights_table.sql
```

### 2. Table Schema

```sql
daily_highlights (
    id UUID PRIMARY KEY,
    summary_date DATE NOT NULL,
    summary_time TIME NOT NULL,
    from_time TIMESTAMP NOT NULL,
    to_time TIMESTAMP NOT NULL,
    highlight_text TEXT NOT NULL,
    news_count INTEGER NOT NULL,
    categories_included TEXT[],
    created_at TIMESTAMP,
    updated_at TIMESTAMP,
    UNIQUE (summary_date, summary_time)
)
```

## Usage

### Generate Summary for Today (Now)

```bash
python generate_daily_summary.py
```

This will:
- Use today's date
- Use current time as the summary time
- Fetch news from 6PM EST yesterday to now
- Generate summary and save to database

### Generate Summary for Specific Date/Time

Edit `generate_daily_summary.py`:

```python
# For a specific date at current time
SUMMARY_DATE = "2025-11-23"  # Format: YYYY-MM-DD
SUMMARY_TIME = None  # Use current time

# For a specific date and time
SUMMARY_DATE = "2025-11-23"  # Format: YYYY-MM-DD
SUMMARY_TIME = "17:00:00"    # Format: HH:MM:SS (EST)
```

Then run:
```bash
python generate_daily_summary.py
```

## Time Window Calculation

The summary includes news published between:

**From**: 6:00 PM EST on `(summary_date - 1 day)`
**To**: `summary_time` EST on `summary_date`

### Examples

| Summary Date | Summary Time | From Time (EST)        | To Time (EST)          |
|--------------|--------------|------------------------|------------------------|
| 2025-11-23   | 09:00:00     | 2025-11-22 18:00:00   | 2025-11-23 09:00:00   |
| 2025-11-23   | 17:00:00     | 2025-11-22 18:00:00   | 2025-11-23 17:00:00   |
| 2025-11-24   | 12:00:00     | 2025-11-23 18:00:00   | 2025-11-24 12:00:00   |

## News Filtering

### Included Categories
All categories **except** `MACRO_NOBODY`:
- MACRO_ECONOMIC
- CENTRAL_BANK_POLICY
- GEOPOLITICAL_SPECIFIC
- INDUSTRY_REGULATION
- EARNINGS_FINANCIALS
- CORPORATE_ACTIONS
- MANAGEMENT_CHANGES
- PRODUCT_TECH_UPDATE
- BUSINESS_OPERATIONS
- ACCIDENT_INCIDENT
- ANALYST_RATING
- MARKET_SENTIMENT
- TECHNICAL_ANALYSIS
- STOCK_MOVEMENT

### Excluded Categories
- MACRO_NOBODY (generic macro commentary without specific entities)

## Output Format

The LLM generates summaries organized by sector/theme:

```markdown
## Technology
- **Apple** (AAPL): Q4 earnings beat expectations with revenue up 8% YoY
- **Microsoft** (MSFT): Announced $10B cloud infrastructure investment in Asia

## Finance
- **JPMorgan** (JPM): CEO warns of potential recession in H2 2024 due to inflation
- **Goldman Sachs** (GS): Upgraded to Buy by Morgan Stanley; PT raised to $450

## Energy
- **Chevron** (CVX): Announces $5B stock buyback program
```

## Programmatic Access

### Fetch Recent Summaries

```python
from supabase import create_client
from db.daily_highlights import DailyHighlightDB

supabase = create_client(url, key)
highlights_db = DailyHighlightDB(supabase)

# Get last 10 summaries
recent = await highlights_db.get_recent_highlights(limit=10)

for highlight in recent:
    print(f"{highlight['summary_date']} {highlight['summary_time']}")
    print(highlight['highlight_text'])
```

### Fetch Summary for Specific Date

```python
from datetime import date, time

# Get summary for Nov 23, 2025 at 5PM
summary = await highlights_db.get_highlight(
    summary_date=date(2025, 11, 23),
    summary_time=time(17, 0, 0)
)

if summary:
    print(summary['highlight_text'])
```

### Fetch Summaries by Date Range

```python
from datetime import date

summaries = await highlights_db.get_highlights_by_date_range(
    start_date=date(2025, 11, 1),
    end_date=date(2025, 11, 30)
)

print(f"Found {len(summaries)} summaries in November")
```

## Monitoring Queries

### Check Recent Summaries

```sql
SELECT
    summary_date,
    summary_time,
    news_count,
    array_length(categories_included, 1) as num_categories,
    length(highlight_text) as summary_length,
    created_at
FROM daily_highlights
ORDER BY summary_date DESC, summary_time DESC
LIMIT 10;
```

### Summaries by Date

```sql
SELECT
    summary_date,
    COUNT(*) as summaries_per_day,
    SUM(news_count) as total_news
FROM daily_highlights
GROUP BY summary_date
ORDER BY summary_date DESC;
```

### Most Common Categories

```sql
SELECT
    unnest(categories_included) as category,
    COUNT(*) as frequency
FROM daily_highlights
GROUP BY category
ORDER BY frequency DESC;
```

## Troubleshooting

### No News Found

If you see "No news found in time window":
- Check if news exists in `stock_news` table for the specified time range
- Verify the time window calculation (6PM previous day to summary time)
- Ensure news has `published_at` timestamps in EST

### LLM API Error

If summary generation fails:
- Verify `ZHIPU_API_KEY` is set correctly in `.env`
- Check API quota/rate limits
- Review error message for specific API issues

### Duplicate Summary Error

If you see a unique constraint violation:
- A summary already exists for this date+time
- Either delete the existing summary or use a different time
- The script will upsert (update) if summary exists

## Best Practices

1. **Regular Schedule**: Run daily summaries at consistent times (e.g., 9AM, 5PM EST)
2. **Historical Backfill**: Use specific dates to generate summaries for past dates
3. **Multiple Times**: Generate multiple summaries per day (morning, afternoon, evening)
4. **Archive**: Daily highlights are automatically stored for historical reference
5. **Timezone**: Always work in EST for consistency with news timestamps

## Configuration

### LLM Temperature

Default: `0.3` (more consistent, less creative)

To adjust, edit `generate_daily_summary.py`:

```python
highlight_text = await summarizer.generate_daily_summary(
    news_items=news_items,
    temperature=0.5  # Higher = more creative, lower = more consistent
)
```

### LLM Model

Default: `glm-4-flash`

To change model, edit `services/daily_summarizer.py`:

```python
self.model = "glm-4-flash"  # or other Zhipu AI models
```

## Example Workflow

### Daily Morning Summary (9AM EST)

```python
# Edit generate_daily_summary.py
SUMMARY_DATE = None  # Today
SUMMARY_TIME = "09:00:00"  # 9AM EST

# Run
python generate_daily_summary.py
```

This captures overnight news (6PM yesterday → 9AM today)

### Daily Closing Summary (5PM EST)

```python
# Edit generate_daily_summary.py
SUMMARY_DATE = None  # Today
SUMMARY_TIME = "17:00:00"  # 5PM EST

# Run
python generate_daily_summary.py
```

This captures full day news (6PM yesterday → 5PM today)

### Backfill Historical Summaries

```python
# Edit generate_daily_summary.py
SUMMARY_DATE = "2025-11-20"  # Specific past date
SUMMARY_TIME = "17:00:00"    # End of trading day

# Run
python generate_daily_summary.py
```

## Integration with News Pipeline

The daily summary works seamlessly with your news fetching pipeline:

1. **Fetch News**: Run `fetch_incremental_llm.py` to get latest news
2. **Categorize**: News is automatically categorized by LLM
3. **Store**: News saved to `stock_news` table
4. **Summarize**: Run `generate_daily_summary.py` to create highlights
5. **Archive**: Summaries stored in `daily_highlights` for historical access

All operations use EST timezone for consistency!
