"""
Programmatically approve Polymarket contracts for trading.
This script approves contracts using your MetaMask private key.

IMPORTANT: 
- Approvals are done FROM your MetaMask wallet address
- But the proxy address (BROWSER_ADDRESS) is what holds funds on Polymarket
- The proxy inherits approvals from the controlling wallet in some cases
- If this doesn't work, you may need to approve directly from the proxy (requires proxy contract interaction)
"""

import os
import sys
import time
from dotenv import load_dotenv
from web3 import Web3
from web3.constants import MAX_INT
from web3.middleware import ExtraDataToPOAMiddleware

# Add parent directory to path
sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), '../..')))

load_dotenv()

# ERC20 ABI for approve function
ERC20_APPROVE_ABI = [
    {
        "constant": False,
        "inputs": [
            {"name": "_spender", "type": "address"},
            {"name": "_value", "type": "uint256"}
        ],
        "name": "approve",
        "outputs": [{"name": "", "type": "bool"}],
        "payable": False,
        "stateMutability": "nonpayable",
        "type": "function"
    }
]

# ERC1155 ABI for setApprovalForAll
ERC1155_SET_APPROVAL_ABI = [
    {
        "inputs": [
            {"internalType": "address", "name": "operator", "type": "address"},
            {"internalType": "bool", "name": "approved", "type": "bool"}
        ],
        "name": "setApprovalForAll",
        "outputs": [],
        "stateMutability": "nonpayable",
        "type": "function"
    }
]

# Contract addresses
USDC_ADDRESS = "0x2791Bca1f2de4661ED88A30C99A7a9449Aa84174"  # USDC.e
CONDITIONAL_TOKENS_ADDRESS = "0x4D97DCd97eC945f40cF65F87097ACe5EA0476045"

# Polymarket exchange addresses that need approval
POLYMARKET_CONTRACTS = {
    'CTF Exchange': '0x4bFb41d5B3570DeFd03C39a9A4D8dE6Bd8B8982E',
    'Neg Risk CTF Exchange': '0xC5d563A36AE78145C45a50134d48A1215220f80a',
    'Neg Risk Adapter': '0xd91E80cF2E7be2e162c6513ceD06f1dD0dA35296',
}

CHAIN_ID = 137  # Polygon
RPC_URL = "https://polygon-rpc.com"


