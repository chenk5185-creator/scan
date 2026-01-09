"""
Configuration for multi-chain wallet scanner.
"""
import os
from typing import Dict, List

# DeBank API Configuration
DEBANK_API_BASE_URL = "https://pro-openapi.debank.com/v1"
DEBANK_API_KEY = os.getenv("DEBANK_API_KEY", "")

# Rate limiting
RATE_LIMIT_PER_SECOND = 3
MAX_WORKERS = 3

# Minimum token value filter (USD)
MIN_TOKEN_VALUE_USD = 0.01

# Supported chains with their DeBank chain IDs
SUPPORTED_CHAINS: Dict[str, str] = {
    "eth": "Ethereum",
    "bsc": "BSC",
    "matic": "Polygon",
    "arb": "Arbitrum",
    "op": "Optimism",
    "base": "Base",
    "blast": "Blast",
    "era": "zkSync Era",
    "linea": "Linea",
    "merlin": "Merlin",
}

# Chain IDs list for filtering
SUPPORTED_CHAIN_IDS: List[str] = list(SUPPORTED_CHAINS.keys())

# Excel Sheet Configuration
# 11 chain sheets + Summary + All Tokens + Statistics
EXCEL_SHEETS = [
    "Summary",           # Overall summary statistics
    "All_Tokens",        # All tokens across all chains
    "Statistics",        # Detailed statistics
    "Ethereum",          # eth
    "BSC",               # bsc
    "Polygon",           # matic
    "Arbitrum",          # arb
    "Optimism",          # op
    "Base",              # base
    "Blast",             # blast
    "zkSync_Era",        # era
    "Linea",             # linea
    "Merlin",            # merlin
    "Errors",            # Failed addresses
]

# Chain ID to Sheet name mapping
CHAIN_TO_SHEET: Dict[str, str] = {
    "eth": "Ethereum",
    "bsc": "BSC",
    "matic": "Polygon",
    "arb": "Arbitrum",
    "op": "Optimism",
    "base": "Base",
    "blast": "Blast",
    "era": "zkSync_Era",
    "linea": "Linea",
    "merlin": "Merlin",
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
