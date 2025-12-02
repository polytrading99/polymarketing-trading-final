from dotenv import load_dotenv          # Environment variable management
import os                           # Operating system interface

# Polymarket API client libraries
from py_clob_client.client import ClobClient
from py_clob_client.clob_types import OrderArgs, BalanceAllowanceParams, AssetType, PartialCreateOrderOptions
from py_clob_client.constants import POLYGON

# Web3 libraries for blockchain interaction
from web3 import Web3
from web3.middleware import ExtraDataToPOAMiddleware
from eth_account import Account

import requests                     # HTTP requests
import pandas as pd                 # Data analysis
import json                         # JSON processing
import subprocess                   # For calling external processes

from py_clob_client.clob_types import OpenOrderParams

# Smart contract ABIs
from poly_data.abis import NegRiskAdapterABI, ConditionalTokenABI, erc20_abi

# Load environment variables
load_dotenv()


class PolymarketClient:
    """
    Client for interacting with Polymarket's API and smart contracts.
    
    This class provides methods for:
    - Creating and managing orders
    - Querying order book data
    - Checking balances and positions
    - Merging positions
    
    The client connects to both the Polymarket API and the Polygon blockchain.
    """
    
    def __init__(self, pk='default') -> None:
        """
        Initialize the Polymarket client with API and blockchain connections.
        
        Args:
            pk (str, optional): Private key identifier, defaults to 'default'
        """
        host="https://clob.polymarket.com"

        # Get credentials from environment variables
        key=os.getenv("PK")
        browser_address = os.getenv("BROWSER_ADDRESS")

        # Validate credentials are set
        if not key:
            raise ValueError("PK (private key) environment variable is not set! Bot cannot authenticate.")
        if not browser_address:
            raise ValueError("BROWSER_ADDRESS environment variable is not set! Bot cannot identify wallet.")
        
        # Validate and clean private key format
        key = key.strip()
        # Remove 0x prefix if present (ClobClient expects key without 0x)
        if key.startswith('0x') or key.startswith('0X'):
            key = key[2:]
            print(f"WARNING: Removed '0x' prefix from private key")
        
        # Validate private key length (should be 64 hex characters)
        if len(key) != 64:
            raise ValueError(
                f"Invalid private key length! Expected 64 hex characters (without 0x), "
                f"got {len(key)}. Check your PK in .env file."
            )
        
        # Validate it's hex
        try:
            int(key, 16)
        except ValueError:
            raise ValueError(
                f"Invalid private key format! Must be hexadecimal (0-9, a-f). "
                f"Check your PK in .env file."
            )
        
        # Clean up browser_address - remove any duplicates or extra characters
        browser_address = browser_address.strip()
        # If address appears duplicated, take the first occurrence
        if browser_address.startswith('0x') and len(browser_address) > 42:
            # Check if it's duplicated (should be 42 chars: 0x + 40 hex)
            expected_length = 42
            if len(browser_address) >= expected_length * 2:
                # Likely duplicated, take first part
                browser_address = browser_address[:expected_length]
                print(f"WARNING: BROWSER_ADDRESS appears duplicated, using first part only")
        
        # Validate address format
        if not browser_address.startswith('0x'):
            raise ValueError(f"BROWSER_ADDRESS must start with '0x'. Got: {browser_address[:20]}...")
        if len(browser_address) != 42:
            raise ValueError(f"BROWSER_ADDRESS must be 42 characters (0x + 40 hex). Got {len(browser_address)} characters: {browser_address[:20]}...")
        
        print("Initializing Polymarket client...")
        print(f"Wallet address: {browser_address[:10]}...{browser_address[-8:]}")
        chain_id=POLYGON
        
        try:
            self.browser_wallet=Web3.to_checksum_address(browser_address)
        except Exception as e:
            raise ValueError(f"Invalid BROWSER_ADDRESS format: {e}. Address: {browser_address[:20]}...")

        # Initialize the Polymarket API client
        self.client = ClobClient(
            host=host,
            key=key,
            chain_id=chain_id,
            funder=self.browser_wallet,
            signature_type=2
        )

        # Set up API credentials
        self.creds = self.client.create_or_derive_api_creds()
        self.client.set_api_creds(creds=self.creds)
        
        # Initialize Web3 connection to Polygon
        web3 = Web3(Web3.HTTPProvider("https://polygon-rpc.com"))
        web3.middleware_onion.inject(ExtraDataToPOAMiddleware, layer=0)
        
        # Set up USDC contract for balance checks
        self.usdc_contract = web3.eth.contract(
            address="0x2791Bca1f2de4661ED88A30C99A7a9449Aa84174", 
            abi=erc20_abi
        )

        # Store key contract addresses
        self.addresses = {
            'neg_risk_adapter': '0xd91E80cF2E7be2e162c6513ceD06f1dD0dA35296',
            'collateral': '0x2791Bca1f2de4661ED88A30C99A7a9449Aa84174',
            'conditional_tokens': '0x4D97DCd97eC945f40cF65F87097ACe5EA0476045'
        }

        # Initialize contract interfaces
        self.neg_risk_adapter = web3.eth.contract(
            address=self.addresses['neg_risk_adapter'], 
            abi=NegRiskAdapterABI
        )

        self.conditional_tokens = web3.eth.contract(
            address=self.addresses['conditional_tokens'], 
            abi=ConditionalTokenABI
        )

        self.web3 = web3

    
    def create_order(self, marketId, action, price, size, neg_risk=False):
        """
        Create and submit a new order to the Polymarket order book.
        
        Args:
            marketId (str): ID of the market token to trade
            action (str): "BUY" or "SELL"
            price (float): Order price (0-1 range for prediction markets)
            size (float): Order size in USDC
            neg_risk (bool, optional): Whether this is a negative risk market. Defaults to False.
            
        Returns:
            dict: Response from the API containing order details, or empty dict on error
        """
        # Create order parameters
        order_args = OrderArgs(
            token_id=str(marketId),
            price=price,
            size=size,
            side=action
        )

        signed_order = None

        # Handle regular vs negative risk markets differently
        if neg_risk == False:
            signed_order = self.client.create_order(order_args)
        else:
            signed_order = self.client.create_order(order_args, options=PartialCreateOrderOptions(neg_risk=True))
            
        try:
            # Submit the signed order to the API
            resp = self.client.post_order(signed_order)
            return resp
        except Exception as ex:
            error_str = str(ex)
            print(f"ERROR in create_order: {error_str}")
            
            # Provide helpful diagnostics for invalid signature
            if "invalid signature" in error_str.lower():
                print(f"\n{'='*60}")
                print(f"INVALID SIGNATURE - Detailed Diagnostics:")
                print(f"  Token ID: {str(marketId)}")
                print(f"  Price: {price}")
                print(f"  Size: {size}")
                print(f"  Side: {action}")
                print(f"  Neg Risk: {neg_risk}")
                print(f"  Wallet: {self.browser_wallet}")
                print(f"\n  Most common cause: Wallet hasn't done manual trade on Polymarket")
                print(f"  Solution:")
                print(f"    1. Go to https://polymarket.com")
                print(f"    2. Connect wallet: {self.browser_wallet}")
                print(f"    3. Make ONE small manual trade (buy or sell any market)")
                print(f"    4. Wait for transaction to confirm")
                print(f"    5. Then try again")
                print(f"{'='*60}\n")
            
            # Re-raise the exception so caller can handle it
            raise

    def get_order_book(self, market):
        """
        Get the current order book for a specific market.
        
        Args:
            market (str): Market ID to query
            
        Returns:
            tuple: (bids_df, asks_df) - DataFrames containing bid and ask orders
        """
        orderBook = self.client.get_order_book(market)
        return pd.DataFrame(orderBook.bids).astype(float), pd.DataFrame(orderBook.asks).astype(float)


    def get_usdc_balance(self):
        """
        Get the USDC balance of the connected wallet.
        Checks both USDC.e (bridged) and native USDC contracts.
        
        Returns:
            float: USDC balance in decimal format (sum of both contracts)
        """
        # Check USDC.e (bridged USDC) - the one Polymarket typically uses
        balance_usdce = self.usdc_contract.functions.balanceOf(self.browser_wallet).call() / 10**6
        
        # Also check native USDC on Polygon
        native_usdc_address = "0x3c499c542cEF5E3811e1192ce70d8cC03d5c3359"
        try:
            native_usdc_contract = self.web3.eth.contract(
                address=native_usdc_address,
                abi=erc20_abi
            )
            balance_native = native_usdc_contract.functions.balanceOf(self.browser_wallet).call() / 10**6
        except:
            balance_native = 0.0
        
        total_balance = balance_usdce + balance_native
        return total_balance
     
    def get_pos_balance(self):
        """
        Get the total value of all positions for the connected wallet.
        
        Returns:
            float: Total position value in USDC
        """
        res = requests.get(f'https://data-api.polymarket.com/value?user={self.browser_wallet}')
        data = res.json()
        
        # Handle different response formats
        if isinstance(data, dict):
            if 'value' in data:
                return float(data['value'])
            else:
                # Try other possible keys
                for key in ['total', 'portfolio_value', 'balance']:
                    if key in data:
                        return float(data[key])
                return 0.0
        elif isinstance(data, list) and len(data) > 0:
            # If it's a list, try to extract value from first item
            if isinstance(data[0], dict) and 'value' in data[0]:
                return float(data[0]['value'])
            return 0.0
        else:
            return 0.0

    def get_total_balance(self):
        """
        Get the combined value of USDC balance and all positions.
        
        Returns:
            float: Total account value in USDC
        """
        return self.get_usdc_balance() + self.get_pos_balance()

    def get_all_positions(self):
        """
        Get all positions for the connected wallet across all markets.
        
        Returns:
            DataFrame: All positions with details like market, size, avgPrice
        """
        res = requests.get(f'https://data-api.polymarket.com/positions?user={self.browser_wallet}')
        data = res.json()
        
        # Handle different response formats
        if isinstance(data, list):
            # Expected format: list of position objects
            if len(data) == 0:
                return pd.DataFrame()
            return pd.DataFrame(data)
        elif isinstance(data, dict):
            # If it's a dict, try to find positions key
            if 'positions' in data:
                return pd.DataFrame(data['positions'])
            elif 'data' in data:
                return pd.DataFrame(data['data'])
            else:
                # If dict has position-like structure, try to convert
                return pd.DataFrame([data])
        else:
            return pd.DataFrame()
    
    def get_raw_position(self, tokenId):
        """
        Get the raw token balance for a specific market outcome token.
        
        Args:
            tokenId (int): Token ID to query
            
        Returns:
            int: Raw token amount (before decimal conversion)
        """
        return int(self.conditional_tokens.functions.balanceOf(self.browser_wallet, int(tokenId)).call())

    def get_position(self, tokenId):
        """
        Get both raw and formatted position size for a token.
        
        Args:
            tokenId (int): Token ID to query
            
        Returns:
            tuple: (raw_position, shares) - Raw token amount and decimal shares
                   Shares less than 1 are treated as 0 to avoid dust amounts
        """
        raw_position = self.get_raw_position(tokenId)
        shares = float(raw_position / 1e6)

        # Ignore very small positions (dust)
        if shares < 1:
            shares = 0

        return raw_position, shares
    
    def get_all_orders(self):
        """
        Get all open orders for the connected wallet.
        
        Returns:
            DataFrame: All open orders with their details
        """
        orders_df = pd.DataFrame(self.client.get_orders())

        # Convert numeric columns to float
        for col in ['original_size', 'size_matched', 'price']:
            if col in orders_df.columns:
                orders_df[col] = orders_df[col].astype(float)

        return orders_df
    
    def get_market_orders(self, market):
        """
        Get all open orders for a specific market.
        
        Args:
            market (str): Market ID to query
            
        Returns:
            DataFrame: Open orders for the specified market
        """
        orders_df = pd.DataFrame(self.client.get_orders(OpenOrderParams(
            market=market,
        )))

        # Convert numeric columns to float
        for col in ['original_size', 'size_matched', 'price']:
            if col in orders_df.columns:
                orders_df[col] = orders_df[col].astype(float)

        return orders_df
    

    def cancel_all_asset(self, asset_id):
        """
        Cancel all orders for a specific asset token.
        
        Args:
            asset_id (str): Asset token ID
        """
        self.client.cancel_market_orders(asset_id=str(asset_id))


    
    def cancel_all_market(self, marketId):
        """
        Cancel all orders in a specific market.
        
        Args:
            marketId (str): Market ID
        """
        self.client.cancel_market_orders(market=marketId)

    
    def merge_positions(self, amount_to_merge, condition_id, is_neg_risk_market):
        """
        Merge positions in a market to recover collateral.
        
        This function calls the external poly_merger Node.js script to execute
        the merge operation on-chain. When you hold both YES and NO positions
        in the same market, merging them recovers your USDC.
        
        Args:
            amount_to_merge (int): Raw token amount to merge (before decimal conversion)
            condition_id (str): Market condition ID
            is_neg_risk_market (bool): Whether this is a negative risk market
            
        Returns:
            str: Transaction hash or output from the merge script
            
        Raises:
            Exception: If the merge operation fails
        """
        amount_to_merge_str = str(amount_to_merge)

        # Prepare the command to run the JavaScript script
        node_command = f'node poly_merger/merge.js {amount_to_merge_str} {condition_id} {"true" if is_neg_risk_market else "false"}'
        print(node_command)

        # Run the command and capture the output
        result = subprocess.run(node_command, shell=True, capture_output=True, text=True)
        
        # Check if there was an error
        if result.returncode != 0:
            print("Error:", result.stderr)
            raise Exception(f"Error in merging positions: {result.stderr}")
        
        print("Done merging")

        # Return the transaction hash or output
        return result.stdout