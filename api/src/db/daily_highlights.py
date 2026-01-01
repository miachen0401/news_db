"""Database operations for daily highlights."""
from typing import Optional, Dict, Any, List
from datetime import datetime, date, time, timezone
from supabase import Client
import asyncio
import logging
logger = logging.getLogger(__name__)


# UTC timezone
UTC = timezone.utc


class DailyHighlightDB:
    """Manages daily highlights in the database."""

    def __init__(self, client: Client):
        """
        Initialize daily highlight database manager.

        Args:
            client: Supabase client instance
        """
        self.client = client
        self.table_name = "daily_highlights"

    async def save_highlight(
        self,
        summary_date: date,
        summary_time: time,
        from_time: datetime,
        to_time: datetime,
        highlight_text: str,
        news_count: int,
        categories_included: List[str],
        symbol: Optional[str] = None
    ) -> bool:
        """
        Save or update a daily highlight.

        Args:
            summary_date: Date of the summary (EST)
            summary_time: Time of the summary (EST)
            from_time: Start of news window (UTC)
            to_time: End of news window (UTC)
            highlight_text: LLM-generated summary
            news_count: Number of news articles
            categories_included: List of categories included
            symbol: Optional company stock symbol for company-specific summaries

        Returns:
            True if successful
        """
        try:
            data = {
                "summary_date": summary_date.isoformat(),
                "summary_time": summary_time.isoformat(),
                "from_time": from_time.isoformat(),
                "to_time": to_time.isoformat(),
                "highlight_text": highlight_text,
                "news_count": news_count,
                "categories_included": categories_included,
                "symbol": symbol,
                "updated_at": datetime.now(UTC).replace(tzinfo=None).isoformat(),
            }

            def _upsert():
                return (
                    self.client
                    .table(self.table_name)
                    .upsert(data, on_conflict="summary_date,summary_time,symbol")
                    .execute()
                )

            await asyncio.to_thread(_upsert)

            symbol_text = f" for {symbol}" if symbol else ""
            logger.debug(f"✅ Saved daily highlight{symbol_text}: {summary_date} {summary_time}")
            return True

        except Exception as e:
            logger.error(f"❌ Error saving daily highlight: {e}")
            import traceback
            logger.error(traceback.format_exc())
            return False

    async def get_highlight(
        self,
        summary_date: date,
        summary_time: Optional[time] = None,
        symbol: Optional[str] = None
    ) -> Optional[Dict[str, Any]]:
        """
        Get a daily highlight by date and optionally time.

        Args:
            summary_date: Date of the summary
            summary_time: Optional time of the summary
            symbol: Optional company stock symbol ("general" for general summaries, specific symbol for company summaries)

        Returns:
            Highlight data or None if not found
        """
        try:
            def _fetch():
                query = (
                    self.client
                    .table(self.table_name)
                    .select("*")
                    .eq("summary_date", summary_date.isoformat())
                )

                if summary_time:
                    query = query.eq("summary_time", summary_time.isoformat())

                # Filter by symbol (None means don't filter, specific value matches that symbol)
                if symbol is not None:
                    query = query.eq("symbol", symbol)

                return query.order("summary_time", desc=True).limit(1).execute()

            result = await asyncio.to_thread(_fetch)

            if result.data and len(result.data) > 0:
                return result.data[0]

            return None

        except Exception as e:
            logger.debug(f"❌ Error getting daily highlight: {e}")
            return None

    async def get_recent_highlights(
        self,
        limit: int = 10
    ) -> List[Dict[str, Any]]:
        """
        Get recent daily highlights.

        Args:
            limit: Maximum number of highlights to return

        Returns:
            List of highlight records
        """
        try:
            def _fetch():
                return (
                    self.client
                    .table(self.table_name)
                    .select("*")
                    .order("summary_date", desc=True)
                    .order("summary_time", desc=True)
                    .limit(limit)
                    .execute()
                )

            result = await asyncio.to_thread(_fetch)
            return result.data or []

        except Exception as e:
            logger.debug(f"❌ Error getting recent highlights: {e}")
            return []

    async def get_highlights_by_date_range(
        self,
        start_date: date,
        end_date: date
    ) -> List[Dict[str, Any]]:
        """
        Get highlights within a date range.

        Args:
            start_date: Start date (inclusive)
            end_date: End date (inclusive)

        Returns:
            List of highlight records
        """
        try:
            def _fetch():
                return (
                    self.client
                    .table(self.table_name)
                    .select("*")
                    .gte("summary_date", start_date.isoformat())
                    .lte("summary_date", end_date.isoformat())
                    .order("summary_date", desc=True)
                    .order("summary_time", desc=True)
                    .execute()
                )

            result = await asyncio.to_thread(_fetch)
            return result.data or []

        except Exception as e:
            logger.debug(f"❌ Error getting highlights by date range: {e}")
            return []
