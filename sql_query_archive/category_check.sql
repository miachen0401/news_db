-- ============================================================
-- Category Health Check Queries
-- Purpose: Check news items with categories outside defined list
-- ============================================================

-- ============================================================
-- 1. SIMPLE COUNT - Quick health check
-- ============================================================
-- Count of news items needing re-categorization
SELECT COUNT(*) as items_needing_fix
FROM stock_news
WHERE category NOT IN (
    'MACRO_ECONOMY',
    'CENTRAL_BANK_POLICY',
    'GEOPOLITICAL_EVENT',
    'INDUSTRY_REGULATION',
    'CORPORATE_EARNINGS',
    'CORPORATE_ACTIONS',
    'MANAGEMENT_CHANGE',
    'PRODUCT_TECH_UPDATE',
    'BUSINESS_OPERATIONS',
    'INCIDENT_LEGAL',
    'ANALYST_OPINION',
    'MARKET_SENTIMENT',
    'ERROR',
    'NON_FINANCIAL'
);


-- ============================================================
-- 2. CATEGORY BREAKDOWN - What invalid categories exist
-- ============================================================
SELECT
    category,
    COUNT(*) as count,
    ROUND(COUNT(*) * 100.0 / SUM(COUNT(*)) OVER (), 2) as percentage
FROM stock_news
WHERE category NOT IN (
    'MACRO_ECONOMY',
    'CENTRAL_BANK_POLICY',
    'GEOPOLITICAL_EVENT',
    'INDUSTRY_REGULATION',
    'CORPORATE_EARNINGS',
    'CORPORATE_ACTIONS',
    'MANAGEMENT_CHANGE',
    'PRODUCT_TECH_UPDATE',
    'BUSINESS_OPERATIONS',
    'INCIDENT_LEGAL',
    'ANALYST_OPINION',
    'MARKET_SENTIMENT',
    'ERROR',
    'NON_FINANCIAL'
)
GROUP BY category
ORDER BY count DESC;


-- ============================================================
-- 3. SAMPLE NEWS ITEMS - See actual examples
-- ============================================================
SELECT
    category,
    title,
    source,
    created_at,
    error_log
FROM stock_news
WHERE category NOT IN (
    'MACRO_ECONOMY',
    'CENTRAL_BANK_POLICY',
    'GEOPOLITICAL_EVENT',
    'INDUSTRY_REGULATION',
    'CORPORATE_EARNINGS',
    'CORPORATE_ACTIONS',
    'MANAGEMENT_CHANGE',
    'PRODUCT_TECH_UPDATE',
    'BUSINESS_OPERATIONS',
    'INCIDENT_LEGAL',
    'ANALYST_OPINION',
    'MARKET_SENTIMENT',
    'ERROR',
    'NON_FINANCIAL'
)
ORDER BY created_at DESC
LIMIT 20;


-- ============================================================
-- 4. COMPREHENSIVE DASHBOARD - Full overview
-- ============================================================
WITH category_stats AS (
    SELECT
        CASE
            WHEN category IN (
                'MACRO_ECONOMY', 'CENTRAL_BANK_POLICY', 'GEOPOLITICAL_EVENT',
                'INDUSTRY_REGULATION', 'CORPORATE_EARNINGS', 'CORPORATE_ACTIONS',
                'MANAGEMENT_CHANGE', 'PRODUCT_TECH_UPDATE', 'BUSINESS_OPERATIONS',
                'INCIDENT_LEGAL', 'ANALYST_OPINION', 'MARKET_SENTIMENT'
            ) THEN 'Valid Financial'
            WHEN category = 'ERROR' THEN 'Permanent Error'
            WHEN category = 'NON_FINANCIAL' THEN 'Non-Financial'
            WHEN category = 'UNCATEGORIZED' THEN 'Needs Retry'
            ELSE 'Invalid Category'
        END as category_type,
        category,
        COUNT(*) as count
    FROM stock_news
    GROUP BY category
)
SELECT
    category_type,
    category,
    count,
    ROUND(count * 100.0 / SUM(count) OVER (), 2) as pct_of_total
FROM category_stats
ORDER BY
    CASE category_type
        WHEN 'Valid Financial' THEN 1
        WHEN 'Non-Financial' THEN 2
        WHEN 'Needs Retry' THEN 3
        WHEN 'Invalid Category' THEN 4
        WHEN 'Permanent Error' THEN 5
    END,
    count DESC;


-- ============================================================
-- 5. TIMELINE - When did invalid categories appear
-- ============================================================
SELECT
    DATE_TRUNC('day', created_at) as date,
    category,
    COUNT(*) as daily_count
