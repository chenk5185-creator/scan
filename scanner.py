"""
Multi-threaded wallet scanner using Moralis API.
"""
import time
import threading
from concurrent.futures import ThreadPoolExecutor, as_completed
from dataclasses import dataclass, field
from typing import Dict, List, Optional, Callable
from queue import Queue
import logging

from moralis_client import MoralisClient, Token
from config import (
    MAX_WORKERS,
    MIN_TOKEN_VALUE_USD,
    SUPPORTED_CHAIN_IDS,
)

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s - %(levelname)s - %(message)s",
)
logger = logging.getLogger(__name__)


@dataclass
class WalletResult:
    """Result for a single wallet scan."""
    address: str
    tokens: Dict[str, List[Token]] = field(default_factory=dict)
    active_chains: List[str] = field(default_factory=list)
    total_value_usd: float = 0.0
    error: Optional[str] = None
    scan_time: float = 0.0

    @property
    def is_success(self) -> bool:
        return self.error is None

    @property
    def token_count(self) -> int:
        return sum(len(tokens) for tokens in self.tokens.values())

    def get_chain_value(self, chain: str) -> float:
        """Get total value for a specific chain."""
        if chain not in self.tokens:
            return 0.0
        return sum(t.value_usd for t in self.tokens[chain])


@dataclass
class ScanProgress:
    """Track scanning progress."""
    total: int = 0
    completed: int = 0
    success: int = 0
    failed: int = 0
    _lock: threading.Lock = field(default_factory=threading.Lock)

    def update(self, success: bool):
        with self._lock:
            self.completed += 1
            if success:
                self.success += 1
            else:
                self.failed += 1

    @property
    def progress_percent(self) -> float:
        if self.total == 0:
            return 0.0
        return (self.completed / self.total) * 100


class WalletScanner:
    """Multi-threaded wallet scanner."""

    def __init__(
        self,
        api_key: Optional[str] = None,
        max_workers: int = MAX_WORKERS,
        min_token_value: float = MIN_TOKEN_VALUE_USD,
        progress_callback: Optional[Callable[[ScanProgress], None]] = None,
    ):
        """
        Initialize the scanner.

        Args:
            api_key: Moralis API key
            max_workers: Number of concurrent workers
            min_token_value: Minimum token value to include (USD)
            progress_callback: Optional callback for progress updates
        """
        self.api_key = api_key
        self.max_workers = max_workers
        self.min_token_value = min_token_value
        self.progress_callback = progress_callback

        # Shared client for rate limiting
        self._client: Optional[MoralisClient] = None
        self._client_lock = threading.Lock()

    def _get_client(self) -> MoralisClient:
        """Get or create the shared client."""
        with self._client_lock:
            if self._client is None:
                self._client = MoralisClient(api_key=self.api_key)
            return self._client

    def _scan_single_wallet(self, address: str) -> WalletResult:
        """
        Scan a single wallet address.

        Args:
            address: Ethereum address to scan

        Returns:
            WalletResult with token data
        """
        start_time = time.time()
        result = WalletResult(address=address)

        try:
            client = self._get_client()

            # Get all tokens across all supported chains
            tokens_by_chain = client.get_all_tokens_for_address(
                address,
                chains=SUPPORTED_CHAIN_IDS,
                filter_dust=True,
                min_value=self.min_token_value,
                include_native=True,
            )

            result.tokens = tokens_by_chain
            result.active_chains = list(tokens_by_chain.keys())

            # Calculate total value
            for chain, tokens in tokens_by_chain.items():
                result.total_value_usd += sum(t.value_usd for t in tokens)

            result.scan_time = time.time() - start_time
            return result

        except Exception as e:
            result.error = str(e)
            result.scan_time = time.time() - start_time
            logger.error(f"Error scanning {address}: {e}")
            return result

    def scan_wallets(
        self,
        addresses: List[str],
        show_progress: bool = True,
    ) -> List[WalletResult]:
        """
        Scan multiple wallet addresses concurrently.

        Args:
            addresses: List of Ethereum addresses to scan
            show_progress: Whether to log progress

        Returns:
            List of WalletResult objects
        """
        # Clean and validate addresses
        clean_addresses = []
        for addr in addresses:
            addr = addr.strip()
            if addr and addr.startswith("0x") and len(addr) == 42:
                clean_addresses.append(addr.lower())
            elif addr:
                logger.warning(f"Invalid address format: {addr}")

        if not clean_addresses:
            logger.warning("No valid addresses to scan")
            return []

        # Initialize progress tracking
        progress = ScanProgress(total=len(clean_addresses))
        results: List[WalletResult] = []
        results_lock = threading.Lock()

        logger.info(f"Starting scan of {len(clean_addresses)} addresses with {self.max_workers} workers")
        start_time = time.time()

        def scan_and_update(address: str) -> WalletResult:
            result = self._scan_single_wallet(address)
            progress.update(result.is_success)

            if show_progress and progress.completed % 10 == 0:
                logger.info(
                    f"Progress: {progress.completed}/{progress.total} "
                    f"({progress.progress_percent:.1f}%) - "
                    f"Success: {progress.success}, Failed: {progress.failed}"
                )

            if self.progress_callback:
                self.progress_callback(progress)

            return result

        # Use thread pool for concurrent scanning
        with ThreadPoolExecutor(max_workers=self.max_workers) as executor:
            future_to_address = {
                executor.submit(scan_and_update, addr): addr
                for addr in clean_addresses
            }

            for future in as_completed(future_to_address):
                address = future_to_address[future]
                try:
                    result = future.result()
                    with results_lock:
                        results.append(result)
                except Exception as e:
                    logger.error(f"Unexpected error for {address}: {e}")
                    with results_lock:
                        results.append(WalletResult(
                            address=address,
                            error=str(e),
                        ))

        elapsed_time = time.time() - start_time
        logger.info(
            f"Scan completed in {elapsed_time:.1f}s - "
            f"Total: {len(results)}, Success: {progress.success}, Failed: {progress.failed}"
        )

        # Get client stats
        if self._client:
            stats = self._client.get_stats()
            logger.info(
                f"API Stats - Requests: {stats['request_count']}, Errors: {stats['error_count']}"
            )

        return results

    def close(self):
        """Close the scanner and release resources."""
        with self._client_lock:
            if self._client:
                self._client.close()
                self._client = None

    def __enter__(self):
        return self

    def __exit__(self, exc_type, exc_val, exc_tb):
        self.close()


def load_addresses_from_file(file_path: str) -> List[str]:
    """
    Load wallet addresses from a text file.

    Args:
        file_path: Path to file containing addresses (one per line)

    Returns:
        List of addresses
    """
    addresses = []
    try:
        with open(file_path, "r") as f:
            for line in f:
                line = line.strip()
                # Skip empty lines and comments
                if line and not line.startswith("#"):
                    addresses.append(line)
        logger.info(f"Loaded {len(addresses)} addresses from {file_path}")
    except FileNotFoundError:
        logger.error(f"File not found: {file_path}")
    except Exception as e:
        logger.error(f"Error reading file {file_path}: {e}")

    return addresses
