"""
Moralis API client with rate limiting for multi-chain wallet scanning.
"""
import time
import threading
import requests
from typing import Dict, List, Optional, Any
from dataclasses import dataclass
from config import (
    MORALIS_API_BASE_URL,
    MORALIS_API_KEY,
    RATE_LIMIT_PER_SECOND,
    REQUEST_TIMEOUT,
    MAX_RETRIES,
    RETRY_DELAY,
    SUPPORTED_CHAIN_IDS,
    CHAIN_HEX_IDS,
    NATIVE_TOKENS,
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
    is_native: bool

    @classmethod
    def from_erc20_response(cls, data: Dict[str, Any], chain: str) -> "Token":
        """Create Token from Moralis ERC20 balance response."""
        decimals = int(data.get("decimals", 18))
        raw_amount = int(data.get("balance", 0))
        amount = raw_amount / (10 ** decimals) if decimals > 0 else raw_amount

        # Get USD price if available
        price = 0.0
        if data.get("usd_price"):
            price = float(data.get("usd_price", 0))

        value_usd = price * amount

        return cls(
            chain=chain,
            symbol=data.get("symbol", ""),
            name=data.get("name", ""),
            address=data.get("token_address", ""),
            decimals=decimals,
            price=price,
            amount=amount,
            raw_amount=raw_amount,
            value_usd=value_usd,
            logo_url=data.get("logo", "") or data.get("thumbnail", "") or "",
            is_verified=data.get("verified_contract", False),
            is_native=False,
        )

    @classmethod
    def from_native_balance(cls, balance: str, chain: str, price: float = 0.0) -> "Token":
        """Create Token from native balance."""
        native_info = NATIVE_TOKENS.get(chain, {"symbol": "ETH", "name": "Native", "decimals": 18})
        decimals = native_info["decimals"]
        raw_amount = int(balance)
        amount = raw_amount / (10 ** decimals)
        value_usd = price * amount

        return cls(
            chain=chain,
            symbol=native_info["symbol"],
            name=native_info["name"],
            address="0x0000000000000000000000000000000000000000",
            decimals=decimals,
            price=price,
            amount=amount,
            raw_amount=raw_amount,
            value_usd=value_usd,
            logo_url="",
            is_verified=True,
            is_native=True,
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


class MoralisClient:
    """Moralis API client for wallet scanning."""

    def __init__(self, api_key: Optional[str] = None):
        self.api_key = api_key or MORALIS_API_KEY
        if not self.api_key:
            raise ValueError("Moralis API key is required. Set MORALIS_API_KEY environment variable.")

        self.base_url = MORALIS_API_BASE_URL
        self.rate_limiter = RateLimiter(RATE_LIMIT_PER_SECOND)
        self.session = requests.Session()
        self.session.headers.update({
            "Accept": "application/json",
            "X-API-Key": self.api_key,
        })

        # Statistics
        self.request_count = 0
        self.error_count = 0
        self._stats_lock = threading.Lock()

        # Cache for native token prices
        self._native_prices: Dict[str, float] = {}
        self._prices_lock = threading.Lock()

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
                elif response.status_code in (400, 404):
                    # Bad request or not found - likely invalid address
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

    def get_native_balance(self, address: str, chain: str) -> Optional[str]:
        """
        Get native token balance for an address on a specific chain.

        Args:
            address: Ethereum address (0x...)
            chain: Chain ID (e.g., 'eth', 'bsc')

        Returns:
            Balance in wei as string, or None on error
        """
        chain_hex = CHAIN_HEX_IDS.get(chain)
        if not chain_hex:
            return None

        response = self._make_request(
            f"/{address}/balance",
            params={"chain": chain_hex},
        )

        if response and "balance" in response:
            return response["balance"]
        return None

    def get_native_price(self, chain: str) -> float:
        """Get native token price in USD."""
        with self._prices_lock:
            if chain in self._native_prices:
                return self._native_prices[chain]

        chain_hex = CHAIN_HEX_IDS.get(chain)
        if not chain_hex:
            return 0.0

        # Use wrapped native token address to get price
        wrapped_addresses = {
            "eth": "0xC02aaA39b223FE8D0A0e5C4F27eAD9083C756Cc2",  # WETH
            "bsc": "0xbb4CdB9CBd36B01bD1cBaEBF2De08d9173bc095c",  # WBNB
            "polygon": "0x0d500B1d8E8eF31E21C99d1Db9A6444d3ADf1270",  # WMATIC
            "arbitrum": "0x82aF49447D8a07e3bd95BD0d56f35241523fBab1",  # WETH
            "optimism": "0x4200000000000000000000000000000000000006",  # WETH
            "base": "0x4200000000000000000000000000000000000006",  # WETH
            "linea": "0xe5D7C2a44FfDDf6b295A15c148167daaAf5Cf34f",  # WETH
            "zksync": "0x5AEa5775959fBC2557Cc8789bC1bf90A239D9a91",  # WETH
        }

        wrapped_addr = wrapped_addresses.get(chain)
        if not wrapped_addr:
            return 0.0

        response = self._make_request(
            f"/erc20/{wrapped_addr}/price",
            params={"chain": chain_hex},
        )

        price = 0.0
        if response and "usdPrice" in response:
            price = float(response["usdPrice"])
            with self._prices_lock:
                self._native_prices[chain] = price

        return price

    def get_erc20_balances(
        self,
        address: str,
        chain: str,
    ) -> List[Token]:
        """
        Get all ERC20 token balances for an address on a specific chain.

        Args:
            address: Ethereum address (0x...)
            chain: Chain ID (e.g., 'eth', 'bsc')

        Returns:
            List of Token objects
        """
        chain_hex = CHAIN_HEX_IDS.get(chain)
        if not chain_hex:
            return []

        tokens = []
        cursor = None

        while True:
            params = {
                "chain": chain_hex,
                "exclude_spam": "true",
            }
            if cursor:
                params["cursor"] = cursor

            response = self._make_request(
                f"/{address}/erc20",
                params=params,
            )

            if response is None:
                break

            for token_data in response.get("result", []):
                token = Token.from_erc20_response(token_data, chain)
                if token.amount > 0:
                    tokens.append(token)

            cursor = response.get("cursor")
            if not cursor:
                break

        return tokens

    def get_all_tokens_for_address(
        self,
        address: str,
        chains: Optional[List[str]] = None,
        filter_dust: bool = True,
        min_value: float = 0.01,
        include_native: bool = True,
    ) -> Dict[str, List[Token]]:
        """
        Get all tokens for an address across specified chains.

        Args:
            address: Ethereum address (0x...)
            chains: List of chain IDs to query. If None, query all supported chains
            filter_dust: Whether to filter out tokens worth less than min_value
            min_value: Minimum token value in USD
            include_native: Whether to include native token balance

        Returns:
            Dictionary mapping chain ID to list of tokens
        """
        if chains is None:
            chains = SUPPORTED_CHAIN_IDS

        result: Dict[str, List[Token]] = {}

        for chain in chains:
            chain_tokens = []

            # Get native balance
            if include_native:
                native_balance = self.get_native_balance(address, chain)
                if native_balance and int(native_balance) > 0:
                    native_price = self.get_native_price(chain)
                    native_token = Token.from_native_balance(native_balance, chain, native_price)
                    if not filter_dust or native_token.value_usd >= min_value:
                        chain_tokens.append(native_token)

            # Get ERC20 tokens
            erc20_tokens = self.get_erc20_balances(address, chain)

            for token in erc20_tokens:
                if not filter_dust or token.value_usd >= min_value:
                    chain_tokens.append(token)

            if chain_tokens:
                result[chain] = chain_tokens

        return result

    def get_active_chains(self, address: str) -> List[str]:
        """
        Get list of chains where the address has any balance.
        This is a quick check to optimize full scans.

        Args:
            address: Ethereum address (0x...)

        Returns:
            List of chain IDs with activity
        """
        active_chains = []

        for chain in SUPPORTED_CHAIN_IDS:
            # Quick check: just look for native balance
            balance = self.get_native_balance(address, chain)
            if balance and int(balance) > 0:
                active_chains.append(chain)
                continue

            # Check for any ERC20 tokens (limited query)
            chain_hex = CHAIN_HEX_IDS.get(chain)
            if chain_hex:
                response = self._make_request(
                    f"/{address}/erc20",
                    params={"chain": chain_hex, "limit": 1},
                )
                if response and response.get("result"):
                    active_chains.append(chain)

        return active_chains

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
