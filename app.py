#!/usr/bin/env python3
"""
多链钱包扫描器 - Streamlit Web 界面
===================================

基于 Web 的多链钱包地址扫描界面。

使用方法:
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
    MORALIS_API_KEY,
)
from scanner import WalletScanner, WalletResult
from processor import DataProcessor
from exporter import ExcelExporter

# 页面配置
st.set_page_config(
    page_title="多链钱包扫描器",
    page_icon="🔍",
    layout="wide",
    initial_sidebar_state="expanded",
)

# 自定义 CSS
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
    """初始化会话状态变量。"""
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
    """从文本输入解析地址。"""
    addresses = []
    for line in text.strip().split("\n"):
        line = line.strip()
        # 处理逗号分隔的地址
        for addr in line.split(","):
            addr = addr.strip().lower()
            if addr.startswith("0x") and len(addr) == 42:
                try:
                    int(addr, 16)  # 验证十六进制
                    addresses.append(addr)
                except ValueError:
                    pass
    # 去重并保持顺序
    seen = set()
    unique = []
    for addr in addresses:
        if addr not in seen:
            seen.add(addr)
            unique.append(addr)
    return unique


def run_scan(addresses: List[str], api_key: str, workers: int, min_value: float) -> tuple:
    """运行钱包扫描。"""
    import logging
    import io

    # 创建内存日志处理器
    log_stream = io.StringIO()
    handler = logging.StreamHandler(log_stream)
    handler.setLevel(logging.INFO)
    formatter = logging.Formatter('%(asctime)s - %(name)s - %(message)s')
    handler.setFormatter(formatter)

    # 添加到所有相关的 logger
    for logger_name in ['moralis_client', 'scanner', '__main__', 'root']:
        logger = logging.getLogger(logger_name)
        logger.setLevel(logging.INFO)
        logger.addHandler(handler)

    results = []
    try:
        with WalletScanner(
            api_key=api_key,
            max_workers=workers,
            min_token_value=min_value,
        ) as scanner:
            results = scanner.scan_wallets(addresses, show_progress=False)
    finally:
        # 获取日志内容
        log_content = log_stream.getvalue()

    return results, log_content


def create_excel_download(processor: DataProcessor) -> bytes:
    """在内存中创建 Excel 文件供下载。"""
    exporter = ExcelExporter(processor)
    exporter.workbook = __import__("openpyxl").Workbook()

    # 删除默认工作表
    if "Sheet" in exporter.workbook.sheetnames:
        del exporter.workbook["Sheet"]

    # 创建所有工作表
    exporter._create_summary_sheet()
    exporter._create_all_tokens_sheet()
    exporter._create_statistics_sheet()

    from config import CHAIN_TO_SHEET
    for chain_id, sheet_name in CHAIN_TO_SHEET.items():
        exporter._create_chain_sheet(chain_id, sheet_name)

    exporter._create_errors_sheet()

    # 保存到字节流
    output = io.BytesIO()
    exporter.workbook.save(output)
    output.seek(0)
    return output.getvalue()


def render_sidebar():
    """渲染侧边栏配置选项。"""
    st.sidebar.markdown("## ⚙️ 配置设置")

    # 扫描设置
    st.sidebar.markdown("### 扫描设置")

    workers = st.sidebar.slider(
        "并发线程数",
        min_value=1,
        max_value=5,
        value=MAX_WORKERS,
        help="并行工作线程数（受 API 速率限制）",
    )

    min_value = st.sidebar.number_input(
        "最小代币价值 (USD)",
        min_value=0.0,
        max_value=100.0,
        value=MIN_TOKEN_VALUE_USD,
        step=0.01,
        help="过滤掉价值低于此金额的代币",
    )

    st.sidebar.markdown("---")

    # 支持的链信息
    st.sidebar.markdown("### 🔗 支持的区块链")
    chains_html = ""
    for chain_id, chain_name in SUPPORTED_CHAINS.items():
        chains_html += f'<span class="chain-badge">{chain_name}</span> '
    st.sidebar.markdown(chains_html, unsafe_allow_html=True)

    st.sidebar.markdown("---")
    st.sidebar.markdown(
        "💡 **提示:** 扫描器会先检查每个钱包在哪些链上有活动，以优化 API 调用次数。"
    )

    return workers, min_value


def render_results(processed_data):
    """渲染扫描结果。"""
    data = processed_data

    # 汇总指标
    st.markdown("## 📊 扫描结果")

    col1, col2, col3, col4, col5 = st.columns(5)

    with col1:
        st.metric("钱包总数", data.total_wallets)
    with col2:
        st.metric("成功", data.successful_scans)
    with col3:
        st.metric("失败", data.failed_scans)
    with col4:
        st.metric("总价值", f"${data.total_value_usd:,.2f}")
    with col5:
        st.metric("代币持仓数", data.total_tokens)

    st.markdown("---")

    # 不同视图的标签页 - 默认显示全部代币
    tab1, tab2, tab3, tab4 = st.tabs([
        "🪙 全部代币",
        "📈 链分布",
        "👛 钱包汇总",
        "❌ 错误"
    ])

    with tab1:
        render_all_tokens(data)

    with tab2:
        render_chain_distribution(data)

    with tab3:
        render_wallet_summary(data)

    with tab4:
        render_errors(data)


def render_chain_distribution(data):
    """渲染链分布图表和表格。"""
    st.markdown("### 各链价值分布")

    # 准备图表数据
    chain_data = []
    for chain_id, summary in data.chain_summaries.items():
        if summary.total_value_usd > 0:
            chain_data.append({
                "区块链": summary.chain_name,
                "价值 (USD)": summary.total_value_usd,
                "钱包数": summary.wallet_count,
                "代币数": summary.token_count,
            })

    if chain_data:
        df = pd.DataFrame(chain_data)
        df = df.sort_values("价值 (USD)", ascending=False)

        col1, col2 = st.columns([2, 1])

        with col1:
            # 柱状图
            st.bar_chart(df.set_index("区块链")["价值 (USD)"])

        with col2:
            # 占比明细
            st.markdown("#### 链占比明细")
            total = df["价值 (USD)"].sum()
            for _, row in df.iterrows():
                pct = (row["价值 (USD)"] / total) * 100
                st.markdown(f"**{row['区块链']}**: ${row['价值 (USD)']:,.2f} ({pct:.1f}%)")

        # 表格
        st.markdown("#### 详细统计")
        st.dataframe(
            df.style.format({
                "价值 (USD)": "${:,.2f}",
            }),
            use_container_width=True,
        )
    else:
        st.info("暂无链数据")


def render_all_tokens(data):
    """渲染全部代币表格。"""
    st.markdown("### 全部代币持仓")

    if data.all_tokens:
        df = pd.DataFrame(data.all_tokens)
        df = df.sort_values("value_usd", ascending=False)

        # 重命名列用于显示
        display_df = df[[
            "wallet_address", "chain_name", "token_symbol",
            "token_name", "price_usd", "amount", "value_usd"
        ]].copy()
        display_df.columns = [
            "钱包地址", "区块链", "代币符号", "代币名称", "价格", "数量", "价值 (USD)"
        ]

        # 筛选器
        col1, col2 = st.columns(2)
        with col1:
            chain_filter = st.multiselect(
                "按链筛选",
                options=display_df["区块链"].unique().tolist(),
                default=[],
            )
        with col2:
            min_val_filter = st.number_input(
                "最小价值筛选",
                min_value=0.0,
                value=0.0,
                step=1.0,
            )

        # 应用筛选
        filtered_df = display_df.copy()
        if chain_filter:
            filtered_df = filtered_df[filtered_df["区块链"].isin(chain_filter)]
        if min_val_filter > 0:
            filtered_df = filtered_df[filtered_df["价值 (USD)"] >= min_val_filter]

        st.markdown(f"显示 **{len(filtered_df)}** / **{len(display_df)}** 个代币")

        st.dataframe(
            filtered_df.style.format({
                "价格": "${:.6f}",
                "数量": "{:,.4f}",
                "价值 (USD)": "${:,.2f}",
            }),
            use_container_width=True,
            height=400,
        )
    else:
        st.info("暂无代币数据")


def render_wallet_summary(data):
    """渲染钱包汇总表格。"""
    st.markdown("### 钱包汇总")

    if data.wallet_summaries:
        wallet_data = []
        for addr, summary in sorted(
            data.wallet_summaries.items(),
            key=lambda x: x[1].total_value_usd,
            reverse=True,
        ):
            wallet_data.append({
                "地址": addr,
                "总价值 (USD)": summary.total_value_usd,
                "活跃链数": len(summary.active_chains),
                "代币数量": summary.token_count,
                "所在链": ", ".join(summary.active_chains),
            })

        df = pd.DataFrame(wallet_data)

        st.dataframe(
            df.style.format({
                "总价值 (USD)": "${:,.2f}",
            }),
            use_container_width=True,
            height=400,
        )

        # 排名前20的钱包图表
        if len(df) > 0:
            st.markdown("#### 价值排名前20的钱包")
            top_df = df.head(20).copy()
            top_df["短地址"] = top_df["地址"].apply(
                lambda x: f"{x[:6]}...{x[-4:]}"
            )
            st.bar_chart(top_df.set_index("短地址")["总价值 (USD)"])
    else:
        st.info("暂无钱包数据")


def render_errors(data):
    """渲染错误表格。"""
    st.markdown("### 扫描失败的地址")

    if data.failed_addresses:
        df = pd.DataFrame(data.failed_addresses)
        df.columns = ["地址", "错误信息"]
        st.dataframe(df, use_container_width=True)
        st.warning(f"⚠️ {len(data.failed_addresses)} 个地址扫描失败")
    else:
        st.success("✅ 所有地址扫描成功！")


def main():
    """主应用入口。"""
    init_session_state()

    # 头部
    st.markdown('<p class="main-header">🔍 多链钱包扫描器</p>', unsafe_allow_html=True)
    st.markdown(
        '<p class="sub-header">使用 Moralis API 扫描 8 条区块链上的钱包资产</p>',
        unsafe_allow_html=True,
    )

    # 侧边栏
    workers, min_value = render_sidebar()

    # 使用配置的 API Key
    api_key = MORALIS_API_KEY

    # 主内容
    st.markdown("## 📝 输入钱包地址")

    # 地址输入
    addresses_text = st.text_area(
        "粘贴钱包地址（每行一个或逗号分隔）",
        height=200,
        placeholder="0x742d35Cc6634C0532925a3b844Bc9e7595f...\n0x8ba1f109551bD432803012645Hac136c...\n...",
        help="输入以太坊地址（0x...）。支持最多 1000 个地址。",
    )

    # 解析和验证地址
    addresses = parse_addresses(addresses_text)

    if addresses_text:
        st.info(f"📍 找到 **{len(addresses)}** 个有效的唯一地址")

    # 扫描按钮
    col1, col2, col3 = st.columns([1, 1, 1])

    with col2:
        scan_button = st.button(
            "🚀 开始扫描",
            type="primary",
            use_container_width=True,
            disabled=not addresses,
        )

    if not addresses:
        st.info("💡 在上方输入钱包地址以开始扫描")

    # 运行扫描
    if scan_button and addresses:
        st.markdown("---")
        st.markdown("## ⏳ 扫描中...")

        progress_bar = st.progress(0)
        status_text = st.empty()

        try:
            status_text.text(f"正在扫描 {len(addresses)} 个地址...")

            # 运行扫描
            results, _ = run_scan(addresses, api_key, workers, min_value)

            progress_bar.progress(80)

            status_text.text("正在处理结果...")

            # 处理结果
            processor = DataProcessor()
            processed_data = processor.process(results)

            progress_bar.progress(100)
            status_text.text("扫描完成！")

            # 存储到会话状态
            st.session_state.scan_results = results
            st.session_state.processed_data = processed_data

            time.sleep(1)
            st.rerun()

        except Exception as e:
            st.error(f"❌ 扫描失败: {str(e)}")
            st.exception(e)

    # 显示结果（如果有）
    if st.session_state.processed_data:
        st.markdown("---")
        render_results(st.session_state.processed_data)

        # 下载按钮
        st.markdown("---")
        st.markdown("## 📥 下载报告")

        col1, col2, col3 = st.columns([1, 1, 1])
        with col2:
            try:
                processor = DataProcessor()
                processor.processed_data = st.session_state.processed_data
                excel_data = create_excel_download(processor)

                timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
                filename = f"钱包扫描报告_{timestamp}.xlsx"

                st.download_button(
                    label="📊 下载 Excel 报告",
                    data=excel_data,
                    file_name=filename,
                    mime="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
                    use_container_width=True,
                )
            except Exception as e:
                st.error(f"生成 Excel 失败: {str(e)}")

        # 重置按钮
        col1, col2, col3 = st.columns([1, 1, 1])
        with col2:
            if st.button("🔄 新建扫描", use_container_width=True):
                st.session_state.scan_results = None
                st.session_state.processed_data = None
                st.rerun()


if __name__ == "__main__":
    main()
