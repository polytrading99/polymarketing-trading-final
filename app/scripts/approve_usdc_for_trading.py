#!/usr/bin/env python3
"""
Approve USDC contract for Polymarket Exchange to allow trading.
This fixes the "not enough balance / allowance" error.

The bot can READ your balance (that works), but to PLACE ORDERS,
the Exchange contract needs permission to spend your USDC.
"""
import os
import sys
from pathlib import Path
from web3 import Web3

print("="*70)
print("  APPROVE USDC FOR POLYMARKET TRADING")
print("="*70)

# Get credentials
pk = os.environ.get("PK")
proxy_address = os.environ.get("BROWSER_ADDRESS")

if not pk or pk.upper() in ("API", "NOT SET", "NONE", ""):
    print("\n✗ ERROR: PK environment variable not set!")
    sys.exit(1)

if not proxy_address or proxy_address.upper() in ("WALLET API", "NOT SET", "NONE", "NULL", ""):
    print("\n✗ ERROR: BROWSER_ADDRESS environment variable not set!")
    sys.exit(1)

print(f"\nProxy Address: {proxy_address}")

# Connect to Polygon
polygon_rpc = "https://polygon-rpc.com"
w3 = Web3(Web3.HTTPProvider(polygon_rpc))

if not w3.is_connected():
    print("\n✗ ERROR: Cannot connect to Polygon RPC")
    sys.exit(1)

print("✓ Connected to Polygon")

# Contract addresses
USDC_ADDRESS = "0x2791Bca1f2de4661ED88A30C99A7a9449Aa84174"

# Try to get Exchange address from py-clob-client
try:
    from py_clob_client.client import ClobClient
    
    # Initialize client to get exchange address
    client = ClobClient(
        host="https://clob.polymarket.com",
        key=pk,
        chain_id=137,
        funder=proxy_address,
        signature_type=2
    )
    
    # Try to get exchange address from client
    if hasattr(client, 'exchange_address') or hasattr(client, '_exchange_address'):
        exchange_address = getattr(client, 'exchange_address', None) or getattr(client, '_exchange_address', None)
    else:
        # Default Polymarket Exchange address on Polygon
        # This is the CLOB Exchange contract that needs USDC approval
        exchange_address = "0x4bfb41d5b3570dfe3a6c6c0c11b55b319906cb0a"
    
    print(f"Exchange Address: {exchange_address}")
    
except Exception as e:
    print(f"⚠️  Could not get exchange address from client: {e}")
    # Use known Exchange address
    exchange_address = "0x4bfb41d5b3570dfe3a6c6c0c11b55b319906cb0a"
    print(f"Using default Exchange address: {exchange_address}")

# ERC20 ABI for approve and allowance
erc20_abi = [
    {
        "constant": False,
        "inputs": [
            {"name": "_spender", "type": "address"},
            {"name": "_value", "type": "uint256"}
        ],
        "name": "approve",
        "outputs": [{"name": "", "type": "bool"}],
        "type": "function"
    },
    {
        "constant": True,
        "inputs": [
            {"name": "_owner", "type": "address"},
            {"name": "_spender", "type": "address"}
        ],
        "name": "allowance",
        "outputs": [{"name": "", "type": "uint256"}],
        "type": "function"
    },
    {
        "constant": True,
        "inputs": [],
        "name": "decimals",
        "outputs": [{"name": "", "type": "uint8"}],
        "type": "function"
    }
]

# Get wallet from private key
from eth_account import Account
account = Account.from_key(pk)
wallet_address = account.address

print(f"Wallet Address (from PK): {wallet_address}")
print(f"Proxy Address (from env): {proxy_address}")

# Check which address has USDC
usdc_contract_temp = w3.eth.contract(
    address=Web3.to_checksum_address(USDC_ADDRESS),
    abi=erc20_abi
)

wallet_balance = usdc_contract_temp.functions.balanceOf(Web3.to_checksum_address(wallet_address)).call()
proxy_balance = usdc_contract_temp.functions.balanceOf(Web3.to_checksum_address(proxy_address)).call()

decimals_temp = usdc_contract_temp.functions.decimals().call()
wallet_balance_usd = wallet_balance / (10 ** decimals_temp)
proxy_balance_usd = proxy_balance / (10 ** decimals_temp)

print(f"\nUSDC Balances:")
print(f"  Wallet ({wallet_address}): ${wallet_balance_usd:,.2f}")
print(f"  Proxy ({proxy_address}): ${proxy_balance_usd:,.2f}")

# Determine which address to use for approval
# The bot uses proxy_address for trading (signature_type=2), so we need to approve from proxy
# But we can only sign from wallet_address (we have its private key)
# So we need to approve from proxy_address, but sign with wallet_address's key
# This only works if wallet_address has MATIC for gas

