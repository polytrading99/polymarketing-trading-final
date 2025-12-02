"""
Check USDC balance on Polygon - checks both USDC.e and native USDC contracts.
"""

import os
from dotenv import load_dotenv
from web3 import Web3
from web3.middleware import ExtraDataToPOAMiddleware
from poly_data.abis import erc20_abi

load_dotenv()


def main():
    print("=" * 60)
    print("CHECKING USDC BALANCE ON POLYGON")
    print("=" * 60)
    
    browser_address = os.getenv("BROWSER_ADDRESS", "").strip()
    browser_address = Web3.to_checksum_address(browser_address)
    
    print(f"\nWallet: {browser_address}\n")
    
    # Connect to Polygon
    web3 = Web3(Web3.HTTPProvider("https://polygon-rpc.com"))
    web3.middleware_onion.inject(ExtraDataToPOAMiddleware, layer=0)
    
    # USDC contract addresses on Polygon
    usdc_contracts = {
        "USDC.e (Bridged)": "0x2791Bca1f2de4661ED88A30C99A7a9449Aa84174",
        "Native USDC": "0x3c499c542cEF5E3811e1192ce70d8cC03d5c3359",  # Native USDC on Polygon
    }
    
    total_usdc = 0.0
    
    for name, address in usdc_contracts.items():
        try:
            contract = web3.eth.contract(address=address, abi=erc20_abi)
            balance_raw = contract.functions.balanceOf(browser_address).call()
            balance_usdc = balance_raw / 10**6
            
            print(f"{name}:")
            print(f"  Contract: {address}")
            print(f"  Balance: {balance_usdc:.6f} USDC")
            
            if balance_usdc > 0:
                print(f"  ✅ Found {balance_usdc:.2f} USDC!")
                total_usdc += balance_usdc
            else:
                print(f"  ⚠️  No balance")
            print()
        except Exception as e:
            print(f"{name}:")
            print(f"  ❌ Error checking: {e}")
            print()
    
    print("=" * 60)
    print(f"TOTAL USDC: {total_usdc:.6f} USDC")
    print("=" * 60)
    
    if total_usdc > 0:
        print(f"\n✅ You have {total_usdc:.2f} USDC available for trading!")
    else:
        print(f"\n⚠️  No USDC found in either contract.")
        print(f"   Make sure:")
        print(f"   1. Wallet address is correct: {browser_address}")
        print(f"   2. You're on Polygon network")
        print(f"   3. USDC is in your wallet")


if __name__ == "__main__":
    main()

