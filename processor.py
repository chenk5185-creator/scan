"""
Data processor for wallet scan results.
"""
from dataclasses import dataclass, field
from typing import Dict, List, Optional, Any
from collections import defaultdict

from scanner import WalletResult
from debank_client import Token
from config import SUPPORTED_CHAINS, CHAIN_TO_SHEET


@dataclass
class TokenSummary:
    """Summary for a specific token across all wallets."""
    chain: str
    symbol: str
    name: str
    address: str
    total_amount: float = 0.0
    total_value_usd: float = 0.0
    holder_count: int = 0
    price: float = 0.0
    holders: List[str] = field(default_factory=list)

    def add_holding(self, wallet: str, amount: float, value: float, price: float):
        """Add a holding to this token summary."""
        self.total_amount += amount
        self.total_value_usd += value
        self.holder_count += 1
        self.holders.append(wallet)
        if price > 0:
            self.price = price


@dataclass
class ChainSummary:
    """Summary for a specific chain."""
    chain_id: str
    chain_name: str
    total_value_usd: float = 0.0
    wallet_count: int = 0
    token_count: int = 0
    unique_tokens: int = 0
    wallets: List[str] = field(default_factory=list)


@dataclass
class WalletSummary:
    """Summary for a specific wallet."""
    address: str
    total_value_usd: float = 0.0
    active_chains: List[str] = field(default_factory=list)
    chain_values: Dict[str, float] = field(default_factory=dict)
    token_count: int = 0


@dataclass
class ProcessedData:
    """Container for all processed data."""
    # Overall statistics
    total_wallets: int = 0
    successful_scans: int = 0
    failed_scans: int = 0
    total_value_usd: float = 0.0
    total_tokens: int = 0

    # By chain
    chain_summaries: Dict[str, ChainSummary] = field(default_factory=dict)

    # By token
    token_summaries: Dict[str, TokenSummary] = field(default_factory=dict)

    # By wallet
    wallet_summaries: Dict[str, WalletSummary] = field(default_factory=dict)

    # All tokens flat list
    all_tokens: List[Dict[str, Any]] = field(default_factory=list)

    # Chain-specific token lists
    chain_tokens: Dict[str, List[Dict[str, Any]]] = field(default_factory=dict)

    # Failed addresses
    failed_addresses: List[Dict[str, str]] = field(default_factory=list)


