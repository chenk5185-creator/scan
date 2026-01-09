#!/usr/bin/env python3
"""
Multi-Chain Wallet Scanner
==========================

Scans multiple Ethereum addresses across 8 blockchains using Moralis API
and generates a comprehensive Excel report.

Supported Chains:
- Ethereum, BSC, Polygon, Arbitrum, Optimism
- Base, Linea, zkSync Era

Usage:
    python scan.py -i wallets.txt -o report.xlsx
    python scan.py --addresses 0x123... 0x456...
    cat wallets.txt | python scan.py -o report.xlsx

Environment:
    MORALIS_API_KEY: Your Moralis API key (required)
"""

import argparse
import logging
import sys
import os
from datetime import datetime
from typing import List, Optional

from config import (
    DEFAULT_INPUT_FILE,
    DEFAULT_OUTPUT_FILE,
    MAX_WORKERS,
    MIN_TOKEN_VALUE_USD,
    SUPPORTED_CHAINS,
)
from scanner import WalletScanner, load_addresses_from_file, ScanProgress
from processor import DataProcessor
from exporter import export_to_excel

# Configure logging
logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s - %(levelname)s - %(message)s",
    handlers=[
        logging.StreamHandler(sys.stdout),
    ]
)
logger = logging.getLogger(__name__)


def parse_arguments() -> argparse.Namespace:
    """Parse command line arguments."""
    parser = argparse.ArgumentParser(
        description="Multi-Chain Wallet Scanner - Scan wallet addresses across multiple blockchains",
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog="""
Examples:
  # Scan addresses from file
  python scan.py -i wallets.txt -o report.xlsx

  # Scan specific addresses
  python scan.py --addresses 0x123... 0x456... 0x789...

  # Read from stdin
  cat wallets.txt | python scan.py -o report.xlsx

  # Custom settings
  python scan.py -i wallets.txt -o report.xlsx -w 5 --min-value 1.0

Environment Variables:
  MORALIS_API_KEY    Your Moralis API key (required, free at moralis.io)
        """,
    )

    parser.add_argument(
        "-i", "--input",
        type=str,
        default=None,
        help=f"Input file containing wallet addresses (one per line). Default: {DEFAULT_INPUT_FILE}",
    )

    parser.add_argument(
        "-o", "--output",
        type=str,
        default=DEFAULT_OUTPUT_FILE,
        help=f"Output Excel file path. Default: {DEFAULT_OUTPUT_FILE}",
    )

    parser.add_argument(
        "--addresses",
        nargs="+",
        type=str,
        help="Wallet addresses to scan (space-separated)",
    )

    parser.add_argument(
        "-w", "--workers",
        type=int,
        default=MAX_WORKERS,
        help=f"Number of concurrent workers. Default: {MAX_WORKERS}",
    )

    parser.add_argument(
        "--min-value",
        type=float,
        default=MIN_TOKEN_VALUE_USD,
        help=f"Minimum token value in USD to include. Default: {MIN_TOKEN_VALUE_USD}",
    )

    parser.add_argument(
        "--api-key",
        type=str,
        default=None,
        help="Moralis API key (overrides MORALIS_API_KEY env var)",
    )

    parser.add_argument(
        "-v", "--verbose",
        action="store_true",
        help="Enable verbose logging",
    )

    parser.add_argument(
        "--dry-run",
        action="store_true",
        help="Validate addresses without making API calls",
    )

    return parser.parse_args()


def get_addresses(args: argparse.Namespace) -> List[str]:
    """Get addresses from arguments, file, or stdin."""
    addresses = []

    # From command line arguments
    if args.addresses:
        addresses.extend(args.addresses)
        logger.info(f"Loaded {len(args.addresses)} addresses from command line")

    # From input file
    if args.input:
        file_addresses = load_addresses_from_file(args.input)
        addresses.extend(file_addresses)
    elif not args.addresses and not sys.stdin.isatty():
        # Read from stdin if no other input
        logger.info("Reading addresses from stdin...")
        for line in sys.stdin:
            line = line.strip()
            if line and not line.startswith("#"):
                addresses.append(line)
        logger.info(f"Loaded {len(addresses)} addresses from stdin")
    elif not args.addresses:
        # Try default input file
        if os.path.exists(DEFAULT_INPUT_FILE):
            addresses = load_addresses_from_file(DEFAULT_INPUT_FILE)
        else:
            logger.error(f"No input specified. Use -i FILE, --addresses, or create {DEFAULT_INPUT_FILE}")
            sys.exit(1)

    return addresses


