"""
Quick script to check MATIC balance for gas fees.
"""

import os
import sys
from dotenv import load_dotenv
from web3 import Web3
from web3.middleware import ExtraDataToPOAMiddleware

# Add parent directory to path
sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), '../..')))

load_dotenv()


def main():
    print("=" * 70)
    print("CHECK MATIC BALANCE")
    print("=" * 70)
    
    # Get private key
    priv_key = os.getenv("PK")
    browser_address = os.getenv("BROWSER_ADDRESS")
    
    if not priv_key:
        print("❌ PK not found")
        return
    
    if not browser_address:
        print("❌ BROWSER_ADDRESS not found")
        return
    
    # Clean private key
    if priv_key.startswith('0x') or priv_key.startswith('0X'):
        priv_key = priv_key[2:]
    
    # Connect to Polygon
    web3 = Web3(Web3.HTTPProvider("https://polygon-rpc.com"))
    web3.middleware_onion.inject(ExtraDataToPOAMiddleware, layer=0)
    
    # Get wallet address
    wallet = web3.eth.account.from_key(priv_key)
    metamask_address = wallet.address
    
    # Clean and checksum browser address (proxy)
    browser_address = browser_address.strip()
    if browser_address.startswith('0x') and len(browser_address) > 42:
        browser_address = browser_address[:42]
    proxy_address = Web3.to_checksum_address(browser_address)
    
    print(f"\nMetaMask Wallet: {metamask_address}")
    print(f"Polymarket Proxy: {proxy_address}\n")
    
    # Check MATIC balance for MetaMask wallet
    matic_balance = web3.eth.get_balance(metamask_address) / 10**18
    
    print(f"{'='*70}")
    print(f"MATIC BALANCE (for gas fees)")
    print(f"{'='*70}")
    print(f"Address: {metamask_address}")
    print(f"Balance: {matic_balance:.6f} MATIC")
    
    if matic_balance < 0.001:
        print(f"\n❌ CRITICAL: Very low MATIC balance!")
        print(f"   You need at least 0.01 MATIC for contract approvals")
        print(f"   Send MATIC to: {metamask_address}")
    elif matic_balance < 0.01:
        print(f"\n⚠️  WARNING: Low MATIC balance")
        print(f"   You have enough for a few transactions, but consider adding more")
        print(f"   Recommended: 0.1-0.5 MATIC for regular trading")
    else:
        print(f"\n✅ Sufficient MATIC balance for transactions")
    
    # Also check proxy balance (for reference)
    proxy_balance = web3.eth.get_balance(proxy_address) / 10**18
    print(f"\n{'='*70}")
    print(f"PROXY BALANCE (for reference)")
    print(f"{'='*70}")
    print(f"Address: {proxy_address}")
    print(f"Balance: {proxy_balance:.6f} MATIC")
    print(f"\nNote: Gas fees are paid from MetaMask wallet, not proxy")
    
    print(f"\n{'='*70}")
    print("HOW TO GET MATIC")
    print("="*70)
    print(f"1. Buy MATIC on an exchange (Coinbase, Binance, etc.)")
    print(f"2. Withdraw to Polygon network")
    print(f"3. Send to your MetaMask address: {metamask_address}")
    print(f"4. Or use a MATIC faucet: https://faucet.polygon.technology/")


if __name__ == "__main__":
    main()

