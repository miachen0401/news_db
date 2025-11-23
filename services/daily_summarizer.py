"""Daily news summarizer using Zhipu AI GLM-4.5-flash."""
from typing import List, Dict, Any, Optional
import httpx
import json
import asyncio


class DailySummarizer:
    """Generates daily news highlights using Zhipu AI GLM-4.5-flash model."""

    def __init__(self, api_key: str):
        """
        Initialize summarizer.

        Args:
            api_key: Zhipu AI API key
        """
        self.api_key = api_key
        self.base_url = "https://open.bigmodel.cn/api/paas/v4/chat/completions"
        self.model = "glm-4.5-flash"
        self.client = httpx.AsyncClient(timeout=120.0)

    def _build_summary_prompt(self, news_items: List[Dict[str, Any]]) -> str:
        """
        Build prompt for daily summary.

        Args:
            news_items: List of news items with title, summary, category, published_at

        Returns:
            Formatted prompt string
        """
        # Group news by category
        news_by_category = {}
        for item in news_items:
            category = item.get('category', 'UNCATEGORIZED')
            if category not in news_by_category:
                news_by_category[category] = []
            news_by_category[category].append(item)

        # Build news list
        news_list = []
        for category, items in sorted(news_by_category.items()):
            news_list.append(f"\n## {category} ({len(items)} articles)")
            for idx, item in enumerate(items, 1):
                title = item.get('title', 'No title')
                summary = item.get('summary', 'No summary')
                published_at = item.get('published_at', 'Unknown time')
                secondary_category = item.get('secondary_category', '')

                news_list.append(f"\n{idx}. [{published_at}] {title}")
                if secondary_category:
                    news_list.append(f"   Stocks: {secondary_category}")
                if summary:
                    news_list.append(f"   Summary: {summary}")

        news_text = "\n".join(news_list)

        prompt = f"""You are a financial news analyst creating daily market highlights for traders and investors.

# Task
Generate a concise daily highlight summary of the following news articles. Focus on the most market-moving and actionable information.

# News Articles ({len(news_items)} total)
{news_text}

# Guidelines
1. **Structure**: Organize by themes/sectors (e.g., Tech, Finance, Macro, Energy, etc.)
2. **Prioritize**: Focus on earnings, major corporate actions, policy changes, and significant market-moving events
3. **Brevity**: Keep each item to 1-2 sentences maximum
4. **Stocks**: Mention specific tickers when relevant (use the secondary_category field)
5. **Exclude**: Filter out minor news, opinion pieces without substance, or redundant information
6. **Tone**: Professional, factual, action-oriented

# Output Format
Use markdown with clear headers:

## [Sector/Theme]
- **[Company/Topic]** ([TICKER]): [Key point]
- **[Company/Topic]** ([TICKER]): [Key point]

Example:
## Technology
- **Apple** (AAPL): Q4 earnings beat expectations with revenue up 8% YoY; iPhone sales strong in emerging markets
- **Microsoft** (MSFT): Announced $10B cloud infrastructure investment in Asia-Pacific region

## Finance
- **JPMorgan** (JPM): CEO warns of potential recession in H2 2024 due to persistent inflation

Generate the daily highlights below:
"""
        return prompt

    async def generate_daily_summary(
        self,
        news_items: List[Dict[str, Any]],
        temperature: float = 0.3
    ) -> Optional[str]:
        """
        Generate daily summary from news items.

        Args:
            news_items: List of news dictionaries with title, summary, category
            temperature: LLM temperature (lower = more consistent)

        Returns:
            Generated summary text or None if failed
        """
        if not news_items:
            return "No significant news for this period."

        try:
            prompt = self._build_summary_prompt(news_items)

            response = await self.client.post(
                self.base_url,
                headers={
                    "Authorization": f"Bearer {self.api_key}",
                    "Content-Type": "application/json"
                },
                json={
                    "model": self.model,
                    "messages": [
                        {
                            "role": "user",
                            "content": prompt
                        }
                    ],
                    "temperature": temperature,
                }
            )

            if response.status_code == 200:
                result = response.json()
                summary = result['choices'][0]['message']['content'].strip()

                print(f"✅ Generated daily summary ({len(news_items)} articles)")
                return summary
            else:
                print(f"❌ LLM API error: {response.status_code}")
                print(f"   Response: {response.text}")
                return None

        except Exception as e:
            print(f"❌ Error generating daily summary: {e}")
            return None

    async def close(self):
        """Close HTTP client."""
        await self.client.aclose()
