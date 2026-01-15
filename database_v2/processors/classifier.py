"""LLM-based event classifier."""
import asyncio
import re
from pathlib import Path
from typing import List, Optional, Tuple
import httpx
import logging

from config import LLM_MODELS

logger = logging.getLogger(__name__)


def load_prompt() -> str:
    """Load the event classification prompt from file."""
    prompt_file = Path(__file__).parent.parent / "prompts/event_prompt.txt"
    with open(prompt_file, 'r') as f:
        content = f.read()

    # Extract the NEWS_CLASSIFICATION_PROMPT value
    match = re.search(r'NEWS_CLASSIFICATION_PROMPT = """(.+?)"""', content, re.DOTALL)
    if match:
        return match.group(1).strip()

    # If no match found, return the entire content
    return content


class EventClassifier:
    """Classifies news as event-based or not using GLM 4.5 Flash."""

    def __init__(self, api_key: str):
        """Initialize the classifier with Zhipu API key."""
        self.api_key = api_key
        self.base_url = "https://open.bigmodel.cn/api/paas/v4/chat/completions"
        self.model_config = LLM_MODELS["categorization"]
        self.client = httpx.AsyncClient(timeout=self.model_config["timeout"])
        self.prompt = load_prompt()
        self.batch_size = 5  # Process 5 news per LLM call
        logger.info(f"EventClassifier initialized with model: {self.model_config['model']} (batch size: {self.batch_size})")

    async def classify_news_batch(self, summaries: List[str]) -> List[Tuple[Optional[bool], Optional[str], Optional[str]]]:
        """
        Classify multiple news articles as event-based or not in a single LLM call.

        Args:
            summaries: List of news article summaries (up to 5)

        Returns:
            List of tuples (event_based, reasoning, error_message) for each summary
        """
        if not summaries:
            return []

        # Build the user message with numbered news items
        news_list = []
        for i, summary in enumerate(summaries, 1):
            news_list.append(f"{i}. {summary}")

        user_message = "Classify each of the following news articles:\n\n" + "\n\n".join(news_list)

        # Call Zhipu API
        payload = {
            "model": self.model_config["model"],
            "messages": [
                {"role": "system", "content": self.prompt},
                {"role": "user", "content": user_message}
            ],
            "temperature": self.model_config["temperature"],
            "max_tokens": 2000  # Allow longer responses for batch classification
        }

        headers = {
            "Authorization": f"Bearer {self.api_key}",
            "Content-Type": "application/json"
        }

        for retry in range(self.model_config["max_retries"] + 1):
            try:
                logger.debug(f"Calling Zhipu API with {len(summaries)} news (attempt {retry + 1})...")
                response = await self.client.post(
                    self.base_url,
                    json=payload,
                    headers=headers
                )
                response.raise_for_status()

                data = response.json()
                content = data["choices"][0]["message"]["content"]

                # Check for empty response (API issue)
                if not content or content.strip() == "":
                    error_msg = "LLM returned empty response"
                    logger.warning(f"{error_msg} (attempt {retry + 1})")
                    if retry < self.model_config["max_retries"]:
                        await asyncio.sleep(2 ** retry)
                        continue
                    return [(None, None, error_msg) for _ in summaries]

                # Remove <tool_call> tags and fix malformed tags (LLM sometimes adds these)
                content = re.sub(r'<tool_call>.*?</tool_call>', '', content, flags=re.DOTALL)
                content = re.sub(r'<tool_call>.*', '', content, flags=re.DOTALL)  # Unclosed tags
                # Fix GLM's incorrect closing tags (</arg_value> instead of </think>)
                content = re.sub(r'</arg_value>', '</think>', content)
                content = re.sub(r'<arg_value>', '<think>', content)

                # Log the LLM response for debugging
                #logger.info(f"\n=== LLM Response (batch of {len(summaries)}) ===")
                #logger.info(content[:500])
                #logger.info("=" * 50)

                # Parse the response for multiple classifications
                results = self._parse_batch_response(content, len(summaries))

                if len(results) != len(summaries):
                    error_msg = f"Expected {len(summaries)} results, got {len(results)}"
                    logger.warning(error_msg)
                    logger.warning(f"LLM response was: {content[:500]}")
                    # Retry if we have attempts left
                    if retry < self.model_config["max_retries"]:
                        await asyncio.sleep(2 ** retry)
                        continue
                    # Return error for all
                    return [(None, None, error_msg) for _ in summaries]

                return results

            except httpx.HTTPStatusError as e:
                error_msg = f"HTTP error {e.response.status_code}: {e.response.text}"
                logger.debug(error_msg)
                if retry < self.model_config["max_retries"]:
                    await asyncio.sleep(2 ** retry)  # Exponential backoff
                    continue
                return [(None, None, error_msg) for _ in summaries]

            except Exception as e:
                error_msg = f"Unexpected error: {str(e)}"
                logger.debug(error_msg)
                if retry < self.model_config["max_retries"]:
                    await asyncio.sleep(2 ** retry)
                    continue
                return [(None, None, error_msg) for _ in summaries]

        return [(None, None, "Max retries exceeded") for _ in summaries]

    def _parse_batch_response(self, content: str, expected_count: int) -> List[Tuple[Optional[bool], Optional[str], Optional[str]]]:
        """
        Parse the LLM response to extract multiple event_based and reasoning pairs.

        Returns:
            List of tuples (event_based, reasoning, error_message)
        """
        results = []

        # Strategy 1: Try numbered pattern with <think> and <answer> tags
        pattern1 = r'(\d+)[.:)]\s*\n?\s*<think>\s*(.+?)\s*</think>\s*\n?\s*<answer>\s*(.+?)\s*</answer>'
        matches = list(re.finditer(pattern1, content, re.DOTALL | re.IGNORECASE))

        matches_dict = {}
        for match in matches:
            news_num = int(match.group(1))
            reasoning = match.group(2).strip()
            answer = match.group(3).strip().lower()

            # Parse boolean
            event_based = None
            if "true" in answer:
                event_based = True
            elif "false" in answer:
                event_based = False

            if event_based is not None:
                matches_dict[news_num] = (event_based, reasoning, None)

        # Strategy 2: If no numbered matches, try sequential <think>/<answer> pairs
        if not matches_dict:
            logger.info("No numbered patterns found, trying sequential pairs...")
            pattern2 = r'<think>\s*(.+?)\s*</think>\s*\n?\s*<answer>\s*(.+?)\s*</answer>'
            matches = list(re.finditer(pattern2, content, re.DOTALL | re.IGNORECASE))

            for idx, match in enumerate(matches, 1):
                if idx > expected_count:
                    break
                reasoning = match.group(1).strip()
                answer = match.group(2).strip().lower()

                event_based = None
                if "true" in answer:
                    event_based = True
                elif "false" in answer:
                    event_based = False

                if event_based is not None:
                    matches_dict[idx] = (event_based, reasoning, None)

        # Log what we found
        logger.info(f"Parsed {len(matches_dict)} classifications from response")

        # Build results in order
        for i in range(1, expected_count + 1):
            if i in matches_dict:
                results.append(matches_dict[i])
            else:
                # Missing result
                error_msg = f"No valid classification found for news {i}"
                logger.warning(f"{error_msg}. Response preview: {content[:300]}")
                results.append((None, None, error_msg))

        return results

    async def close(self):
        """Close the HTTP client."""
        await self.client.aclose()
