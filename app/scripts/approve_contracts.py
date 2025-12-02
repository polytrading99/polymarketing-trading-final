"""
Script to approve Polymarket contracts for trading.
This must be run to allow the bot to place orders.
"""

import os
from dotenv import load_dotenv
from web3 import Web3
from web3.middleware import ExtraDataToPOAMiddleware
from poly_data.abis import erc20_abi, ConditionalTokenABI

load_dotenv()


def main():
    print("=" * 60)
    print("APPROVE POLYMARKET CONTRACTS")
    print("=" * 60)
    print("\nThis script will help you approve Polymarket contracts.")
    print("You need to approve contracts so the bot can trade on your behalf.\n")
    
    pk = os.getenv("PK", "").strip()
    if pk.startswith("0x") or pk.startswith("0X"):
        pk = pk[2:]
    
    browser_address = os.getenv("BROWSER_ADDRESS", "").strip()
    browser_address = Web3.to_checksum_address(browser_address)
    
    print(f"Wallet: {browser_address}\n")
    
    # Connect to Polygon
    web3 = Web3(Web3.HTTPProvider("https://polygon-rpc.com"))
    web3.middleware_onion.inject(ExtraDataToPOAMiddleware, layer=0)
    
    # Get account from private key
    from eth_account import Account
    account = Account.from_key(pk)
    
    if account.address.lower() != browser_address.lower():
        print(f"❌ ERROR: PK doesn't match BROWSER_ADDRESS!")
        print(f"   PK wallet: {account.address}")
        print(f"   BROWSER_ADDRESS: {browser_address}")
        return
    
    print(f"✅ Wallet matches PK\n")
    
    # Contract addresses
    usdc_address = "0x2791Bca1f2de4661ED88A30C99A7a9449Aa84174"
    conditional_tokens_address = "0x4D97DCd97eC945f40cF65F87097ACe5EA0476045"
    
    contracts_to_approve = [
        ("Conditional Tokens (ERC1155)", conditional_tokens_address, "0x4bFb41d5B3570DeFd03C39a9A4D8dE6Bd8B8982E", True),  # Exchange
        ("Conditional Tokens (ERC1155)", conditional_tokens_address, "0xC5d563A36AE78145C45a50134d48A1215220f80a", True),  # Another contract
        ("Conditional Tokens (ERC1155)", conditional_tokens_address, "0xd91E80cF2E7be2e162c6513ceD06f1dD0dA35296", True),  # Neg Risk Adapter
        ("USDC (ERC20)", usdc_address, "0x4bFb41d5B3570DeFd03C39a9A4D8dE6Bd8B8982E", False),  # Exchange
        ("USDC (ERC20)", usdc_address, "0xC5d563A36AE78145C45a50134d48A1215220f80a", False),  # Another contract
        ("USDC (ERC20)", usdc_address, "0xd91E80cF2E7be2e162c6513ceD06f1dD0dA35296", False),  # Neg Risk Adapter
    ]
    
    print("Contracts that need approval:")
    for name, token_addr, spender_addr, is_erc1155 in contracts_to_approve:
        print(f"  - {name} for {spender_addr[:20]}...")
    print()
    
    # Check current approvals
    print("Checking current approvals...")
    needs_approval = []
    
    for name, token_addr, spender_addr, is_erc1155 in contracts_to_approve:
        try:
            if is_erc1155:
                contract = web3.eth.contract(address=token_addr, abi=ConditionalTokenABI)
                is_approved = contract.functions.isApprovedForAll(browser_address, spender_addr).call()
                if not is_approved:
                    needs_approval.append((name, token_addr, spender_addr, is_erc1155))
                    print(f"  ❌ {name} for {spender_addr[:20]}...: NOT approved")
                else:
                    print(f"  ✅ {name} for {spender_addr[:20]}...: Already approved")
            else:
                contract = web3.eth.contract(address=token_addr, abi=erc20_abi)
                allowance = contract.functions.allowance(browser_address, spender_addr).call()
                if allowance == 0:
                    needs_approval.append((name, token_addr, spender_addr, is_erc1155))
                    print(f"  ❌ {name} for {spender_addr[:20]}...: NOT approved")
                else:
                    print(f"  ✅ {name} for {spender_addr[:20]}...: Approved ({allowance / 10**6:.2f} USDC)")
        except Exception as e:
            print(f"  ⚠️  Could not check {name}: {e}")
    
    if not needs_approval:
        print("\n✅ All contracts are already approved!")
        return
    
    print(f"\n⚠️  {len(needs_approval)} approvals needed")
    print("\n" + "=" * 60)
    print("APPROVAL INSTRUCTIONS")
    print("=" * 60)
    print("\nYou have two options:")
    print("\nOPTION 1: Approve via Polymarket website (EASIEST)")
    print("  1. Go to https://polymarket.com")
    print(f"  2. Connect wallet: {browser_address}")
    print("  3. Make ONE small trade (buy or sell any market)")
    print("  4. This will automatically approve all contracts")
    print("  5. Wait for transaction to confirm")
    print("  6. Run this script again to verify")
    
    print("\nOPTION 2: Approve via script (AUTOMATED)")
    print("  This will send transactions to approve contracts.")
    print("  You'll need MATIC for gas fees.")
    
    # Check MATIC balance
    try:
        matic_balance = web3.eth.get_balance(browser_address) / 10**18
        print(f"\n  Your MATIC balance: {matic_balance:.4f} MATIC")
        if matic_balance < 0.01:
            print(f"  ⚠️  You need at least 0.01 MATIC for gas fees")
    except:
        pass
    
    print("\n  To approve via script, run:")
    print("    docker exec -it polymarketing-trading-final-backend-1 python -m app.scripts.approve_contracts --execute")
    print("\n  Or use the data_updater/trading_utils.py approveContracts() function")
    
    print("\n" + "=" * 60)
    print("RECOMMENDATION")
    print("=" * 60)
    print("\n✅ EASIEST: Go to polymarket.com, connect wallet, make one small trade")
    print("   This auto-approves everything and also 'activates' API orders")
    print("\n⚠️  After approving, wait 2-3 minutes, then test orders again")


if __name__ == "__main__":
    import sys
    if "--execute" in sys.argv:
        print("\n⚠️  Automated approval not implemented yet.")
        print("   Please use OPTION 1 (polymarket.com) or")
        print("   use data_updater/trading_utils.py approveContracts()")
    else:
        main()

