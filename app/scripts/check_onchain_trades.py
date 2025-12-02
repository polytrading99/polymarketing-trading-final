"""
Check if wallet has done trades on-chain (direct blockchain check, not Polymarket API).
"""

import os
from dotenv import load_dotenv
from web3 import Web3
from web3.middleware import ExtraDataToPOAMiddleware
from poly_data.abis import ConditionalTokenABI

load_dotenv()


def main():
    print("=" * 60)
    print("ON-CHAIN TRADE CHECK")
    print("=" * 60)
    
    browser_address = os.getenv("BROWSER_ADDRESS", "").strip()
    if not browser_address:
        print("ERROR: BROWSER_ADDRESS not set")
        return
    
    wallet = Web3.to_checksum_address(browser_address)
    print(f"\nChecking wallet: {wallet}")
    
    # Connect to Polygon
    web3 = Web3(Web3.HTTPProvider("https://polygon-rpc.com"))
    web3.middleware_onion.inject(ExtraDataToPOAMiddleware, layer=0)
    
    # Conditional Tokens contract (where positions are stored)
    conditional_tokens_address = "0x4D97DCd97eC945f40cF65F87097ACe5EA0476045"
    conditional_tokens = web3.eth.contract(
        address=conditional_tokens_address,
        abi=ConditionalTokenABI
    )
    
    print(f"\n1. Checking for token balances (positions)...")
    print(f"   If you have positions, you've likely done trades")
    
    # We can't easily enumerate all tokens, but we can check recent events
    # Let's check Transfer events from/to this wallet
    
    print(f"\n2. Checking recent Transfer events (this may take a moment)...")
    try:
        # Get recent Transfer events where this wallet is involved
        # We'll check the last 10000 blocks (roughly last few hours)
        latest_block = web3.eth.block_number
        from_block = max(0, latest_block - 10000)
        
        print(f"   Scanning blocks {from_block} to {latest_block}...")
        
        # Get Transfer events
        transfer_filter = conditional_tokens.events.Transfer.create_filter(
            fromBlock=from_block,
            toBlock=latest_block,
            argument_filters={
                'from': wallet
            }
        )
        
        transfers_from = transfer_filter.get_all_entries()
        
        transfer_filter_to = conditional_tokens.events.Transfer.create_filter(
            fromBlock=from_block,
            toBlock=latest_block,
            argument_filters={
                'to': wallet
            }
        )
        
        transfers_to = transfer_filter_to.get_all_entries()
        
        all_transfers = transfers_from + transfers_to
        
        if all_transfers:
            print(f"   ✅ Found {len(all_transfers)} Transfer events involving this wallet!")
            print(f"   Recent transfers:")
            for i, event in enumerate(all_transfers[-5:]):  # Show last 5
                print(f"      Block {event.blockNumber}: {event.event}")
        else:
            print(f"   ⚠️  No Transfer events found in recent blocks")
            print(f"   This means either:")
            print(f"      - No trades happened recently")
            print(f"      - Trades happened more than ~10000 blocks ago")
            print(f"      - Trades were on a different wallet")
    except Exception as e:
        print(f"   ⚠️  Could not check events: {e}")
    
    # Check USDC transfers (trades involve USDC)
    print(f"\n3. Checking USDC transfers (trades involve USDC)...")
    try:
        from poly_data.abis import erc20_abi
        usdc_address = "0x2791Bca1f2de4661ED88A30C99A7a9449Aa84174"
        usdc_contract = web3.eth.contract(address=usdc_address, abi=erc20_abi)
        
        # Get Transfer events for USDC
        latest_block = web3.eth.block_number
        from_block = max(0, latest_block - 10000)
        
        transfer_filter = usdc_contract.events.Transfer.create_filter(
            fromBlock=from_block,
            toBlock=latest_block,
            argument_filters={
                'from': wallet
            }
        )
        
        usdc_transfers = transfer_filter.get_all_entries()
        
        if usdc_transfers:
            print(f"   ✅ Found {len(usdc_transfers)} USDC transfers FROM this wallet")
            print(f"   This suggests trades were made!")
        else:
            print(f"   ⚠️  No USDC transfers found FROM this wallet")
    except Exception as e:
        print(f"   ⚠️  Could not check USDC transfers: {e}")
    
    print(f"\n4. Checking wallet transaction history...")
    try:
        # Get recent transactions
        latest_block = web3.eth.block_number
        tx_count = web3.eth.get_transaction_count(wallet)
        print(f"   Total transactions from this wallet: {tx_count}")
        
        if tx_count == 0:
            print(f"   ⚠️  Wallet has NEVER sent a transaction!")
            print(f"   This means no trades could have happened")
        elif tx_count > 0:
            print(f"   ✅ Wallet has sent transactions (likely has done trades)")
    except Exception as e:
        print(f"   ⚠️  Could not check transaction count: {e}")
    
    print(f"\n{'='*60}")
    print("SUMMARY")
    print("=" * 60)
    print("\nIf you see Transfer events or USDC transfers, trades happened on-chain.")
    print("If Polymarket API still shows no trades, wait a few minutes for indexing.")
    print("\nIf you see NO on-chain activity, the trade might have:")
    print("  1. Failed to confirm")
    print("  2. Been done on a different wallet")
    print("  3. Not actually executed")


if __name__ == "__main__":
    main()

