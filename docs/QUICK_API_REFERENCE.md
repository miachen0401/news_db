# Quick API Reference

Fast reference for manual job triggers.

## 🚀 Quick Commands

### Local (Development)
```bash
# Trigger incremental fetch
curl -X POST http://localhost:8000/trigger/fetch

# Trigger re-categorization
curl -X POST http://localhost:8000/trigger/recategorize

# Trigger daily summary
curl -X POST http://localhost:8000/trigger/summary

# Trigger all jobs
curl -X POST http://localhost:8000/trigger/all

# Check status
curl http://localhost:8000/status
```

### Production (Render)
```bash
# Set your URL
export API_URL="https://your-app-name.onrender.com"

# Trigger incremental fetch
curl -X POST $API_URL/trigger/fetch

# Trigger re-categorization
curl -X POST $API_URL/trigger/recategorize

# Trigger daily summary
curl -X POST $API_URL/trigger/summary

# Trigger all jobs
curl -X POST $API_URL/trigger/all

# Check status
curl $API_URL/status

# Request company news
curl http://localhost:8000/news/company/AAPL
curl "http://localhost:8000/news/company/AAPL,TSLA?limit=15"

# Request daily summary
curl http://localhost:8000/summary/daily
```

## 📊 Monitor Jobs

```bash
# View job history
curl http://localhost:8000/ | jq '.jobs'

# Watch in real-time
watch -n 5 'curl -s http://localhost:8000/ | jq .jobs'
```

## 🐍 Python One-Liner

```python
# Trigger fetch
import requests; requests.post("http://localhost:8000/trigger/fetch")

# Trigger recategorize
import requests; requests.post("http://localhost:8000/trigger/recategorize")

# Trigger summary
import requests; requests.post("http://localhost:8000/trigger/summary")

# Trigger all
import requests; requests.post("http://localhost:8000/trigger/all")
```

## ⏰ What Each Job Does

### `/trigger/fetch`
- Fetches incremental news from APIs
- Processes with LLM categorization
- Stores in database
- **Duration:** ~2-5 minutes

### `/trigger/recategorize`
- Processes pending raw news items
- Validates and fixes invalid categories
- Pre-filters "nobody" categories
- Re-categorizes with LLM
- **Duration:** ~1-3 minutes (depends on pending items)

### `/trigger/summary`
- Generates daily news summary
- Uses LLM for summarization
- Saves to database and log file
- **Duration:** ~30-60 seconds

### `/trigger/all`
- Runs all three jobs in parallel
- **Duration:** ~2-5 minutes total

