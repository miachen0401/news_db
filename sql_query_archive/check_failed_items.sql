-- Check failed processing items to understand what's wrong
SELECT
    id,
    symbol,
    fetch_source,
    url,
    processing_status,
    error_log,
    created_at
FROM stock_news_raw
WHERE processing_status = 'failed'
ORDER BY created_at DESC
LIMIT 20;

-- Check summary of failures by error type
SELECT
    error_log,
    COUNT(*) as count,
    string_agg(DISTINCT symbol, ', ') as symbols
FROM stock_news_raw
WHERE processing_status = 'failed'
GROUP BY error_log
ORDER BY count DESC;
