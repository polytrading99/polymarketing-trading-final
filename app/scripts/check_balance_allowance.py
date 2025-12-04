"""
Check USDC balance and contract approvals to diagnose 'not enough balance / allowance' error.
"""

import os
import sys
from dotenv import load_dotenv
from web3 import Web3
from web3.middleware import ExtraDataToPOAMiddleware

# Add parent directory to path
sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), '../..')))

load_dotenv()

# ERC20 ABI
ERC20_ABI = [
    {
        "constant": True,
        "inputs": [{"name": "_owner", "type": "address"}],
        "name": "balanceOf",
        "outputs": [{"name": "balance", "type": "uint256"}],
        "type": "function"
    },
    {
        "constant": True,
        "inputs": [{"name": "_owner", "type": "address"}, {"name": "_spender", "type": "address"}],
        "name": "allowance",
        "outputs": [{"name": "", "type": "uint256"}],
        "type": "function"
    }
]

USDC_ADDRESS = "0x2791Bca1f2de4661ED88A30C99A7a9449Aa84174"  # USDC.e
POLYMARKET_CONTRACTS = {
    'exchange': '0x4bFb41d5B3570DeFd03C39a9A4D8dE6Bd8B8982E',
    'neg_risk_adapter': '0xd91E80cF2E7be2e162c6513ceD06f1D0dA35296',
    'exchange_v2': '0xC5d563A36AE78145C45a50134d48A1215220f80a',
}


def main():
    print("=" * 70)
    print("CHECK BALANCE & ALLOWANCE")
    print("=" * 70)
    
    browser_address = os.getenv("BROWSER_ADDRESS", "").strip()
    if not browser_address:
        print("❌ BROWSER_ADDRESS not set")
        return
    
    if browser_address.startswith('0x') and len(browser_address) > 42:
        browser_address = browser_address[:42]
    
    proxy_address = Web3.to_checksum_address(browser_address)
    
    print(f"\nProxy Address: {proxy_address}\n")
    
    # Connect to Polygon
    web3 = Web3(Web3.HTTPProvider("https://polygon-rpc.com"))
    web3.middleware_onion.inject(ExtraDataToPOAMiddleware, layer=0)
    
    # Check USDC balance
    usdc_contract = web3.eth.contract(
        address=Web3.to_checksum_address(USDC_ADDRESS),
        abi=ERC20_ABI
    )
    
    balance_raw = usdc_contract.functions.balanceOf(proxy_address).call()
    balance_usd = balance_raw / 10**6  # USDC has 6 decimals
    
    print(f"{'='*70}")
    print("USDC BALANCE")
    print(f"{'='*70}")
    print(f"Address: {proxy_address}")
    print(f"Balance: {balance_usd:.2f} USDC")
    print(f"Balance (raw): {balance_raw}")
    
    if balance_usd < 5:
        print(f"\n⚠️  WARNING: Low USDC balance!")
        print(f"   You need at least 5 USDC to place orders")
        print(f"   Current balance: {balance_usd:.2f} USDC")
    else:
        print(f"\n✅ Sufficient USDC balance for trading")
    
    # Check allowances for each contract
    print(f"\n{'='*70}")
    print("CONTRACT ALLOWANCES")
    print(f"{'='*70}")
    
    max_uint = 2**256 - 1
    
    for name, contract_addr in POLYMARKET_CONTRACTS.items():
        contract_addr_checksum = Web3.to_checksum_address(contract_addr)
        allowance_raw = usdc_contract.functions.allowance(proxy_address, contract_addr_checksum).call()
        allowance_usd = allowance_raw / 10**6
        
        if allowance_raw >= max_uint - 1000:
            status = "✅ APPROVED (max)"
        elif allowance_usd >= balance_usd:
            status = f"✅ APPROVED (${allowance_usd:.2f})"
        elif allowance_usd > 0:
            status = f"⚠️  PARTIAL (${allowance_usd:.2f})"
        else:
            status = "❌ NOT APPROVED"
        
        print(f"{name:20} ({contract_addr[:10]}...): {status}")
        if allowance_usd > 0:
            print(f"   Allowance: ${allowance_usd:.2f} USDC")
    
    # Summary
    print(f"\n{'='*70}")
    print("SUMMARY")
    print(f"{'='*70}")
    
    if balance_usd < 5:
        print(f"❌ INSUFFICIENT BALANCE")
        print(f"   You have ${balance_usd:.2f} USDC, but need at least $5.00")
        print(f"   Send USDC to: {proxy_address}")
    else:
        print(f"✅ Balance is sufficient: ${balance_usd:.2f} USDC")
    
    # Check if all contracts are approved
    all_approved = True
    for name, contract_addr in POLYMARKET_CONTRACTS.items():
        contract_addr_checksum = Web3.to_checksum_address(contract_addr)
        allowance_raw = usdc_contract.functions.allowance(proxy_address, contract_addr_checksum).call()
        if allowance_raw < max_uint - 1000:
            all_approved = False
            break
    
    if all_approved:
        print(f"✅ All contracts are approved")
    else:
        print(f"⚠️  Some contracts may not be fully approved")
        print(f"   Run: docker exec -it BACKEND_CONTAINER python -m app.scripts.approve_contracts_programmatic")
    
    # Check if balance is enough for the order size that failed (100 USDC)
    if balance_usd < 100:
        print(f"\n⚠️  ORDER SIZE ISSUE")
        print(f"   The test order tried to use 100 USDC")
        print(f"   But you only have ${balance_usd:.2f} USDC")
        print(f"   Solution: Use smaller order size (5-10 USDC) or add more USDC")


if __name__ == "__main__":
    main()

