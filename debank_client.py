"""
DeBank OpenAPI client with rate limiting.
"""
import time
import threading
import requests
from typing import Dict, List, Optional, Any
from dataclasses import dataclass
from config import (
    DEBANK_API_BASE_URL,
    DEBANK_API_KEY,
    RATE_LIMIT_PER_SECOND,
    REQUEST_TIMEOUT,
    MAX_RETRIES,
    RETRY_DELAY,
    SUPPORTED_CHAIN_IDS,
)


@dataclass
class Token:
    """Token data structure."""
    chain: str
    symbol: str
    name: str
    address: str
    decimals: int
    price: float
    amount: float
    raw_amount: int
    value_usd: float
    logo_url: str
    is_verified: bool
    is_core: bool

    @classmethod
    def from_api_response(cls, data: Dict[str, Any], chain: str) -> "Token":
        """Create Token from API response."""
        price = data.get("price", 0) or 0
        amount = data.get("amount", 0) or 0
        return cls(
            chain=chain,
            symbol=data.get("symbol", ""),
            name=data.get("name", ""),
            address=data.get("id", ""),
            decimals=data.get("decimals", 18),
            price=price,
            amount=amount,
            raw_amount=data.get("raw_amount", 0),
            value_usd=price * amount,
            logo_url=data.get("logo_url", ""),
            is_verified=data.get("is_verified", False),
            is_core=data.get("is_core", False),
        )


class RateLimiter:
    """Thread-safe rate limiter."""

    def __init__(self, rate_per_second: int):
        self.rate = rate_per_second
        self.interval = 1.0 / rate_per_second
        self.lock = threading.Lock()
        self.last_request_time = 0.0

    def acquire(self):
        """Wait until we can make a request."""
        with self.lock:
            now = time.time()
            time_since_last = now - self.last_request_time
            if time_since_last < self.interval:
                sleep_time = self.interval - time_since_last
                time.sleep(sleep_time)
            self.last_request_time = time.time()


class DeBankClient:
    """DeBank OpenAPI client."""

    def __init__(self, api_key: Optional[str] = None):
        self.api_key = api_key or DEBANK_API_KEY
        if not self.api_key:
            raise ValueError("DeBank API key is required. Set DEBANK_API_KEY environment variable.")

        self.base_url = DEBANK_API_BASE_URL
        self.rate_limiter = RateLimiter(RATE_LIMIT_PER_SECOND)
        self.session = requests.Session()
        self.session.headers.update({
            "Accept": "application/json",
            "AccessKey": self.api_key,
        })

        # Statistics
        self.request_count = 0
        self.error_count = 0
        self._stats_lock = threading.Lock()

    def _make_request(
        self,
        endpoint: str,
        params: Optional[Dict[str, Any]] = None,
        retries: int = MAX_RETRIES,
    ) -> Optional[Any]:
        """Make an API request with rate limiting and retries."""
        url = f"{self.base_url}{endpoint}"

        for attempt in range(retries):
            self.rate_limiter.acquire()

            try:
                with self._stats_lock:
                    self.request_count += 1

                response = self.session.get(
                    url,
                    params=params,
                    timeout=REQUEST_TIMEOUT,
                )
                response.raise_for_status()
                return response.json()

            except requests.exceptions.HTTPError as e:
                if response.status_code == 429:  # Rate limited
                    wait_time = RETRY_DELAY * (2 ** attempt)
                    time.sleep(wait_time)
                    continue
                elif response.status_code == 400:
                    # Bad request - likely invalid address
                    with self._stats_lock:
                        self.error_count += 1
                    return None
                else:
                    with self._stats_lock:
                        self.error_count += 1
                    if attempt < retries - 1:
                        time.sleep(RETRY_DELAY)
                        continue
                    raise

            except requests.exceptions.RequestException as e:
                with self._stats_lock:
                    self.error_count += 1
                if attempt < retries - 1:
                    time.sleep(RETRY_DELAY * (attempt + 1))
                    continue
                raise

        return None

    def get_used_chains(self, address: str) -> List[str]:
        """
        Get list of chains where the address has activity.

        Args:
            address: Ethereum address (0x...)

        Returns:
            List of chain IDs (e.g., ['eth', 'bsc', 'matic'])
        """
        response = self._make_request(
            "/user/used_chain_list",
            params={"id": address.lower()},
        )

        if response is None:
            return []

        # Filter to only supported chains
        used_chains = []
        for chain in response:
            chain_id = chain.get("id") if isinstance(chain, dict) else chain
            if chain_id in SUPPORTED_CHAIN_IDS:
                used_chains.append(chain_id)

        return used_chains

    def get_token_list(
        self,
        address: str,
        chain: str,
        is_all: bool = False,
    ) -> List[Token]:
        """
        Get token list for an address on a specific chain.

        Args:
            address: Ethereum address (0x...)
            chain: Chain ID (e.g., 'eth', 'bsc')
            is_all: If True, include all tokens; if False, only verified tokens

        Returns:
            List of Token objects
        """
        response = self._make_request(
            "/user/token_list",
            params={
                "id": address.lower(),
                "chain_id": chain,
                "is_all": str(is_all).lower(),
            },
        )

        if response is None:
            return []

        tokens = []
        for token_data in response:
            token = Token.from_api_response(token_data, chain)
            tokens.append(token)

        return tokens

    def get_all_tokens_for_address(
        self,
        address: str,
        chains: Optional[List[str]] = None,
        filter_dust: bool = True,
        min_value: float = 0.01,
    ) -> Dict[str, List[Token]]:
        """
        Get all tokens for an address across specified chains.

        Args:
            address: Ethereum address (0x...)
            chains: List of chain IDs to query. If None, auto-detect using used_chain_list
            filter_dust: Whether to filter out tokens worth less than min_value
            min_value: Minimum token value in USD

        Returns:
            Dictionary mapping chain ID to list of tokens
        """
        # If no chains specified, get the chains where address is active
        if chains is None:
            chains = self.get_used_chains(address)

        if not chains:
            return {}

        result: Dict[str, List[Token]] = {}

        for chain in chains:
            tokens = self.get_token_list(address, chain, is_all=True)

            if filter_dust:
                tokens = [t for t in tokens if t.value_usd >= min_value]

            if tokens:
                result[chain] = tokens

        return result

    def get_stats(self) -> Dict[str, int]:
        """Get request statistics."""
        with self._stats_lock:
            return {
                "request_count": self.request_count,
                "error_count": self.error_count,
            }

    def close(self):
        """Close the session."""
        self.session.close()

    def __enter__(self):
        return self

    def __exit__(self, exc_type, exc_val, exc_tb):
        self.close()
