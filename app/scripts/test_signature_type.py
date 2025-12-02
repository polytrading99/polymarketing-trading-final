"""
Test different signature types and check contract approvals.
"""

import os
from dotenv import load_dotenv
from web3 import Web3
from web3.middleware import ExtraDataToPOAMiddleware
from py_clob_client.client import ClobClient
from py_clob_client.constants import POLYGON
from py_clob_client.clob_types import OrderArgs, PartialCreateOrderOptions
from poly_data.abis import erc20_abi

load_dotenv()


def check_approvals(web3, wallet, token_address, spender_address):
    """Check if token is approved for spender."""
    try:
        contract = web3.eth.contract(address=token_address, abi=erc20_abi)
        allowance = contract.functions.allowance(wallet, spender_address).call()
        return allowance
    except:
        return 0


def main():
    print("=" * 60)
    print("TESTING SIGNATURE TYPES & CONTRACT APPROVALS")
    print("=" * 60)
    
    pk = os.getenv("PK", "").strip()
    if pk.startswith("0x") or pk.startswith("0X"):
        pk = pk[2:]
    
    browser_address = os.getenv("BROWSER_ADDRESS", "").strip()
    browser_address = Web3.to_checksum_address(browser_address)
    
    print(f"\nWallet: {browser_address}\n")
    
    # Connect to Polygon
    web3 = Web3(Web3.HTTPProvider("https://polygon-rpc.com"))
    web3.middleware_onion.inject(ExtraDataToPOAMiddleware, layer=0)
    
    # Check contract approvals
    print("1. Checking contract approvals...")
    usdc_address = "0x2791Bca1f2de4661ED88A30C99A7a9449Aa84174"
    
    # Polymarket contract addresses that need approval
    polymarket_contracts = [
        ("Conditional Tokens", "0x4D97DCd97eC945f40cF65F87097ACe5EA0476045"),
        ("Neg Risk Adapter", "0xd91E80cF2E7be2e162c6513ceD06f1dD0dA35296"),
        ("Exchange", "0x4bFb41d5B3570DeFd03C39a9A4D8dE6Bd8B8982E"),
    ]
    
    for name, contract_addr in polymarket_contracts:
        try:
            # Check ERC1155 approval (setApprovalForAll)
            from poly_data.abis import ConditionalTokenABI
            ctf_contract = web3.eth.contract(address="0x4D97DCd97eC945f40cF65F87097ACe5EA0476045", abi=ConditionalTokenABI)
            is_approved = ctf_contract.functions.isApprovedForAll(browser_address, contract_addr).call()
            print(f"   {name} ({contract_addr[:20]}...): {'✅ Approved' if is_approved else '❌ NOT Approved'}")
        except Exception as e:
            print(f"   {name}: ⚠️  Could not check ({e})")
    
    # Check USDC approval
    for name, contract_addr in polymarket_contracts:
        allowance = check_approvals(web3, browser_address, usdc_address, contract_addr)
        if allowance > 0:
            print(f"   USDC approved for {name}: ✅ {allowance / 10**6:.2f} USDC")
        else:
            print(f"   USDC approved for {name}: ❌ 0")
    
    # Test signature_type=1
    print(f"\n2. Testing signature_type=1...")
    try:
        client1 = ClobClient(
            host="https://clob.polymarket.com",
            key=pk,
            chain_id=POLYGON,
            funder=browser_address,
            signature_type=1  # Try type 1 instead of 2
        )
        
        creds1 = client1.create_or_derive_api_creds()
        client1.set_api_creds(creds=creds1)
        print(f"   ✅ ClobClient with signature_type=1 created")
        
        # Get a test market
        markets = client1.get_sampling_markets()
        if markets and 'data' in markets and len(markets['data']) > 0:
            market = markets['data'][0]
            tokens = market.get('tokens', [])
            if tokens:
                token_yes = tokens[0].get('token_id')
                rewards = market.get('rewards', {})
                is_neg_risk = bool(rewards.get('min_size') or rewards.get('max_spread'))
                
                print(f"   Testing with token: {token_yes}")
                print(f"   Neg Risk: {is_neg_risk}")
                
                order_args = OrderArgs(
                    token_id=str(token_yes),
                    price=0.5,
                    size=1.0,
                    side="BUY"
                )
                
                if is_neg_risk:
                    signed_order = client1.create_order(order_args, options=PartialCreateOrderOptions(neg_risk=True))
                else:
                    signed_order = client1.create_order(order_args)
                
                print(f"   ✅ Order signed with signature_type=1")
                
                try:
                    resp = client1.post_order(signed_order)
                    print(f"   ✅✅✅ SUCCESS with signature_type=1!")
                    print(f"   Response: {resp}")
                    print(f"\n   🎉 SOLUTION FOUND: Use signature_type=1 instead of 2!")
                    return
                except Exception as e:
                    error_str = str(e)
                    print(f"   ❌ Failed with signature_type=1: {error_str}")
    except Exception as e:
        print(f"   ❌ Error with signature_type=1: {e}")
    
    # Test signature_type=2 (current)
    print(f"\n3. Testing signature_type=2 (current)...")
    try:
        client2 = ClobClient(
            host="https://clob.polymarket.com",
            key=pk,
            chain_id=POLYGON,
            funder=browser_address,
            signature_type=2  # Current type
        )
        
        creds2 = client2.create_or_derive_api_creds()
        client2.set_api_creds(creds=creds2)
        print(f"   ✅ ClobClient with signature_type=2 created")
        
        # Get a test market
        markets = client2.get_sampling_markets()
        if markets and 'data' in markets and len(markets['data']) > 0:
            market = markets['data'][0]
            tokens = market.get('tokens', [])
            if tokens:
                token_yes = tokens[0].get('token_id')
                rewards = market.get('rewards', {})
                is_neg_risk = bool(rewards.get('min_size') or rewards.get('max_spread'))
                
                order_args = OrderArgs(
                    token_id=str(token_yes),
                    price=0.5,
                    size=1.0,
                    side="BUY"
                )
                
                if is_neg_risk:
                    signed_order = client2.create_order(order_args, options=PartialCreateOrderOptions(neg_risk=True))
                else:
                    signed_order = client2.create_order(order_args)
                
                print(f"   ✅ Order signed with signature_type=2")
                
                try:
                    resp = client2.post_order(signed_order)
                    print(f"   ✅✅✅ SUCCESS with signature_type=2!")
                    print(f"   Response: {resp}")
                    return
                except Exception as e:
                    error_str = str(e)
                    print(f"   ❌ Failed with signature_type=2: {error_str}")
    except Exception as e:
        print(f"   ❌ Error with signature_type=2: {e}")
    
    print(f"\n{'='*60}")
    print("SUMMARY")
    print("=" * 60)
    print("\nIf both signature types failed, the issue is likely:")
    print("1. Wallet needs to do a trade specifically through Polymarket's CLOB API")
    print("2. Contract approvals are missing (check output above)")
    print("3. There's a bug in py_clob_client library")


if __name__ == "__main__":
    main()

