#!/usr/bin/env python3
"""
Multi-Chain Wallet Scanner - Streamlit Web Interface
=====================================================

A web-based interface for scanning wallet addresses across multiple blockchains.

Usage:
    streamlit run app.py
"""

import streamlit as st
import pandas as pd
import time
import io
from datetime import datetime
from typing import List, Dict, Any, Optional

from config import (
    SUPPORTED_CHAINS,
    MAX_WORKERS,
    MIN_TOKEN_VALUE_USD,
    DEFAULT_OUTPUT_FILE,
)
from scanner import WalletScanner, WalletResult
from processor import DataProcessor
from exporter import ExcelExporter

# Page configuration
st.set_page_config(
    page_title="Multi-Chain Wallet Scanner",
    page_icon="🔍",
    layout="wide",
    initial_sidebar_state="expanded",
)

# Custom CSS
st.markdown("""
<style>
    .main-header {
        font-size: 2.5rem;
        font-weight: bold;
        color: #1E88E5;
        text-align: center;
        margin-bottom: 1rem;
    }
    .sub-header {
        font-size: 1.2rem;
        color: #666;
        text-align: center;
        margin-bottom: 2rem;
    }
    .metric-card {
        background-color: #f0f2f6;
        border-radius: 10px;
        padding: 1rem;
        text-align: center;
    }
    .chain-badge {
        display: inline-block;
        padding: 0.25rem 0.5rem;
        margin: 0.1rem;
        border-radius: 5px;
        background-color: #e3f2fd;
        font-size: 0.8rem;
    }
    .stProgress > div > div > div > div {
        background-color: #1E88E5;
    }
</style>
""", unsafe_allow_html=True)


def init_session_state():
    """Initialize session state variables."""
    if "scan_results" not in st.session_state:
        st.session_state.scan_results = None
    if "processed_data" not in st.session_state:
        st.session_state.processed_data = None
    if "scan_running" not in st.session_state:
        st.session_state.scan_running = False
    if "scan_progress" not in st.session_state:
        st.session_state.scan_progress = 0
    if "scan_status" not in st.session_state:
        st.session_state.scan_status = ""


def parse_addresses(text: str) -> List[str]:
    """Parse addresses from text input."""
    addresses = []
    for line in text.strip().split("\n"):
        line = line.strip()
        # Handle comma-separated addresses
        for addr in line.split(","):
            addr = addr.strip().lower()
            if addr.startswith("0x") and len(addr) == 42:
                try:
                    int(addr, 16)  # Validate hex
                    addresses.append(addr)
                except ValueError:
                    pass
    # Remove duplicates while preserving order
    seen = set()
    unique = []
    for addr in addresses:
        if addr not in seen:
            seen.add(addr)
            unique.append(addr)
    return unique


def run_scan(addresses: List[str], api_key: str, workers: int, min_value: float) -> List[WalletResult]:
    """Run the wallet scan with progress tracking."""
    results = []

    with WalletScanner(
        api_key=api_key,
        max_workers=workers,
        min_token_value=min_value,
    ) as scanner:
        results = scanner.scan_wallets(addresses, show_progress=False)

    return results


def create_excel_download(processor: DataProcessor) -> bytes:
    """Create Excel file in memory for download."""
    exporter = ExcelExporter(processor)
    exporter.workbook = __import__("openpyxl").Workbook()

    # Remove default sheet
    if "Sheet" in exporter.workbook.sheetnames:
        del exporter.workbook["Sheet"]

    # Create all sheets
    exporter._create_summary_sheet()
    exporter._create_all_tokens_sheet()
    exporter._create_statistics_sheet()

    from config import CHAIN_TO_SHEET
    for chain_id, sheet_name in CHAIN_TO_SHEET.items():
        exporter._create_chain_sheet(chain_id, sheet_name)

    exporter._create_errors_sheet()

    # Save to bytes
    output = io.BytesIO()
    exporter.workbook.save(output)
    output.seek(0)
    return output.getvalue()


def render_sidebar():
    """Render the sidebar with configuration options."""
    st.sidebar.markdown("## ⚙️ Configuration")

    # API Key
    api_key = st.sidebar.text_input(
        "Moralis API Key",
        type="password",
        help="Enter your Moralis API key (get free at moralis.io)",
    )

    st.sidebar.markdown("---")

    # Scan settings
    st.sidebar.markdown("### Scan Settings")

    workers = st.sidebar.slider(
        "Concurrent Workers",
        min_value=1,
        max_value=5,
        value=MAX_WORKERS,
        help="Number of parallel workers (limited by API rate)",
    )

    min_value = st.sidebar.number_input(
        "Min Token Value (USD)",
        min_value=0.0,
        max_value=100.0,
        value=MIN_TOKEN_VALUE_USD,
        step=0.01,
        help="Filter out tokens worth less than this amount",
    )

    st.sidebar.markdown("---")

    # Supported chains info
    st.sidebar.markdown("### 🔗 Supported Chains")
    chains_html = ""
    for chain_id, chain_name in SUPPORTED_CHAINS.items():
        chains_html += f'<span class="chain-badge">{chain_name}</span> '
    st.sidebar.markdown(chains_html, unsafe_allow_html=True)

    st.sidebar.markdown("---")
    st.sidebar.markdown(
        "💡 **Tip:** The scanner first checks which chains "
        "each wallet is active on to optimize API calls."
    )

    return api_key, workers, min_value


