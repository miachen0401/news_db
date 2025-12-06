# Deployment Guide for Render

This guide explains how to deploy the News Fetcher & Summarizer API to Render.com.

## Overview

The application runs two scheduled tasks:
- **Incremental News Fetch**: Runs every 4 hours
- **Daily Summary**: Runs at 7 AM EST and 5 PM EST

## Deployment Options

### Option 1: Web Service with APScheduler (Recommended)

Deploy as a single always-on web service with built-in scheduling.

**Pros:**
- Simple setup (one service)
- No external dependencies
- All scheduling handled automatically
- Easy monitoring via HTTP endpoints

**Cons:**
- Requires paid plan ($7/month Starter plan)
- Uses compute resources even when idle

**Cost:** ~$7/month

---

### Option 2: Web Service + Render Cron Jobs

Deploy a web service for the API + separate cron jobs that run the scripts.

**Pros:**
- Can use free tier for cron jobs
- Only runs when needed
- Lower compute costs

**Cons:**
- More complex setup (multiple services)
- Need to manage multiple services
- Cron jobs limited on free tier

**Cost:** Free tier possible, or ~$7/month for web service + free cron jobs

---

## Recommended Setup: Option 1 (Web Service with APScheduler)

### Step 1: Prepare Your Repository

1. Ensure all files are committed to GitHub:
   ```bash
   git add .
   git commit -m "Add FastAPI server for Render deployment"
   git push origin main
   ```

2. Verify these files exist:
   - `api_server.py` - FastAPI application
   - `requirements.txt` - Python dependencies
   - `render.yaml` - Render configuration
   - `.env.example` - Example environment variables

### Step 2: Create Render Account

1. Go to [Render.com](https://render.com)
2. Sign up or log in
3. Connect your GitHub account

### Step 3: Create New Web Service

1. Click "New +" → "Web Service"
2. Connect your GitHub repository
3. Render will auto-detect `render.yaml`

**OR manually configure:**
- **Name**: `news-fetcher-api`
- **Region**: Choose closest to your location
- **Branch**: `main`
- **Runtime**: Python
- **Build Command**: `pip install -r requirements.txt`
- **Start Command**: `uvicorn api_server:app --host 0.0.0.0 --port $PORT`
- **Plan**: Starter ($7/month) or higher

### Step 4: Configure Environment Variables

In Render Dashboard → Environment tab, add:

```
FINNHUB_API_KEY=your_finnhub_key
MASSIVE_API_KEY=your_polygon_key
ZHIPU_API_KEY=your_zhipu_key
SUPABASE_NEWS_URL=your_supabase_url
SUPABASE_NEWS_KEY=your_supabase_key
PYTHON_VERSION=3.11.0
```

### Step 5: Deploy

1. Click "Create Web Service"
2. Render will build and deploy automatically
3. Wait for deployment to complete (~3-5 minutes)

### Step 6: Verify Deployment

Once deployed, test the endpoints:

```bash
# Replace with your Render URL
RENDER_URL=https://news-fetcher-api.onrender.com

# Health check
curl $RENDER_URL/health

# Full status
curl $RENDER_URL/status

# View job history
curl $RENDER_URL/
```

### Step 7: Monitor Jobs

Check the scheduler status:
```bash
curl https://news-fetcher-api.onrender.com/status
```

Response will show:
- Scheduled jobs and next run times
- Job execution history
- Last run status and errors

---

## Manual Job Triggers

You can manually trigger jobs via HTTP:

```bash
# Trigger incremental fetch
curl -X POST https://news-fetcher-api.onrender.com/trigger/fetch

# Trigger daily summary
curl -X POST https://news-fetcher-api.onrender.com/trigger/summary

# Trigger all jobs
curl -X POST https://news-fetcher-api.onrender.com/trigger/all
```

---

## Alternative: Option 2 (Cron Jobs)

If you prefer to use Render Cron Jobs:

### Step 1: Deploy Web Service (for API)

Follow Steps 1-6 above, but use free tier or minimal plan.

### Step 2: Create Cron Jobs

**Fetch Incremental (every 6 hours):**
1. Click "New +" → "Cron Job"
2. Configure:
   - **Name**: `news-fetch-cron`
   - **Schedule**: `0 */6 * * *` (every 6 hours)
   - **Command**: `python fetch_incremental_llm_new.py`
   - **Environment**: Same as web service
   - **Plan**: Free

**Daily Summary (7 AM EST):**
1. Click "New +" → "Cron Job"
2. Configure:
   - **Name**: `news-summary-morning`
   - **Schedule**: `0 12 * * *` (12 PM UTC = 7 AM EST)
   - **Command**: `python generate_daily_summary.py`
   - **Environment**: Same as web service
   - **Plan**: Free

**Daily Summary (5 PM EST):**
1. Click "New +" → "Cron Job"
2. Configure:
   - **Name**: `news-summary-evening`
   - **Schedule**: `0 22 * * *` (10 PM UTC = 5 PM EST)
   - **Command**: `python generate_daily_summary.py`
   - **Environment**: Same as web service
   - **Plan**: Free

---

## Troubleshooting

### Scheduler Not Running

Check logs in Render Dashboard:
```bash
# Look for startup message
"Scheduler started successfully"
```

### Jobs Not Executing

1. Check `/status` endpoint for next run times
2. Verify timezone settings (scheduler uses UTC)
3. Check job history for errors

### Memory Issues

If running out of memory:
1. Upgrade to higher plan
2. Reduce batch sizes in `config.py`
3. Reduce concurrency limits

### Environment Variables Not Loading

1. Verify all required vars are set in Render Dashboard
2. Check for typos in variable names
3. Restart service after adding new variables

---

## Cost Estimation

### Option 1 (APScheduler):
- **Starter Plan**: $7/month
- **Total**: ~$7/month

### Option 2 (Cron Jobs):
- **Web Service**: Free or $7/month
- **Cron Jobs**: Free (3 jobs)
- **Total**: Free to ~$7/month

---

## Next Steps

After deployment:

1. **Monitor initial runs**: Check logs for first few scheduled executions
2. **Set up alerts**: Configure Render notifications for failures
3. **Review data**: Verify news is being fetched and stored correctly
4. **Adjust schedules**: Modify timing in `api_server.py` if needed
5. **Scale up**: Upgrade plan if needed for more compute/memory

---

## Support

- [Render Documentation](https://render.com/docs)
- [FastAPI Documentation](https://fastapi.tiangolo.com)
- [APScheduler Documentation](https://apscheduler.readthedocs.io)
