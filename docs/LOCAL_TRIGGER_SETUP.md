# Local Trigger Setup for Render Free Tier

## Problem
Render's free tier spins down services after 15 minutes of inactivity. Background scheduled jobs don't count as "activity", so the service shuts down even though jobs are scheduled.

## Solution Options

### Option 1: Keep-Alive Mechanism (Already Configured)
The API server now pings itself every 10 minutes to stay alive. This should work on Render free tier.

**How it works:**
- Every 10 minutes, scheduler sends HTTP GET to `/health`
- Keeps service "active" in Render's eyes
- No additional setup needed

**Limitations:**
- May still spin down during very long idle periods
- Uses minimal resources but still consumes your free tier hours

---

### Option 2: Local Triggering (Recommended for Free Tier)

Trigger API jobs from your local computer using cron. The service can spin down between triggers, and wake up when needed.

## Setup Instructions

### 1. Update Configuration

Edit `trigger_remote.py` line 7:
```python
API_URL = "https://your-app-name.onrender.com"  # Replace with your actual URL
```

### 2. Make Script Executable
```bash
chmod +x trigger_remote.py
```

### 3. Test Manual Triggering

```bash
# Check API status
python trigger_remote.py status

# Trigger news fetch
python trigger_remote.py fetch

# Trigger re-categorization
python trigger_remote.py recategorize

# Trigger daily summary
python trigger_remote.py summary

# Trigger all jobs
python trigger_remote.py all
```

### 4. Setup Automated Triggers

**Option A: Using Cron (Linux/Mac)**

```bash
# Edit crontab
crontab -e

# Add these lines (update paths to match your system)
# Fetch news every hour
0 * * * * cd /path/to/news_db && python3 trigger_remote.py fetch >> .log/cron_fetch.log 2>&1

# Re-categorize every 4 hours
0 */4 * * * cd /path/to/news_db && python3 trigger_remote.py recategorize >> .log/cron_recat.log 2>&1

# Daily summary at 7 AM and 5 PM
0 7,17 * * * cd /path/to/news_db && python3 trigger_remote.py summary >> .log/cron_summary.log 2>&1
```

**Option B: Using Task Scheduler (Windows)**

1. Open Task Scheduler
2. Create tasks for each job:
   - **Fetch**: Trigger every 1 hour
   - **Recategorize**: Trigger every 4 hours
   - **Summary**: Trigger at 7 AM and 5 PM daily
3. Action: `python trigger_remote.py <job_name>`
4. Start in: Path to news_db directory

**Option C: Using macOS launchd** (More reliable than cron on Mac)

Create files in `~/Library/LaunchAgents/`:

`com.news.fetch.plist`:
```xml
<?xml version="1.0" encoding="UTF-8"?>
<!DOCTYPE plist PUBLIC "-//Apple//DTD PLIST 1.0//EN" "http://www.apple.com/DTDs/PropertyList-1.0.dtd">
<plist version="1.0">
<dict>
    <key>Label</key>
    <string>com.news.fetch</string>
    <key>ProgramArguments</key>
    <array>
        <string>/usr/bin/python3</string>
        <string>/Users/miaomiao/Documents/pythonProject/news_db/trigger_remote.py</string>
        <string>fetch</string>
    </array>
    <key>StartInterval</key>
    <integer>3600</integer>
    <key>StandardOutPath</key>
    <string>/Users/miaomiao/Documents/pythonProject/news_db/.log/launchd_fetch.log</string>
    <key>StandardErrorPath</key>
    <string>/Users/miaomiao/Documents/pythonProject/news_db/.log/launchd_fetch_error.log</string>
</dict>
</plist>
```

Load the job:
```bash
launchctl load ~/Library/LaunchAgents/com.news.fetch.plist
```

### 5. Monitor Execution

Check logs:
```bash
# View cron logs
tail -f .log/cron_fetch.log
tail -f .log/cron_recat.log
tail -f .log/cron_summary.log

# Check API status
python trigger_remote.py status
```

## Benefits of Local Triggering

✅ **Cost Effective**: Service can spin down between triggers (saves Render hours)
✅ **Reliable**: Not dependent on Render staying awake
✅ **Flexible**: Easy to change schedules without redeploying
✅ **Monitoring**: Local logs show trigger success/failure
✅ **No Code Changes**: API server doesn't need modifications

## Comparison

| Method | Free Tier Friendly | Reliability | Setup Complexity |
|--------|-------------------|-------------|------------------|
| Keep-alive ping | Moderate | Good | Low (already done) |
| Local cron triggers | High | Excellent | Medium |
| Paid Render plan | N/A | Excellent | Low |

## Recommended Approach

**For Free Tier**: Use local cron triggers + let service spin down between jobs

**For Paid Tier**: Use keep-alive ping (already configured) or remove it to save resources

## Troubleshooting

### Service timing out on first request
- **Cause**: Service is spinning up from cold start
- **Solution**: Normal behavior, request will complete in 30-60 seconds

### Jobs not triggering
- **Check**: Verify cron is running: `crontab -l`
- **Check**: Look at log files for errors
- **Check**: Verify API_URL is correct in trigger_remote.py

### Service shows old data
- **Cause**: Jobs may have failed silently
- **Solution**: Check Render logs at dashboard.render.com
