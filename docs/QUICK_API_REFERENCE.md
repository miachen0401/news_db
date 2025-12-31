# Quick API Reference

Fast reference for API endpoints, commands, and workflows.

## 📋 Table of Contents

- [Quick Commands](#-quick-commands)
- [API Endpoints](#-api-endpoints)
- [Monitor Jobs](#-monitor-jobs)
- [Python Usage](#-python-usage)
- [What Each Job Does](#-what-each-job-does)
- [Query Parameters](#-query-parameters)
- [Response Formats](#-response-formats)

## 🚀 Quick Commands

### Local Development
```bash
# Health check
curl http://localhost:8000/

# System status
curl http://localhost:8000/status

# Trigger incremental fetch
curl -X POST http://localhost:8000/trigger/fetch

# Trigger re-categorization
curl -X POST http://localhost:8000/trigger/recategorize

# Trigger daily summary
curl -X POST http://localhost:8000/trigger/summary

# Trigger all jobs in parallel
curl -X POST http://localhost:8000/trigger/all

# Get company news
curl http://localhost:8000/news/company/AAPL
curl "http://localhost:8000/news/company/AAPL,TSLA?limit=15"

# Get daily summary
curl http://localhost:8000/summary/daily
curl "http://localhost:8000/summary/daily?date=2025-12-29"
```

### Production (Render)
```bash
# Set your production URL
export API_URL="https://your-app-name.onrender.com"

# All the same commands work with $API_URL
curl $API_URL/
curl $API_URL/status
curl -X POST $API_URL/trigger/fetch
curl -X POST $API_URL/trigger/recategorize
curl -X POST $API_URL/trigger/summary
curl -X POST $API_URL/trigger/all
curl $API_URL/news/company/AAPL
curl "$API_URL/summary/daily?date=2025-12-29"
```

## 🔌 API Endpoints

### Health & Status

| Method | Endpoint | Description | Response |
|--------|----------|-------------|----------|
| GET | `/` | Root health check | System info & job history |
| GET | `/status` | Detailed system status | Database stats, last fetch times |

### Job Triggers

| Method | Endpoint | Description | Duration |
|--------|----------|-------------|----------|
| POST | `/trigger/fetch` | Incremental news fetch + LLM categorization | 2-5 min |
| POST | `/trigger/recategorize` | Re-categorize pending/failed items | 1-3 min |
| POST | `/trigger/summary` | Generate daily news summary | 30-60 sec |
| POST | `/trigger/all` | Run all jobs in parallel | 2-5 min |

### Data Retrieval

| Method | Endpoint | Description | Parameters |
|--------|----------|-------------|------------|
| GET | `/news/company/{symbols}` | Get company-specific news | `symbols`: comma-separated (e.g., AAPL,TSLA)<br>`limit`: max results (default: 10) |
| GET | `/summary/daily` | Get latest daily summary | `date`: YYYY-MM-DD (default: today) |

## 📊 Monitor Jobs

### Using curl + jq
```bash
# View all system info
curl http://localhost:8000/ | jq

# View job history only
curl http://localhost:8000/ | jq '.jobs'

# View latest job
curl http://localhost:8000/ | jq '.jobs[0]'

# Check status
curl http://localhost:8000/status | jq

# Watch in real-time
watch -n 5 'curl -s http://localhost:8000/ | jq .jobs'

# Watch status in real-time
watch -n 10 'curl -s http://localhost:8000/status | jq'
```

### Database Queries
```sql
-- Check fetch state (last fetch times)
SELECT symbol, fetch_source, last_fetch_to, articles_fetched
FROM fetch_state
ORDER BY updated_at DESC;

-- Count pending raw news
SELECT COUNT(*) FROM stock_news_raw
WHERE processing_status = 'pending';

-- Recent categorized news
SELECT category, headline, published_at
FROM stock_news
ORDER BY published_at DESC
LIMIT 10;

-- Recent daily summaries
SELECT summary_date, news_count,
       array_length(categories_included, 1) as num_categories
FROM daily_highlights
ORDER BY summary_date DESC, summary_time DESC
LIMIT 5;
```

## 🐍 Python Usage

### Quick Triggers
```python
import requests

# Base URL
API_URL = "http://localhost:8000"  # or production URL

# Trigger fetch
requests.post(f"{API_URL}/trigger/fetch")

# Trigger recategorize
requests.post(f"{API_URL}/trigger/recategorize")

# Trigger summary
requests.post(f"{API_URL}/trigger/summary")

# Trigger all jobs
requests.post(f"{API_URL}/trigger/all")
```

### Get Data
```python
import requests

API_URL = "http://localhost:8000"

# Get company news
response = requests.get(f"{API_URL}/news/company/AAPL")
news = response.json()

# Get multiple companies with limit
response = requests.get(f"{API_URL}/news/company/AAPL,TSLA,NVDA",
                       params={"limit": 20})
news = response.json()

# Get daily summary
response = requests.get(f"{API_URL}/summary/daily")
summary = response.json()

# Get specific date summary
response = requests.get(f"{API_URL}/summary/daily",
                       params={"date": "2025-12-29"})
summary = response.json()

# Check system status
response = requests.get(f"{API_URL}/status")
status = response.json()
print(f"Raw news pending: {status['raw_news_pending']}")
print(f"Total categorized: {status['categorized_news_count']}")
```

### Error Handling
```python
import requests

API_URL = "http://localhost:8000"

try:
    response = requests.post(f"{API_URL}/trigger/fetch", timeout=300)
    response.raise_for_status()
    result = response.json()
    print(f"Job ID: {result['job_id']}")
    print(f"Status: {result['status']}")
except requests.exceptions.Timeout:
    print("Request timed out (job may still be running)")
except requests.exceptions.HTTPError as e:
    print(f"HTTP error: {e}")
except Exception as e:
    print(f"Error: {e}")
```

## ⏰ What Each Job Does

### `/trigger/fetch` - Incremental News Fetch
**What it does:**
1. Fetches new news from APIs (Finnhub general, merger, company-specific; Polygon)
2. Stores raw news in `stock_news_raw` table
3. LLM categorization (batches of 5, max 20 items per run)
4. Stores financial news in `stock_news` table (filters NON_FINANCIAL)
5. Runs data corrections (cleanup empty strings)
6. Updates fetch state checkpoints

**Duration:** ~2-5 minutes
**Frequency:** Every 15-30 minutes or hourly
**Output:** Categorized financial news ready for analysis

### `/trigger/recategorize` - Re-categorization
**What it does:**
1. Finds pending/failed items in `stock_news_raw`
2. Validates existing categories
3. Pre-filters "nobody" categories (generic geopolitical)
4. Re-categorizes with LLM
5. Updates `stock_news` table

**Duration:** ~1-3 minutes (depends on pending count)
**Frequency:** As needed (when seeing failed items or bad categories)
**Output:** Fixed/updated categorizations

### `/trigger/summary` - Daily Summary
**What it does:**
1. Fetches news from 6PM EST (previous day) to now
2. Filters to 13 valid financial categories
3. Generates structured LLM summary
4. Saves to `daily_highlights` table
5. Caches locally in `.log/summary_*.log`

**Duration:** ~30-60 seconds
**Frequency:** Daily (after market hours)
**Output:** Human-readable daily highlights

### `/trigger/all` - Run All Jobs
**What it does:**
- Runs fetch, recategorize, and summary in parallel
- Most efficient way to update everything at once

**Duration:** ~2-5 minutes total
**Frequency:** On-demand
**Output:** Complete system update

## 🔧 Query Parameters

### `/news/company/{symbols}`
| Parameter | Type | Required | Description | Example |
|-----------|------|----------|-------------|---------|
| `symbols` | string | Yes | Comma-separated stock symbols | `AAPL` or `AAPL,TSLA,NVDA` |
| `limit` | integer | No | Max results to return (default: 10) | `limit=20` |

**Example:**
```bash
curl "http://localhost:8000/news/company/AAPL,TSLA?limit=15"
```

### `/summary/daily`
| Parameter | Type | Required | Description | Example |
|-----------|------|----------|-------------|---------|
| `date` | string | No | Date in YYYY-MM-DD format (default: today) | `date=2025-12-29` |

**Example:**
```bash
curl "http://localhost:8000/summary/daily?date=2025-12-29"
```

## 📦 Response Formats

### `/` - Root Endpoint
```json
{
  "service": "News Database API",
  "status": "running",
  "timestamp": "2025-12-30T10:30:00Z",
  "jobs": [
    {
      "job_id": "fetch_1735556400",
      "job_type": "fetch",
      "status": "completed",
      "started_at": "2025-12-30T10:00:00Z",
      "completed_at": "2025-12-30T10:03:45Z",
      "duration_seconds": 225,
      "result": {
        "articles_fetched": 45,
        "articles_categorized": 38,
        "articles_stored": 38
      }
    }
  ]
}
```

### `/status` - System Status
```json
{
  "database_connected": true,
  "raw_news_pending": 5,
  "categorized_news_count": 1247,
  "last_fetch_times": {
    "finnhub_general": "2025-12-30T10:00:00Z",
    "polygon": "2025-12-30T09:55:00Z",
    "finnhub_AAPL": "2025-12-30T10:00:00Z"
  },
  "daily_summaries_count": 15
}
```

### `/trigger/*` - Job Triggers
```json
{
  "status": "started",
  "job_id": "fetch_1735556400",
  "job_type": "fetch",
  "message": "Job started successfully",
  "started_at": "2025-12-30T10:00:00Z"
}
```

### `/news/company/{symbols}` - Company News
```json
{
  "symbols": ["AAPL", "TSLA"],
  "count": 15,
  "news": [
    {
      "id": 1234,
      "symbol": "AAPL",
      "category": "PRODUCT_TECH_UPDATE",
      "headline": "Apple Announces New AI Features",
      "summary": "Apple revealed new AI capabilities...",
      "url": "https://example.com/article",
      "published_at": "2025-12-30T09:30:00Z",
      "source": "Bloomberg",
      "related_stocks": ["AAPL", "MSFT"]
    }
  ]
}
```

### `/summary/daily` - Daily Summary
```json
{
  "summary_date": "2025-12-30",
  "summary_time": "17:00:00",
  "from_time": "2025-12-29T23:00:00Z",
  "to_time": "2025-12-30T22:00:00Z",
  "news_count": 127,
  "categories_included": [
    "MACRO_ECONOMIC",
    "EARNINGS_FINANCIALS",
    "CORPORATE_ACTIONS",
    "PRODUCT_TECH_UPDATE"
  ],
  "highlight_text": "**Market Overview**\n\n- Tech sector showed strong momentum...\n\n**Key Developments**\n\n- Apple announced new AI features...\n- Tesla reported record deliveries...\n\n**Earnings & Financials**\n\n- Multiple companies beat earnings expectations..."
}
```

## 🔍 Common Workflows

### Daily Update Routine
```bash
# Morning: Fetch overnight news
curl -X POST $API_URL/trigger/fetch

# Check what was fetched
curl $API_URL/status | jq

# After market close: Generate summary
curl -X POST $API_URL/trigger/summary

# View the summary
curl $API_URL/summary/daily | jq '.highlight_text'
```

### Debugging Failed Items
```bash
# Check for pending items
curl $API_URL/status | jq '.raw_news_pending'

# Re-categorize if needed
curl -X POST $API_URL/trigger/recategorize

# Verify it worked
curl $API_URL/status | jq '.raw_news_pending'
```

### Complete System Refresh
```bash
# Run everything at once
curl -X POST $API_URL/trigger/all

# Watch progress
watch -n 10 'curl -s $API_URL/status | jq'
```

## 📝 Notes

- All timestamps in UTC (database storage)
- Summary times displayed in EST (user-facing)
- Jobs run asynchronously - check `/status` for completion
- Rate limits: Zhipu AI has 2 concurrent request limit (system handles this)
- Duplicate prevention: URL-based deduplication in `stock_news_raw`
- Categories: 15 total, 13 included in summaries (excludes MACRO_NOBODY, NON_FINANCIAL)