def render_results(processed_data):
    """Render the scan results."""
    data = processed_data

    # Summary metrics
    st.markdown("## 📊 Scan Results")

    col1, col2, col3, col4, col5 = st.columns(5)

    with col1:
        st.metric("Total Wallets", data.total_wallets)
    with col2:
        st.metric("Successful", data.successful_scans)
    with col3:
        st.metric("Failed", data.failed_scans)
    with col4:
        st.metric("Total Value", f"${data.total_value_usd:,.2f}")
    with col5:
        st.metric("Token Holdings", data.total_tokens)

    st.markdown("---")

    # Tabs for different views
    tab1, tab2, tab3, tab4 = st.tabs([
        "📈 Chain Distribution",
        "🪙 All Tokens",
        "👛 Wallet Summary",
        "❌ Errors"
    ])

    with tab1:
        render_chain_distribution(data)

    with tab2:
        render_all_tokens(data)

    with tab3:
        render_wallet_summary(data)

    with tab4:
        render_errors(data)


def render_chain_distribution(data):
    """Render chain distribution charts and table."""
    st.markdown("### Value Distribution by Chain")

    # Prepare data for chart
    chain_data = []
    for chain_id, summary in data.chain_summaries.items():
        if summary.total_value_usd > 0:
            chain_data.append({
                "Chain": summary.chain_name,
                "Value (USD)": summary.total_value_usd,
                "Wallets": summary.wallet_count,
                "Tokens": summary.token_count,
            })

    if chain_data:
        df = pd.DataFrame(chain_data)
        df = df.sort_values("Value (USD)", ascending=False)

        col1, col2 = st.columns([2, 1])

        with col1:
            # Bar chart
            st.bar_chart(df.set_index("Chain")["Value (USD)"])

        with col2:
            # Pie chart data
            st.markdown("#### Chain Breakdown")
            total = df["Value (USD)"].sum()
            for _, row in df.iterrows():
                pct = (row["Value (USD)"] / total) * 100
                st.markdown(f"**{row['Chain']}**: ${row['Value (USD)']:,.2f} ({pct:.1f}%)")

        # Table
        st.markdown("#### Detailed Statistics")
        st.dataframe(
            df.style.format({
                "Value (USD)": "${:,.2f}",
            }),
            use_container_width=True,
        )
    else:
        st.info("No chain data available")


def render_all_tokens(data):
    """Render all tokens table."""
    st.markdown("### All Token Holdings")

    if data.all_tokens:
        df = pd.DataFrame(data.all_tokens)
        df = df.sort_values("value_usd", ascending=False)

        # Rename columns for display
        display_df = df[[
            "wallet_address", "chain_name", "token_symbol",
            "token_name", "price_usd", "amount", "value_usd"
        ]].copy()
        display_df.columns = [
            "Wallet", "Chain", "Symbol", "Name", "Price", "Amount", "Value (USD)"
        ]

        # Filters
        col1, col2 = st.columns(2)
        with col1:
            chain_filter = st.multiselect(
                "Filter by Chain",
                options=display_df["Chain"].unique().tolist(),
                default=[],
            )
        with col2:
            min_val_filter = st.number_input(
                "Min Value Filter",
                min_value=0.0,
                value=0.0,
                step=1.0,
            )

        # Apply filters
        filtered_df = display_df.copy()
        if chain_filter:
            filtered_df = filtered_df[filtered_df["Chain"].isin(chain_filter)]
        if min_val_filter > 0:
            filtered_df = filtered_df[filtered_df["Value (USD)"] >= min_val_filter]

        st.markdown(f"Showing **{len(filtered_df)}** of **{len(display_df)}** tokens")

        st.dataframe(
            filtered_df.style.format({
                "Price": "${:.6f}",
                "Amount": "{:,.4f}",
                "Value (USD)": "${:,.2f}",
            }),
            use_container_width=True,
            height=400,
        )
    else:
        st.info("No token data available")


