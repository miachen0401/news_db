#!/usr/bin/env python3
"""Quick test with just glm-4-flash and timeout."""
import asyncio
import os
import sys
import time
from pathlib import Path
from dotenv import load_dotenv
import httpx

# Load API key
env_path = Path(__file__).parent.parent / "api" / ".env"
load_dotenv(env_path)

async def test_quick():
    """Quick test with timeout."""
    api_key = os.getenv("ZHIPU_API_KEY")

    if not api_key:
        print("✗ ZHIPU_API_KEY not found")
        return

    print(f"API key: {api_key[:10]}...")
    print(f"\nTesting glm-4-flash with 30s timeout...")

    timeout_config = httpx.Timeout(
        connect=10.0,
        read=30.0,  # 30 second timeout
        write=10.0,
        pool=5.0
    )

    client = httpx.AsyncClient(timeout=timeout_config)

    try:
        start = time.time()

        response = await asyncio.wait_for(
            client.post(
                "https://open.bigmodel.cn/api/paas/v4/chat/completions",
                headers={
                    "Authorization": f"Bearer {api_key}",
                    "Content-Type": "application/json"
                },
                json={
                    "model": "glm-4-flash",
                    "messages": [{"role": "user", "content": "Say hello"}],
                    "temperature": 0.3,
                }
            ),
            timeout=30.0  # Overall timeout
        )

        elapsed = time.time() - start

        if response.status_code == 200:
            data = response.json()
            content = data.get("choices", [{}])[0].get("message", {}).get("content", "")
            print(f"✓ SUCCESS in {elapsed:.2f}s")
            print(f"Response: {content}")
        else:
            print(f"✗ FAILED: {response.status_code}")
            print(f"Response: {response.text[:200]}")

    except asyncio.TimeoutError:
        elapsed = time.time() - start
        print(f"✗ TIMEOUT after {elapsed:.2f}s")
        print("\nPossible issues:")
        print("1. Network/firewall blocking Zhipu AI API")
        print("2. API service is down or slow")
        print("3. API key is invalid or rate limited")

    except httpx.TimeoutException as e:
        elapsed = time.time() - start
        print(f"✗ HTTP TIMEOUT after {elapsed:.2f}s")
        print(f"Error: {e}")

    except Exception as e:
        elapsed = time.time() - start
        print(f"✗ ERROR after {elapsed:.2f}s")
        print(f"{type(e).__name__}: {e}")

    finally:
        await client.aclose()

if __name__ == "__main__":
    asyncio.run(test_quick())
