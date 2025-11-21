-- ============================================================
-- Add secondary_category column to stock_news table
-- ============================================================
-- Stores stock ticker symbols mentioned in the news

-- Add the column
ALTER TABLE stock_news
ADD COLUMN IF NOT EXISTS secondary_category TEXT;

-- Add index for filtering by secondary category
CREATE INDEX IF NOT EXISTS idx_stock_news_secondary_category
ON stock_news(secondary_category);

-- Add comment
COMMENT ON COLUMN stock_news.secondary_category IS 'Stock ticker symbols mentioned in the news (comma-separated if multiple), empty if not company-specific';

-- Update category column comment for clarity
COMMENT ON COLUMN stock_news.category IS 'Primary news category (MACRO_ECONOMIC, EARNINGS_FINANCIALS, etc.)';

-- Verify
SELECT column_name, data_type, is_nullable
FROM information_schema.columns
WHERE table_name = 'stock_news'
AND column_name IN ('category', 'secondary_category')
ORDER BY ordinal_position;
