from py_clob_client.constants import POLYGON
from py_clob_client.client import ClobClient
from py_clob_client.clob_types import OrderArgs, BalanceAllowanceParams, AssetType
from py_clob_client.order_builder.constants import BUY

from web3 import Web3
from web3.middleware import ExtraDataToPOAMiddleware

import json

from dotenv import load_dotenv
load_dotenv()

import time

import os

MAX_INT = 2**256 - 1

def get_clob_client():
    host = "https://clob.polymarket.com"
    key = os.getenv("PK")
    browser_address = os.getenv("BROWSER_ADDRESS")
    chain_id = POLYGON
    
    if key is None:
        print("Environment variable 'PK' cannot be found")
        return None
    
    if browser_address is None:
        print("Environment variable 'BROWSER_ADDRESS' cannot be found")
        return None
    
    # Clean up key (remove 0x if present)
    if key.startswith('0x') or key.startswith('0X'):
        key = key[2:]
    
    # Clean up browser_address
    browser_address = browser_address.strip()
    if browser_address.startswith('0x') and len(browser_address) > 42:
        browser_address = browser_address[:42]
    
    try:
        from web3 import Web3
        browser_address = Web3.to_checksum_address(browser_address)
        
        # Initialize ClobClient following Polymarket guide
        # signature_type=2 for Browser Wallet (Metamask, Coinbase Wallet, etc)
        # 
        # CRITICAL: The 'funder' parameter MUST be the POLYMARKET PROXY ADDRESS:
        # - This is the address shown BELOW your profile picture on Polymarket.com
        # - This is DIFFERENT from your MetaMask wallet address
        # - When you connect MetaMask to Polymarket, Polymarket creates a proxy contract
        # - The proxy address is what actually holds your funds on Polymarket
        # - The PK should still be your MetaMask private key (which controls the proxy)
        client = ClobClient(
            host=host,
            key=key,
            chain_id=chain_id,
            funder=browser_address,  # POLYMARKET_PROXY_ADDRESS (below profile picture)
            signature_type=2  # 2 for Browser Wallet, 1 for Email/Magic
        )
        api_creds = client.create_or_derive_api_creds()
        client.set_api_creds(api_creds)
        return client
    except Exception as ex: 
        print("Error creating clob client")
        print("________________")
        print(ex)
        return None


