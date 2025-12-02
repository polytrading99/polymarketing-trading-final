"""
Check if Polymarket contracts are approved for the wallet.
This is critical for API orders to work.
"""

import os
from dotenv import load_dotenv
from web3 import Web3
from web3.middleware import ExtraDataToPOAMiddleware
import json

load_dotenv()

# ERC20 ABI for checking approvals
ERC20_ABI = [
    {
        "constant": True,
        "inputs": [{"name": "_owner", "type": "address"}, {"name": "_spender", "type": "address"}],
        "name": "allowance",
        "outputs": [{"name": "", "type": "uint256"}],
        "type": "function"
    },
    {
        "constant": True,
        "inputs": [{"name": "_owner", "type": "address"}],
        "name": "balanceOf",
        "outputs": [{"name": "balance", "type": "uint256"}],
        "type": "function"
    }
]

# ERC1155 ABI for checking conditional token approvals
ERC1155_ABI = [
    {
        "constant": True,
        "inputs": [
            {"name": "account", "type": "address"},
            {"name": "operator", "type": "address"}
        ],
        "name": "isApprovedForAll",
        "outputs": [{"name": "", "type": "bool"}],
        "type": "function"
    }
]

# Polymarket contract addresses
POLYMARKET_CONTRACTS = {
    'exchange': '0x4bFb41d5B3570DeFd03C39a9A4D8dE6Bd8B8982E',
    'neg_risk_adapter': '0xd91E80cF2E7be2e162c6513ceD06f1dD0a35296',
    'exchange_v2': '0xC5d563A36AE78145C45a50134d48A1215220f80a',
}

USDC_ADDRESS = "0x2791Bca1f2de4661ED88A30C99A7a9449Aa84174"  # USDC.e
CONDITIONAL_TOKENS_ADDRESS = "0x4D97DCd97eC945f40cF65F87097ACe5EA0476045"


def main():
    print("=" * 70)
    print("CHECKING CONTRACT APPROVALS")
    print("=" * 70)
    
    # Get wallet address
    browser_address = os.getenv("BROWSER_ADDRESS", "").strip()
    if not browser_address:
        print("❌ BROWSER_ADDRESS not set!")
        return
    
    browser_address = Web3.to_checksum_address(browser_address)
    print(f"\nWallet: {browser_address}\n")
    
    # Connect to Polygon
    web3 = Web3(Web3.HTTPProvider("https://polygon-rpc.com"))
    web3.middleware_onion.inject(ExtraDataToPOAMiddleware, layer=0)
    
    # Check USDC balance
    usdc_contract = web3.eth.contract(address=Web3.to_checksum_address(USDC_ADDRESS), abi=ERC20_ABI)
    usdc_balance = usdc_contract.functions.balanceOf(browser_address).call() / 10**6
    print(f"USDC Balance: ${usdc_balance:.2f}")
    
    # Check USDC approvals for each Polymarket contract
    print(f"\n{'='*70}")
    print("USDC APPROVALS (ERC20)")
    print("=" * 70)
    
    for name, contract_addr in POLYMARKET_CONTRACTS.items():
        try:
            # Checksum the contract address before using it
            contract_addr_checksum = Web3.to_checksum_address(contract_addr)
            allowance = usdc_contract.functions.allowance(browser_address, contract_addr_checksum).call()
            allowance_usd = allowance / 10**6
            max_uint = 2**256 - 1
            
            if allowance >= max_uint - 1000:  # Close to max
                status = "✅ APPROVED (max)"
            elif allowance > 0:
                status = f"⚠️  PARTIAL (${allowance_usd:.2f})"
            else:
                status = "❌ NOT APPROVED"
            
            print(f"{name:20} ({contract_addr[:10]}...): {status}")
            if allowance > 0 and allowance < max_uint - 1000:
                print(f"  Allowance: ${allowance_usd:.2f}")
        except Exception as e:
            print(f"{name:20} ({contract_addr[:10]}...): ❌ ERROR - {e}")
    
    # Check Conditional Token approvals (ERC1155)
    print(f"\n{'='*70}")
    print("CONDITIONAL TOKEN APPROVALS (ERC1155)")
    print("=" * 70)
    
    ctf_contract = web3.eth.contract(address=Web3.to_checksum_address(CONDITIONAL_TOKENS_ADDRESS), abi=ERC1155_ABI)
    
    for name, contract_addr in POLYMARKET_CONTRACTS.items():
        try:
            # Checksum the contract address before using it
            contract_addr_checksum = Web3.to_checksum_address(contract_addr)
            is_approved = ctf_contract.functions.isApprovedForAll(browser_address, contract_addr_checksum).call()
            status = "✅ APPROVED" if is_approved else "❌ NOT APPROVED"
            print(f"{name:20} ({contract_addr[:10]}...): {status}")
        except Exception as e:
            print(f"{name:20} ({contract_addr[:10]}...): ❌ ERROR - {e}")
    
    # Summary
    print(f"\n{'='*70}")
    print("SUMMARY & INSTRUCTIONS")
    print("=" * 70)
    
    # Re-check approvals to give summary
    all_usdc_approved = True
    all_ctf_approved = True
    
    for name, contract_addr in POLYMARKET_CONTRACTS.items():
        try:
            contract_addr_checksum = Web3.to_checksum_address(contract_addr)
            allowance = usdc_contract.functions.allowance(browser_address, contract_addr_checksum).call()
            max_uint = 2**256 - 1
            if allowance < max_uint - 1000:
                all_usdc_approved = False
            
            is_approved = ctf_contract.functions.isApprovedForAll(browser_address, contract_addr_checksum).call()
            if not is_approved:
                all_ctf_approved = False
        except Exception:
            # If we can't check, assume not approved
            all_usdc_approved = False
            all_ctf_approved = False
    
    if all_usdc_approved and all_ctf_approved:
        print("✅ All contracts are approved!")
        print("\nIf you're still getting 'invalid signature' errors:")
        print("1. Make sure you did a NEW trade on Polymarket.com AFTER setting up the bot")
        print("2. Wait 2-3 minutes after the trade confirms")
        print("3. Try placing an order again")
    else:
        print("❌ Some contracts are NOT approved!")
        print("\nYou need to approve contracts for API orders to work.")
        print("\nOPTION 1: Manual approval on Polymarket.com")
        print("  1. Go to https://polymarket.com")
        print(f"  2. Connect wallet: {browser_address}")
        print("  3. Try to place a trade (even if you cancel)")
        print("  4. This will trigger contract approvals")
        print("\nOPTION 2: Run automated approval script")
        print("  docker exec -it polymarketing-trading-final-backend-1 python -m data_updater.trading_utils approveContracts")
        print("\n⚠️  WARNING: Automated approval will cost gas fees!")


if __name__ == "__main__":
    main()