FROM stock_news
WHERE category NOT IN (
    'MACRO_ECONOMY', 'CENTRAL_BANK_POLICY', 'GEOPOLITICAL_EVENT',
    'INDUSTRY_REGULATION', 'CORPORATE_EARNINGS', 'CORPORATE_ACTIONS',
    'MANAGEMENT_CHANGE', 'PRODUCT_TECH_UPDATE', 'BUSINESS_OPERATIONS',
    'INCIDENT_LEGAL', 'ANALYST_OPINION', 'MARKET_SENTIMENT',
    'ERROR', 'NON_FINANCIAL'
)
GROUP BY DATE_TRUNC('day', created_at), category
ORDER BY date DESC, daily_count DESC
LIMIT 50;


-- ============================================================
-- 6. HEALTH CHECK - Overall data quality metrics
-- ============================================================
SELECT
    COUNT(*) as total_news,
    COUNT(*) FILTER (WHERE category IN (
        'MACRO_ECONOMY', 'CENTRAL_BANK_POLICY', 'GEOPOLITICAL_EVENT',
        'INDUSTRY_REGULATION', 'CORPORATE_EARNINGS', 'CORPORATE_ACTIONS',
        'MANAGEMENT_CHANGE', 'PRODUCT_TECH_UPDATE', 'BUSINESS_OPERATIONS',
        'INCIDENT_LEGAL', 'ANALYST_OPINION', 'MARKET_SENTIMENT'
    )) as valid_financial,
    COUNT(*) FILTER (WHERE category = 'UNCATEGORIZED') as uncategorized,
    COUNT(*) FILTER (WHERE category = 'ERROR') as permanent_errors,
    COUNT(*) FILTER (WHERE category = 'NON_FINANCIAL') as non_financial,
    COUNT(*) FILTER (WHERE category NOT IN (
        'MACRO_ECONOMY', 'CENTRAL_BANK_POLICY', 'GEOPOLITICAL_EVENT',
        'INDUSTRY_REGULATION', 'CORPORATE_EARNINGS', 'CORPORATE_ACTIONS',
        'MANAGEMENT_CHANGE', 'PRODUCT_TECH_UPDATE', 'BUSINESS_OPERATIONS',
        'INCIDENT_LEGAL', 'ANALYST_OPINION', 'MARKET_SENTIMENT',
        'ERROR', 'NON_FINANCIAL', 'UNCATEGORIZED'
    )) as invalid_categories,
    ROUND(
        COUNT(*) FILTER (WHERE category IN (
            'MACRO_ECONOMY', 'CENTRAL_BANK_POLICY', 'GEOPOLITICAL_EVENT',
            'INDUSTRY_REGULATION', 'CORPORATE_EARNINGS', 'CORPORATE_ACTIONS',
            'MANAGEMENT_CHANGE', 'PRODUCT_TECH_UPDATE', 'BUSINESS_OPERATIONS',
            'INCIDENT_LEGAL', 'ANALYST_OPINION', 'MARKET_SENTIMENT'
        )) * 100.0 / COUNT(*),
        2
    ) as valid_percentage
FROM stock_news;


-- ============================================================
-- 7. "NOBODY" CATEGORIES - Check categories with "nobody"
-- ============================================================
-- These should be auto-filtered as NON_FINANCIAL by the pre-filter
SELECT
    category,
    COUNT(*) as count,
    array_agg(DISTINCT title) FILTER (WHERE title IS NOT NULL) as sample_titles
FROM stock_news
WHERE LOWER(category) LIKE '%nobody%'
GROUP BY category
ORDER BY count DESC;


-- ============================================================
-- 8. PRE-FILTER AUDIT - Items auto-filtered by "nobody" check
-- ============================================================
SELECT
    category,
    title,
    error_log,
    created_at,
    updated_at
FROM stock_news
WHERE category = 'NON_FINANCIAL'
  AND error_log LIKE '%Auto-filtered: category contained ''nobody''%'
ORDER BY updated_at DESC
LIMIT 50;


-- ============================================================
-- USAGE GUIDE
-- ============================================================
-- Quick check:          Run Query #1 or #6
-- Debugging:            Run Query #2 to see invalid categories
-- Investigation:        Run Query #3 for actual examples
-- Monitoring:           Run Query #4 for dashboard view
-- Trend analysis:       Run Query #5 for timeline
-- "Nobody" check:       Run Query #7
-- Pre-filter audit:     Run Query #8
-- ============================================================
