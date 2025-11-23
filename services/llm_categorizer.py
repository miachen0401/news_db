"""LLM-based news categorization using Zhipu AI."""
from typing import Dict, List, Optional, Any
import httpx
import json
import asyncio

from config import LLM_CONFIG


class NewsCategorizer:
    """Categorizes news using Zhipu AI GLM-4.5-flash model."""

    def __init__(self, api_key: str):
        """
        Initialize categorizer.

        Args:
            api_key: Zhipu AI API key
        """
        self.api_key = api_key
        self.base_url = "https://open.bigmodel.cn/api/paas/v4/chat/completions"
        self.model = "glm-4.5-flash"
        self.client = httpx.AsyncClient(timeout=60.0)

    def _build_categorization_prompt(self, news_items: List[Dict[str, Any]]) -> str:
        """
        Build prompt for categorization.

        Args:
            news_items: List of news items with title and summary

        Returns:
            Formatted prompt string
        """
        categories_definition = """
Primary Categories (select ONE only):

1. MACRO_ECONOMIC - Macroeconomic indicators affecting overall market
2. CENTRAL_BANK_POLICY - Monetary policy, interest rates, central bank decisions
3. MACRO_NOBODY - Geopolitical/macro commentary without specific leaders/institutions
4. GEOPOLITICAL_SPECIFIC - Geopolitical news with named countries/leaders/governments
5. INDUSTRY_REGULATION - Regulatory/policy news targeting specific industry/sector
6. EARNINGS_FINANCIALS - Company earnings, financial statements, revenue data
7. CORPORATE_ACTIONS - M&A, stock splits, buybacks, spinoffs, bankruptcies
8. MANAGEMENT_CHANGES - CEO, CFO, board member changes
9. PRODUCT_TECH_UPDATE - New products, technology developments, R&D, launches
10. BUSINESS_OPERATIONS - Supply chain, contracts, partnerships, operational decisions
11. ACCIDENT_INCIDENT - Data breaches, accidents, recalls, lawsuits, fines
12. ANALYST_RATING - Analyst upgrades/downgrades, price targets, commentary
13. MARKET_SENTIMENT - Investor sentiment, market flows, surveys, risk appetite
14. COMMODITY_FOREX_CRYPTO - Commodities, forex, cryptocurrency markets
15. NON_FINANCIAL - Non-market news (sports, lifestyle, entertainment, culture)

Secondary Category:
- If news is about specific company/stock, output stock ticker symbols (e.g., AAPL, TSLA)
- If not company-specific, output empty string

"""

        news_text = ""
        for idx, item in enumerate(news_items, 1):
            title = item.get('title', 'No title')
            summary = item.get('summary', 'No summary')
            news_text += f"\n[NEWS {idx}]\nTitle: {title}\nSummary: {summary}\n"

        prompt = f"""{categories_definition}

Analyze the following news articles and categorize each one.

Output format (JSON array):
[
  {{
    "news_id": 1,
    "primary_category": "CATEGORY_NAME",
    "secondary_category": "STOCK_SYMBOLS or empty string",
    "confidence": 0.0-1.0
  }},
  ...
]

News articles to categorize:
{news_text}

Output only the JSON array, no additional text."""

        return prompt

    async def categorize_batch(
        self,
        news_items: List[Dict[str, Any]],
        batch_size: int = 10
    ) -> List[Dict[str, Any]]:
        """
        Categorize a batch of news items.

        Args:
            news_items: List of news dicts with 'title' and 'summary'
            batch_size: Maximum items per API call

        Returns:
            List of categorization results
        """
        if not news_items:
            return []

        # Process in batches
        all_results = []

        for i in range(0, len(news_items), batch_size):
            batch = news_items[i:i + batch_size]

            print(f"🤖 Categorizing batch {i//batch_size + 1} ({len(batch)} items)...")

            try:
                prompt = self._build_categorization_prompt(batch)

                # Call Zhipu AI API
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
                        "temperature": LLM_CONFIG['temperature'],
                    }
                )

                if response.status_code == 200:
                    data = response.json()
                    content = data.get("choices", [{}])[0].get("message", {}).get("content", "")

                    # Parse JSON response
                    try:
                        # Extract JSON from markdown code blocks if present
                        if "```json" in content:
                            content = content.split("```json")[1].split("```")[0].strip()
                        elif "```" in content:
                            content = content.split("```")[1].split("```")[0].strip()

                        results = json.loads(content)

                        # Map results back to news items
                        for j, result in enumerate(results):
                            if j < len(batch):
                                batch[j]['categorization'] = result
                                all_results.append({
                                    **batch[j],
                                    **result
                                })

                        print(f"✅ Categorized {len(results)} items")

                    except json.JSONDecodeError as e:
                        print(f"⚠️  Failed to parse LLM response: {e}")
                        print(f"Response: {content[:200]}")
                        # Add items without categorization
                        for item in batch:
                            all_results.append({
                                **item,
                                'primary_category': 'UNCATEGORIZED',
                                'secondary_category': '',
                                'confidence': 0.0
                            })

                else:
                    print(f"❌ Zhipu API error: {response.status_code}")
                    print(f"Response: {response.text}")
                    # Add items without categorization
                    for item in batch:
                        all_results.append({
                            **item,
                            'primary_category': 'UNCATEGORIZED',
                            'secondary_category': '',
                            'confidence': 0.0
                        })

                # Rate limiting
                await asyncio.sleep(1)

            except Exception as e:
                print(f"❌ Error categorizing batch: {e}")
                # Add items without categorization
                for item in batch:
                    all_results.append({
                        **item,
                        'primary_category': 'UNCATEGORIZED',
                        'secondary_category': '',
                        'confidence': 0.0
                    })

        return all_results

    async def categorize_single(
        self,
        title: str,
        summary: str
    ) -> Dict[str, Any]:
        """
        Categorize a single news item.

        Args:
            title: News title
            summary: News summary

        Returns:
            Categorization result dict
        """
        results = await self.categorize_batch([{
            'title': title,
            'summary': summary
        }])

        return results[0] if results else {
            'primary_category': 'UNCATEGORIZED',
            'secondary_category': '',
            'confidence': 0.0
        }

    async def close(self):
        """Close HTTP client."""
        await self.client.aclose()