def main():
    print("=" * 70)
    print("APPROVE POLYMARKET CONTRACTS PROGRAMMATICALLY")
    print("=" * 70)
    
    # Get credentials
    priv_key = os.getenv("PK")
    browser_address = os.getenv("BROWSER_ADDRESS")
    
    if not priv_key:
        print("❌ PK (private key) not found in environment")
        return
    
    if not browser_address:
        print("❌ BROWSER_ADDRESS not found in environment")
        return
    
    # Clean private key
    if priv_key.startswith('0x') or priv_key.startswith('0X'):
        priv_key = priv_key[2:]
    
    # Clean and checksum browser address
    browser_address = browser_address.strip()
    if browser_address.startswith('0x') and len(browser_address) > 42:
        browser_address = browser_address[:42]
    browser_address = Web3.to_checksum_address(browser_address)
    
    # Connect to Polygon
    web3 = Web3(Web3.HTTPProvider(RPC_URL))
    web3.middleware_onion.inject(ExtraDataToPOAMiddleware, layer=0)
    
    # Get wallet from private key
    try:
        wallet = web3.eth.account.from_key(priv_key)
        pub_key = wallet.address
        print(f"\nMetaMask Wallet: {pub_key}")
        print(f"Polymarket Proxy: {browser_address}")
        
        if pub_key.lower() != browser_address.lower():
            print(f"\n⚠️  WARNING: MetaMask address differs from proxy address")
            print(f"   This is normal - the proxy is controlled by your MetaMask wallet")
            print(f"   We'll approve from MetaMask wallet, proxy should inherit approvals")
    except Exception as e:
        print(f"❌ Failed to create wallet from private key: {e}")
        return
    
    # Check MATIC balance (needed for gas)
    matic_balance = web3.eth.get_balance(pub_key) / 10**18
    print(f"MATIC Balance: {matic_balance:.4f} MATIC")
    
    if matic_balance < 0.01:
        print(f"⚠️  WARNING: Low MATIC balance. You need MATIC for gas fees!")
        print(f"   Send some MATIC to: {pub_key}")
        return
    
    # Initialize contracts
    usdc_contract = web3.eth.contract(
        address=Web3.to_checksum_address(USDC_ADDRESS),
        abi=ERC20_APPROVE_ABI
    )
    
    ctf_contract = web3.eth.contract(
        address=Web3.to_checksum_address(CONDITIONAL_TOKENS_ADDRESS),
        abi=ERC1155_SET_APPROVAL_ABI
    )
    
    print(f"\n{'='*70}")
    print("APPROVING CONTRACTS")
    print("=" * 70)
    print(f"This will approve {len(POLYMARKET_CONTRACTS)} Polymarket contracts")
    print(f"Total transactions: {len(POLYMARKET_CONTRACTS) * 2} (USDC + CTF for each)")
    print(f"\nPress Ctrl+C to cancel, or wait 5 seconds to continue...")
    
    try:
        time.sleep(5)
    except KeyboardInterrupt:
        print("\n❌ Cancelled by user")
        return
    
    # Approve each contract
    for contract_name, contract_address in POLYMARKET_CONTRACTS.items():
        print(f"\n{'-'*70}")
        print(f"Approving: {contract_name}")
        print(f"Address: {contract_address}")
        print(f"{'-'*70}")
        
        contract_address_checksum = Web3.to_checksum_address(contract_address)
        
        # 1. Approve USDC
        try:
            print(f"\n1. Approving USDC for {contract_name}...")
            nonce = web3.eth.get_transaction_count(pub_key)
            
            raw_usdc_txn = usdc_contract.functions.approve(
                contract_address_checksum,
                int(MAX_INT, 0)
            ).build_transaction({
                "chainId": CHAIN_ID,
                "from": pub_key,
                "nonce": nonce,
                "gasPrice": web3.eth.gas_price,
            })
            
            # Estimate gas
            try:
                gas_estimate = web3.eth.estimate_gas(raw_usdc_txn)
                raw_usdc_txn['gas'] = int(gas_estimate * 1.2)  # Add 20% buffer
            except Exception as e:
                print(f"   ⚠️  Could not estimate gas, using default: {e}")
                raw_usdc_txn['gas'] = 100000
            
            signed_usdc_txn = web3.eth.account.sign_transaction(raw_usdc_txn, private_key=priv_key)
            tx_hash = web3.eth.send_raw_transaction(signed_usdc_txn.raw_transaction)
            
            print(f"   Transaction hash: {tx_hash.hex()}")
            print(f"   Waiting for confirmation...")
            
            receipt = web3.eth.wait_for_transaction_receipt(tx_hash, timeout=600)
            
            if receipt.status == 1:
                print(f"   ✅ USDC approval successful!")
                print(f"   Block: {receipt.blockNumber}, Gas used: {receipt.gasUsed}")
            else:
                print(f"   ❌ USDC approval failed!")
                return
                
        except Exception as e:
            print(f"   ❌ Error approving USDC: {e}")
            import traceback
            traceback.print_exc()
            continue
        
        time.sleep(2)  # Wait between transactions
        
        # 2. Approve Conditional Tokens (ERC1155)
        try:
            print(f"\n2. Approving Conditional Tokens (ERC1155) for {contract_name}...")
            nonce = web3.eth.get_transaction_count(pub_key)
            
            raw_ctf_txn = ctf_contract.functions.setApprovalForAll(
                contract_address_checksum,
                True
            ).build_transaction({
                "chainId": CHAIN_ID,
                "from": pub_key,
                "nonce": nonce,
                "gasPrice": web3.eth.gas_price,
            })
            
            # Estimate gas
            try:
                gas_estimate = web3.eth.estimate_gas(raw_ctf_txn)
                raw_ctf_txn['gas'] = int(gas_estimate * 1.2)  # Add 20% buffer
            except Exception as e:
                print(f"   ⚠️  Could not estimate gas, using default: {e}")
                raw_ctf_txn['gas'] = 100000
            
            signed_ctf_txn = web3.eth.account.sign_transaction(raw_ctf_txn, private_key=priv_key)
            tx_hash = web3.eth.send_raw_transaction(signed_ctf_txn.raw_transaction)
            
            print(f"   Transaction hash: {tx_hash.hex()}")
            print(f"   Waiting for confirmation...")
            
            receipt = web3.eth.wait_for_transaction_receipt(tx_hash, timeout=600)
            
            if receipt.status == 1:
                print(f"   ✅ Conditional Tokens approval successful!")
                print(f"   Block: {receipt.blockNumber}, Gas used: {receipt.gasUsed}")
            else:
                print(f"   ❌ Conditional Tokens approval failed!")
                return
                
        except Exception as e:
            print(f"   ❌ Error approving Conditional Tokens: {e}")
            import traceback
            traceback.print_exc()
            continue
        
        time.sleep(2)  # Wait between contract approvals
    
    print(f"\n{'='*70}")
    print("✅ ALL APPROVALS COMPLETE!")
    print("=" * 70)
    print(f"\nApproved contracts from: {pub_key}")
    print(f"Polymarket proxy: {browser_address}")
    print(f"\nNext steps:")
    print(f"1. Wait 1-2 minutes for approvals to propagate")
    print(f"2. Run: python -m app.scripts.check_contract_approvals")
    print(f"3. Try placing a test order: python -m app.scripts.place_test_order")


if __name__ == "__main__":
    main()

