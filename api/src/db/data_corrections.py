"""Database data correction utilities."""
import asyncio
from typing import Dict, Any
from supabase import Client
import logging
logger = logging.getLogger(__name__)



class DataCorrector:
    """Handles data corrections and cleanup in the database."""

    def __init__(self, client: Client):
        """
        Initialize data corrector.

        Args:
            client: Supabase client instance
        """
        self.client = client
        self.stock_news_table = "stock_news"

    async def correct_empty_strings_in_stock_news(self) -> Dict[str, int]:
        """
        Correct "empty string" and null values in stock_news table.

        Targets:
        - symbol column: Change "empty string", "", or null to "GENERAL" (symbol is NOT NULL, can't be NULL)

        Returns:
            Dict with correction statistics
        """
        logger.debug("🔧 Correcting 'empty string' and null values in stock_news table...")
        stats = {
            "symbol_corrected": 0,
            "total_checked": 0,
            "errors": 0
        }

        try:
            # STEP 1: Find all records with empty/null/problematic values in symbol
            def _fetch_problematic():
                return (
                    self.client
                    .table(self.stock_news_table)
                    .select("id, symbol, source, metadata")
                    .or_(f'symbol.eq.empty string,symbol.eq.,symbol.is.null,symbol.eq.null')
                    .execute()
                )

            result = await asyncio.to_thread(_fetch_problematic)
            problematic_records = result.data or []

            stats["total_checked"] = len(problematic_records)

            if not problematic_records:
                logger.debug("✅ No problematic symbol values found")
                return stats

            logger.debug(f"📊 Found {len(problematic_records)} records with problematic symbol values")
            # STEP 2: Correct each record
            for record in problematic_records:
                record_id = record.get("id")
                symbol = record.get("symbol")
                source = record.get("source") or ""
                metadata = record.get("metadata") or {}

                update_data = {}

                # Check if symbol is "empty string", empty, null, or "null" string
                if not symbol or symbol in ("empty string", "", "null"):
                    update_data["symbol"] = "GENERAL"
                    stats["symbol_corrected"] += 1

                # Update if needed
                if update_data:
                    try:
                        def _update():
                            return (
                                self.client
                                .table(self.stock_news_table)
                                .update(update_data)
                                .eq("id", record_id)
                                .execute()
                            )

                        await asyncio.to_thread(_update)

                    except Exception as e:
                        logger.debug(f"⚠️  Error updating record {record_id}: {e}")
                        stats["errors"] += 1

            logger.debug(f"✅ Correction complete:")
            logger.debug(f"   Symbol corrected: {stats['symbol_corrected']}")
            if stats["errors"] > 0:
                logger.debug(f"   Errors: {stats['errors']}")
        except Exception as e:
            logger.debug(f"❌ Error during correction: {e}")
            stats["errors"] += 1

        return stats

    async def correct_all(self) -> Dict[str, Any]:
        """
        Run all data corrections.

        Returns:
            Dict with all correction statistics
        """
        logger.debug("=" * 70)
        logger.debug("🔧 RUNNING DATABASE CORRECTIONS")
        logger.debug("=" * 70)
        logger.debug("")
        all_stats = {}

        # Run empty string corrections
        all_stats["empty_strings"] = await self.correct_empty_strings_in_stock_news()

        logger.debug("")
        logger.debug("=" * 70)
        logger.debug("✅ ALL CORRECTIONS COMPLETE")
        logger.debug("=" * 70)
        return all_stats