def validate_addresses(addresses: List[str]) -> List[str]:
    """Validate and clean addresses."""
    valid = []
    invalid_count = 0

    for addr in addresses:
        addr = addr.strip().lower()
        if addr.startswith("0x") and len(addr) == 42:
            try:
                int(addr, 16)  # Validate hex
                valid.append(addr)
            except ValueError:
                invalid_count += 1
        elif addr:
            invalid_count += 1

    if invalid_count > 0:
        logger.warning(f"Skipped {invalid_count} invalid addresses")

    # Remove duplicates while preserving order
    seen = set()
    unique = []
    for addr in valid:
        if addr not in seen:
            seen.add(addr)
            unique.append(addr)

    if len(valid) != len(unique):
        logger.info(f"Removed {len(valid) - len(unique)} duplicate addresses")

    return unique


def progress_callback(progress: ScanProgress):
    """Callback for scan progress updates."""
    if progress.completed % 50 == 0 or progress.completed == progress.total:
        pct = progress.progress_percent
        print(f"\rProgress: {progress.completed}/{progress.total} ({pct:.1f}%) "
              f"- Success: {progress.success}, Failed: {progress.failed}", end="", flush=True)


def main():
    """Main entry point."""
    args = parse_arguments()

    # Set logging level
    if args.verbose:
        logging.getLogger().setLevel(logging.DEBUG)

    # Get API key
    api_key = args.api_key or os.getenv("MORALIS_API_KEY")
    if not api_key:
        logger.error("Moralis API key is required. Set MORALIS_API_KEY environment variable or use --api-key")
        sys.exit(1)

    # Print configuration
    print("\n" + "=" * 60)
    print("Multi-Chain Wallet Scanner (Moralis API)")
    print("=" * 60)
    print(f"Supported Chains: {', '.join(SUPPORTED_CHAINS.values())}")
    print(f"Workers: {args.workers}")
    print(f"Min Token Value: ${args.min_value}")
    print(f"Output File: {args.output}")
    print("=" * 60 + "\n")

    # Get and validate addresses
    addresses = get_addresses(args)
    addresses = validate_addresses(addresses)

    if not addresses:
        logger.error("No valid addresses to scan")
        sys.exit(1)

    logger.info(f"Found {len(addresses)} valid unique addresses to scan")

    # Dry run mode
    if args.dry_run:
        print("\n[DRY RUN] Would scan the following addresses:")
        for i, addr in enumerate(addresses[:10], 1):
            print(f"  {i}. {addr}")
        if len(addresses) > 10:
            print(f"  ... and {len(addresses) - 10} more")
        print("\n[DRY RUN] No API calls made.")
        return

    # Initialize scanner
    start_time = datetime.now()
    logger.info("Starting scan...")

    try:
        with WalletScanner(
            api_key=api_key,
            max_workers=args.workers,
            min_token_value=args.min_value,
            progress_callback=progress_callback,
        ) as scanner:
            # Perform scan
            results = scanner.scan_wallets(addresses, show_progress=True)

        print()  # New line after progress

        if not results:
            logger.error("No results returned from scan")
            sys.exit(1)

        # Process results
        logger.info("Processing scan results...")
        processor = DataProcessor()
        processed_data = processor.process(results)

        # Print summary
        print("\n" + "=" * 60)
        print("Scan Summary")
        print("=" * 60)
        print(f"Total Wallets: {processed_data.total_wallets}")
        print(f"Successful: {processed_data.successful_scans}")
        print(f"Failed: {processed_data.failed_scans}")
        print(f"Total Value: ${processed_data.total_value_usd:,.2f}")
        print(f"Total Token Holdings: {processed_data.total_tokens}")
        print("=" * 60 + "\n")

        # Print chain breakdown
        print("Value by Chain:")
        print("-" * 40)
        for chain_id, summary in sorted(
            processed_data.chain_summaries.items(),
            key=lambda x: x[1].total_value_usd,
            reverse=True,
        ):
            if summary.total_value_usd > 0:
                print(f"  {summary.chain_name:15} ${summary.total_value_usd:>15,.2f}")
        print()

        # Export to Excel
        logger.info("Generating Excel report...")
        output_path = export_to_excel(processor, args.output)

        # Calculate elapsed time
        elapsed = datetime.now() - start_time
        minutes, seconds = divmod(elapsed.total_seconds(), 60)

        print("\n" + "=" * 60)
        print("Scan Complete!")
        print("=" * 60)
        print(f"Report saved to: {output_path}")
        print(f"Time elapsed: {int(minutes)}m {int(seconds)}s")
        print("=" * 60)

    except KeyboardInterrupt:
        print("\n\nScan interrupted by user")
        sys.exit(130)
    except Exception as e:
        logger.exception(f"Scan failed: {e}")
        sys.exit(1)


if __name__ == "__main__":
    main()