def approveContracts():
    """
    Approve Polymarket contracts programmatically.
    This approves contracts from your MetaMask wallet address.
    
    Note: If you're using a Polymarket proxy address (different from MetaMask),
    you may need to approve from the proxy address instead. In that case,
    use the approve_contracts_programmatic.py script which handles both cases.
    """
    web3 = Web3(Web3.HTTPProvider("https://polygon-rpc.com"))
    web3.middleware_onion.inject(ExtraDataToPOAMiddleware, layer=0)
    
    # Get private key
    priv_key = os.getenv("PK")
    if not priv_key:
        raise ValueError("PK environment variable not set")
    
    # Clean private key (remove 0x if present)
    if priv_key.startswith('0x') or priv_key.startswith('0X'):
        priv_key = priv_key[2:]
    
    wallet = web3.eth.account.from_key(priv_key)
    pub_key = wallet.address
    
    print(f"Approving contracts from wallet: {pub_key}")
    
    # ERC20 ABI for approve
    erc20_approve_abi = [
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
    erc1155_set_approval_abi = [
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
    
    ctf_address = "0x4D97DCd97eC945f40cF65F87097ACe5EA0476045"
    usdc_address = "0x2791Bca1f2de4661ED88A30C99A7a9449Aa84174"
    
    usdc_contract = web3.eth.contract(
        address=Web3.to_checksum_address(usdc_address),
        abi=erc20_approve_abi
    )
    ctf_contract = web3.eth.contract(
        address=Web3.to_checksum_address(ctf_address),
        abi=erc1155_set_approval_abi
    )
    
    # Polymarket contract addresses to approve
    polymarket_addresses = [
        '0x4bFb41d5B3570DeFd03C39a9A4D8dE6Bd8B8982E',  # CTF Exchange
        '0xC5d563A36AE78145C45a50134d48A1215220f80a',  # Neg Risk CTF Exchange
        '0xd91E80cF2E7be2e162c6513ceD06f1dD0dA35296',  # Neg Risk Adapter
    ]
    
    for contract_addr in polymarket_addresses:
        contract_addr_checksum = Web3.to_checksum_address(contract_addr)
        print(f"\nApproving contracts for: {contract_addr}")
        
        # 1. Approve USDC
        try:
            nonce = web3.eth.get_transaction_count(pub_key)
            raw_usdc_txn = usdc_contract.functions.approve(
                contract_addr_checksum,
                int(MAX_INT, 0)
            ).build_transaction({
                "chainId": 137,
                "from": pub_key,
                "nonce": nonce,
                "gasPrice": web3.eth.gas_price,
            })
            
            # Estimate gas
            try:
                gas_estimate = web3.eth.estimate_gas(raw_usdc_txn)
                raw_usdc_txn['gas'] = int(gas_estimate * 1.2)
            except:
                raw_usdc_txn['gas'] = 100000
            
            signed_usdc_txn = web3.eth.account.sign_transaction(raw_usdc_txn, private_key=priv_key)
            tx_hash = web3.eth.send_raw_transaction(signed_usdc_txn.raw_transaction)
            usdc_tx_receipt = web3.eth.wait_for_transaction_receipt(tx_hash, timeout=600)
            
            if usdc_tx_receipt.status == 1:
                print(f'  ✅ USDC approval successful: {tx_hash.hex()}')
            else:
                print(f'  ❌ USDC approval failed: {tx_hash.hex()}')
        except Exception as e:
            print(f'  ❌ USDC approval error: {e}')
            continue
        
        time.sleep(1)
        
        # 2. Approve Conditional Tokens (ERC1155)
        try:
            nonce = web3.eth.get_transaction_count(pub_key)
            raw_ctf_txn = ctf_contract.functions.setApprovalForAll(
                contract_addr_checksum,
                True
            ).build_transaction({
                "chainId": 137,
                "from": pub_key,
                "nonce": nonce,
                "gasPrice": web3.eth.gas_price,
            })
            
            # Estimate gas
            try:
                gas_estimate = web3.eth.estimate_gas(raw_ctf_txn)
                raw_ctf_txn['gas'] = int(gas_estimate * 1.2)
            except:
                raw_ctf_txn['gas'] = 100000
            
            signed_ctf_txn = web3.eth.account.sign_transaction(raw_ctf_txn, private_key=priv_key)
            tx_hash = web3.eth.send_raw_transaction(signed_ctf_txn.raw_transaction)
            ctf_tx_receipt = web3.eth.wait_for_transaction_receipt(tx_hash, timeout=600)
            
            if ctf_tx_receipt.status == 1:
                print(f'  ✅ Conditional Tokens approval successful: {tx_hash.hex()}')
            else:
                print(f'  ❌ Conditional Tokens approval failed: {tx_hash.hex()}')
        except Exception as e:
            print(f'  ❌ Conditional Tokens approval error: {e}')
            continue
        
        time.sleep(1)
    
    print(f"\n✅ Approval process complete!")
    
    
def market_action( marketId, action, price, size ):
    order_args = OrderArgs(
        price=price,
        size=size,
        side=action,
        token_id=marketId,
    )
    signed_order = get_clob_client().create_order(order_args)
    
    try:
        resp = get_clob_client().post_order(signed_order)
        print(resp)
    except Exception as ex:
        print(ex)
        pass
    
    
def get_position(marketId):
    client = get_clob_client()
    position_res = client.get_balance_allowance(
        BalanceAllowanceParams(
            asset_type=AssetType.CONDITIONAL,
            token_id=marketId
        )
    )
    orderBook = client.get_order_book(marketId)
    price = float(orderBook.bids[-1].price)
    shares = int(position_res['balance']) / 1e6
    return shares * price