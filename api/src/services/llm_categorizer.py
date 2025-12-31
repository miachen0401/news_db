"""LLM-based news categorization using Zhipu AI."""
from typing import Dict, List, Optional, Any
import httpx
import json
import asyncio
import time

from src.config import LLM_MODELS
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
        self.primary_model = self.model_config['model']
        self.fallback_model = self.model_config.get('fallback_model', 'glm-4-flash')
        self.model = self.primary_model  # Start with primary model
        self.temperature = self.model_config['temperature']
        self.timeout = self.model_config['timeout']
        self.max_retries = self.model_config['max_retries']
        self.delay_between_batches = self.model_config['delay_between_batches']

        # Track if we've fallen back to the fallback model
        self.using_fallback = False

        # Concurrency control: limit concurrent API calls
        self.concurrency_limit = self.model_config['concurrency_limit']
        self.semaphore = asyncio.Semaphore(self.concurrency_limit)

        # Configure timeout for httpx client
        timeout_config = httpx.Timeout(
            connect=10.0,
            read=self.timeout,
            write=10.0,
            pool=5.0
        )
        self.client = httpx.AsyncClient(timeout=timeout_config)

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
            title = item.get('title', 'No title')
            summary = item.get('summary', 'No summary')
            # Truncate title and summary to avoid excessive prompt length
            title = title[:150] if title else 'No title'
            summary = summary[:400] if summary else 'No summary'
            news_text += f"\n[NEWS {idx}]\nTitle: {title}\nSummary: {summary}\n"

        prompt = f"""{categories_definition}

Analyze the following news articles and categorize each one.

Output format (JSON array):
[
  {{
    "news_id": 1,
    "primary_category": "CATEGORY_NAME",
    "symbol": "STOCK_SYMBOLS or empty string",
    "confidence": 0.0-1.0
  }},
  ...
]

News articles to categorize:
{news_text}

Output only the JSON array, no additional text."""

        return prompt

    def _switch_to_fallback(self):
        """Switch to fallback model if not already using it."""
        if not self.using_fallback and self.fallback_model:
            logger.info(f"Switching from {self.model} to fallback model {self.fallback_model}")
            self.model = self.fallback_model
            self.using_fallback = True

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
        async with self.semaphore:
            try:
                logger.debug(f"API call with {self.model} (attempt {retry_count + 1}/{self.max_retries + 1})")
                response = await self.client.post(
                    self.base_url,
                    headers={
                        "Authorization": f"Bearer {self.api_key}",
                        "Content-Type": "application/json"
                    },
                    json={
                        "model": self.model,
                        "messages": [{"role": "user", "content": prompt}],
                        "temperature": self.temperature,
                    }
                )

                if response.status_code == 200:
                    data = response.json()
                    content = data.get("choices", [{}])[0].get("message", {}).get("content", "")
                    return (content, None)

                elif response.status_code == 429 and retry_count < self.max_retries:
                    wait_time = (retry_count + 1) * 5
                    logger.debug(f"Rate limit (429), retrying in {wait_time}s...")
                    await asyncio.sleep(wait_time)
                    return await self._call_llm_api(prompt, retry_count + 1)

                else:
                    error_msg = f"API Error {response.status_code}: {response.text[:200]}"
                    logger.debug(f"API error: {response.status_code}")
                    return (None, error_msg)

            except httpx.TimeoutException as e:
                # On timeout, switch to fallback model if using primary
                if not self.using_fallback and retry_count == 0:
                    logger.warning(f"Model {self.model} timed out, switching to fallback")
                    self._switch_to_fallback()
                    return await self._call_llm_api(prompt, retry_count)

                # If already using fallback or retrying, continue with retries
                if retry_count < self.max_retries:
                    wait_time = (retry_count + 1) * 3
                    logger.debug(f"Timeout, retrying in {wait_time}s...")
                    await asyncio.sleep(wait_time)
                    return await self._call_llm_api(prompt, retry_count + 1)
                else:
                    error_msg = f"Timeout after {self.max_retries + 1} attempts"
                    logger.error(error_msg)
                    return (None, error_msg)

            except Exception as e:
                error_msg = f"{type(e).__name__}: {str(e)}"
                if retry_count < self.max_retries:
                    wait_time = (retry_count + 1) * 3
                    logger.debug(f"Error: {error_msg}, retrying in {wait_time}s...")
                    await asyncio.sleep(wait_time)
                    return await self._call_llm_api(prompt, retry_count + 1)
                else:
                    logger.error(f"API failed after {self.max_retries + 1} attempts: {error_msg}")
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

        all_results = []
        num_batches = (len(news_items) + batch_size - 1) // batch_size
        logger.debug(f"Processing {len(news_items)} items in {num_batches} batches")

        for i in range(0, len(news_items), batch_size):
            batch = news_items[i:i + batch_size]
            batch_num = i//batch_size + 1

            try:
                start_time = time.time()
                prompt = self._build_categorization_prompt(batch)

                # Call LLM API (with automatic fallback on timeout)
                content, error_msg = await self._call_llm_api(prompt)

                api_time = time.time() - start_time
                logger.debug(f"Batch {batch_num}/{num_batches} took {api_time:.1f}s")

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

                        logger.debug(f"Categorized {len(results)} items from batch {batch_num}")
                    except json.JSONDecodeError as e:
                        logger.debug(f"Failed to parse LLM response: {e}")
                        logger.debug(f"Response: {content[:200]}")
                        # Add items with parsing error
                        parse_error = f"JSON parse error: {str(e)}"
                        for item in batch:
                            all_results.append({
                                **item,
                                'primary_category': 'ERROR',
                                'symbol': '',
                                'confidence': 0.0,
                                'api_error': parse_error
                            })

                else:
                    # API call failed after retries - mark as ERROR with details
                    for item in batch:
                        all_results.append({
                            **item,
                            'primary_category': 'ERROR',
                            'symbol': '',
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
                        'symbol': '',
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
            'symbol': '',
            'confidence': 0.0
        }

    async def close(self):
        """Close HTTP client."""
        await self.client.aclose()
