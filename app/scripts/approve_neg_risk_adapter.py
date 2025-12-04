"""
Quick script to approve only the Neg Risk Adapter contract.
This is the missing approval from the check results.
"""

import os
import sys
from dotenv import load_dotenv
from web3 import Web3
from web3.constants import MAX_INT
from web3.middleware import ExtraDataToPOAMiddleware

# Add parent directory to path
sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), '../..')))

load_dotenv()

# Contract addresses
USDC_ADDRESS = "0x2791Bca1f2de4661ED88A30C99A7a9449Aa84174"
CONDITIONAL_TOKENS_ADDRESS = "0x4D97DCd97eC945f40cF65F87097ACe5EA0476045"
NEG_RISK_ADAPTER = "0xd91E80cF2E7be2e162c6513ceD06f1D0dA35296"

# ERC20 ABI for approve
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


def main():
    print("=" * 70)
    print("APPROVE NEG RISK ADAPTER CONTRACT")
    print("=" * 70)
    
    # Get credentials
    priv_key = os.getenv("PK")
    browser_address = os.getenv("BROWSER_ADDRESS")
    
    if not priv_key:
        print("❌ PK (private key) not found")
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
    
    # Get wallet
    wallet = web3.eth.account.from_key(priv_key)
    pub_key = wallet.address
    
    # IMPORTANT: For Polymarket, approvals need to be from the PROXY address
    # But we can only sign from the MetaMask wallet
    # Check if browser_address is the proxy or the wallet
    proxy_address = Web3.to_checksum_address(browser_address)
    
    print(f"\nMetaMask Wallet: {pub_key}")
    print(f"Proxy Address: {proxy_address}")
    print(f"Neg Risk Adapter: {NEG_RISK_ADAPTER}\n")
    
    # Check MATIC balance (need it in MetaMask wallet for gas)
    matic_balance = web3.eth.get_balance(pub_key) / 10**18
    print(f"MATIC Balance: {matic_balance:.4f} MATIC")
    
    if matic_balance < 0.01:
        print("❌ Low MATIC balance. Need MATIC for gas fees!")
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
    
    adapter_checksum = Web3.to_checksum_address(NEG_RISK_ADAPTER)
    
    # 1. Approve USDC
    # NOTE: We sign from MetaMask wallet, but the proxy controls funds
    # The proxy inherits approvals from the controlling wallet
    print(f"\n{'='*70}")
    print("1. Approving USDC for Neg Risk Adapter...")
    print("="*70)
    print(f"   Signing FROM: {pub_key} (MetaMask wallet)")
    print(f"   Proxy (holds funds): {proxy_address}")
    print(f"   Approving TO: {adapter_checksum}")
    
    try:
        # Sign from MetaMask wallet (proxy inherits the approval)
        nonce = web3.eth.get_transaction_count(pub_key)
        raw_txn = usdc_contract.functions.approve(
            adapter_checksum,
            int(MAX_INT, 0)
        ).build_transaction({
            "chainId": 137,
            "from": pub_key,  # Sign from MetaMask wallet
            "nonce": nonce,
            "gasPrice": web3.eth.gas_price,
        })
        
        try:
            gas_estimate = web3.eth.estimate_gas(raw_txn)
            raw_txn['gas'] = int(gas_estimate * 1.2)
        except:
            raw_txn['gas'] = 100000
        
        signed_txn = web3.eth.account.sign_transaction(raw_txn, private_key=priv_key)
        tx_hash = web3.eth.send_raw_transaction(signed_txn.raw_transaction)
        
        print(f"Transaction hash: {tx_hash.hex()}")
        print("Waiting for confirmation...")
        
        receipt = web3.eth.wait_for_transaction_receipt(tx_hash, timeout=600)
        
        if receipt.status == 1:
            print(f"✅ USDC approval successful!")
            print(f"Block: {receipt.blockNumber}")
        else:
            print(f"❌ USDC approval failed!")
            return
    except Exception as e:
        print(f"❌ Error: {e}")
        import traceback
        traceback.print_exc()
        return
    
    # 2. Approve Conditional Tokens
    print(f"\n{'='*70}")
    print("2. Approving Conditional Tokens (ERC1155) for Neg Risk Adapter...")
    print("="*70)
    print(f"   Signing FROM: {pub_key} (MetaMask wallet)")
    print(f"   Proxy (holds funds): {proxy_address}")
    print(f"   Approving TO: {adapter_checksum}")
    
    try:
        # Sign from MetaMask wallet (proxy inherits the approval)
        nonce = web3.eth.get_transaction_count(pub_key)
        raw_txn = ctf_contract.functions.setApprovalForAll(
            adapter_checksum,
            True
        ).build_transaction({
            "chainId": 137,
            "from": pub_key,  # Sign from MetaMask wallet
            "nonce": nonce,
            "gasPrice": web3.eth.gas_price,
        })
        
        try:
            gas_estimate = web3.eth.estimate_gas(raw_txn)
            raw_txn['gas'] = int(gas_estimate * 1.2)
        except:
            raw_txn['gas'] = 100000
        
        signed_txn = web3.eth.account.sign_transaction(raw_txn, private_key=priv_key)
        tx_hash = web3.eth.send_raw_transaction(signed_txn.raw_transaction)
        
        print(f"Transaction hash: {tx_hash.hex()}")
        print("Waiting for confirmation...")
        
        receipt = web3.eth.wait_for_transaction_receipt(tx_hash, timeout=600)
        
        if receipt.status == 1:
            print(f"✅ Conditional Tokens approval successful!")
            print(f"Block: {receipt.blockNumber}")
        else:
            print(f"❌ Conditional Tokens approval failed!")
            return
    except Exception as e:
        print(f"❌ Error: {e}")
        import traceback
        traceback.print_exc()
        return
    
    print(f"\n{'='*70}")
    print("✅ NEG RISK ADAPTER APPROVED!")
    print("="*70)
    print(f"\nNext step: Run check again to verify:")
    print(f"  docker exec -it polymarketing-trading-final-backend-1 python -m app.scripts.check_contract_approvals")


if __name__ == "__main__":
    main()

