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
        Correct "empty string" text in stock_news table.

        Targets:
        - symbol column: Change "empty string" to "GENERAL" (symbol is NOT NULL, can't be NULL)
        - secondary_category column: Change "empty string" to "" (empty string)

        Returns:
            Dict with correction statistics
        """
        logger.debug("🔧 Correcting 'empty string' values in stock_news table...")
        stats = {
            "symbol_corrected": 0,
            "secondary_category_corrected": 0,
            "total_checked": 0,
            "errors": 0
        }

        try:
            # STEP 1: Find all records with "empty string" in symbol or secondary_category
            def _fetch_problematic():
                return (
                    self.client
                    .table(self.stock_news_table)
                    .select("id, symbol, secondary_category, source, metadata")
                    .or_(f'symbol.eq.empty string,secondary_category.eq.empty string')
                    .execute()
                )

            result = await asyncio.to_thread(_fetch_problematic)
            problematic_records = result.data or []

            stats["total_checked"] = len(problematic_records)

            if not problematic_records:
                logger.debug("✅ No 'empty string' values found")
                return stats

            logger.debug(f"📊 Found {len(problematic_records)} records with 'empty string' values")
            # STEP 2: Correct each record
            for record in problematic_records:
                record_id = record.get("id")
                symbol = record.get("symbol")
                secondary_category = record.get("secondary_category")
                source = record.get("source") or ""
                metadata = record.get("metadata") or {}

                update_data = {}

                # Check if symbol is "empty string" or None (fix null constraint violation)
                if symbol == "empty string":
                    update_data["symbol"] = "" 
                    stats["symbol_corrected"] += 1

                # Check if secondary_category is "empty string"
                if secondary_category == "empty string":
                    update_data["secondary_category"] = ""  # Empty string, not NULL
                    stats["secondary_category_corrected"] += 1

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
            logger.debug(f"   Secondary category corrected: {stats['secondary_category_corrected']}")
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
