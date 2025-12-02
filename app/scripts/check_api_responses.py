"""
Check what Polymarket APIs actually return - raw responses.
"""

import os
from dotenv import load_dotenv
import requests
from web3 import Web3
from web3.middleware import ExtraDataToPOAMiddleware
from poly_data.abis import erc20_abi

load_dotenv()


def main():
    print("=" * 60)
    print("CHECKING POLYMARKET API RESPONSES (RAW)")
    print("=" * 60)
    
    browser_address = os.getenv("BROWSER_ADDRESS", "").strip()
    browser_address = Web3.to_checksum_address(browser_address)
    
    print(f"\nWallet: {browser_address}\n")
    
    # 1. Check USDC balance on-chain
    print("1. Checking USDC balance on-chain...")
    try:
        web3 = Web3(Web3.HTTPProvider("https://polygon-rpc.com"))
        web3.middleware_onion.inject(ExtraDataToPOAMiddleware, layer=0)
        
        usdc_address = "0x2791Bca1f2de4661ED88A30C99A7a9449Aa84174"
        usdc_contract = web3.eth.contract(address=usdc_address, abi=erc20_abi)
        
        balance_raw = usdc_contract.functions.balanceOf(browser_address).call()
        balance_usdc = balance_raw / 10**6
        
        print(f"   USDC Contract: {usdc_address}")
        print(f"   Balance (raw): {balance_raw}")
        print(f"   Balance (USDC): {balance_usdc:.6f} USDC")
        
        if balance_usdc == 0:
            print(f"   ⚠️  No USDC in this contract")
            print(f"   Note: Your $29.58 might be in a different token or wallet")
    except Exception as e:
        print(f"   ❌ Error: {e}")
        import traceback
        traceback.print_exc()
    
    # 2. Check portfolio value API
    print(f"\n2. Checking portfolio value API...")
    try:
        url = f'https://data-api.polymarket.com/value?user={browser_address}'
        print(f"   URL: {url}")
        res = requests.get(url, timeout=10)
        print(f"   Status: {res.status_code}")
        data = res.json()
        print(f"   Response type: {type(data)}")
        print(f"   Response: {data}")
        
        if isinstance(data, dict):
            print(f"   Keys: {list(data.keys())}")
            if 'value' in data:
                print(f"   Portfolio Value: ${float(data['value']):.2f}")
        elif isinstance(data, list):
            print(f"   Response is a list (unexpected)")
            if len(data) > 0:
                print(f"   First item: {data[0]}")
    except Exception as e:
        print(f"   ❌ Error: {e}")
        import traceback
        traceback.print_exc()
    
    # 3. Check positions API
    print(f"\n3. Checking positions API...")
    try:
        url = f'https://data-api.polymarket.com/positions?user={browser_address}'
        print(f"   URL: {url}")
        res = requests.get(url, timeout=10)
        print(f"   Status: {res.status_code}")
        data = res.json()
        print(f"   Response type: {type(data)}")
        
        if isinstance(data, list):
            print(f"   ✅ Response is a list with {len(data)} items")
            if len(data) > 0:
                print(f"   First position: {data[0]}")
                if isinstance(data[0], dict):
                    print(f"   Keys in first position: {list(data[0].keys())}")
        elif isinstance(data, dict):
            print(f"   Response is a dict")
            print(f"   Keys: {list(data.keys())}")
            print(f"   Full response: {data}")
        else:
            print(f"   Unexpected type: {type(data)}")
            print(f"   Response: {data}")
    except Exception as e:
        print(f"   ❌ Error: {e}")
        import traceback
        traceback.print_exc()
    
    # 4. Check trades API
    print(f"\n4. Checking trades API...")
    try:
        url = f'https://data-api.polymarket.com/trades?user={browser_address}&limit=10'
        print(f"   URL: {url}")
        res = requests.get(url, timeout=10)
        print(f"   Status: {res.status_code}")
        data = res.json()
        print(f"   Response type: {type(data)}")
        
        if isinstance(data, list):
            print(f"   ✅ Found {len(data)} trades")
            if len(data) > 0:
                print(f"   Latest trade: {data[0]}")
        elif isinstance(data, dict):
            print(f"   Response is a dict: {data}")
        else:
            print(f"   Response: {data}")
    except Exception as e:
        print(f"   ❌ Error: {e}")
        import traceback
        traceback.print_exc()
    
    print(f"\n{'='*60}")
    print("SUMMARY")
    print("=" * 60)
    print("\nThis shows what the APIs actually return.")
    print("If USDC balance is 0, your $29.58 might be:")
    print("  - In a different token (not USDC)")
    print("  - In a different wallet address")
    print("  - In a different network (not Polygon)")


if __name__ == "__main__":
    main()

