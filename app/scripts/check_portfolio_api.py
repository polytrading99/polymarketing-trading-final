"""
Simple script to check what the portfolio API actually returns.
"""

import os
import json
from dotenv import load_dotenv
import requests
from web3 import Web3

load_dotenv()


def main():
    browser_address = os.getenv("BROWSER_ADDRESS", "").strip()
    browser_address = Web3.to_checksum_address(browser_address)
    
    print(f"Wallet: {browser_address}\n")
    
    # Check portfolio value
    print("1. Portfolio Value API:")
    try:
        url = f'https://data-api.polymarket.com/value?user={browser_address}'
        res = requests.get(url, timeout=10)
        print(f"   Status: {res.status_code}")
        print(f"   Response (raw): {res.text[:500]}")
        print(f"   Response (JSON): {res.json()}")
    except Exception as e:
        print(f"   Error: {e}")
        import traceback
        traceback.print_exc()
    
    # Check positions
    print(f"\n2. Positions API:")
    try:
        url = f'https://data-api.polymarket.com/positions?user={browser_address}'
        res = requests.get(url, timeout=10)
        print(f"   Status: {res.status_code}")
        print(f"   Response (raw): {res.text[:1000]}")
        data = res.json()
        print(f"   Response type: {type(data)}")
        if isinstance(data, list):
            print(f"   Number of positions: {len(data)}")
            if len(data) > 0:
                print(f"   First position: {json.dumps(data[0], indent=2)}")
        elif isinstance(data, dict):
            print(f"   Dict keys: {list(data.keys())}")
            print(f"   Full response: {json.dumps(data, indent=2)}")
    except Exception as e:
        print(f"   Error: {e}")
        import traceback
        traceback.print_exc()


if __name__ == "__main__":
    main()

