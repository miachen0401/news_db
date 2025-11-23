"""Fetch state manager for incremental news fetching."""
from typing import Optional, Dict, Any, Tuple
from datetime import datetime, timedelta, timezone
from supabase import Client
import asyncio

# EST timezone (UTC-5) - for display only
EST = timezone(timedelta(hours=-5))
UTC = timezone.utc


class FetchStateManager:
    """Manages fetch state for incremental news fetching."""

    def __init__(self, client: Client):
        """
        Initialize fetch state manager.

        Args:
            client: Supabase client instance
        """
        self.client = client
        self.table_name = "fetch_state"

    async def get_latest_news_timestamp(
        self,
        symbol: str,
        fetch_source: str
    ) -> Optional[datetime]:
        """
        Get the latest published_at timestamp from stock_news_raw for a source.

        Args:
            symbol: Stock ticker symbol
            fetch_source: Source name (finnhub, polygon, etc.)

        Returns:
            Latest published_at datetime or None if no news found
        """
        try:
            def _fetch():
                return (
                    self.client
                    .table("stock_news_raw")
                    .select("published_at")
                    .eq("symbol", symbol.upper())
                    .eq("fetch_source", fetch_source)
                    .order("published_at", desc=True)
                    .limit(1)
                    .execute()
                )

            result = await asyncio.to_thread(_fetch)

            if result.data and len(result.data) > 0:
                return datetime.fromisoformat(result.data[0]["published_at"])

        except Exception as e:
            print(f"⚠️  Error getting latest news timestamp: {e}")

        return None

    async def get_last_fetch_time(
        self,
        symbol: str,
        fetch_source: str,
        buffer_minutes: int = 1
    ) -> Tuple[datetime, datetime]:
        """
        Get the last fetch timestamp for a symbol+source.

        Args:
            symbol: Stock ticker symbol
            fetch_source: Source name (finnhub, polygon, etc.)
            buffer_minutes: Minutes to subtract from last fetch (overlap window)

        Returns:
            Tuple of (from_time, to_time) for incremental fetch
            If no previous fetch, returns (7 days ago, now)
        """
        # Try to get the latest news timestamp from actual fetched news
        latest_news_time = await self.get_latest_news_timestamp(symbol, fetch_source)

        if latest_news_time:
            # Use actual latest news timestamp (with buffer for overlap)
            # All timestamps stored in UTC, work in UTC
            from_time = latest_news_time - timedelta(minutes=buffer_minutes)
            to_time = datetime.now(UTC).replace(tzinfo=None)  # Current time in UTC

            # Strip timezone if present
            if from_time.tzinfo:
                from_time = from_time.replace(tzinfo=None)

            # Display in EST for user
            latest_est = latest_news_time.replace(tzinfo=UTC).astimezone(EST)
            print(f"📍 {symbol} ({fetch_source}): Incremental from latest news {latest_est.strftime('%Y-%m-%d %H:%M')} EST")
            return from_time, to_time

        # Fallback: check fetch_state table
        try:
            def _fetch():
                return (
                    self.client
                    .table(self.table_name)
                    .select("last_fetch_to, status")
                    .eq("symbol", symbol.upper())
                    .eq("fetch_source", fetch_source)
                    .single()
                    .execute()
                )

            result = await asyncio.to_thread(_fetch)

            if result.data:
                last_fetch_to = datetime.fromisoformat(result.data["last_fetch_to"])

                # Subtract buffer to create overlap window (avoid missing news)
                # Work in UTC
                from_time = last_fetch_to - timedelta(minutes=buffer_minutes)
                to_time = datetime.now(UTC).replace(tzinfo=None)  # Current time in UTC

                # Display in EST for user
                from_est = from_time.replace(tzinfo=UTC).astimezone(EST)
                print(f"📍 {symbol} ({fetch_source}): Incremental fetch from {from_est.strftime('%Y-%m-%d %H:%M')} EST")
                return from_time, to_time

        except Exception as e:
            # No previous fetch found or error - do full fetch
            pass

        # Default: fetch yesterday only (last 24 hours)
        to_time = datetime.now(UTC).replace(tzinfo=None)  # Current time in UTC
        from_time = to_time - timedelta(days=1)

        print(f"🆕 {symbol} ({fetch_source}): First fetch, getting last 24 hours")
        return from_time, to_time

    async def get_finnhub_max_id(
        self,
        symbol: str,
        fetch_source: str
    ) -> Optional[int]:
        """
        Get the last Finnhub max ID for incremental fetching.

        Args:
            symbol: Stock ticker symbol
            fetch_source: Source name (should be 'finnhub')

        Returns:
            Last max ID or None if not found
        """
        try:
            def _fetch():
                return (
                    self.client
                    .table(self.table_name)
                    .select("finnhub_max_id")
                    .eq("symbol", symbol.upper())
                    .eq("fetch_source", fetch_source)
                    .single()
                    .execute()
                )

            result = await asyncio.to_thread(_fetch)

            if result.data and result.data.get("finnhub_max_id"):
                return result.data["finnhub_max_id"]

        except Exception:
            pass

        return None

    async def update_fetch_state(
        self,
        symbol: str,
        fetch_source: str,
        from_time: datetime,
        to_time: datetime,
        articles_fetched: int,
        articles_stored: int,
        status: str = "success",
        error_message: Optional[str] = None,
        finnhub_max_id: Optional[int] = None
    ) -> bool:
        """
        Update fetch state after successful fetch.

        Args:
            symbol: Stock ticker symbol
            fetch_source: Source name
            from_time: Start of fetch window
            to_time: End of fetch window
            articles_fetched: Number of articles fetched
            articles_stored: Number of articles stored (after dedup)
            status: Status (success/failed/partial)
            error_message: Optional error message
            finnhub_max_id: Optional Finnhub max news ID (for incremental fetching)

        Returns:
            True if update successful
        """
        try:
            data = {
                "symbol": symbol.upper(),
                "fetch_source": fetch_source,
                "last_fetch_from": from_time.isoformat(),
                "last_fetch_to": to_time.isoformat(),
                "articles_fetched": articles_fetched,
                "articles_stored": articles_stored,
                "status": status,
                "error_message": error_message,
                "updated_at": datetime.now(UTC).replace(tzinfo=None).isoformat(),
            }

            # Add finnhub_max_id if provided (Finnhub only)
            if finnhub_max_id is not None:
                data["finnhub_max_id"] = finnhub_max_id

            def _upsert():
                return (
                    self.client
                    .table(self.table_name)
                    .upsert(data, on_conflict="symbol,fetch_source")
                    .execute()
                )

            await asyncio.to_thread(_upsert)

            print(f"✅ Updated fetch state: {symbol} ({fetch_source}) - {articles_stored} stored")
            return True

        except Exception as e:
            print(f"❌ Error updating fetch state: {e}")
            return False

    async def get_stale_fetches(
        self,
        max_age_hours: int = 24
    ) -> list[Dict[str, Any]]:
        """
        Get fetch states that haven't been updated in max_age_hours.

        Args:
            max_age_hours: Maximum age in hours

        Returns:
            List of stale fetch state records
        """
        try:
            cutoff = datetime.now() - timedelta(hours=max_age_hours)

            def _fetch():
                return (
                    self.client
                    .table(self.table_name)
                    .select("*")
                    .lt("last_fetch_to", cutoff.isoformat())
                    .execute()
                )

            result = await asyncio.to_thread(_fetch)
            return result.data or []

        except Exception as e:
            print(f"❌ Error getting stale fetches: {e}")
            return []

    async def get_all_states(self) -> list[Dict[str, Any]]:
        """
        Get all fetch states.

        Returns:
            List of all fetch state records
        """
        try:
            def _fetch():
                return (
                    self.client
                    .table(self.table_name)
                    .select("*")
                    .order("last_fetch_to", desc=True)
                    .execute()
                )

            result = await asyncio.to_thread(_fetch)
            return result.data or []

        except Exception as e:
            print(f"❌ Error getting fetch states: {e}")
            return []

    async def reset_fetch_state(
        self,
        symbol: Optional[str] = None,
        fetch_source: Optional[str] = None
    ) -> int:
        """
        Reset fetch state (force full refresh on next fetch).

        Args:
            symbol: Optional symbol to reset (if None, reset all)
            fetch_source: Optional source to reset (if None, reset all)

        Returns:
            Number of records deleted
        """
        try:
            def _delete():
                query = self.client.table(self.table_name).delete()

                if symbol:
                    query = query.eq("symbol", symbol.upper())
                if fetch_source:
                    query = query.eq("fetch_source", fetch_source)

                # Safety: require at least one filter
                if not symbol and not fetch_source:
                    raise ValueError("Must specify symbol or fetch_source to reset")

                return query.execute()

            result = await asyncio.to_thread(_delete)
            deleted = len(result.data) if result.data else 0

            print(f"🔄 Reset {deleted} fetch state(s)")
            return deleted

        except Exception as e:
            print(f"❌ Error resetting fetch state: {e}")
            return 0
