#!/usr/bin/env python3
"""Test Zhipu AI model connection with simple prompts."""
import asyncio
import os
import sys
import time
from pathlib import Path
from dotenv import load_dotenv
import httpx

# Add parent directory to path
sys.path.insert(0, str(Path(__file__).parent.parent / "api"))

from src.services.llm_categorizer import NewsCategorizer


async def test_simple_prompt(model_name: str, api_key: str):
    """Test model with a simple prompt."""
    print(f"\n{'='*70}")
    print(f"Testing model: {model_name}")
    print(f"{'='*70}")

    # Simple test prompt
    test_prompt = """Categorize this news:
Title: Apple announces new iPhone with improved camera
Summary: Apple Inc. unveiled its latest iPhone model featuring enhanced camera capabilities.

Choose ONE category: PRODUCT_TECH_UPDATE or NON_FINANCIAL

Output format: {"category": "CATEGORY_NAME"}
"""

    timeout_config = httpx.Timeout(
        connect=10.0,
        read=60.0,
        write=10.0,
        pool=5.0
    )

    client = httpx.AsyncClient(timeout=timeout_config)

    try:
        start_time = time.time()

        print(f"\nSending test prompt...")
        print(f"Prompt length: {len(test_prompt)} chars")

        response = await client.post(
            "https://open.bigmodel.cn/api/paas/v4/chat/completions",
            headers={
                "Authorization": f"Bearer {api_key}",
                "Content-Type": "application/json"
            },
            json={
                "model": model_name,
                "messages": [{"role": "user", "content": test_prompt}],
                "temperature": 0.3,
            }
        )

        elapsed_time = time.time() - start_time

        if response.status_code == 200:
            data = response.json()
            content = data.get("choices", [{}])[0].get("message", {}).get("content", "")

            print(f"✓ SUCCESS")
            print(f"  Response time: {elapsed_time:.2f}s")
            print(f"  Response length: {len(content)} chars")
            print(f"  Response: {content[:200]}")
            return True
        else:
            print(f"✗ FAILED")
            print(f"  Status code: {response.status_code}")
            print(f"  Response: {response.text[:200]}")
            return False

    except httpx.TimeoutException as e:
        elapsed_time = time.time() - start_time
        print(f"✗ TIMEOUT after {elapsed_time:.2f}s")
        print(f"  Error: {e}")
        return False

    except Exception as e:
        elapsed_time = time.time() - start_time
        print(f"✗ ERROR after {elapsed_time:.2f}s")
        print(f"  Error: {type(e).__name__}: {e}")
        return False

    finally:
        await client.aclose()


async def test_categorizer():
    """Test the NewsCategorizer class."""
    print(f"\n{'='*70}")
    print(f"Testing NewsCategorizer with fallback")
    print(f"{'='*70}")

    # Load API key
    env_path = Path(__file__).parent.parent / "api" / ".env"
    load_dotenv(env_path)
    api_key = os.getenv("ZHIPU_API_KEY")

    if not api_key:
        print("✗ ZHIPU_API_KEY not found in .env")
        return False

    # Test news items
    test_news = [
        {
            "title": "Tesla reports record quarterly deliveries",
            "summary": "Tesla Inc. announced record vehicle deliveries in Q4, exceeding analyst expectations."
        },
        {
            "title": "Federal Reserve maintains interest rates",
            "summary": "The Federal Reserve decided to keep interest rates unchanged amid inflation concerns."
        }
    ]

    categorizer = NewsCategorizer(api_key=api_key)

    try:
        print(f"\nPrimary model: {categorizer.primary_model}")
        print(f"Fallback model: {categorizer.fallback_model}")
        print(f"\nCategorizing {len(test_news)} test items...")

        start_time = time.time()
        results = await categorizer.categorize_batch(test_news, batch_size=2)
        elapsed_time = time.time() - start_time

        print(f"\n✓ SUCCESS")
        print(f"  Total time: {elapsed_time:.2f}s")
        print(f"  Results: {len(results)} items")

        if categorizer.using_fallback:
            print(f"  ⚠️  Used fallback model: {categorizer.fallback_model}")
        else:
            print(f"  ✓ Used primary model: {categorizer.primary_model}")

        print(f"\nCategorization results:")
        for i, result in enumerate(results, 1):
            cat = result.get("primary_category", "N/A")
            conf = result.get("confidence", 0)
            print(f"  {i}. {cat} (confidence: {conf})")

        return True

    except Exception as e:
        print(f"\n✗ ERROR: {type(e).__name__}: {e}")
        return False

    finally:
        await categorizer.close()


async def main():
    """Run all tests."""
    print("\n" + "="*70)
    print("ZHIPU AI MODEL CONNECTION TEST")
    print("="*70)

    # Load API key
    env_path = Path(__file__).parent.parent / "api" / ".env"
    load_dotenv(env_path)

    api_key = os.getenv("ZHIPU_API_KEY")

    if not api_key:
        print("\n✗ ERROR: ZHIPU_API_KEY not found in .env file")
        print(f"  Expected location: {env_path}")
        return

    print(f"\n✓ API key loaded from: {env_path}")
    print(f"  API key (first 10 chars): {api_key[:10]}...")

    # Test both models
    results = {}

    # Test glm-4.5-flash
    results["glm-4.5-flash"] = await test_simple_prompt("glm-4.5-flash", api_key)
    await asyncio.sleep(2)  # Delay between tests

    # Test glm-4-flash
    results["glm-4-flash"] = await test_simple_prompt("glm-4-flash", api_key)
    await asyncio.sleep(2)

    # Test categorizer with fallback
    results["categorizer"] = await test_categorizer()

    # Summary
    print(f"\n{'='*70}")
    print("TEST SUMMARY")
    print(f"{'='*70}")

    for test_name, success in results.items():
        status = "✓ PASS" if success else "✗ FAIL"
        print(f"  {test_name}: {status}")

    total_tests = len(results)
    passed_tests = sum(1 for r in results.values() if r)

    print(f"\nTotal: {passed_tests}/{total_tests} tests passed")

    if passed_tests == total_tests:
        print("\n✓ All tests passed!")
    else:
        print("\n✗ Some tests failed")


if __name__ == "__main__":
    asyncio.run(main())
