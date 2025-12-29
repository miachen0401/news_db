#!/usr/bin/env python3
"""Trigger remote API jobs from local machine."""
import requests
import sys
from datetime import datetime

# CONFIGURATION - Update with your Render URL
API_URL = "https://news-db-1pgr.onrender.com"  # Update this!
API_URL = "http://localhost:8000"

def trigger_job(job_name: str) -> bool:
    """
    Trigger a specific job on the remote API.

    Args:
        job_name: One of 'fetch', 'recategorize', 'summary', 'all'

    Returns:
        True if successful
    """
    endpoint = f"{API_URL}/trigger/{job_name}"

    try:
        print(f"[{datetime.now().strftime('%Y-%m-%d %H:%M:%S')}] Triggering {job_name}...")
        response = requests.post(endpoint, timeout=30)

        if response.status_code == 200:
            result = response.json()
            print(f"✓ Success: {result.get('message', 'Job triggered')}")
            return True
        else:
            print(f"✗ Error {response.status_code}: {response.text}")
            return False

    except requests.exceptions.Timeout:
        print(f"✗ Timeout: Request took too long (service may be spinning up)")
        return False
    except Exception as e:
        print(f"✗ Error: {e}")
        return False

def check_status() -> bool:
    """Check API status."""
    try:
        response = requests.get(f"{API_URL}/status", timeout=10)
        if response.status_code == 200:
            data = response.json()

            if 'job_history' in data:
                print("\n  Last execution:")
                for job_name, job_data in data['job_history'].items():
                    last_run = job_data.get('last_run', 'Never')
                    status = job_data.get('last_status', 'N/A')
                    print(f"    - {job_name}: {status} (at {last_run})")

            return True
        else:
            print(f"✗ Error {response.status_code}")
            return False
    except Exception as e:
        print(f"✗ Error: {e}")
        return False

def main():
    """Main entry point."""
    if len(sys.argv) < 2:
        print("Usage:")
        print("  python trigger_remote.py fetch        # Trigger news fetch")
        print("  python trigger_remote.py recategorize # Trigger re-categorization")
        print("  python trigger_remote.py summary      # Trigger daily summary")
        print("  python trigger_remote.py all          # Trigger all jobs")
        print("  python trigger_remote.py status       # Check API status")
        sys.exit(1)

    command = sys.argv[1].lower()

    if command == "status":
        check_status()
    elif command in ["fetch", "recategorize", "summary", "all"]:
        trigger_job(command)
    else:
        print(f"Unknown command: {command}")
        print("Valid commands: fetch, recategorize, summary, all, status")
        sys.exit(1)

if __name__ == "__main__":
    main()
