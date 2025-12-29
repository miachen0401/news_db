"""LLM-based news categorization using Zhipu AI."""
from typing import Dict, List, Optional, Any
import httpx
import json
import asyncio

from src.config import LLM_CONFIG, LLM_MODELS
import logging
logger = logging.getLogger(__name__)


def normalize_category(category: str) -> str:
    """
    Normalize category name to match expected format.

    - Converts to uppercase
    - Replaces spaces with underscores
    - Handles common variations

    Args:
        category: Raw category name from LLM

    Returns:
        Normalized category name
    """
    if not category:
        return category

    # Convert to uppercase and replace spaces with underscores
    normalized = category.upper().strip().replace(' ', '_').replace('-', '_')

    # Handle multiple underscores
    while '__' in normalized:
        normalized = normalized.replace('__', '_')

    return normalized



class NewsCategorizer:
    """Categorizes news using Zhipu AI model with concurrency control."""

    def __init__(self, api_key: str):
        """
        Initialize categorizer.

        Args:
            api_key: Zhipu AI API key
        """
        self.api_key = api_key
        self.base_url = "https://open.bigmodel.cn/api/paas/v4/chat/completions"

        # Use model config from LLM_MODELS
        self.model_config = LLM_MODELS['categorization']
        self.model = self.model_config['model']
        self.temperature = self.model_config['temperature']
        self.timeout = self.model_config['timeout']
        self.max_retries = self.model_config['max_retries']
        self.delay_between_batches = self.model_config['delay_between_batches']

        # Concurrency control: limit concurrent API calls
        self.concurrency_limit = self.model_config['concurrency_limit']
        self.semaphore = asyncio.Semaphore(self.concurrency_limit)

        self.client = httpx.AsyncClient(timeout=self.timeout)

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

MACRO_ECONOMY - Concrete macroeconomic indicators or official data releases (e.g., CPI, GDP, PMI, unemployment reports)
CENTRAL_BANK_POLICY - Official central bank decisions, rate changes, speeches by named officials
GEOPOLITICAL_EVENT - Geopolitical news ONLY when involving specific named countries, leaders, governments, or concrete actions
INDUSTRY_REGULATION - Regulatory/policy news targeting specific industry/sector
CORPORATE_EARNINGS - Company earnings, financial statements, revenue data
CORPORATE_ACTIONS - M&A, stock splits, buybacks, spinoffs, bankruptcies
MANAGEMENT_CHANGE - CEO, CFO, board member changes
INCIDENT_LEGAL - Lawsuits, fines, regulatory investigations, accidents, data breaches
PRODUCT_TECH_UPDATE - New products, technology developments, R&D, clinical trial results
BUSINESS_OPERATIONS - Supply chain, contracts, partnerships, operational decisions
ANALYST_OPINION - Analyst upgrades/downgrades, price targets, commentary
MARKET_SENTIMENT - Investor sentiment, market flows, surveys, risk appetite
NON_FINANCIAL - Any general commentary, opinions without specific actors, or news unrelated to financial markets    

Secondary Category:
- If news is about specific company/stock, output stock ticker symbols (e.g., AAPL, TSLA)
- If not company-specific, output empty string

RULES:
- You MUST choose one of the EXACT category names listed above.
- NEVER invent new categories.
- NEVER output numbers, abbreviations, or synonyms.
- If the news does NOT mention a concrete decision, named institution, named government, named company, or measurable data → ALWAYS classify as "NON_FINANCIAL".
"""

        news_text = ""
        for idx, item in enumerate(news_items, 1):
            #title = item.get('title', 'No title')
            summary = item.get('summary', 'No summary')
            news_text += f"\n[NEWS {idx}]\nSummary: {summary}\n"

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

    async def _call_llm_api(self, prompt: str, retry_count: int = 0) -> tuple[Optional[str], Optional[str]]:
        """
        Call LLM API with retry logic and concurrency control.

        Args:
            prompt: Prompt to send to LLM
            retry_count: Current retry attempt

        Returns:
            Tuple of (content, error_message):
            - content: LLM response content or None if failed
            - error_message: Error details if failed, None if successful
        """
        async with self.semaphore:  # Limit concurrent API calls
            try:
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
                        "temperature": self.temperature,
                    }
                )

                if response.status_code == 200:
                    data = response.json()
                    content = data.get("choices", [{}])[0].get("message", {}).get("content", "")
                    return (content, None)

                elif response.status_code == 429 and retry_count < self.max_retries:
                    # Rate limit exceeded, wait and retry
                    wait_time = (retry_count + 1) * 5  # Exponential backoff: 5s, 10s, 15s
                    logger.debug(f"Rate limit hit (429), retrying in {wait_time}s... (attempt {retry_count + 1}/{self.max_retries})")
                    await asyncio.sleep(wait_time)
                    return await self._call_llm_api(prompt, retry_count + 1)

                else:
                    # Permanent error - return error details
                    error_msg = f"API Error {response.status_code}: {response.text[:200]}"
                    logger.debug(f"Zhipu API error: {response.status_code}")
                    logger.debug(f"Response: {response.text}")
                    return (None, error_msg)

            except Exception as e:
                if retry_count < self.max_retries:
                    wait_time = (retry_count + 1) * 3
                    logger.debug(f"API call failed: {e}, retrying in {wait_time}s...")
                    await asyncio.sleep(wait_time)
                    return await self._call_llm_api(prompt, retry_count + 1)
                else:
                    error_msg = f"Exception after {self.max_retries} retries: {str(e)}"
                    logger.debug(f"Error calling LLM API after {self.max_retries} retries: {e}")
                    return (None, error_msg)

    async def categorize_batch(
        self,
        news_items: List[Dict[str, Any]],
        batch_size: int = 10
    ) -> List[Dict[str, Any]]:
        """
        Categorize a batch of news items with concurrency control.

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

            logger.debug(f"Categorizing batch {i//batch_size + 1} ({len(batch)} items)...")
            try:
                prompt = self._build_categorization_prompt(batch)

                # Call LLM API with retry and concurrency control
                content, error_msg = await self._call_llm_api(prompt)

                if content:
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
                                # Normalize the primary_category
                                if 'primary_category' in result:
                                    result['primary_category'] = normalize_category(result['primary_category'])

                                batch[j]['categorization'] = result
                                all_results.append({
                                    **batch[j],
                                    **result,
                                    'api_error': None  # No error
                                })

                        logger.debug(f"Categorized {len(results)} items")
                    except json.JSONDecodeError as e:
                        logger.debug(f"Failed to parse LLM response: {e}")
                        logger.debug(f"Response: {content[:200]}")
                        # Add items with parsing error
                        parse_error = f"JSON parse error: {str(e)}"
                        for item in batch:
                            all_results.append({
                                **item,
                                'primary_category': 'ERROR',
                                'secondary_category': '',
                                'confidence': 0.0,
                                'api_error': parse_error
                            })

                else:
                    # API call failed after retries - mark as ERROR with details
                    for item in batch:
                        all_results.append({
                            **item,
                            'primary_category': 'ERROR',
                            'secondary_category': '',
                            'confidence': 0.0,
                            'api_error': error_msg  # Include error details
                        })

                # Delay between batches to avoid rate limiting
                await asyncio.sleep(self.delay_between_batches)

            except Exception as e:
                logger.debug(f"Error categorizing batch: {e}")
                # Add items with exception error
                exception_error = f"Batch processing exception: {str(e)}"
                for item in batch:
                    all_results.append({
                        **item,
                        'primary_category': 'ERROR',
                        'secondary_category': '',
                        'confidence': 0.0,
                        'api_error': exception_error
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
