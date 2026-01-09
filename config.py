"""
Configuration for multi-chain wallet scanner using Moralis API.
"""
import os
from typing import Dict, List

# Moralis API Configuration
MORALIS_API_BASE_URL = "https://deep-index.moralis.io/api/v2.2"
MORALIS_API_KEY = os.getenv("MORALIS_API_KEY", "")

# Rate limiting (Moralis free tier: 25 req/sec)
RATE_LIMIT_PER_SECOND = 10
MAX_WORKERS = 3

# Minimum token value filter (USD)
MIN_TOKEN_VALUE_USD = 0.01

# Supported chains with Moralis chain identifiers
# Format: {moralis_chain_id: display_name}
SUPPORTED_CHAINS: Dict[str, str] = {
    "eth": "Ethereum",
    "bsc": "BSC",
    "polygon": "Polygon",
    "arbitrum": "Arbitrum",
    "optimism": "Optimism",
    "base": "Base",
    "linea": "Linea",
    "zksync": "zkSync Era",
}

# Moralis chain hex IDs for API calls
CHAIN_HEX_IDS: Dict[str, str] = {
    "eth": "0x1",
    "bsc": "0x38",
    "polygon": "0x89",
    "arbitrum": "0xa4b1",
    "optimism": "0xa",
    "base": "0x2105",
    "linea": "0xe708",
    "zksync": "0x144",
}

# Chain IDs list for iteration
SUPPORTED_CHAIN_IDS: List[str] = list(SUPPORTED_CHAINS.keys())

# Excel Sheet Configuration
# 8 chain sheets + Summary + All Tokens + Statistics + Errors = 12 sheets
EXCEL_SHEETS = [
    "Summary",           # Overall summary statistics
    "All_Tokens",        # All tokens across all chains
    "Statistics",        # Detailed statistics
    "Ethereum",          # eth
    "BSC",               # bsc
    "Polygon",           # polygon
    "Arbitrum",          # arbitrum
    "Optimism",          # optimism
    "Base",              # base
    "Linea",             # linea
    "zkSync_Era",        # zksync
    "Errors",            # Failed addresses
]

# Chain ID to Sheet name mapping
CHAIN_TO_SHEET: Dict[str, str] = {
    "eth": "Ethereum",
    "bsc": "BSC",
    "polygon": "Polygon",
    "arbitrum": "Arbitrum",
    "optimism": "Optimism",
    "base": "Base",
    "linea": "Linea",
    "zksync": "zkSync_Era",
}

# Native token symbols per chain
NATIVE_TOKENS: Dict[str, Dict[str, str]] = {
    "eth": {"symbol": "ETH", "name": "Ethereum", "decimals": 18},
    "bsc": {"symbol": "BNB", "name": "BNB", "decimals": 18},
    "polygon": {"symbol": "MATIC", "name": "Polygon", "decimals": 18},
    "arbitrum": {"symbol": "ETH", "name": "Ethereum", "decimals": 18},
    "optimism": {"symbol": "ETH", "name": "Ethereum", "decimals": 18},
    "base": {"symbol": "ETH", "name": "Ethereum", "decimals": 18},
    "linea": {"symbol": "ETH", "name": "Ethereum", "decimals": 18},
    "zksync": {"symbol": "ETH", "name": "Ethereum", "decimals": 18},
}

# Request timeout (seconds)
REQUEST_TIMEOUT = 30

# Retry configuration
MAX_RETRIES = 3
RETRY_DELAY = 1.0  # seconds

# Output file
DEFAULT_OUTPUT_FILE = "wallet_scan_report.xlsx"

# Input file for wallet addresses
DEFAULT_INPUT_FILE = "wallets.txt"

# Batch size for processing
BATCH_SIZE = 100
