"""
Moralis API client with rate limiting for multi-chain wallet scanning.
"""
import time
import threading
import requests
import logging
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

logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)


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
    def from_wallet_token_response(cls, data: Dict[str, Any], chain: str) -> "Token":
        """Create Token from Moralis wallet token balance response (v2.2)."""
        decimals = int(data.get("decimals", 18))

        # Handle balance - can be string or int
        balance_raw = data.get("balance", "0")
        if isinstance(balance_raw, str):
            raw_amount = int(balance_raw) if balance_raw else 0
        else:
            raw_amount = int(balance_raw)

        amount = raw_amount / (10 ** decimals) if decimals > 0 else raw_amount

        # Get USD price - check multiple fields
        price = 0.0
        if data.get("usd_price") is not None:
            price = float(data.get("usd_price", 0))
        elif data.get("usdPrice") is not None:
            price = float(data.get("usdPrice", 0))

        value_usd = price * amount

        # Check if native token
        is_native = data.get("native_token", False) or data.get("nativeToken", False)

        # Get token address
        token_address = data.get("token_address", "") or data.get("tokenAddress", "")
        if is_native:
            token_address = "0x0000000000000000000000000000000000000000"

        return cls(
            chain=chain,
            symbol=data.get("symbol", "") or "UNKNOWN",
            name=data.get("name", "") or "Unknown Token",
            address=token_address,
            decimals=decimals,
            price=price,
            amount=amount,
            raw_amount=raw_amount,
            value_usd=value_usd,
            logo_url=data.get("logo", "") or data.get("thumbnail", "") or "",
            is_verified=data.get("verified_contract", False) or data.get("verifiedContract", False),
            is_native=is_native,
        )

    @classmethod
    def from_erc20_response(cls, data: Dict[str, Any], chain: str) -> "Token":
        """Create Token from Moralis ERC20 balance response."""
        decimals = int(data.get("decimals", 18))

        balance_raw = data.get("balance", "0")
        if isinstance(balance_raw, str):
            raw_amount = int(balance_raw) if balance_raw else 0
        else:
            raw_amount = int(balance_raw)

        amount = raw_amount / (10 ** decimals) if decimals > 0 else raw_amount

        # Get USD price if available
        price = 0.0
        if data.get("usd_price") is not None:
            price = float(data.get("usd_price", 0))
        elif data.get("usdPrice") is not None:
            price = float(data.get("usdPrice", 0))

        value_usd = price * amount

        return cls(
            chain=chain,
            symbol=data.get("symbol", "") or "UNKNOWN",
            name=data.get("name", "") or "Unknown Token",
            address=data.get("token_address", "") or data.get("tokenAddress", ""),
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

        if isinstance(balance, str):
            raw_amount = int(balance) if balance else 0
        else:
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

        logger.debug(f"Making request to: {url} with params: {params}")

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

                logger.debug(f"Response status: {response.status_code}")

                if response.status_code == 401:
                    logger.error("API Key is invalid or unauthorized")
                    return None

                response.raise_for_status()
                result = response.json()
                logger.debug(f"Response data keys: {result.keys() if isinstance(result, dict) else 'list'}")
                return result

            except requests.exceptions.HTTPError as e:
                logger.warning(f"HTTP Error: {e}, Status: {response.status_code}")
                if response.status_code == 429:  # Rate limited
                    wait_time = RETRY_DELAY * (2 ** attempt)
                    logger.info(f"Rate limited, waiting {wait_time}s")
                    time.sleep(wait_time)
                    continue
                elif response.status_code in (400, 404):
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
                logger.warning(f"Request error: {e}")
                with self._stats_lock:
                    self.error_count += 1
                if attempt < retries - 1:
                    time.sleep(RETRY_DELAY * (attempt + 1))
                    continue
                raise

        return None

    def get_wallet_tokens_with_price(self, address: str, chain: str) -> List[Token]:
        """
        Get all tokens (native + ERC20) with prices for a wallet on a chain.
        Uses the v2.2 endpoint: /wallets/{address}/tokens

        Args:
            address: Ethereum address (0x...)
            chain: Chain ID (e.g., 'eth', 'bsc')

        Returns:
            List of Token objects
        """
        chain_hex = CHAIN_HEX_IDS.get(chain)
        if not chain_hex:
            logger.warning(f"Unknown chain: {chain}")
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

            # Use the v2.2 wallets endpoint
            response = self._make_request(
                f"/wallets/{address}/tokens",
                params=params,
            )

            if response is None:
                logger.warning(f"No response for {address} on {chain}")
                break

            # Handle response - can be list or dict with 'result'
            token_list = []
            if isinstance(response, list):
                token_list = response
            elif isinstance(response, dict):
                token_list = response.get("result", [])
                cursor = response.get("cursor")

            logger.info(f"Found {len(token_list)} tokens for {address[:10]}... on {chain}")

            for token_data in token_list:
                try:
                    token = Token.from_wallet_token_response(token_data, chain)
                    if token.amount > 0:
                        tokens.append(token)
                        logger.debug(f"Token: {token.symbol} = {token.amount} (${token.value_usd:.2f})")
                except Exception as e:
                    logger.warning(f"Error parsing token: {e}")
                    continue

            # Check if we need to paginate
            if not cursor or not isinstance(response, dict):
                break

        return tokens

    def get_native_balance(self, address: str, chain: str) -> Optional[str]:
        """
        Get native token balance for an address on a specific chain.
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

    def get_erc20_balances(self, address: str, chain: str) -> List[Token]:
        """
        Get all ERC20 token balances for an address on a specific chain.
        Fallback method using older endpoint.
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
        """
        if chains is None:
            chains = SUPPORTED_CHAIN_IDS

        result: Dict[str, List[Token]] = {}

        logger.info(f"Scanning address {address[:10]}... across {len(chains)} chains")

        for chain in chains:
            chain_tokens = []

            # Try the new v2.2 endpoint first
            tokens = self.get_wallet_tokens_with_price(address, chain)

            if tokens:
                for token in tokens:
                    # Apply dust filter
                    if filter_dust and token.value_usd < min_value and token.value_usd > 0:
                        continue
                    # Include tokens with 0 price but non-zero balance (price might be unavailable)
                    if token.amount > 0:
                        chain_tokens.append(token)
            else:
                # Fallback to old method
                logger.debug(f"Falling back to legacy method for {chain}")

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
                logger.info(f"  {chain}: {len(chain_tokens)} tokens")

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