class DataProcessor:
    """Process wallet scan results into structured data."""

    def __init__(self):
        self.processed_data: Optional[ProcessedData] = None

    def process(self, results: List[WalletResult]) -> ProcessedData:
        """
        Process scan results into structured data for export.

        Args:
            results: List of WalletResult from scanner

        Returns:
            ProcessedData with all aggregated data
        """
        data = ProcessedData()
        data.total_wallets = len(results)

        # Initialize chain summaries
        for chain_id, chain_name in SUPPORTED_CHAINS.items():
            data.chain_summaries[chain_id] = ChainSummary(
                chain_id=chain_id,
                chain_name=chain_name,
            )
            data.chain_tokens[chain_id] = []

        # Token key -> TokenSummary
        token_map: Dict[str, TokenSummary] = {}

        for result in results:
            if not result.is_success:
                data.failed_scans += 1
                data.failed_addresses.append({
                    "address": result.address,
                    "error": result.error or "Unknown error",
                })
                continue

            data.successful_scans += 1

            # Create wallet summary
            wallet_summary = WalletSummary(
                address=result.address,
                total_value_usd=result.total_value_usd,
                active_chains=result.active_chains.copy(),
                token_count=result.token_count,
            )

            # Process tokens by chain
            for chain_id, tokens in result.tokens.items():
                chain_value = sum(t.value_usd for t in tokens)
                wallet_summary.chain_values[chain_id] = chain_value

                # Update chain summary
                chain_summary = data.chain_summaries[chain_id]
                chain_summary.total_value_usd += chain_value
                chain_summary.wallet_count += 1
                chain_summary.token_count += len(tokens)
                chain_summary.wallets.append(result.address)

                # Process individual tokens
                for token in tokens:
                    # Add to all tokens list
                    token_dict = self._token_to_dict(token, result.address)
                    data.all_tokens.append(token_dict)
                    data.chain_tokens[chain_id].append(token_dict)
                    data.total_tokens += 1

                    # Aggregate by token
                    token_key = f"{chain_id}:{token.address}"
                    if token_key not in token_map:
                        token_map[token_key] = TokenSummary(
                            chain=chain_id,
                            symbol=token.symbol,
                            name=token.name,
                            address=token.address,
                            price=token.price,
                        )
                    token_map[token_key].add_holding(
                        result.address,
                        token.amount,
                        token.value_usd,
                        token.price,
                    )

            data.wallet_summaries[result.address] = wallet_summary
            data.total_value_usd += result.total_value_usd

        # Calculate unique tokens per chain
        for chain_id in SUPPORTED_CHAINS:
            unique_tokens = set()
            for token in data.chain_tokens[chain_id]:
                unique_tokens.add(token["token_address"])
            data.chain_summaries[chain_id].unique_tokens = len(unique_tokens)

        data.token_summaries = token_map
        self.processed_data = data
        return data

    def _token_to_dict(self, token: Token, wallet_address: str) -> Dict[str, Any]:
        """Convert Token to dictionary for export."""
        return {
            "wallet_address": wallet_address,
            "chain": token.chain,
            "chain_name": SUPPORTED_CHAINS.get(token.chain, token.chain),
            "token_symbol": token.symbol,
            "token_name": token.name,
            "token_address": token.address,
            "price_usd": token.price,
            "amount": token.amount,
            "value_usd": token.value_usd,
            "is_verified": token.is_verified,
            "is_core": token.is_core,
        }

    def get_summary_stats(self) -> Dict[str, Any]:
        """Get summary statistics."""
        if not self.processed_data:
            return {}

        data = self.processed_data

        # Top tokens by value
        top_tokens = sorted(
            data.token_summaries.values(),
            key=lambda x: x.total_value_usd,
            reverse=True,
        )[:20]

        # Chain distribution
        chain_distribution = {
            chain_id: {
                "name": summary.chain_name,
                "value_usd": summary.total_value_usd,
                "wallet_count": summary.wallet_count,
                "token_count": summary.token_count,
            }
            for chain_id, summary in data.chain_summaries.items()
            if summary.total_value_usd > 0
        }

        # Top wallets by value
        top_wallets = sorted(
            data.wallet_summaries.values(),
            key=lambda x: x.total_value_usd,
            reverse=True,
        )[:20]

        return {
            "total_wallets": data.total_wallets,
            "successful_scans": data.successful_scans,
            "failed_scans": data.failed_scans,
            "total_value_usd": data.total_value_usd,
            "total_tokens": data.total_tokens,
            "unique_tokens": len(data.token_summaries),
            "chain_distribution": chain_distribution,
            "top_tokens": [
                {
                    "chain": t.chain,
                    "symbol": t.symbol,
                    "name": t.name,
                    "total_value_usd": t.total_value_usd,
                    "holder_count": t.holder_count,
                }
                for t in top_tokens
            ],
            "top_wallets": [
                {
                    "address": w.address,
                    "total_value_usd": w.total_value_usd,
                    "chain_count": len(w.active_chains),
                    "token_count": w.token_count,
                }
                for w in top_wallets
            ],
        }

    def get_chain_data(self, chain_id: str) -> List[Dict[str, Any]]:
        """Get token data for a specific chain."""
        if not self.processed_data:
            return []
        return self.processed_data.chain_tokens.get(chain_id, [])

    def get_all_tokens(self) -> List[Dict[str, Any]]:
        """Get all tokens data."""
        if not self.processed_data:
            return []
        return self.processed_data.all_tokens

    def get_failed_addresses(self) -> List[Dict[str, str]]:
        """Get list of failed addresses."""
        if not self.processed_data:
            return []
        return self.processed_data.failed_addresses

    def get_wallet_summaries(self) -> List[Dict[str, Any]]:
        """Get wallet summaries for export."""
        if not self.processed_data:
            return []

        summaries = []
        for wallet in sorted(
            self.processed_data.wallet_summaries.values(),
            key=lambda x: x.total_value_usd,
            reverse=True,
        ):
            summary = {
                "address": wallet.address,
                "total_value_usd": wallet.total_value_usd,
                "active_chains": ", ".join(wallet.active_chains),
                "chain_count": len(wallet.active_chains),
                "token_count": wallet.token_count,
            }
            # Add chain-specific values
            for chain_id in SUPPORTED_CHAINS:
                summary[f"{chain_id}_value"] = wallet.chain_values.get(chain_id, 0.0)

            summaries.append(summary)

        return summaries
