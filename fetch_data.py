#!/usr/bin/env python3
"""Fetch NIFTY chart data from DataSpear API."""

import asyncio
import sys
from dataspear.Utils.request_handler import RequestHandler

# The extra query string for NIFTY data
EXTRA_QUERY = "NIFTY?endTimeInMillis=1783880980000&intervalInMinutes=5&startTimeInMillis=1782153000000"


async def main():
    handler = RequestHandler()
    print("=" * 60)
    print("Fetching NIFTY data...")
    print(f"Query: {EXTRA_QUERY}")
    print("=" * 60)
    
    response = await handler.fetch(EXTRA_QUERY)
    
    if response:
        print("\n" + "=" * 60)
        print("SUCCESS!")
        print("=" * 60)
        print(f"Status Code: {response.status_code}")
        print(f"Content-Type: {response.headers.get('content-type', 'N/A')}")
        print("\nResponse Body:")
        print("-" * 40)
        print(response.text)
        return 0
    else:
        print("\n" + "=" * 60)
        print("FAILED to fetch data")
        print("=" * 60)
        return 1


if __name__ == "__main__":
    exit_code = asyncio.run(main())
    sys.exit(exit_code)
