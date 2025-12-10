#!/usr/bin/env python3
"""
Test the account API endpoints to see what errors occur.
"""
import sys
from app.services.account_service import (
    get_account_balance,
    get_account_positions,
    get_open_orders,
    get_account_summary,
)

print("="*70)
print("  TESTING ACCOUNT API")
print("="*70)

print("\n1. Testing get_account_balance()...")
try:
    result = get_account_balance()
    print(f"Result: {result}")
except Exception as e:
    print(f"ERROR: {e}")
    import traceback
    traceback.print_exc()

print("\n2. Testing get_account_positions()...")
try:
    result = get_account_positions()
    print(f"Result keys: {list(result.keys())}")
    print(f"Success: {result.get('success')}")
    if not result.get('success'):
        print(f"Error: {result.get('error')}")
except Exception as e:
    print(f"ERROR: {e}")
    import traceback
    traceback.print_exc()

print("\n3. Testing get_open_orders()...")
try:
    result = get_open_orders()
    print(f"Result keys: {list(result.keys())}")
    print(f"Success: {result.get('success')}")
    if not result.get('success'):
        print(f"Error: {result.get('error')}")
except Exception as e:
    print(f"ERROR: {e}")
    import traceback
    traceback.print_exc()

print("\n4. Testing get_account_summary()...")
try:
    result = get_account_summary()
    print(f"Result keys: {list(result.keys())}")
    print(f"Balance success: {result.get('balance', {}).get('success')}")
    print(f"Positions success: {result.get('positions', {}).get('success')}")
    print(f"Orders success: {result.get('orders', {}).get('success')}")
    print(f"Wallet: {result.get('wallet_address')}")
except Exception as e:
    print(f"ERROR: {e}")
    import traceback
    traceback.print_exc()

print("\n" + "="*70)

