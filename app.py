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
    page_title="多链钱包扫描器 | Chain Scanner",
    page_icon="⛓️",
    layout="wide",
    initial_sidebar_state="expanded",
)

# ============================================================================
# 赛博朋克/未来科技风格 CSS
# ============================================================================
st.markdown("""
<style>
    /* ===== 导入科技感字体 ===== */
    @import url('https://fonts.googleapis.com/css2?family=Orbitron:wght@400;500;600;700;800;900&family=JetBrains+Mono:wght@300;400;500;600;700&family=Rajdhani:wght@300;400;500;600;700&display=swap');

    /* ===== CSS 变量定义 ===== */
    :root {
        --bg-primary: #0a0a0f;
        --bg-secondary: #12121a;
        --bg-tertiary: #1a1a2e;
        --bg-card: rgba(20, 20, 35, 0.8);
        --bg-glass: rgba(15, 15, 25, 0.6);

        --neon-cyan: #00f5ff;
        --neon-purple: #a855f7;
        --neon-pink: #ff00ff;
        --neon-green: #00ff88;
        --neon-orange: #ff6b35;
        --neon-blue: #3b82f6;

        --text-primary: #e6edf3;
        --text-secondary: #8b949e;
        --text-muted: #6e7681;

        --glow-cyan: 0 0 20px rgba(0, 245, 255, 0.5), 0 0 40px rgba(0, 245, 255, 0.3);
        --glow-purple: 0 0 20px rgba(168, 85, 247, 0.5), 0 0 40px rgba(168, 85, 247, 0.3);
        --glow-pink: 0 0 20px rgba(255, 0, 255, 0.5), 0 0 40px rgba(255, 0, 255, 0.3);

        --border-glow: 1px solid rgba(0, 245, 255, 0.3);
        --border-subtle: 1px solid rgba(255, 255, 255, 0.1);

        --font-display: 'Orbitron', sans-serif;
        --font-body: 'JetBrains Mono', monospace;
        --font-ui: 'Rajdhani', sans-serif;
    }

    /* ===== 全局背景和动画 ===== */
    .stApp {
        background:
            linear-gradient(135deg, var(--bg-primary) 0%, var(--bg-secondary) 50%, var(--bg-tertiary) 100%);
        background-attachment: fixed;
    }

    .stApp::before {
        content: '';
        position: fixed;
        top: 0;
        left: 0;
        right: 0;
        bottom: 0;
        background-image:
            linear-gradient(rgba(0, 245, 255, 0.03) 1px, transparent 1px),
            linear-gradient(90deg, rgba(0, 245, 255, 0.03) 1px, transparent 1px);
        background-size: 50px 50px;
        pointer-events: none;
        z-index: 0;
        animation: gridPulse 4s ease-in-out infinite;
    }

    @keyframes gridPulse {
        0%, 100% { opacity: 0.5; }
        50% { opacity: 1; }
    }

    /* 扫描线效果 */
    .stApp::after {
        content: '';
        position: fixed;
        top: 0;
        left: 0;
        right: 0;
        height: 2px;
        background: linear-gradient(90deg, transparent, var(--neon-cyan), transparent);
        animation: scanLine 3s linear infinite;
        pointer-events: none;
        z-index: 9999;
    }

    @keyframes scanLine {
        0% { top: -2px; opacity: 0; }
        10% { opacity: 1; }
        90% { opacity: 1; }
        100% { top: 100vh; opacity: 0; }
    }

    /* ===== 主标题样式 ===== */
    .cyber-title {
        font-family: var(--font-display);
        font-size: 3.5rem;
        font-weight: 900;
        text-align: center;
        margin: 2rem 0 0.5rem 0;
        background: linear-gradient(135deg, var(--neon-cyan) 0%, var(--neon-purple) 50%, var(--neon-pink) 100%);
        -webkit-background-clip: text;
        -webkit-text-fill-color: transparent;
        background-clip: text;
        text-shadow: none;
        filter: drop-shadow(0 0 30px rgba(0, 245, 255, 0.5));
        letter-spacing: 0.1em;
        animation: titleGlow 2s ease-in-out infinite alternate;
    }

    @keyframes titleGlow {
        0% { filter: drop-shadow(0 0 20px rgba(0, 245, 255, 0.5)); }
        100% { filter: drop-shadow(0 0 40px rgba(168, 85, 247, 0.8)); }
    }

    .cyber-subtitle {
        font-family: var(--font-ui);
        font-size: 1.3rem;
        color: var(--text-secondary);
        text-align: center;
        margin-bottom: 2rem;
        letter-spacing: 0.3em;
        text-transform: uppercase;
    }

    /* ===== 分隔线装饰 ===== */
    .cyber-divider {
        height: 2px;
        background: linear-gradient(90deg, transparent, var(--neon-cyan), var(--neon-purple), var(--neon-pink), transparent);
        margin: 2rem 0;
        position: relative;
    }

    .cyber-divider::before {
        content: '◆';
        position: absolute;
        left: 50%;
        top: 50%;
        transform: translate(-50%, -50%);
        color: var(--neon-cyan);
        font-size: 1rem;
        background: var(--bg-primary);
        padding: 0 1rem;
        text-shadow: var(--glow-cyan);
    }

    /* ===== 区块标题样式 ===== */
    .section-header {
        font-family: var(--font-display);
        font-size: 1.5rem;
        font-weight: 700;
        color: var(--neon-cyan);
        text-shadow: var(--glow-cyan);
        margin: 1.5rem 0 1rem 0;
        padding-left: 1rem;
        border-left: 3px solid var(--neon-cyan);
        letter-spacing: 0.05em;
    }

    .section-header-purple {
        color: var(--neon-purple);
        text-shadow: var(--glow-purple);
        border-left-color: var(--neon-purple);
    }

    .section-header-pink {
        color: var(--neon-pink);
        text-shadow: var(--glow-pink);
        border-left-color: var(--neon-pink);
    }

    /* ===== 玻璃拟态卡片 ===== */
    .glass-card {
        background: var(--bg-glass);
        backdrop-filter: blur(20px);
        -webkit-backdrop-filter: blur(20px);
        border: 1px solid rgba(0, 245, 255, 0.2);
        border-radius: 16px;
        padding: 1.5rem;
        margin: 1rem 0;
        position: relative;
        overflow: hidden;
        transition: all 0.3s ease;
    }

    .glass-card::before {
        content: '';
        position: absolute;
        top: 0;
        left: -100%;
        width: 100%;
        height: 100%;
        background: linear-gradient(90deg, transparent, rgba(0, 245, 255, 0.1), transparent);
        transition: left 0.5s ease;
    }

    .glass-card:hover::before {
        left: 100%;
    }

    .glass-card:hover {
        border-color: rgba(0, 245, 255, 0.5);
        box-shadow: 0 0 30px rgba(0, 245, 255, 0.2);
    }

    /* ===== 指标卡片 ===== */
    .metric-card {
        background: linear-gradient(145deg, var(--bg-card) 0%, rgba(30, 30, 50, 0.9) 100%);
        border: 1px solid rgba(0, 245, 255, 0.3);
        border-radius: 12px;
        padding: 1.5rem;
        text-align: center;
        position: relative;
        overflow: hidden;
        transition: all 0.3s ease;
    }

    .metric-card::after {
        content: '';
        position: absolute;
        top: 0;
        left: 0;
        right: 0;
        height: 3px;
        background: linear-gradient(90deg, var(--neon-cyan), var(--neon-purple));
    }

    .metric-card:hover {
        transform: translateY(-5px);
        box-shadow: 0 10px 40px rgba(0, 245, 255, 0.3);
        border-color: var(--neon-cyan);
    }

    .metric-value {
        font-family: var(--font-display);
        font-size: 2.5rem;
        font-weight: 700;
        color: var(--neon-cyan);
        text-shadow: var(--glow-cyan);
        margin-bottom: 0.5rem;
    }

    .metric-value-purple {
        color: var(--neon-purple);
        text-shadow: var(--glow-purple);
    }

    .metric-value-green {
        color: var(--neon-green);
        text-shadow: 0 0 20px rgba(0, 255, 136, 0.5);
    }

    .metric-value-orange {
        color: var(--neon-orange);
        text-shadow: 0 0 20px rgba(255, 107, 53, 0.5);
    }

    .metric-label {
        font-family: var(--font-ui);
        font-size: 0.9rem;
        color: var(--text-secondary);
        text-transform: uppercase;
        letter-spacing: 0.1em;
    }

    /* ===== 链徽章 ===== */
    .chain-badge {
        display: inline-block;
        padding: 0.4rem 0.8rem;
        margin: 0.2rem;
        border-radius: 20px;
        font-family: var(--font-body);
        font-size: 0.75rem;
        font-weight: 600;
        background: linear-gradient(135deg, rgba(0, 245, 255, 0.1) 0%, rgba(168, 85, 247, 0.1) 100%);
        border: 1px solid rgba(0, 245, 255, 0.3);
        color: var(--neon-cyan);
        transition: all 0.3s ease;
        cursor: default;
    }

    .chain-badge:hover {
        background: linear-gradient(135deg, rgba(0, 245, 255, 0.2) 0%, rgba(168, 85, 247, 0.2) 100%);
        box-shadow: 0 0 15px rgba(0, 245, 255, 0.4);
        transform: scale(1.05);
    }

    /* ===== 侧边栏样式 ===== */
    section[data-testid="stSidebar"] {
        background: linear-gradient(180deg, var(--bg-secondary) 0%, var(--bg-primary) 100%);
        border-right: 1px solid rgba(0, 245, 255, 0.2);
    }

    section[data-testid="stSidebar"]::before {
        content: '';
        position: absolute;
        top: 0;
        left: 0;
        right: 0;
        height: 3px;
        background: linear-gradient(90deg, var(--neon-cyan), var(--neon-purple), var(--neon-pink));
    }

    .sidebar-title {
        font-family: var(--font-display);
        font-size: 1.2rem;
        font-weight: 700;
        color: var(--neon-cyan);
        text-shadow: var(--glow-cyan);
        margin-bottom: 1rem;
        padding-bottom: 0.5rem;
        border-bottom: 1px solid rgba(0, 245, 255, 0.3);
    }

    /* ===== 输入框样式 ===== */
    .stTextArea textarea, .stTextInput input, .stNumberInput input {
        background: var(--bg-card) !important;
        border: 1px solid rgba(0, 245, 255, 0.3) !important;
        border-radius: 8px !important;
        color: var(--text-primary) !important;
        font-family: var(--font-body) !important;
        transition: all 0.3s ease !important;
    }

    .stTextArea textarea:focus, .stTextInput input:focus, .stNumberInput input:focus {
        border-color: var(--neon-cyan) !important;
        box-shadow: 0 0 20px rgba(0, 245, 255, 0.3) !important;
    }

    .stTextArea textarea::placeholder {
        color: var(--text-muted) !important;
    }

    /* ===== 按钮样式 ===== */
    .stButton > button {
        font-family: var(--font-display) !important;
        font-weight: 600 !important;
        letter-spacing: 0.1em !important;
        text-transform: uppercase !important;
        background: linear-gradient(135deg, var(--neon-cyan) 0%, var(--neon-purple) 100%) !important;
        border: none !important;
        border-radius: 8px !important;
        padding: 0.75rem 2rem !important;
        color: var(--bg-primary) !important;
        transition: all 0.3s ease !important;
        position: relative !important;
        overflow: hidden !important;
    }

    .stButton > button:hover {
        transform: translateY(-2px) !important;
        box-shadow: 0 10px 40px rgba(0, 245, 255, 0.4) !important;
    }

    .stButton > button:active {
        transform: translateY(0) !important;
    }

    .stButton > button[kind="primary"] {
        background: linear-gradient(135deg, var(--neon-cyan) 0%, var(--neon-blue) 100%) !important;
    }

    /* 下载按钮特殊样式 */
    .stDownloadButton > button {
        font-family: var(--font-display) !important;
        font-weight: 600 !important;
        letter-spacing: 0.05em !important;
        background: linear-gradient(135deg, var(--neon-green) 0%, var(--neon-cyan) 100%) !important;
        border: none !important;
        border-radius: 8px !important;
        color: var(--bg-primary) !important;
    }

    .stDownloadButton > button:hover {
        box-shadow: 0 10px 40px rgba(0, 255, 136, 0.4) !important;
    }

    /* ===== 进度条样式 ===== */
    .stProgress > div > div > div > div {
        background: linear-gradient(90deg, var(--neon-cyan), var(--neon-purple), var(--neon-pink)) !important;
        box-shadow: 0 0 20px rgba(0, 245, 255, 0.5) !important;
        animation: progressGlow 1s ease-in-out infinite alternate !important;
    }

    @keyframes progressGlow {
        0% { box-shadow: 0 0 10px rgba(0, 245, 255, 0.5); }
        100% { box-shadow: 0 0 30px rgba(168, 85, 247, 0.8); }
    }

    /* ===== 标签页样式 ===== */
    .stTabs [data-baseweb="tab-list"] {
        background: var(--bg-card);
        border-radius: 12px;
        padding: 0.5rem;
        gap: 0.5rem;
        border: 1px solid rgba(0, 245, 255, 0.2);
    }

    .stTabs [data-baseweb="tab"] {
        font-family: var(--font-ui) !important;
        font-weight: 600 !important;
        letter-spacing: 0.05em !important;
        color: var(--text-secondary) !important;
        border-radius: 8px !important;
        padding: 0.75rem 1.5rem !important;
        transition: all 0.3s ease !important;
    }

    .stTabs [data-baseweb="tab"]:hover {
        color: var(--neon-cyan) !important;
        background: rgba(0, 245, 255, 0.1) !important;
    }

    .stTabs [aria-selected="true"] {
        background: linear-gradient(135deg, rgba(0, 245, 255, 0.2) 0%, rgba(168, 85, 247, 0.2) 100%) !important;
        color: var(--neon-cyan) !important;
        border: 1px solid rgba(0, 245, 255, 0.5) !important;
    }

    /* ===== 数据表格样式 ===== */
    .stDataFrame {
        border: 1px solid rgba(0, 245, 255, 0.2) !important;
        border-radius: 12px !important;
        overflow: hidden !important;
    }

    .stDataFrame [data-testid="stDataFrameResizable"] {
        background: var(--bg-card) !important;
    }

    /* ===== 滑块样式 ===== */
    .stSlider [data-baseweb="slider"] [data-testid="stThumbValue"] {
        color: var(--neon-cyan) !important;
        font-family: var(--font-body) !important;
    }

    .stSlider [data-baseweb="slider"] div[role="slider"] {
        background: var(--neon-cyan) !important;
        box-shadow: 0 0 15px rgba(0, 245, 255, 0.5) !important;
    }

    /* ===== 多选框样式 ===== */
    .stMultiSelect [data-baseweb="tag"] {
        background: linear-gradient(135deg, rgba(0, 245, 255, 0.2) 0%, rgba(168, 85, 247, 0.2) 100%) !important;
        border: 1px solid rgba(0, 245, 255, 0.5) !important;
        color: var(--neon-cyan) !important;
    }

    /* ===== 提示框样式 ===== */
    .stAlert {
        background: var(--bg-card) !important;
        border: 1px solid rgba(0, 245, 255, 0.3) !important;
        border-radius: 12px !important;
        font-family: var(--font-body) !important;
    }

    [data-testid="stAlertContentInfo"] {
        color: var(--neon-cyan) !important;
    }

    [data-testid="stAlertContentWarning"] {
        color: var(--neon-orange) !important;
    }

    [data-testid="stAlertContentError"] {
        color: var(--neon-pink) !important;
    }

    [data-testid="stAlertContentSuccess"] {
        color: var(--neon-green) !important;
    }

    /* ===== 指标组件样式 ===== */
    [data-testid="stMetric"] {
        background: var(--bg-card);
        border: 1px solid rgba(0, 245, 255, 0.2);
        border-radius: 12px;
        padding: 1rem;
        transition: all 0.3s ease;
    }

    [data-testid="stMetric"]:hover {
        border-color: var(--neon-cyan);
        box-shadow: 0 0 20px rgba(0, 245, 255, 0.2);
    }

    [data-testid="stMetricValue"] {
        font-family: var(--font-display) !important;
        color: var(--neon-cyan) !important;
        text-shadow: var(--glow-cyan);
    }

    [data-testid="stMetricLabel"] {
        font-family: var(--font-ui) !important;
        color: var(--text-secondary) !important;
        text-transform: uppercase !important;
        letter-spacing: 0.1em !important;
    }

    /* ===== 柱状图样式 ===== */
    .stBarChart {
        background: var(--bg-card);
        border: 1px solid rgba(0, 245, 255, 0.2);
        border-radius: 12px;
        padding: 1rem;
    }

    /* ===== 分隔线 ===== */
    hr {
        border: none;
        height: 1px;
        background: linear-gradient(90deg, transparent, rgba(0, 245, 255, 0.3), transparent);
        margin: 2rem 0;
    }

    /* ===== 滚动条样式 ===== */
    ::-webkit-scrollbar {
        width: 8px;
        height: 8px;
    }

    ::-webkit-scrollbar-track {
        background: var(--bg-secondary);
    }

    ::-webkit-scrollbar-thumb {
        background: linear-gradient(180deg, var(--neon-cyan), var(--neon-purple));
        border-radius: 4px;
    }

    ::-webkit-scrollbar-thumb:hover {
        background: linear-gradient(180deg, var(--neon-purple), var(--neon-pink));
    }

    /* ===== 加载动画 ===== */
    .scanning-animation {
        display: flex;
        justify-content: center;
        align-items: center;
        gap: 0.5rem;
        margin: 2rem 0;
    }

    .scan-dot {
        width: 12px;
        height: 12px;
        border-radius: 50%;
        background: var(--neon-cyan);
        animation: scanPulse 1.4s ease-in-out infinite;
        box-shadow: 0 0 20px var(--neon-cyan);
    }

    .scan-dot:nth-child(2) {
        animation-delay: 0.2s;
        background: var(--neon-purple);
        box-shadow: 0 0 20px var(--neon-purple);
    }

    .scan-dot:nth-child(3) {
        animation-delay: 0.4s;
        background: var(--neon-pink);
        box-shadow: 0 0 20px var(--neon-pink);
    }

    @keyframes scanPulse {
        0%, 80%, 100% { transform: scale(0.6); opacity: 0.5; }
        40% { transform: scale(1); opacity: 1; }
    }

    /* ===== 状态文本动画 ===== */
    .status-text {
        font-family: var(--font-body);
        color: var(--neon-cyan);
        text-align: center;
        animation: statusBlink 1s ease-in-out infinite;
    }

    @keyframes statusBlink {
        0%, 100% { opacity: 1; }
        50% { opacity: 0.5; }
    }

    /* ===== 隐藏默认 Streamlit 元素 ===== */
    #MainMenu {visibility: hidden;}
    footer {visibility: hidden;}
    header {visibility: hidden;}

    /* ===== 响应式调整 ===== */
    @media (max-width: 768px) {
        .cyber-title {
            font-size: 2rem;
        }
        .cyber-subtitle {
            font-size: 0.9rem;
            letter-spacing: 0.15em;
        }
        .metric-value {
            font-size: 1.8rem;
        }
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
    st.sidebar.markdown('<p class="sidebar-title">⚙️ 系统配置</p>', unsafe_allow_html=True)

    # 扫描设置
    st.sidebar.markdown("### 🔧 扫描参数")

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

    st.sidebar.markdown('<div class="cyber-divider"></div>', unsafe_allow_html=True)

    # 支持的链信息
    st.sidebar.markdown("### 🔗 支持的区块链")
    chains_html = '<div style="display: flex; flex-wrap: wrap; gap: 0.3rem;">'
    for chain_id, chain_name in SUPPORTED_CHAINS.items():
        chains_html += f'<span class="chain-badge">{chain_name}</span>'
    chains_html += '</div>'
    st.sidebar.markdown(chains_html, unsafe_allow_html=True)

    st.sidebar.markdown('<div class="cyber-divider"></div>', unsafe_allow_html=True)

    # 提示信息
    st.sidebar.markdown("""
    <div class="glass-card" style="padding: 1rem; margin-top: 1rem;">
        <p style="color: var(--neon-cyan); margin: 0; font-size: 0.85rem;">
            💡 <strong>智能扫描</strong><br>
            <span style="color: var(--text-secondary); font-size: 0.8rem;">
                系统会先检测钱包活跃链，优化 API 调用
            </span>
        </p>
    </div>
    """, unsafe_allow_html=True)

    return workers, min_value


def render_results(processed_data):
    """渲染扫描结果。"""
    data = processed_data

    # 结果标题
    st.markdown('<p class="section-header">📊 扫描结果</p>', unsafe_allow_html=True)

    # 汇总指标 - 使用自定义HTML
    st.markdown("""
    <div style="display: grid; grid-template-columns: repeat(5, 1fr); gap: 1rem; margin: 1.5rem 0;">
    """, unsafe_allow_html=True)

    col1, col2, col3, col4, col5 = st.columns(5)

    with col1:
        st.markdown(f"""
        <div class="metric-card">
            <div class="metric-value">{data.total_wallets}</div>
            <div class="metric-label">钱包总数</div>
        </div>
        """, unsafe_allow_html=True)
    with col2:
        st.markdown(f"""
        <div class="metric-card">
            <div class="metric-value metric-value-green">{data.successful_scans}</div>
            <div class="metric-label">扫描成功</div>
        </div>
        """, unsafe_allow_html=True)
    with col3:
        st.markdown(f"""
        <div class="metric-card">
            <div class="metric-value metric-value-orange">{data.failed_scans}</div>
            <div class="metric-label">扫描失败</div>
        </div>
        """, unsafe_allow_html=True)
    with col4:
        st.markdown(f"""
        <div class="metric-card">
            <div class="metric-value metric-value-purple">${data.total_value_usd:,.2f}</div>
            <div class="metric-label">总价值 USD</div>
        </div>
        """, unsafe_allow_html=True)
    with col5:
        st.markdown(f"""
        <div class="metric-card">
            <div class="metric-value">{data.total_tokens}</div>
            <div class="metric-label">代币持仓</div>
        </div>
        """, unsafe_allow_html=True)

    st.markdown('<div class="cyber-divider"></div>', unsafe_allow_html=True)

    # 不同视图的标签页 - 默认显示全部代币
    tab1, tab2, tab3, tab4 = st.tabs([
        "🪙 全部代币",
        "📈 链分布",
        "👛 钱包汇总",
        "❌ 错误日志"
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
    st.markdown('<p class="section-header section-header-purple">📊 各链价值分布</p>', unsafe_allow_html=True)

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
            st.markdown('<p class="section-header" style="font-size: 1.1rem;">💎 链占比</p>', unsafe_allow_html=True)
            total = df["价值 (USD)"].sum()
            for _, row in df.iterrows():
                pct = (row["价值 (USD)"] / total) * 100
                st.markdown(f"""
                <div style="margin: 0.5rem 0; padding: 0.5rem; background: var(--bg-card); border-radius: 8px; border-left: 3px solid var(--neon-cyan);">
                    <span style="color: var(--neon-cyan); font-weight: 600;">{row['区块链']}</span><br>
                    <span style="color: var(--text-secondary); font-size: 0.85rem;">${row['价值 (USD)']:,.2f} ({pct:.1f}%)</span>
                </div>
                """, unsafe_allow_html=True)

        # 表格
        st.markdown('<p class="section-header" style="font-size: 1.1rem; margin-top: 2rem;">📋 详细统计</p>', unsafe_allow_html=True)
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
    st.markdown('<p class="section-header">🪙 全部代币持仓</p>', unsafe_allow_html=True)

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
                "🔗 按链筛选",
                options=display_df["区块链"].unique().tolist(),
                default=[],
            )
        with col2:
            min_val_filter = st.number_input(
                "💰 最小价值筛选",
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

        st.markdown(f"""
        <div style="margin: 1rem 0; padding: 0.75rem; background: var(--bg-card); border-radius: 8px; border: 1px solid rgba(0, 245, 255, 0.2);">
            <span style="color: var(--text-secondary);">显示</span>
            <span style="color: var(--neon-cyan); font-weight: 600;">{len(filtered_df)}</span>
            <span style="color: var(--text-secondary);">/</span>
            <span style="color: var(--neon-purple); font-weight: 600;">{len(display_df)}</span>
            <span style="color: var(--text-secondary);">个代币</span>
        </div>
        """, unsafe_allow_html=True)

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
    st.markdown('<p class="section-header section-header-pink">👛 钱包汇总</p>', unsafe_allow_html=True)

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
            st.markdown('<p class="section-header" style="font-size: 1.1rem; margin-top: 2rem;">🏆 价值排名 TOP 20</p>', unsafe_allow_html=True)
            top_df = df.head(20).copy()
            top_df["短地址"] = top_df["地址"].apply(
                lambda x: f"{x[:6]}...{x[-4:]}"
            )
            st.bar_chart(top_df.set_index("短地址")["总价值 (USD)"])
    else:
        st.info("暂无钱包数据")


def render_errors(data):
    """渲染错误表格。"""
    st.markdown('<p class="section-header section-header-pink">❌ 扫描失败记录</p>', unsafe_allow_html=True)

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
    st.markdown('<h1 class="cyber-title">⛓️ CHAIN SCANNER</h1>', unsafe_allow_html=True)
    st.markdown('<p class="cyber-subtitle">多链钱包资产扫描系统 · Powered by Moralis</p>', unsafe_allow_html=True)
    st.markdown('<div class="cyber-divider"></div>', unsafe_allow_html=True)

    # 侧边栏
    workers, min_value = render_sidebar()

    # 使用配置的 API Key
    api_key = MORALIS_API_KEY

    # 主内容
    st.markdown('<p class="section-header">📝 输入钱包地址</p>', unsafe_allow_html=True)

    # 地址输入
    addresses_text = st.text_area(
        "粘贴钱包地址（每行一个或逗号分隔）",
        height=200,
        placeholder="0x742d35Cc6634C0532925a3b844Bc9e7595f...\n0x8ba1f109551bD432803012645Hac136c...\n...",
        help="输入以太坊地址（0x...）。支持最多 1000 个地址。",
        label_visibility="collapsed",
    )

    # 解析和验证地址
    addresses = parse_addresses(addresses_text)

    if addresses_text:
        st.markdown(f"""
        <div class="glass-card" style="padding: 1rem; text-align: center;">
            <span style="color: var(--neon-cyan);">📍 检测到</span>
            <span style="color: var(--neon-purple); font-size: 1.5rem; font-weight: 700; margin: 0 0.5rem;">{len(addresses)}</span>
            <span style="color: var(--neon-cyan);">个有效地址</span>
        </div>
        """, unsafe_allow_html=True)

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
        st.markdown("""
        <div style="text-align: center; margin: 2rem 0; color: var(--text-secondary);">
            💡 在上方输入钱包地址以开始扫描
        </div>
        """, unsafe_allow_html=True)

    # 运行扫描
    if scan_button and addresses:
        st.markdown('<div class="cyber-divider"></div>', unsafe_allow_html=True)
        st.markdown('<p class="section-header">⏳ 正在扫描</p>', unsafe_allow_html=True)

        # 扫描动画
        st.markdown("""
        <div class="scanning-animation">
            <div class="scan-dot"></div>
            <div class="scan-dot"></div>
            <div class="scan-dot"></div>
        </div>
        """, unsafe_allow_html=True)

        progress_bar = st.progress(0)
        status_text = st.empty()

        try:
            status_text.markdown(f'<p class="status-text">正在扫描 {len(addresses)} 个地址...</p>', unsafe_allow_html=True)

            # 运行扫描
            results, _ = run_scan(addresses, api_key, workers, min_value)

            progress_bar.progress(80)

            status_text.markdown('<p class="status-text">正在处理结果...</p>', unsafe_allow_html=True)

            # 处理结果
            processor = DataProcessor()
            processed_data = processor.process(results)

            progress_bar.progress(100)
            status_text.markdown('<p class="status-text" style="color: var(--neon-green);">✓ 扫描完成！</p>', unsafe_allow_html=True)

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
        st.markdown('<div class="cyber-divider"></div>', unsafe_allow_html=True)
        render_results(st.session_state.processed_data)

        # 下载按钮
        st.markdown('<div class="cyber-divider"></div>', unsafe_allow_html=True)
        st.markdown('<p class="section-header section-header-purple">📥 导出报告</p>', unsafe_allow_html=True)

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