if proxy_address and proxy_address.lower() != wallet_address.lower():
    print(f"\n⚠️  Proxy address differs from wallet address")
    print(f"   Bot uses proxy address for trading (signature_type=2)")
    
    # Check MATIC balance of wallet address
    wallet_matic = w3.eth.get_balance(Web3.to_checksum_address(wallet_address))
    wallet_matic_eth = wallet_matic / 1e18
    
    if wallet_matic == 0:
        print(f"\n✗ ERROR: Wallet address has 0 MATIC!")
        print(f"   Wallet needs MATIC to pay for gas fees.")
        print(f"   Send some MATIC to: {wallet_address}")
        print(f"   You can get MATIC from: https://faucet.polygon.technology/")
        print(f"\n   Or if proxy address has MATIC, you may need to approve manually via MetaMask")
        sys.exit(1)
    
    print(f"   Wallet MATIC balance: {wallet_matic_eth:.6f} MATIC")
    
    # Use proxy address for approval (where USDC is)
    # But sign from wallet address (where private key is)
    trading_address = Web3.to_checksum_address(proxy_address)
    signing_address = Web3.to_checksum_address(wallet_address)
    print(f"   Approving USDC from: {trading_address} (proxy - has USDC)")
    print(f"   Signing transaction from: {signing_address} (wallet - has private key)")
else:
    trading_address = Web3.to_checksum_address(wallet_address)
    signing_address = Web3.to_checksum_address(wallet_address)

exchange_address = Web3.to_checksum_address(exchange_address)
print(f"\nApproving from: {trading_address}")
print(f"Approving to: {exchange_address}")

# Check current allowance
usdc_contract = w3.eth.contract(
    address=Web3.to_checksum_address(USDC_ADDRESS),
    abi=erc20_abi
)

print(f"\nChecking current allowance...")
current_allowance = usdc_contract.functions.allowance(
    trading_address,
    exchange_address
).call()

decimals = usdc_contract.functions.decimals().call()
current_allowance_usd = current_allowance / (10 ** decimals)

print(f"Current USDC Allowance: ${current_allowance_usd:,.2f}")

if current_allowance_usd >= 1000:
    print("✓ Allowance is sufficient (>= $1000)")
    print("  If you're still getting errors, the issue might be something else.")
else:
    print(f"⚠️  Allowance is low (${current_allowance_usd:,.2f})")
    print("  Approving maximum allowance...")
    
    # Approve maximum amount (2^256 - 1)
    max_approval = 2**256 - 1
    
    try:
        # Build transaction
        # IMPORTANT: We can only approve from the address that owns the USDC
        # But we can only sign with the wallet address's private key
        # So trading_address MUST be the same as signing_address (wallet_address)
        # OR trading_address must be controlled by the same private key
        
        # If they're different, we need to approve from wallet_address
        # But first, we need to ensure wallet_address has USDC OR we need MATIC in wallet_address
        if trading_address.lower() != signing_address.lower():
            print(f"\n⚠️  WARNING: Proxy address has USDC but wallet address has private key")
            print(f"   We can only approve from wallet address (we have its private key)")
            print(f"   If proxy address has USDC, you may need to transfer USDC to wallet address first")
            print(f"   OR approve manually from proxy address if you have its private key")
            
            # Try to approve from wallet address anyway (in case USDC was moved)
            approve_from = signing_address
        else:
            approve_from = trading_address
        
        approve_txn = usdc_contract.functions.approve(
            exchange_address,
            max_approval
        ).build_transaction({
            'from': approve_from,  # Must match the address we're signing with
            'nonce': w3.eth.get_transaction_count(signing_address),
            'gas': 100000,
            'gasPrice': w3.eth.gas_price,
        })
        
        # Sign transaction
        signed_txn = account.sign_transaction(approve_txn)
        
        # Send transaction
        print("\nSending approval transaction...")
        # Handle both old and new eth_account versions
        raw_tx = getattr(signed_txn, 'rawTransaction', None) or getattr(signed_txn, 'raw_transaction', None)
        if raw_tx is None:
            raise ValueError("Could not find raw transaction data in signed transaction")
        tx_hash = w3.eth.send_raw_transaction(raw_tx)
        print(f"✓ Transaction sent: {tx_hash.hex()}")
        print(f"  View on PolygonScan: https://polygonscan.com/tx/{tx_hash.hex()}")
        
        # Wait for confirmation
        print("Waiting for confirmation...")
        receipt = w3.eth.wait_for_transaction_receipt(tx_hash, timeout=120)
        
        if receipt.status == 1:
            print("✓ Transaction confirmed!")
            print(f"  Block: {receipt.blockNumber}")
            print(f"  Gas used: {receipt.gasUsed:,}")
            
            # Verify new allowance
            new_allowance = usdc_contract.functions.allowance(
                trading_address,
                exchange_address
            ).call()
            new_allowance_usd = new_allowance / (10 ** decimals)
            print(f"\n✓ New Allowance: ${new_allowance_usd:,.2f}")
            print("\n✅ USDC is now approved for trading!")
        else:
            print("✗ Transaction failed!")
            sys.exit(1)
            
    except Exception as e:
        print(f"\n✗ Error approving USDC: {e}")
        import traceback
        traceback.print_exc()
        
        # If signing from proxy address fails, try from wallet address
        if "insufficient funds" in str(e).lower() or "nonce" in str(e).lower():
            print("\n⚠️  Note: If you're using a proxy address, you may need to:")
            print("   1. Approve from your MetaMask wallet directly")
            print("   2. Or ensure the proxy address has MATIC for gas")
        sys.exit(1)

print("\n" + "="*70)
print("  ✅ APPROVAL COMPLETE")
print("="*70)
print("\n⚠️  IMPORTANT: Restart the bot for changes to take effect!")
print("   Run: curl -X POST http://localhost:8000/mm-bot/restart")
print("="*70)