def render_wallet_summary(data):
    """Render wallet summary table."""
    st.markdown("### Wallet Summary")

    if data.wallet_summaries:
        wallet_data = []
        for addr, summary in sorted(
            data.wallet_summaries.items(),
            key=lambda x: x[1].total_value_usd,
            reverse=True,
        ):
            wallet_data.append({
                "Address": addr,
                "Total Value (USD)": summary.total_value_usd,
                "Active Chains": len(summary.active_chains),
                "Token Count": summary.token_count,
                "Chains": ", ".join(summary.active_chains),
            })

        df = pd.DataFrame(wallet_data)

        st.dataframe(
            df.style.format({
                "Total Value (USD)": "${:,.2f}",
            }),
            use_container_width=True,
            height=400,
        )

        # Top wallets chart
        if len(df) > 0:
            st.markdown("#### Top 20 Wallets by Value")
            top_df = df.head(20).copy()
            top_df["Short Address"] = top_df["Address"].apply(
                lambda x: f"{x[:6]}...{x[-4:]}"
            )
            st.bar_chart(top_df.set_index("Short Address")["Total Value (USD)"])
    else:
        st.info("No wallet data available")


def render_errors(data):
    """Render error table."""
    st.markdown("### Failed Addresses")

    if data.failed_addresses:
        df = pd.DataFrame(data.failed_addresses)
        df.columns = ["Address", "Error"]
        st.dataframe(df, use_container_width=True)
        st.warning(f"⚠️ {len(data.failed_addresses)} addresses failed to scan")
    else:
        st.success("✅ All addresses scanned successfully!")


def main():
    """Main application entry point."""
    init_session_state()

    # Header
    st.markdown('<p class="main-header">🔍 Multi-Chain Wallet Scanner</p>', unsafe_allow_html=True)
    st.markdown(
        '<p class="sub-header">Scan wallet addresses across 8 blockchains using Moralis API</p>',
        unsafe_allow_html=True,
    )

    # Sidebar
    api_key, workers, min_value = render_sidebar()

    # Main content
    st.markdown("## 📝 Enter Wallet Addresses")

    # Address input
    addresses_text = st.text_area(
        "Paste wallet addresses (one per line or comma-separated)",
        height=200,
        placeholder="0x742d35Cc6634C0532925a3b844Bc9e7595f...\n0x8ba1f109551bD432803012645Hac136c...\n...",
        help="Enter Ethereum addresses (0x...). Supports up to 1000 addresses.",
    )

    # Parse and validate addresses
    addresses = parse_addresses(addresses_text)

    if addresses_text:
        st.info(f"📍 Found **{len(addresses)}** valid unique addresses")

    # Scan button
    col1, col2, col3 = st.columns([1, 1, 1])

    with col2:
        scan_button = st.button(
            "🚀 Start Scan",
            type="primary",
            use_container_width=True,
            disabled=not addresses or not api_key,
        )

    if not api_key:
        st.warning("⚠️ Please enter your Moralis API key in the sidebar")
    elif not addresses:
        st.info("💡 Enter wallet addresses above to begin scanning")

    # Run scan
    if scan_button and addresses and api_key:
        st.markdown("---")
        st.markdown("## ⏳ Scanning...")

        progress_bar = st.progress(0)
        status_text = st.empty()

        try:
            status_text.text(f"Scanning {len(addresses)} addresses...")

            # Run scan
            results = run_scan(addresses, api_key, workers, min_value)

            progress_bar.progress(50)
            status_text.text("Processing results...")

            # Process results
            processor = DataProcessor()
            processed_data = processor.process(results)

            progress_bar.progress(100)
            status_text.text("Scan complete!")

            # Store in session state
            st.session_state.scan_results = results
            st.session_state.processed_data = processed_data

            time.sleep(0.5)
            st.rerun()

        except Exception as e:
            st.error(f"❌ Scan failed: {str(e)}")
            st.exception(e)

    # Display results if available
    if st.session_state.processed_data:
        st.markdown("---")
        render_results(st.session_state.processed_data)

        # Download button
        st.markdown("---")
        st.markdown("## 📥 Download Report")

        col1, col2, col3 = st.columns([1, 1, 1])
        with col2:
            try:
                processor = DataProcessor()
                processor.processed_data = st.session_state.processed_data
                excel_data = create_excel_download(processor)

                timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
                filename = f"wallet_scan_report_{timestamp}.xlsx"

                st.download_button(
                    label="📊 Download Excel Report",
                    data=excel_data,
                    file_name=filename,
                    mime="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
                    use_container_width=True,
                )
            except Exception as e:
                st.error(f"Failed to generate Excel: {str(e)}")

        # Reset button
        col1, col2, col3 = st.columns([1, 1, 1])
        with col2:
            if st.button("🔄 New Scan", use_container_width=True):
                st.session_state.scan_results = None
                st.session_state.processed_data = None
                st.rerun()


if __name__ == "__main__":
    main()
