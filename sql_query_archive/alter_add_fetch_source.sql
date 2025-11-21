-- ============================================================
-- Add fetch_source column to stock_news table
-- ============================================================
-- Tracks which API fetched the news (finnhub, polygon, etc.)
-- Useful for data quality analysis

-- Add the column
ALTER TABLE stock_news
ADD COLUMN IF NOT EXISTS fetch_source TEXT;

-- Add index for filtering by fetch source
CREATE INDEX IF NOT EXISTS idx_stock_news_fetch_source
ON stock_news(fetch_source);

-- Add comment
COMMENT ON COLUMN stock_news.fetch_source IS 'API source that fetched the news (finnhub, polygon, newsapi, etc.)';

-- Verify
SELECT column_name, data_type, is_nullable
FROM information_schema.columns
WHERE table_name = 'stock_news'
AND column_name = 'fetch_source';

-- Check distribution of existing data
SELECT
    fetch_source,
    COUNT(*) as count,
    COUNT(DISTINCT symbol) as unique_symbols
FROM stock_news
GROUP BY fetch_source
ORDER BY count DESC;
