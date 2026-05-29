"""Crypto Trading Indicator — Streamlit dashboard.

Run with:  streamlit run app.py
"""
from __future__ import annotations

import json
import time
from concurrent.futures import ThreadPoolExecutor
from datetime import datetime, timezone
from pathlib import Path

import pandas as pd
import plotly.graph_objects as go
import streamlit as st
import streamlit.components.v1 as components
from plotly.subplots import make_subplots

import alerts
import binance_client
import breakout
import btc_outlook
import config
import derivatives
import btc_dominance
import coin_metrics_onchain
import cup_and_handle
import defillama_tvl
import derivatives_velocity
import early_momentum
import forecast
import fred_macro
import long_patterns
import market_regime
import pattern_scout
import recovery_detector
import reversal_approach
# rs_vs_btc imported under its alias below so picks-board cached helpers
# can stay grouped with the other Phase A/B scoring helpers.
import rs_vs_btc
import tokenomics_unlocks
import indicators
import lunarcrush
import market_context
import news as news_mod
import news_impact
import oracle
import orderflow
import live_broker as lb
import paper_bot
import sentiment as sentiment_mod
import signals
import social as social_mod
import spot_signals
import tv_analysis

st.set_page_config(
    page_title="Crypto Trading Indicator",
    page_icon="📈",
    layout="wide",
)

st.markdown(
    """
    <style>
    @import url('https://fonts.googleapis.com/css2?family=Inter:wght@400;500;600;700;800;900&family=Space+Grotesk:wght@500;600;700&display=swap');

    /* ============================================================
       GOODCRYPTO-INSPIRED DESIGN SYSTEM
       Deep navy + electric blue, layered depth, glassmorphism,
       bold typography, premium SaaS feel.
       ============================================================ */

    :root {
        --bg-primary:    #060818;
        --bg-secondary:  #0a0e27;
        --bg-tertiary:   #11152e;
        --bg-card:       rgba(20, 24, 56, 0.5);
        --bg-card-hover: rgba(28, 34, 72, 0.7);

        --accent-primary:   #00d4ff;
        --accent-secondary: #5b8eff;
        --accent-purple:    #8b5cf6;
        --accent-gradient:  linear-gradient(135deg, #00d4ff, #5b8eff);

        --text-primary:   #f1f5ff;
        --text-secondary: #a8b3d4;
        --text-muted:     #6b7494;
        --text-dim:       #4a5378;

        --success: #00e676;
        --danger:  #ff3d57;
        --warning: #ffb547;

        --border-subtle: rgba(150, 180, 255, 0.06);
        --border-soft:   rgba(150, 180, 255, 0.12);
        --border-strong: rgba(150, 180, 255, 0.22);

        --glow-blue:   0 0 24px rgba(0, 212, 255, 0.25);
        --glow-purple: 0 0 24px rgba(139, 92, 246, 0.25);
    }

    html, body, .stApp, [class*="css"], [data-testid="stMarkdownContainer"] {
        font-family: 'Inter', -apple-system, BlinkMacSystemFont, sans-serif;
    }

    /* === Canvas: layered depth like GoodCrypto =================== */
    .stApp {
        background:
            /* Top accent glow */
            radial-gradient(1400px 700px at 30% -20%,
                            rgba(0, 212, 255, 0.10), transparent 70%),
            /* Right accent glow */
            radial-gradient(900px 500px at 90% 10%,
                            rgba(91, 142, 255, 0.08), transparent 60%),
            /* Subtle grid pattern */
            linear-gradient(rgba(150, 180, 255, 0.025) 1px, transparent 1px),
            linear-gradient(90deg, rgba(150, 180, 255, 0.025) 1px, transparent 1px),
            var(--bg-primary);
        background-size: auto, auto, 60px 60px, 60px 60px, auto;
        background-attachment: fixed;
    }
    [data-testid="stHeader"] { background: transparent; }
    div.block-container {
        padding-top: 2.6rem;
        max-width: 1500px;
    }

    /* === Typography — bolder, more dramatic ====================== */
    h1, h2, h3, h4 {
        color: var(--text-primary);
        letter-spacing: -0.022em;
        font-family: 'Inter', sans-serif;
    }
    h1 {
        font-weight: 900;
        font-size: 2.4rem;
        background: linear-gradient(135deg, #ffffff 0%, #a8b3d4 100%);
        -webkit-background-clip: text;
        -webkit-text-fill-color: transparent;
        background-clip: text;
    }
    h2 {
        font-weight: 800;
        font-size: 1.65rem;
        margin-top: 1.2rem;
    }
    h3 {
        font-weight: 700;
        font-size: 1.2rem;
        margin-top: 1rem;
        padding-left: 14px;
        border-left: 3px solid var(--accent-primary);
        position: relative;
    }
    h3::before {
        content: "";
        position: absolute;
        left: -3px; top: 0; bottom: 0; width: 3px;
        background: var(--accent-primary);
        box-shadow: 0 0 12px rgba(0, 212, 255, 0.6);
    }
    h4 {
        font-weight: 700;
        font-size: 1.02rem;
        color: var(--text-secondary);
        margin-top: 0.6rem;
    }
    p, [data-testid="stCaptionContainer"] {
        color: var(--text-secondary);
    }

    /* === Metric cards: glassmorphism ============================ */
    [data-testid="stMetric"] {
        background: var(--bg-card);
        backdrop-filter: blur(12px);
        -webkit-backdrop-filter: blur(12px);
        border: 1px solid var(--border-soft);
        border-radius: 14px;
        padding: 16px 20px;
        transition: all .22s cubic-bezier(0.4, 0, 0.2, 1);
        position: relative;
        overflow: hidden;
    }
    [data-testid="stMetric"]::before {
        content: "";
        position: absolute;
        top: 0; left: 0; right: 0;
        height: 1px;
        background: linear-gradient(90deg,
            transparent, var(--accent-primary), transparent);
        opacity: 0;
        transition: opacity .25s ease;
    }
    [data-testid="stMetric"]:hover {
        border-color: var(--border-strong);
        background: var(--bg-card-hover);
        transform: translateY(-2px);
        box-shadow: 0 8px 28px rgba(0, 212, 255, 0.10);
    }
    [data-testid="stMetric"]:hover::before {
        opacity: 1;
    }
    [data-testid="stMetricValue"] {
        font-size: 1.65rem;
        font-weight: 800;
        color: var(--text-primary);
        font-family: 'Space Grotesk', 'Inter', sans-serif;
        letter-spacing: -0.02em;
    }
    [data-testid="stMetricLabel"] {
        opacity: 0.7;
        text-transform: uppercase;
        font-size: 0.66rem;
        letter-spacing: 0.10em;
        font-weight: 700;
        color: var(--text-muted);
    }
    [data-testid="stMetricDelta"] {
        font-size: 0.8rem;
        font-weight: 600;
    }

    /* === Panels (st.container border) — glass effect ============ */
    div[data-testid="stVerticalBlockBorderWrapper"] {
        background: var(--bg-card);
        backdrop-filter: blur(10px);
        -webkit-backdrop-filter: blur(10px);
        border: 1px solid var(--border-soft);
        border-radius: 16px;
        transition: all .22s ease;
    }
    div[data-testid="stVerticalBlockBorderWrapper"]:hover {
        border-color: var(--border-strong);
    }

    /* === Tabs — accent underline ================================ */
    [data-testid="stTabs"] [data-baseweb="tab-list"] {
        gap: 6px;
        border-bottom: 1px solid var(--border-subtle);
    }
    [data-testid="stTabs"] [data-baseweb="tab"] {
        border-radius: 11px 11px 0 0;
        padding: 10px 22px;
        transition: all .15s ease;
    }
    [data-testid="stTabs"] [data-baseweb="tab"] p {
        font-weight: 600;
        font-size: 0.94rem;
    }
    [data-testid="stTabs"] [data-baseweb="tab"]:hover {
        background: rgba(0, 212, 255, 0.05);
    }
    [data-testid="stTabs"] [aria-selected="true"] {
        background: linear-gradient(180deg,
            rgba(0, 212, 255, 0.10), transparent);
        border-bottom: 2px solid var(--accent-primary);
        box-shadow: 0 -3px 12px rgba(0, 212, 255, 0.15) inset;
    }

    /* === Sidebar — slightly darker for depth ==================== */
    [data-testid="stSidebar"] {
        background:
            linear-gradient(180deg,
                rgba(0, 212, 255, 0.03) 0%, transparent 30%),
            #060818;
        border-right: 1px solid var(--border-subtle);
    }
    [data-testid="stSidebar"] [data-testid="stMarkdownContainer"] h1 {
        font-size: 1.4rem;
        background: linear-gradient(135deg, #00d4ff, #5b8eff);
        -webkit-background-clip: text;
        -webkit-text-fill-color: transparent;
        background-clip: text;
    }

    /* === Buttons — premium electric-blue accent ================= */
    .stButton button {
        border-radius: 11px;
        font-weight: 600;
        font-size: 0.92rem;
        border: 1px solid var(--border-soft);
        background: var(--bg-card);
        backdrop-filter: blur(8px);
        color: var(--text-primary);
        padding: 8px 18px;
        transition: all .18s cubic-bezier(0.4, 0, 0.2, 1);
        position: relative;
        overflow: hidden;
    }
    .stButton button:hover {
        border-color: var(--accent-primary);
        color: var(--accent-primary);
        background: rgba(0, 212, 255, 0.08);
        transform: translateY(-1px);
        box-shadow: 0 4px 16px rgba(0, 212, 255, 0.15);
    }
    .stButton button:active {
        transform: translateY(0);
    }
    /* Primary buttons (when type="primary") get the gradient */
    .stButton button[kind="primary"] {
        background: var(--accent-gradient);
        border: none;
        color: #001122;
        font-weight: 700;
        box-shadow: 0 4px 18px rgba(0, 212, 255, 0.25);
    }
    .stButton button[kind="primary"]:hover {
        box-shadow: 0 6px 24px rgba(0, 212, 255, 0.40);
        transform: translateY(-2px);
    }

    /* === Form inputs ============================================ */
    [data-testid="stTextInput"] input,
    [data-testid="stNumberInput"] input,
    [data-baseweb="select"] > div,
    [data-baseweb="input"] > div {
        background: var(--bg-card) !important;
        border: 1px solid var(--border-soft) !important;
        border-radius: 10px !important;
        color: var(--text-primary) !important;
        transition: border-color .18s ease;
    }
    [data-testid="stTextInput"] input:focus,
    [data-testid="stNumberInput"] input:focus,
    [data-baseweb="select"] > div:focus-within,
    [data-baseweb="input"] > div:focus-within {
        border-color: var(--accent-primary) !important;
        box-shadow: 0 0 0 3px rgba(0, 212, 255, 0.12) !important;
    }

    /* === Expanders =============================================== */
    [data-testid="stExpander"] {
        border: 1px solid var(--border-soft);
        border-radius: 13px;
        background: var(--bg-card);
        backdrop-filter: blur(8px);
        overflow: hidden;
    }
    [data-testid="stExpander"] > details > summary {
        font-weight: 600;
        padding: 14px 18px !important;
    }
    [data-testid="stExpander"] > details > summary:hover {
        background: rgba(0, 212, 255, 0.04);
    }

    /* === DataFrames ============================================= */
    [data-testid="stDataFrame"] {
        border-radius: 12px;
        border: 1px solid var(--border-soft);
        overflow: hidden;
    }

    /* === Progress bars — electric blue ========================== */
    [data-testid="stProgress"] div[role="progressbar"] {
        background: rgba(150, 180, 255, 0.06);
        border-radius: 5px;
    }
    [data-testid="stProgress"] div[role="progressbar"] > div {
        background: var(--accent-gradient);
        box-shadow: 0 0 12px rgba(0, 212, 255, 0.5);
    }

    /* === Sliders ================================================ */
    [data-testid="stSlider"] [role="slider"] {
        background: var(--accent-primary);
        box-shadow: 0 0 12px rgba(0, 212, 255, 0.5);
    }

    /* === Checkboxes / radio ===================================== */
    [data-testid="stCheckbox"] svg[data-baseweb="icon"],
    [data-testid="stRadio"] svg[data-baseweb="icon"] {
        color: var(--accent-primary);
    }

    /* === Dividers — subtle gradient ============================= */
    hr {
        border: none;
        height: 1px;
        background: linear-gradient(90deg,
            transparent, var(--border-soft), transparent);
        margin: 1.2rem 0;
    }

    /* === Scrollbars ============================================= */
    ::-webkit-scrollbar { width: 10px; height: 10px; }
    ::-webkit-scrollbar-thumb {
        background: linear-gradient(180deg, #3a4373, #2a3258);
        border-radius: 6px;
        border: 2px solid var(--bg-primary);
    }
    ::-webkit-scrollbar-thumb:hover {
        background: linear-gradient(180deg, var(--accent-primary), #5b8eff);
    }
    ::-webkit-scrollbar-track { background: transparent; }

    /* ============================================================
       HERO REGIME BANNER — premium glass card
       ============================================================ */
    .regime-hero {
        background:
            linear-gradient(135deg,
                rgba(0, 212, 255, 0.08) 0%,
                rgba(91, 142, 255, 0.04) 50%,
                transparent 100%),
            var(--bg-card);
        backdrop-filter: blur(20px);
        -webkit-backdrop-filter: blur(20px);
        border: 1px solid var(--border-soft);
        border-radius: 20px;
        padding: 24px 28px;
        margin-bottom: 22px;
        position: relative;
        overflow: hidden;
        transition: all .25s cubic-bezier(0.4, 0, 0.2, 1);
    }
    .regime-hero::before {
        content: "";
        position: absolute;
        top: 0; left: 0; right: 0;
        height: 3px;
        background: linear-gradient(90deg,
            var(--regime-accent, var(--accent-primary)),
            transparent);
        box-shadow: 0 0 24px var(--regime-accent, var(--accent-primary));
    }
    .regime-hero::after {
        content: "";
        position: absolute;
        top: -50%; right: -10%;
        width: 400px; height: 400px;
        background: radial-gradient(circle,
            var(--regime-accent, var(--accent-primary)) 0%,
            transparent 70%);
        opacity: 0.07;
        pointer-events: none;
    }
    .regime-hero:hover {
        border-color: var(--border-strong);
        transform: translateY(-2px);
        box-shadow: 0 12px 36px rgba(0, 212, 255, 0.12);
    }
    .regime-hero-title {
        font-size: 1.45rem;
        font-weight: 800;
        letter-spacing: -0.025em;
        display: flex;
        align-items: center;
        gap: 12px;
        font-family: 'Space Grotesk', 'Inter', sans-serif;
    }
    .regime-hero-sub {
        color: var(--text-secondary);
        font-size: 0.86rem;
        margin-top: 8px;
        line-height: 1.6;
    }
    .regime-hero-stats {
        display: flex;
        gap: 14px;
        margin-top: 16px;
        flex-wrap: wrap;
    }
    .regime-stat {
        display: flex;
        flex-direction: column;
        padding: 10px 16px;
        background: rgba(0, 212, 255, 0.04);
        border-radius: 11px;
        border: 1px solid var(--border-soft);
        min-width: 100px;
        transition: all .18s ease;
    }
    .regime-stat:hover {
        background: rgba(0, 212, 255, 0.08);
        border-color: var(--border-strong);
    }
    .regime-stat-label {
        font-size: 0.62rem;
        text-transform: uppercase;
        letter-spacing: 0.10em;
        color: var(--text-muted);
        font-weight: 700;
    }
    .regime-stat-value {
        font-size: 1.05rem;
        font-weight: 800;
        color: var(--text-primary);
        margin-top: 3px;
        font-family: 'Space Grotesk', 'Inter', sans-serif;
        letter-spacing: -0.015em;
    }

    /* === Bias bars — glowing electric ============================ */
    .bias-bar {
        display: flex;
        align-items: center;
        gap: 12px;
        margin-top: 12px;
    }
    .bias-track {
        flex: 1;
        height: 10px;
        background: rgba(150, 180, 255, 0.04);
        border-radius: 6px;
        overflow: hidden;
        position: relative;
        border: 1px solid var(--border-subtle);
    }
    .bias-fill-long {
        height: 100%;
        background: linear-gradient(90deg, #00b85e, #00e676);
        border-radius: 6px;
        transition: width .6s cubic-bezier(0.4, 0, 0.2, 1);
        box-shadow: 0 0 12px rgba(0, 230, 118, 0.4) inset;
    }
    .bias-fill-short {
        height: 100%;
        background: linear-gradient(90deg, #d62845, #ff3d57);
        border-radius: 6px;
        transition: width .6s cubic-bezier(0.4, 0, 0.2, 1);
        box-shadow: 0 0 12px rgba(255, 61, 87, 0.4) inset;
    }
    .bias-label {
        font-size: 0.74rem;
        font-weight: 700;
        min-width: 100px;
        font-family: 'Space Grotesk', 'Inter', sans-serif;
    }

    /* === Pick cards — direction-coded with glow ================== */
    .pick-card-long {
        border-left: 3px solid var(--success);
    }
    .pick-card-short {
        border-left: 3px solid var(--danger);
    }

    /* === Numbered section markers ================================ */
    .section-number {
        display: inline-block;
        font-family: 'Space Grotesk', 'Inter', sans-serif;
        font-size: 0.76rem;
        font-weight: 700;
        color: var(--accent-primary);
        letter-spacing: 0.1em;
        background: rgba(0, 212, 255, 0.08);
        padding: 4px 12px;
        border-radius: 6px;
        border: 1px solid rgba(0, 212, 255, 0.2);
        margin-right: 10px;
    }

    /* === Gradient dividers ====================================== */
    .gradient-divider {
        height: 1px;
        background: linear-gradient(90deg,
            transparent, var(--accent-primary), transparent);
        opacity: 0.3;
        margin: 22px 0;
    }

    /* === Pulse animation for active signals ===================== */
    @keyframes pulse-accent {
        0%, 100% {
            box-shadow: 0 0 0 0 rgba(0, 212, 255, 0.4);
        }
        50% {
            box-shadow: 0 0 0 12px rgba(0, 212, 255, 0);
        }
    }
    .pulse {
        animation: pulse-accent 2.2s ease-in-out infinite;
    }

    /* === Glow keyframe for breakout signals ===================== */
    @keyframes glow-accent {
        0%, 100% { filter: drop-shadow(0 0 4px rgba(0, 212, 255, 0.5)); }
        50%      { filter: drop-shadow(0 0 12px rgba(0, 212, 255, 0.9)); }
    }
    .glow {
        animation: glow-accent 2.5s ease-in-out infinite;
    }

    /* === Toasts / alerts — accent border ======================== */
    [data-testid="stAlert"] {
        background: var(--bg-card) !important;
        border: 1px solid var(--border-soft) !important;
        border-left: 3px solid var(--accent-primary) !important;
        border-radius: 11px !important;
        backdrop-filter: blur(8px);
    }

    /* === Chip enhancement: subtle transform on hover ============ */
    [data-testid="stMarkdownContainer"] span[style*="border-radius"] {
        transition: transform .15s ease, box-shadow .15s ease;
    }
    [data-testid="stMarkdownContainer"] span[style*="border-radius"]:hover {
        transform: scale(1.04);
    }

    /* ============================================================
       PREMIUM PICK CARDS — Linear/Vercel/Stripe-grade
       Multi-layer depth, gradient borders, glass effect,
       animated hover sweep, subtle glow.
       ============================================================ */

    /* The pick cards live inside st.container(border=True) which
       Streamlit renders as stVerticalBlockBorderWrapper. We target
       the SECOND-LEVEL ones (the cards inside the picks board)
       so the regime hero and outer panels stay distinct. */
    div[data-testid="stVerticalBlockBorderWrapper"] {
        background:
            linear-gradient(135deg,
                rgba(0, 212, 255, 0.025) 0%,
                rgba(91, 142, 255, 0.015) 50%,
                transparent 100%),
            linear-gradient(180deg,
                rgba(255, 255, 255, 0.03) 0%,
                transparent 8%),
            var(--bg-card) !important;
        backdrop-filter: blur(16px) saturate(140%);
        -webkit-backdrop-filter: blur(16px) saturate(140%);
        border: 1px solid var(--border-soft);
        border-radius: 18px !important;
        padding: 16px 20px !important;
        margin-bottom: 14px !important;
        position: relative;
        overflow: hidden;
        transition: all .35s cubic-bezier(0.4, 0, 0.2, 1);
        box-shadow:
            0 1px 3px rgba(0, 0, 0, 0.3),
            0 6px 20px rgba(0, 0, 0, 0.15),
            inset 0 1px 0 rgba(255, 255, 255, 0.04);
    }

    /* Top inner highlight (subtle "glass" reflection) */
    div[data-testid="stVerticalBlockBorderWrapper"]::before {
        content: "";
        position: absolute;
        top: 0; left: 0; right: 0;
        height: 1px;
        background: linear-gradient(90deg,
            transparent 0%,
            rgba(255, 255, 255, 0.08) 30%,
            rgba(255, 255, 255, 0.12) 50%,
            rgba(255, 255, 255, 0.08) 70%,
            transparent 100%);
        pointer-events: none;
    }

    /* Soft accent glow in top-right corner (premium SaaS touch) */
    div[data-testid="stVerticalBlockBorderWrapper"]::after {
        content: "";
        position: absolute;
        top: -80px; right: -80px;
        width: 220px; height: 220px;
        background: radial-gradient(circle,
            rgba(0, 212, 255, 0.10) 0%,
            transparent 65%);
        pointer-events: none;
        opacity: 0;
        transition: opacity .4s ease;
    }

    /* Hover lift + glow + reveal corner accent */
    div[data-testid="stVerticalBlockBorderWrapper"]:hover {
        border-color: rgba(0, 212, 255, 0.30);
        transform: translateY(-3px);
        box-shadow:
            0 4px 8px rgba(0, 0, 0, 0.4),
            0 16px 40px rgba(0, 212, 255, 0.12),
            inset 0 1px 0 rgba(255, 255, 255, 0.08);
    }
    div[data-testid="stVerticalBlockBorderWrapper"]:hover::after {
        opacity: 1;
    }

    /* Animated sweep on hover — a thin diagonal light streak */
    div[data-testid="stVerticalBlockBorderWrapper"] {
        background-size: 100% 100%, 100% 100%, 100% 100%;
    }

    @keyframes card-sweep {
        0% {
            background-position: -200% 0, 0 0, 0 0;
        }
        100% {
            background-position: 200% 0, 0 0, 0 0;
        }
    }

    /* === Premium price display blocks inside cards ============== */
    /* Make the inline price text more dramatic by enlarging <b> */
    div[data-testid="stVerticalBlockBorderWrapper"] [data-testid="stMarkdownContainer"] b {
        color: var(--text-primary);
        font-weight: 700;
        font-family: 'Space Grotesk', 'Inter', sans-serif;
        letter-spacing: -0.01em;
    }

    /* === Better chip designs — premium gradient borders ========= */
    /* Use inset shadow for depth on chips */
    [data-testid="stMarkdownContainer"] span[style*="border-radius"][style*="background"] {
        box-shadow:
            inset 0 1px 0 rgba(255, 255, 255, 0.08),
            0 1px 2px rgba(0, 0, 0, 0.2) !important;
        font-family: 'Inter', sans-serif !important;
        font-weight: 700 !important;
        letter-spacing: 0.01em !important;
    }

    /* === Open Trade button — premium CTA inside cards =========== */
    /* Buttons inside pick cards get the gradient treatment */
    div[data-testid="stVerticalBlockBorderWrapper"] .stButton button {
        background: linear-gradient(135deg,
            rgba(0, 212, 255, 0.15),
            rgba(91, 142, 255, 0.10));
        border: 1px solid rgba(0, 212, 255, 0.35);
        color: var(--accent-primary);
        font-weight: 700;
        font-size: 1rem;
        padding: 10px 16px;
        position: relative;
        overflow: hidden;
        transition: all .22s cubic-bezier(0.4, 0, 0.2, 1);
    }

    div[data-testid="stVerticalBlockBorderWrapper"] .stButton button:hover {
        background: linear-gradient(135deg,
            rgba(0, 212, 255, 0.30),
            rgba(91, 142, 255, 0.20));
        border-color: var(--accent-primary);
        color: #ffffff;
        transform: translateY(-1px);
        box-shadow:
            0 4px 16px rgba(0, 212, 255, 0.30),
            inset 0 1px 0 rgba(255, 255, 255, 0.15);
    }

    /* Button shine sweep on hover */
    div[data-testid="stVerticalBlockBorderWrapper"] .stButton button::before {
        content: "";
        position: absolute;
        top: 0; left: -100%;
        width: 100%; height: 100%;
        background: linear-gradient(90deg,
            transparent,
            rgba(255, 255, 255, 0.15),
            transparent);
        transition: left .5s ease;
    }
    div[data-testid="stVerticalBlockBorderWrapper"] .stButton button:hover::before {
        left: 100%;
    }

    /* === Container-level emphasis on PREMIUM cards ============== */
    /* When a card contains 🏆 PREMIUM chip, give the whole card
       a golden tinge. Detected via :has() — modern browsers only. */
    div[data-testid="stVerticalBlockBorderWrapper"]:has(span[style*="ffd700"]) {
        border-color: rgba(255, 215, 0, 0.25) !important;
        background:
            linear-gradient(135deg,
                rgba(255, 215, 0, 0.04) 0%,
                rgba(224, 169, 43, 0.02) 50%,
                transparent 100%),
            var(--bg-card) !important;
    }
    div[data-testid="stVerticalBlockBorderWrapper"]:has(span[style*="ffd700"])::after {
        background: radial-gradient(circle,
            rgba(255, 215, 0, 0.12) 0%,
            transparent 65%) !important;
        opacity: 0.6;
    }
    div[data-testid="stVerticalBlockBorderWrapper"]:has(span[style*="ffd700"])::before {
        background: linear-gradient(90deg,
            transparent 0%,
            rgba(255, 215, 0, 0.20) 30%,
            rgba(255, 215, 0, 0.30) 50%,
            rgba(255, 215, 0, 0.20) 70%,
            transparent 100%) !important;
    }

    /* === Status badge for LONG side cards (green tinge) ========= */
    div[data-testid="stVerticalBlockBorderWrapper"]:has(span[style*="2ed47a"][style*="#06121f"]),
    div[data-testid="stVerticalBlockBorderWrapper"]:has(span[style*="#34c759"]) {
        border-left: 3px solid var(--success);
    }

    /* === Status badge for SHORT side cards (red tinge) ========== */
    div[data-testid="stVerticalBlockBorderWrapper"]:has(span[style*="ff5c5c"][style*="#06121f"]),
    div[data-testid="stVerticalBlockBorderWrapper"]:has(span[style*="🩸"]) {
        border-left: 3px solid var(--danger);
    }

    /* === Typography polish inside cards ========================= */
    div[data-testid="stVerticalBlockBorderWrapper"] [data-testid="stMarkdownContainer"] {
        position: relative;
        z-index: 1;
    }

    /* Make the symbol/base text (the first <span> with font-weight:800) larger */
    div[data-testid="stVerticalBlockBorderWrapper"] [data-testid="stMarkdownContainer"] span[style*="font-weight:800"][style*="font-size:1rem"],
    div[data-testid="stVerticalBlockBorderWrapper"] [data-testid="stMarkdownContainer"] span[style*="font-weight:800"][style*="font-size:1.05rem"] {
        font-size: 1.15rem !important;
        font-family: 'Space Grotesk', 'Inter', sans-serif !important;
        letter-spacing: -0.02em !important;
        background: linear-gradient(135deg, #ffffff 0%, #c8d2ed 100%);
        -webkit-background-clip: text;
        -webkit-text-fill-color: transparent;
        background-clip: text;
    }
    </style>
    """,
    unsafe_allow_html=True,
)

# --- Paper trading bot state file (lives next to app.py, gitignored) ------
PAPER_BOT_FILE = Path(__file__).resolve().parent / ".paper_bot.json"


# --- Colour palette for signal labels --------------------------------------
LABEL_COLORS = {
    "STRONG LONG": "#0b8a3e", "LONG": "#34c759",
    "STRONG BUY": "#0b8a3e", "BUY": "#34c759",
    "NEUTRAL": "#8e8e93",
    "SHORT": "#ff6b5b", "STRONG SHORT": "#c1121f",
    "SELL": "#ff6b5b", "STRONG SELL": "#c1121f",
}
MOOD_COLORS = {"Bullish": "#34c759", "Bearish": "#ff6b5b", "Neutral": "#8e8e93"}


# --- Cached data services --------------------------------------------------
@st.cache_data(ttl=config.MARKET_CACHE_TTL, show_spinner=False)
def load_top_symbols(n: int) -> pd.DataFrame:
    return binance_client.get_top_symbols(n)


@st.cache_data(ttl=config.MARKET_CACHE_TTL, show_spinner=False)
def load_klines(symbol: str, interval: str) -> pd.DataFrame:
    return binance_client.get_klines(symbol, interval)


# --- Early-momentum + Spot-long-term scoring (Phase A/D MVP) --------------
# These are PURE display layers. They do NOT feed into live_broker, the
# auto_trade_gate, or is_premium_tradeable. They surface NEW leading-
# indicator and long-term-hold scores alongside the existing system so
# the user can A/B test before promoting any signal into the live path.

@st.cache_data(ttl=600, show_spinner=False)
def compute_multi_tf_setups_forming(scan_n: int = 30,
                                    _cache_version: int = 1) -> list:
    """Multi-timeframe Setups Forming watchlist — scans coins on 15m,
    1h, and 4h simultaneously. Surfaces coins where the SAME direction
    is forming on MULTIPLE timeframes (genuine money-flow signal).

    Why this works: a single-TF setup may be noise. But when 15m AND
    1h AND 4h ALL show approaching-reversal conditions on the same
    side, that's broad-market positioning shift — institutional money
    rotating. Professional traders watch this.

    Returns list of dicts with per-TF scores. NO TRADE PLANS, NO BUTTONS —
    pure intelligence layer for the user to watch and act on the actual
    fire candle when it prints.
    """
    try:
        top_df = load_top_symbols(scan_n)
    except Exception:
        return []
    results = []
    timeframes = ["15m", "1h", "4h"]
    for _, row in top_df.iterrows():
        sym = row["symbol"]
        base = row["base"]
        last_price = float(row["lastPrice"])
        pct_24h = float(row["priceChangePercent"])
        per_tf = {}
        for tf in timeframes:
            try:
                df = binance_client.get_klines(sym, tf)
                df = indicators.enrich(df)
                r = reversal_approach.scan_both_sides(df)
                per_tf[tf] = {
                    "score": r.get("score", 50),
                    "side": r.get("side", "NEUTRAL"),
                    "conditions": r.get("conditions_met", 0),
                }
            except Exception:
                per_tf[tf] = {"score": 50, "side": "NEUTRAL", "conditions": 0}

        # Count timeframes where conditions are forming (≥ 3/7 met)
        # AND the side is same direction
        long_tfs = [tf for tf, d in per_tf.items()
                    if d["conditions"] >= 3 and d["side"] == "LONG"]
        short_tfs = [tf for tf, d in per_tf.items()
                     if d["conditions"] >= 3 and d["side"] == "SHORT"]

        # Only surface coins where 2+ timeframes agree
        if len(long_tfs) >= 2:
            net_side = "LONG"
            agreeing_tfs = long_tfs
        elif len(short_tfs) >= 2:
            net_side = "SHORT"
            agreeing_tfs = short_tfs
        else:
            continue

        # Total score is sum across agreeing TFs (more = stronger)
        total_score = sum(per_tf[tf]["score"] for tf in agreeing_tfs)
        results.append({
            "symbol": sym,
            "base": base,
            "side": net_side,
            "agreeing_tfs": agreeing_tfs,
            "per_tf": per_tf,
            "total_score": total_score,
            "price": last_price,
            "pct_24h": round(pct_24h, 2),
            "tf_count": len(agreeing_tfs),
        })

    # Rank by tf_count (more TFs agreeing wins) then total_score
    results.sort(key=lambda r: (r["tf_count"], r["total_score"]),
                 reverse=True)
    return results[:10]


@st.cache_data(ttl=300, show_spinner=False)
def compute_unified_best_picks(interval: str, scan_n: int = 50,
                               _cache_version: int = 1) -> list:
    """Unified ranking of the BEST picks across all sources, deduplicated
    by symbol. Highest tier wins per coin. Shown in the top-of-board
    "🏆 Best Trades Now" section so user doesn't have to dig through
    7 different sections to find what to trade.

    Tier priority (highest first):
      S (priority 100): ⚡ CONVERGENCE — backtested +6.8pp uplift, validated
      A (priority 85):  🎯 PATTERN SCOUT STRONG (score ≥ 80)
      B (priority 70):  🔭 SETUPS FORMING STRONG WATCH (score ≥ 80)
      C (priority 55):  🎯 PATTERN SCOUT WATCH (score 65-79)
      D (priority 40):  🔭 SETUPS FORMING WATCH (score 60-79)

    Returns top 8 sorted by tier × score.
    """
    picks_by_sym = {}  # symbol → pick dict (best-tier wins)

    # === S-TIER: Convergence (validated edge) =========================
    try:
        cv_list = compute_convergence_picks(interval, scan_n)
        for cv in cv_list:
            sym = cv["symbol"]
            picks_by_sym[sym] = {
                "tier": "S",
                "tier_label": "⚡ CONVERGENCE",
                "tier_color": "#ffd700",
                "tier_gradient": "linear-gradient(135deg,#ffd700,#ff006e,#8b5cf6)",
                "priority": 100,
                "symbol": sym,
                "base": cv["base"],
                "side": cv["side"],
                "score": float(cv["convergence_score"]),
                "entry": cv.get("entry"),
                "stop": cv.get("stop"),
                "target": cv.get("target"),
                "target_2": cv.get("target_2"),
                "rr": cv.get("rr"),
                "reasons": cv.get("convergence_reasons", []),
                "best_signal": cv.get("best_signal", ""),
                "source": "convergence",
                "pct_24h": cv.get("pct_24h", 0),
                "price": cv.get("price"),
                "has_plan": True,
            }
    except Exception:
        pass

    # === A-TIER: Pattern Scout STRONG (score ≥ 80) ====================
    try:
        scout_list = run_pattern_scout(interval, scan_n)
        for ps in scout_list:
            sym = ps["symbol"]
            if sym in picks_by_sym:
                continue  # already covered by higher tier
            if ps.get("score", 50) < 80:
                continue  # only STRONG into top picks
            picks_by_sym[sym] = {
                "tier": "A",
                "tier_label": "🎯 STRONG PATTERN",
                "tier_color": "#00d4ff",
                "tier_gradient": "linear-gradient(135deg,#00d4ff,#5b8eff)",
                "priority": 85,
                "symbol": sym,
                "base": ps["base"],
                "side": ps["side"],
                "score": float(ps["score"]),
                "entry": ps.get("entry"),
                "stop": ps.get("stop"),
                "target": ps.get("target"),
                "target_2": ps.get("target_2"),
                "rr": ps.get("rr"),
                "best_signal": ps.get("best_signal", ""),
                "signals": ps.get("signals", []),
                "source": "pattern_scout",
                "pct_24h": ps.get("pct_24h", 0),
                "price": ps.get("price"),
                "has_plan": ps.get("entry") is not None,
            }
    except Exception:
        pass

    # === B-TIER: Setups Forming STRONG WATCH (≥ 80) ===================
    try:
        approach_list = run_reversal_approach_scan(interval, scan_n=30)
        for ar in approach_list:
            sym = ar["symbol"]
            if sym in picks_by_sym:
                continue
            if ar.get("score", 50) < 80:
                continue
            picks_by_sym[sym] = {
                "tier": "B",
                "tier_label": "🔭 SETUP FORMING",
                "tier_color": "#ff9500",
                "tier_gradient": "linear-gradient(135deg,#ff9500,#ffcc66)",
                "priority": 70,
                "symbol": sym,
                "base": ar["base"],
                "side": ar["side"],
                "score": float(ar["score"]),
                "entry": ar.get("entry"),
                "stop": ar.get("stop"),
                "target": ar.get("target"),
                "target_2": ar.get("target_2"),
                "rr": ar.get("rr"),
                "best_signal": "approach_to_reversal",
                "conditions_met": ar.get("conditions_met", 0),
                "source": "setups_forming",
                "pct_24h": ar.get("pct_24h", 0),
                "price": ar.get("price"),
                "has_plan": bool(ar.get("has_plan", False)),
            }
    except Exception:
        pass

    # === C-TIER: Pattern Scout WATCH (65-79) ==========================
    try:
        for ps in scout_list:
            sym = ps["symbol"]
            if sym in picks_by_sym:
                continue
            if ps.get("score", 50) < 65 or ps.get("score", 50) >= 80:
                continue
            picks_by_sym[sym] = {
                "tier": "C",
                "tier_label": "🎯 WATCH",
                "tier_color": "#5b8eff",
                "tier_gradient": "linear-gradient(135deg,#5b8eff,#8b5cf6)",
                "priority": 55,
                "symbol": sym,
                "base": ps["base"],
                "side": ps["side"],
                "score": float(ps["score"]),
                "entry": ps.get("entry"),
                "stop": ps.get("stop"),
                "target": ps.get("target"),
                "target_2": ps.get("target_2"),
                "rr": ps.get("rr"),
                "best_signal": ps.get("best_signal", ""),
                "signals": ps.get("signals", []),
                "source": "pattern_scout_watch",
                "pct_24h": ps.get("pct_24h", 0),
                "price": ps.get("price"),
                "has_plan": ps.get("entry") is not None,
            }
    except Exception:
        pass

    # Rank by priority then score, take top 8
    ranked = sorted(picks_by_sym.values(),
                    key=lambda p: (p["priority"], p["score"]),
                    reverse=True)
    return ranked[:8]


@st.cache_data(ttl=600, show_spinner=False)
def compute_convergence_picks(interval: str, scan_n: int = 50,
                              _cache_version: int = 2) -> list:
    """⚡ CONVERGENCE — the highest-conviction picks across the system.

    Cross-references multiple INDEPENDENT signals on the same coin:
      1. Pattern Scout confirmed fire (validated edge — 60-75% win)
      2. Setups Forming pre-conditions (leading indicator)
      3. Market Regime alignment (BULL → LONG, BEAR → SHORT)
      4. 4h trend gate (refuse signals that fight the higher-TF trend)
      5. BTC correlation check (refuse LONG alts when BTC dumps -3%+ in 4h)

    Score formula:
      base = pattern_scout.score
      + 15 if Setups Forming had ≥4 conditions met same side
      + 10 if regime composite aligned with side
      + 10 if 4h trend supports side
      - 25 if BTC adverse correlation (LONG with BTC dumping)

    Only picks scoring ≥ 88 surface as CONVERGENCE. Expected fire rate:
    0-3 per day in most market conditions. Rarity is the edge.
    """
    try:
        scout_picks = run_pattern_scout(interval, scan_n)
        approach_picks = run_reversal_approach_scan(interval, scan_n)
    except Exception:
        return []
    if not scout_picks:
        return []
    # Index approach picks by symbol for fast lookup
    approach_by_sym = {a["symbol"]: a for a in approach_picks}
    # Index scout picks by symbol for BTC-ETH-SOL alignment check
    scout_by_sym = {p["symbol"]: p for p in scout_picks}

    # Get BTC 4h trend for correlation check
    try:
        btc_4h = binance_client.get_klines("BTCUSDT", "4h")
        btc_4h = indicators.enrich(btc_4h)
        btc_last = btc_4h.iloc[-1]
        btc_4h_back = btc_4h.iloc[-2] if len(btc_4h) >= 2 else btc_last
        btc_4h_change = (
            (float(btc_last["close"]) / float(btc_4h_back["close"]) - 1.0)
            * 100 if float(btc_4h_back["close"]) > 0 else 0)
    except Exception:
        btc_4h_change = 0
    # Get regime
    try:
        regime = load_market_regime()
        regime_composite = float(regime.get("composite") or 50)
    except Exception:
        regime_composite = 50

    # --- NEW: BTC-ETH-SOL majors alignment check ---
    # If all three top majors are showing same-direction signals in
    # Pattern Scout, that's broad-market agreement → bonus for picks
    # matching that direction.
    btc_dir = scout_by_sym.get("BTCUSDT", {}).get("side", "NEUTRAL")
    eth_dir = scout_by_sym.get("ETHUSDT", {}).get("side", "NEUTRAL")
    sol_dir = scout_by_sym.get("SOLUSDT", {}).get("side", "NEUTRAL")
    majors_aligned_side = None
    if btc_dir == eth_dir == sol_dir and btc_dir != "NEUTRAL":
        majors_aligned_side = btc_dir

    # --- NEW: Funding rates for all picks (single fapi call) ---
    try:
        all_funding = derivatives.all_funding_rates()
    except Exception:
        all_funding = {}

    convergence = []
    for pick in scout_picks:
        sym = pick["symbol"]
        side = pick.get("side", "NEUTRAL")
        if side == "NEUTRAL":
            continue
        base_score = float(pick.get("score", 50))
        reasons = [f"Pattern Scout {pick.get('best_signal', '')} ({base_score:.0f})"]
        bonus = 0
        penalty = 0

        # 1. Setups Forming overlap on same coin and side
        approach = approach_by_sym.get(sym)
        if (approach
                and approach.get("side") == side
                and approach.get("conditions_met", 0) >= 4):
            bonus += 15
            reasons.append(f"Setups Forming pre-confirmed "
                          f"({approach['conditions_met']}/7)")

        # 2. Regime alignment
        if side == "LONG" and regime_composite >= 50:
            bonus += 10
            reasons.append(f"regime LONG-friendly ({regime_composite:.0f})")
        elif side == "SHORT" and regime_composite < 50:
            bonus += 10
            reasons.append(f"regime SHORT-friendly ({regime_composite:.0f})")

        # 3. 4h trend gate — check pick's own 4h
        try:
            df_4h = binance_client.get_klines(sym, "4h")
            df_4h = indicators.enrich(df_4h)
            last_4h = df_4h.iloc[-1]
            price_4h = float(last_4h["close"])
            ema50_4h = float(last_4h.get("ema_slow") or 0)
            ema_4h_5_ago = float(df_4h["ema_slow"].iloc[-6]
                                 if len(df_4h) >= 6 else ema50_4h)
            ema_rising = ema50_4h > ema_4h_5_ago
            if side == "LONG" and price_4h > ema50_4h and ema_rising:
                bonus += 10
                reasons.append("4h above 50EMA rising")
            elif side == "SHORT" and price_4h < ema50_4h and not ema_rising:
                bonus += 10
                reasons.append("4h below 50EMA falling")
            elif (side == "LONG" and price_4h < ema50_4h
                  and not ema_rising):
                penalty += 15
                reasons.append("⚠ 4h trend opposes LONG")
            elif (side == "SHORT" and price_4h > ema50_4h
                  and ema_rising):
                penalty += 15
                reasons.append("⚠ 4h trend opposes SHORT")
        except Exception:
            pass

        # 4. BTC correlation gate
        if side == "LONG" and btc_4h_change <= -3.0:
            penalty += 25
            reasons.append(
                f"⚠ BTC dumping {btc_4h_change:.1f}% 4h "
                "(alts likely follow)")
        elif side == "SHORT" and btc_4h_change >= 3.0:
            penalty += 25
            reasons.append(
                f"⚠ BTC pumping +{btc_4h_change:.1f}% 4h "
                "(SHORT may get squeezed)")

        # 5. NEW: Funding rate extreme filter
        # When funding is heavily one-sided, crowd is positioned hard
        # — opposite direction has squeeze risk
        funding = all_funding.get(sym)
        if funding is not None:
            funding_pct = funding * 100  # convert to %
            if side == "LONG" and funding_pct >= 0.08:
                penalty += 20
                reasons.append(
                    f"⚠ funding {funding_pct:+.3f}% (crowded longs, "
                    "squeeze risk)")
            elif side == "SHORT" and funding_pct <= -0.08:
                penalty += 20
                reasons.append(
                    f"⚠ funding {funding_pct:+.3f}% (crowded shorts, "
                    "squeeze risk)")
            elif side == "LONG" and funding_pct <= -0.03:
                bonus += 5
                reasons.append(
                    f"funding {funding_pct:+.3f}% (shorts crowded, "
                    "contrarian LONG)")
            elif side == "SHORT" and funding_pct >= 0.03:
                bonus += 5
                reasons.append(
                    f"funding {funding_pct:+.3f}% (longs crowded, "
                    "contrarian SHORT)")

        # 6. NEW: BTC-ETH-SOL alignment bonus
        # When all three top majors show same-direction signals, broad-
        # market move is confirmed by independent corroboration
        if (majors_aligned_side is not None
                and majors_aligned_side == side):
            bonus += 10
            reasons.append(
                f"BTC + ETH + SOL all signal {side} "
                "(broad-market alignment)")

        final_score = max(0, min(100, base_score + bonus - penalty))
        if final_score >= 88:
            # Inherit trade plan from Pattern Scout pick
            converged = dict(pick)
            converged["convergence_score"] = round(final_score, 1)
            converged["convergence_bonus"] = bonus
            converged["convergence_penalty"] = penalty
            converged["convergence_reasons"] = reasons
            converged["base_pattern_score"] = base_score
            convergence.append(converged)

    convergence.sort(key=lambda x: x["convergence_score"], reverse=True)
    return convergence


@st.cache_data(ttl=600, show_spinner=False)
def run_reversal_approach_scan(interval: str, scan_n: int = 30,
                               _cache_version: int = 2) -> list:
    """Scan top N coins for coins APPROACHING reversal conditions.

    Leading-indicator scan — finds coins where pre-shooting-star or
    pre-hammer conditions are forming (3+ of 7 pre-conditions met).
    Now ALSO generates an anticipatory trade plan so the user can
    open the trade directly from the Setups Forming card.

    Trade plan strategy: ANTICIPATORY entry at current price,
    stop placed BEYOND the level (resistance + buffer for SHORT,
    support - buffer for LONG), target at EMA20 mean reversion.

    Cached 10 min.
    """
    try:
        top_df = load_top_symbols(scan_n)
    except Exception:
        return []
    results = []
    for _, row in top_df.iterrows():
        sym = row["symbol"]
        base = row["base"]
        last_price = float(row["lastPrice"])
        pct_24h = float(row["priceChangePercent"])
        try:
            df = binance_client.get_klines(sym, interval)
            df = indicators.enrich(df)
            r = reversal_approach.scan_both_sides(df)
        except Exception:
            continue
        if r["conditions_met"] >= 3 and r["score"] >= 60:
            r["symbol"] = sym
            r["base"] = base
            r["price"] = last_price
            r["volume_24h"] = float(row["quoteVolume"])
            r["pct_24h"] = round(pct_24h, 2)
            # Generate ANTICIPATORY trade plan
            try:
                last = df.iloc[-1]
                price = float(last["close"])
                atr_val = float(last.get("atr") or 0)
                ema20 = float(last.get("ema_fast") or 0)
                level = r["components"].get("approach", {}).get("level", 0)
                if price > 0 and atr_val > 0:
                    if r["side"] == "SHORT" and level > price:
                        # Anticipatory short: bet on rejection at resistance
                        entry = price
                        # Stop beyond resistance + 0.5 ATR buffer
                        stop = level + 0.5 * atr_val
                        # Cap stop distance at 5% to keep R:R reasonable
                        stop = min(stop, price * 1.05)
                        # Target: mean reversion to EMA20 if below
                        if ema20 > 0 and ema20 < price:
                            target_1 = ema20
                        else:
                            target_1 = price - 2 * (stop - entry)
                        target_2 = price - 3 * (stop - entry)
                        rr = abs(target_1 - entry) / abs(stop - entry)
                    elif r["side"] == "LONG" and level < price:
                        # Anticipatory long: bet on bounce at support
                        entry = price
                        stop = level - 0.5 * atr_val
                        stop = max(stop, price * 0.95)
                        if ema20 > 0 and ema20 > price:
                            target_1 = ema20
                        else:
                            target_1 = price + 2 * (entry - stop)
                        target_2 = price + 3 * (entry - stop)
                        rr = abs(target_1 - entry) / abs(entry - stop)
                    else:
                        # Fallback: ATR-based
                        if r["side"] == "SHORT":
                            entry = price
                            stop = price + 1.5 * atr_val
                            target_1 = price - 2.5 * atr_val
                            target_2 = price - 4 * atr_val
                        else:
                            entry = price
                            stop = price - 1.5 * atr_val
                            target_1 = price + 2.5 * atr_val
                            target_2 = price + 4 * atr_val
                        rr = 1.67
                    r["entry"] = entry
                    r["entry_low"] = entry
                    r["entry_high"] = entry
                    r["stop"] = stop
                    r["target"] = target_1
                    r["target_2"] = target_2
                    r["rr"] = rr
                    r["has_plan"] = True
            except Exception:
                r["has_plan"] = False
            results.append(r)
    return results


@st.cache_data(ttl=600, show_spinner=False)
def run_pattern_scout(interval: str, scan_n: int = 50,
                      _cache_version: int = 6) -> list:
    """Universal Pattern Scout — scans top N coins for high-conviction
    setups across all validated-edge patterns, INDEPENDENT of the
    alerts.build_alerts() gate.

    `_cache_version`: bump this when changing the function logic to
    force cache invalidation. Streamlit @st.cache_data doesn't auto-
    invalidate on code changes — only when args change. v3 = added LONG
    trade plan validation guard so SHORT-direction plans never leak
    into the card display.

    Per user feedback: the picks board only surfaces coins that pass
    CONF_ALERT=72. Coins with strong individual patterns (V-bottom,
    long_patterns, morning star, hammer-at-support) but lower scanner
    confidence never appear. This helper surfaces them — AND now also
    generates a full trade plan (entry/stop/TP1/TP2) for each pick so
    the user can open the trade with a 📥 button directly from the
    Pattern Scout cards.

    Cached 10 min — scan of 50 coins × klines fetch + patterns +
    trade plan takes 30-60 sec but the cache keeps repeated visits fast.
    """
    try:
        top_df = load_top_symbols(scan_n)
    except Exception:
        return []
    results = []
    for _, row in top_df.iterrows():
        sym = row["symbol"]
        base = row["base"]
        last_price = float(row["lastPrice"])
        pct_24h = float(row["priceChangePercent"])
        try:
            df = binance_client.get_klines(sym, interval)
            df = indicators.enrich(df)
            r = pattern_scout.scan_one(sym, df, pct_24h=pct_24h)
        except Exception:
            continue
        if r["score"] >= 65:  # surface anything WATCH-tier or above
            # Generate FULL trade plan for openable picks. Two-step
            # strategy + side-aware (LONG or SHORT based on pattern):
            #   1. Try signals._trade_plan with the right label
            #   2. If that returns None or fails, fall back to ATR-based
            # VALIDATION: ensure direction is correct for the side
            _scout_side = r.get("side", "LONG")
            trade_plan = None
            try:
                last = df.iloc[-1]
                from signals import (_regime as _sig_regime,
                                     _trade_plan as _sig_trade_plan)
                regime_str = _sig_regime(last)
                _candidate_plan = _sig_trade_plan(
                    _scout_side, df, regime_str,
                    mode="futures",
                    confidence=float(r["score"])
                )
                # Validate direction
                if _candidate_plan:
                    _p_entry = float(_candidate_plan.get("entry") or 0)
                    _p_stop = float(_candidate_plan.get("stop_loss") or 0)
                    _p_tgt = float(_candidate_plan.get("take_profit") or 0)
                    if _scout_side == "LONG":
                        valid = (_p_entry > 0 and _p_stop > 0 and _p_tgt > 0
                                 and _p_stop < _p_entry < _p_tgt)
                    else:  # SHORT
                        valid = (_p_entry > 0 and _p_stop > 0 and _p_tgt > 0
                                 and _p_tgt < _p_entry < _p_stop)
                    if valid:
                        trade_plan = _candidate_plan
            except Exception:
                pass
            # ATR fallback — side-aware
            if trade_plan is None:
                try:
                    last = df.iloc[-1]
                    price = float(last["close"])
                    atr_val = float(last.get("atr") or 0)
                    if price > 0 and atr_val > 0:
                        stop_dist = max(price * 0.03,
                                        min(price * 0.05, atr_val * 1.5))
                        tgt_dist_1 = max(stop_dist * 1.5, atr_val * 2.5)
                        tgt_dist_2 = max(stop_dist * 2.5, atr_val * 4.0)
                        if _scout_side == "LONG":
                            entry_p = price
                            stop_p = price - stop_dist
                            tgt_1 = price + tgt_dist_1
                            tgt_2 = price + tgt_dist_2
                            tgt_3 = price + tgt_dist_1 + tgt_dist_2
                        else:  # SHORT
                            entry_p = price
                            stop_p = price + stop_dist
                            tgt_1 = price - tgt_dist_1
                            tgt_2 = price - tgt_dist_2
                            tgt_3 = price - tgt_dist_1 - tgt_dist_2
                        trade_plan = {
                            "side": _scout_side,
                            "mode": "futures",
                            "entry": entry_p,
                            "entry_low": entry_p,
                            "entry_high": entry_p,
                            "stop_loss": stop_p,
                            "take_profit": tgt_1,
                            "take_profit_2": tgt_2,
                            "take_profit_3": tgt_3,
                            "risk_reward": tgt_dist_1 / stop_dist,
                            "risk_reward_2": tgt_dist_2 / stop_dist,
                            "maturity": {"stage": "FALLBACK", "confidence": 50,
                                         "note": ("ATR-based plan")},
                        }
                except Exception:
                    trade_plan = None
            # Assign to result if we have one
            if trade_plan:
                r["trade_plan"] = trade_plan
                r["entry_low"] = trade_plan.get("entry_low")
                r["entry_high"] = trade_plan.get("entry_high")
                r["entry"] = trade_plan.get("entry")
                r["stop"] = trade_plan.get("stop_loss")
                r["target"] = trade_plan.get("take_profit")
                r["target_2"] = trade_plan.get("take_profit_2")
                r["rr"] = trade_plan.get("risk_reward")
                r["rr_2"] = trade_plan.get("risk_reward_2")
                r["maturity"] = trade_plan.get("maturity") or {}
                r["scanner_confidence"] = r["score"]
            r["base"] = base
            r["price"] = last_price
            r["volume_24h"] = float(row["quoteVolume"])
            results.append(r)
    return results


@st.cache_data(ttl=config.MARKET_CACHE_TTL, show_spinner=False)
def load_recovery(symbol: str, interval: str) -> dict:
    """Compute V-bottom recovery score for one symbol/timeframe.

    Catches the JTO/INJ-style setup: sharp drawdown + RSI capitulation +
    strong green reversal candle + volume capitulation. Backtest verdict:
    rare-fire (n=4 across 19 coins / 1000 bars) but +2.26% average return
    over 12 bars vs baseline +0.10%. The 75% win rate is meaningful even
    with small sample because the pattern requires extreme conditions
    that are themselves rare.

    Returns the recovery_detector.score dict; falls back to neutral on
    error so the picks board never crashes.
    """
    try:
        df = binance_client.get_klines(symbol, interval)
        df = indicators.enrich(df)
        return recovery_detector.score(df)
    except Exception:
        return {"score": 50.0, "side": "NEUTRAL", "pattern": "neutral",
                "components": {}, "flags": []}


@st.cache_data(ttl=config.MARKET_CACHE_TTL, show_spinner=False)
def load_long_patterns(symbol: str, interval: str) -> dict:
    """Compute proven LONG-pattern conviction for one symbol/timeframe.

    The early_momentum LONG signal failed in backtest because its
    'bullish CVD' definition was catching dip-buyers in a bear market.
    This module uses the textbook patterns that have actual edge:
    bullish RSI divergence (price LL + RSI HL), trend reclaim with
    volume, higher-low structure, bullish engulfing at support.

    Returns the long_patterns dict; falls back to neutral on error so
    the picks board never crashes.
    """
    try:
        df = binance_client.get_klines(symbol, interval)
        df = indicators.enrich(df)
        return long_patterns.score(df)
    except Exception:
        return {"score": 50.0, "weighted_avg": 50.0, "side": "NEUTRAL",
                "components": {}, "flags": [], "n_aligned": 0}


@st.cache_data(ttl=config.MARKET_CACHE_TTL, show_spinner=False)
def load_early_momentum(symbol: str, interval: str) -> dict:
    """Compute the early-momentum score for one symbol/timeframe.

    Pulls primary-TF klines + 4h klines (4h is CONTEXT only, never a gate
    per user spec) and runs early_momentum.score_with_4h_context() on
    the enriched DataFrames. Returns the composite dict; on any failure
    returns a neutral fallback so the picks board never crashes.

    The composite includes a 6th component (3-candle continuation, the
    "3 positive candles" rule the user asked for) and a 4h-context tilt
    of +/-5 points based on whether the 4h side agrees or disagrees
    with the primary TF.
    """
    try:
        df = binance_client.get_klines(symbol, interval)
        df = indicators.enrich(df)
        # 4h context — pull only if primary TF != 4h to avoid double work.
        ctx_df = None
        if interval != "4h":
            try:
                ctx_df = binance_client.get_klines(symbol, "4h")
                ctx_df = indicators.enrich(ctx_df)
            except Exception:
                ctx_df = None
        return early_momentum.score_with_4h_context(df, ctx_df)
    except Exception:
        return {"score": 50.0, "raw_score": 50.0, "side": "NEUTRAL",
                "regime": "unknown", "hurst": 0.5,
                "regime_multiplier": 1.0, "components": {},
                "flags": [], "side_confidence": 0.0,
                "context_4h": "unavailable"}


@st.cache_data(ttl=config.MARKET_CACHE_TTL, show_spinner=False)
def load_rs_vs_btc(symbol: str, interval: str) -> dict:
    """Compute relative strength of `symbol` vs BTC on `interval`.

    Pulls both alt and BTC klines (both will hit the regular kline
    cache — no extra cost beyond the first BTC fetch per scan tick)
    and returns the RS score dict. Phase B addition: surfaces
    "this coin is out-performing BTC" as a leading rotation signal
    on the picks board.
    """
    if symbol == "BTCUSDT":
        # BTC vs itself is meaningless — return neutral so the chip
        # never fires on BTC and the picks board doesn't mislead.
        return {"score": 50.0, "side": "NEUTRAL", "rs_z": 0.0,
                "rs_blended": 0.0, "windows": {}, "detail": "BTC vs BTC (N/A)"}
    try:
        alt_df = binance_client.get_klines(symbol, interval)
        btc_df = binance_client.get_klines("BTCUSDT", interval)
        return rs_vs_btc.score(alt_df, btc_df)
    except Exception as exc:
        return {"score": 50.0, "side": "NEUTRAL", "rs_z": 0.0,
                "rs_blended": 0.0, "windows": {},
                "detail": f"RS fetch failed: {exc}"}


# --- Phase C / E / F cached helpers ---------------------------------------
# All of these are pure display layers — they DO NOT feed live_broker,
# auto_trade_gate, or is_premium_tradeable. Live trading behaves identically
# before/after these adds.

@st.cache_data(ttl=config.MARKET_CACHE_TTL, show_spinner=False)
def load_derivatives_velocity(symbol: str, interval: str) -> dict:
    """Phase C: funding ROC + OI compression + funding-rate flip detector.
    Returns neutral on any failure so chip rendering never crashes."""
    try:
        return derivatives_velocity.score(symbol, interval)
    except Exception:
        return {"score": 50, "side": "NEUTRAL", "components": {}, "flags": []}


@st.cache_data(ttl=3600, show_spinner=False)
def load_onchain(symbol: str) -> dict:
    """Phase E: Coin Metrics on-chain MVRV / NUPL. Daily cache (1h fast TTL
    is plenty since on-chain metrics update once per UTC day)."""
    try:
        return coin_metrics_onchain.score(symbol)
    except Exception:
        return {"score": 50, "side": "NEUTRAL",
                "detail": "on-chain unavailable"}


@st.cache_data(ttl=3600, show_spinner=False)
def load_tvl_growth(symbol: str) -> dict:
    """Phase E: DefiLlama TVL + fee growth. Hourly cache."""
    try:
        return defillama_tvl.score(symbol)
    except Exception:
        return {"score": 50, "side": "NEUTRAL", "detail": "TVL unavailable"}


@st.cache_data(ttl=600, show_spinner=False)
def load_market_regime() -> dict:
    """Detect the overall market regime (BULL/BEAR/CHOP/TRANSITION).

    Per the user's critique: the LONG-signal backtest showed 38% win rate
    because we were sampling a BEAR regime. A LONG signal that prints
    during a BEAR regime SHOULD get penalised; the same signal during a
    BULL regime should get a boost. This module gives us the regime
    state, and regime_tilt() applies the proper directional weighting.

    10-minute cache — regime changes slowly. The market_regime module's
    own breadth cache adds another 30-min layer underneath.
    """
    try:
        return market_regime.detect_regime()
    except Exception as exc:
        return {"regime": "UNKNOWN", "confidence": 0.0,
                "composite": 50.0, "long_bias": 50.0, "short_bias": 50.0,
                "components": {}, "summary": f"regime detection failed: {exc}"}


@st.cache_data(ttl=3600, show_spinner=False)
def load_btc_regime() -> dict:
    """Phase E: BTC.D + ETH/BTC alt-season regime. Hourly cache —
    regime data is slow-moving."""
    try:
        return btc_dominance.regime()
    except Exception:
        return {"regime": "UNKNOWN", "alt_multiplier": 1.0,
                "detail": "BTC.D unavailable"}


@st.cache_data(ttl=21600, show_spinner=False)
def load_macro_regime() -> dict:
    """Phase E: FRED macro overlay (DXY + M2 + real yields). 6h cache —
    macro data updates slowly and FRED has rate limits."""
    try:
        return fred_macro.regime()
    except Exception:
        return {"regime": "UNKNOWN", "risk_multiplier": 1.0,
                "detail": "macro unavailable"}


@st.cache_data(ttl=config.MARKET_CACHE_TTL, show_spinner=False)
def load_cup_and_handle(symbol: str) -> dict:
    """Phase F: weekly cup-and-handle pattern detector. Cached at the
    regular market TTL — weekly patterns don't change inside 2 minutes."""
    try:
        weekly = binance_client.get_klines(symbol, "1w")
        return cup_and_handle.score(weekly)
    except Exception:
        return {"score": 50, "stage": "NO_DATA", "side": "NEUTRAL",
                "detail": "cup/handle unavailable"}


@st.cache_data(ttl=21600, show_spinner=False)
def load_tokenomics(symbol: str) -> dict:
    """Phase F: tokenomics dilution-risk score. 6h cache — supply data
    is slow-moving."""
    try:
        return tokenomics_unlocks.score(symbol)
    except Exception:
        return {"score": 50, "side": "NEUTRAL",
                "detail": "tokenomics unavailable"}


@st.cache_data(ttl=600, show_spinner=False)
def load_spot_long_score(symbol: str, interval: str = "1d") -> dict:
    """Compute the long-term spot score for one symbol on the chosen
    timeframe (default 1d — user feedback was that weekly was too slow
    and 1d/3d/1w trends are more actionable).

    The underlying math is bar-count-relative so it works on any
    timeframe. 1d gives more responsive signals; 1w gives slower
    cycle-level read.
    """
    try:
        bars = binance_client.get_klines(symbol, interval)
        is_btc_or_eth = symbol in ("BTCUSDT", "ETHUSDT")
        return spot_signals.score(
            bars, is_btc_or_eth=is_btc_or_eth, interval=interval)
    except Exception:
        return {"score": 50.0, "side": "LONG", "tier": "AVOID",
                "stage": "UNKNOWN", "interval": interval,
                "components": {}}


def _scan_one(symbol: str, interval: str, funding: float | None = None,
              social: dict | None = None,
              mode: str = "futures") -> dict | None:
    try:
        df = binance_client.get_klines(symbol, interval)
        deriv = {"funding": funding} if funding is not None else None
        result = signals.analyze(df, deriv, social, mode)
        result["symbol"] = symbol
        result["funding"] = funding
        return result
    except Exception:  # skip a symbol that fails rather than break the scan
        return None


@st.cache_data(ttl=config.MARKET_CACHE_TTL, show_spinner=False)
def scan_market(symbols: tuple[str, ...], interval: str,
                mode: str = "futures") -> pd.DataFrame:
    try:
        funding = derivatives.all_funding_rates()
    except Exception:
        funding = {}
    # {} when LunarCrush is not configured; one shared list fetch.
    social_map = lunarcrush.top_coins(
        load_lunarcrush_list() if lunarcrush.is_configured() else [])
    rows: list[dict] = []
    with ThreadPoolExecutor(max_workers=config.SCAN_WORKERS) as pool:
        for res in pool.map(
                lambda s: _scan_one(s, interval, funding.get(s),
                                    social_map.get(s.replace("USDT", "")),
                                    mode),
                symbols):
            if res:
                rows.append(res)
    return pd.DataFrame(rows)


@st.cache_data(ttl=config.MARKET_CACHE_TTL, show_spinner=False)
def forecast_market(symbols: tuple[str, ...]) -> pd.DataFrame:
    """Per-coin multi-horizon forecast — blends the per-timeframe technical
    read with the comprehensive Breakout Radar read (news catalysts, the
    macro / geopolitical backdrop, volume ignition, social heat and funding).
    See forecast.py."""
    tfs = [tf for tf, _ in forecast.HORIZONS]
    try:
        radar_df, backdrop = scan_breakouts(symbols, "imminent")
        radar_by_sym = ({r["symbol"]: r.to_dict()
                         for _, r in radar_df.iterrows()}
                        if radar_df is not None and not radar_df.empty
                        else {})
    except Exception:
        radar_by_sym, backdrop = {}, {}

    def one(sym: str):
        try:
            per_tf = {tf: signals.analyze(binance_client.get_klines(sym, tf))
                      for tf in tfs}
            pred = forecast.predict_one(
                per_tf, radar_by_sym.get(sym), backdrop)
            pred["symbol"] = sym
            pred["base"] = sym[:-4] if sym.endswith("USDT") else sym
            pred["price"] = per_tf[tfs[0]]["price"]
            return pred
        except Exception:  # skip a coin that fails rather than break the scan
            return None

    rows: list[dict] = []
    with ThreadPoolExecutor(max_workers=config.SCAN_WORKERS) as pool:
        for res in pool.map(one, symbols):
            if res:
                rows.append(res)
    return pd.DataFrame(rows)


@st.cache_data(ttl=config.MARKET_CACHE_TTL, show_spinner=False)
def btc_outlook_now(btc_change_24h: float, alt_median_24h: float) -> dict:
    """Build the BTC 24h Outlook (see btc_outlook.py). The caller supplies
    BTC's own 24h % change and the median alt 24h % so the divergence
    detector has the latest tape; everything else is fetched fresh here."""
    try:
        btc_4h = signals.analyze(load_klines("BTCUSDT", "4h"))
    except Exception:
        btc_4h = None
    try:
        btc_1d = signals.analyze(load_klines("BTCUSDT", "1d"))
    except Exception:
        btc_1d = None
    try:
        btc_1w = signals.analyze(load_klines("BTCUSDT", "1w"))
    except Exception:
        btc_1w = None
    try:
        deriv = load_derivatives("BTCUSDT", "4h")
    except Exception:
        deriv = None
    try:
        fg = load_fear_greed().get("value")
    except Exception:
        fg = None
    try:
        mcap_change = load_global_market().get("market_cap_change_24h")
    except Exception:
        mcap_change = None

    # News fusion — BTC-specific + macro/political + general crypto mood.
    news_payload = None
    try:
        nd = load_news()
        if nd is not None and not nd.empty:
            btc_mask = nd["title"].str.contains(
                r"\b(?:bitcoin|btc)\b", case=False, na=False, regex=True)
            btc_news = nd[btc_mask]
            news_payload = {
                "btc": {
                    "count": int(len(btc_news)),
                    "sentiment": (float(btc_news["sentiment"].mean())
                                  if not btc_news.empty else 0.0),
                },
                "macro": news_mod.category_mood(nd, "Macro / Politics"),
                "crypto": news_mod.category_mood(nd, "Crypto"),
            }
    except Exception:
        news_payload = None

    return btc_outlook.compute(
        btc_4h, btc_1d, deriv, fg, mcap_change,
        btc_change_24h, alt_median_24h,
        btc_1w=btc_1w, news=news_payload)


@st.cache_data(ttl=config.MARKET_CACHE_TTL, show_spinner=False)
def scan_breakouts(symbols: tuple[str, ...],
                   horizon: str = "imminent") -> tuple[pd.DataFrame, dict]:
    """Scan symbols for blowout candidates on a horizon ("imminent" or "24h"),
    wiring in funding, social, news and the broad-market backdrop. Returns
    (radar DataFrame, backdrop dict)."""
    try:
        funding = derivatives.all_funding_rates()
    except Exception:
        funding = {}
    lc_rows: list = []
    if lunarcrush.is_configured():
        try:
            lc_rows = load_lunarcrush_list()
        except Exception:
            lc_rows = []
    try:
        news_df = load_news()
    except Exception:
        news_df = pd.DataFrame()
    try:
        fg_val = load_fear_greed().get("value")
    except Exception:
        fg_val = None
    try:
        mcap_change = load_global_market().get("market_cap_change_24h")
    except Exception:
        mcap_change = None
    return breakout.scan(list(symbols), funding, lc_rows, news_df,
                         fg_val, mcap_change, horizon)


@st.cache_data(ttl=config.NEWS_CACHE_TTL, show_spinner=False)
def load_news() -> pd.DataFrame:
    return news_mod.fetch_news()


@st.cache_data(ttl=config.NEWS_CACHE_TTL, show_spinner=False)
def load_impactful_news() -> list[dict]:
    """The headlines that are MOVING the tape right now — used by the BTC
    banner's 'Why this is happening' panel and the live news notifications."""
    try:
        return news_impact.detect_impactful(load_news())
    except Exception:
        return []


@st.cache_data(ttl=config.NEWS_CACHE_TTL, show_spinner=False)
def load_social() -> pd.DataFrame:
    return social_mod.fetch_social()


@st.cache_data(ttl=config.NEWS_CACHE_TTL, show_spinner=False)
def load_fear_greed() -> dict:
    return sentiment_mod.fear_greed()


@st.cache_data(ttl=config.NEWS_CACHE_TTL, show_spinner=False)
def load_global_market() -> dict:
    return market_context.global_market()


@st.cache_data(ttl=config.MARKET_CACHE_TTL, show_spinner=False)
def load_derivatives(symbol: str, interval: str) -> dict | None:
    return derivatives.get_derivatives(symbol, interval)


@st.cache_data(ttl=300, show_spinner=False)
def htf_trend(symbol: str) -> str:
    """Higher-timeframe (weekly) trend filter for a coin — 'Up' / 'Down'
    / 'Sideways'. Genuinely INDEPENDENT of the per-TF scoring the
    scanner and forecast already weight (those look at 15m / 1h / 4h,
    never 1w). Trading WITH the weekly trend has materially better
    statistics than fighting it, so the bot uses this to deprioritise
    counter-trend setups and to refuse them in auto-mode.
    """
    try:
        df = binance_client.get_klines(symbol, "1w")
    except Exception:
        return "Sideways"
    if df is None or len(df) < 12:
        return "Sideways"
    close = df["close"]
    ema_f = close.ewm(span=8,  adjust=False).mean()
    ema_s = close.ewm(span=21, adjust=False).mean()
    p, ef, es = float(close.iloc[-1]), float(ema_f.iloc[-1]), float(ema_s.iloc[-1])
    ef_prev = float(ema_f.iloc[-2])
    if p > ef > es and ef > ef_prev:
        return "Up"
    if p < ef < es and ef < ef_prev:
        return "Down"
    return "Sideways"


def htf_alignment(side: str, trend: str) -> str:
    """How the trade's side aligns with the weekly trend.
    'aligned' / 'counter' / 'neutral'."""
    if trend == "Up"   and side == "LONG":  return "aligned"
    if trend == "Down" and side == "SHORT": return "aligned"
    if trend == "Up"   and side == "SHORT": return "counter"
    if trend == "Down" and side == "LONG":  return "counter"
    return "neutral"


def is_premium_tradeable(
        scanner_conf: int, side: str,
        fc: dict | None, radar_stage: str | None,
        live_rr: float, weekly_align: str) -> bool:
    """STRICT premium-tier gate used by auto-trade and the manual
    'tradeable' badge on the picks board.

    All FIVE conditions must hold:
      1. Scanner conf >= 90 (top-tier signal strength)
      2. Forecast aligned 3/3 AND direction matches setup side
      3. Radar stage is COILED or FRESH (NOT EXTENDED — no chasing)
      4. Live R:R from current price >= 1.3 (green entry zone)
      5. Weekly trend is NOT counter (aligned or neutral both ok)

    Returns True only when ALL are satisfied — the "sure shot" criteria
    the user defined. Most days zero setups pass; some days one or two.
    """
    if int(scanner_conf or 0) < 90:
        return False
    if not fc or not fc.get("aligned"):
        return False
    word = fc.get("outlook_word")
    if side == "LONG" and word != "Bullish":
        return False
    if side == "SHORT" and word != "Bearish":
        return False
    stage = str(radar_stage or "").upper()
    if stage not in ("COILED", "FRESH"):
        return False
    if live_rr < 1.3:
        return False
    if weekly_align == "counter":
        return False
    return True


@st.cache_data(ttl=5, show_spinner=False)
def live_price(symbol: str) -> float | None:
    """Fast 5-second-cached live price for one symbol — used by the Paper
    Trader so open-position cards reflect near-real-time price between
    full scanner refreshes. Falls back to None if the endpoint fails."""
    return binance_client.get_ticker_price(symbol)


@st.cache_data(ttl=config.MARKET_CACHE_TTL, show_spinner=False)
def load_tv_ratings(symbols: tuple[str, ...], interval: str) -> dict:
    return tv_analysis.get_ratings(list(symbols), interval)


@st.cache_data(ttl=config.MARKET_CACHE_TTL, show_spinner=False)
def load_tv_rating(symbol: str, interval: str) -> dict | None:
    return tv_analysis.get_rating(symbol, interval)


@st.cache_data(ttl=config.ORDERFLOW_CACHE_TTL, show_spinner=False)
def load_orderflow(symbol: str) -> dict:
    return orderflow.snapshot(symbol)


@st.cache_data(ttl=config.NEWS_CACHE_TTL, show_spinner=False)
def load_lunarcrush_list() -> list:
    return lunarcrush.coin_list()


@st.cache_data(ttl=config.NEWS_CACHE_TTL, show_spinner=False)
def load_lunarcrush_coin(base_asset: str) -> dict | None:
    return lunarcrush.coin_metrics(base_asset, load_lunarcrush_list())


@st.cache_data(ttl=config.NEWS_CACHE_TTL, show_spinner=False)
def load_lunarcrush_top() -> dict:
    return lunarcrush.top_coins(load_lunarcrush_list())


@st.cache_data(ttl=config.NEWS_CACHE_TTL, show_spinner=False)
def load_crypto_social() -> dict | None:
    return lunarcrush.crypto_social(load_lunarcrush_list())


@st.cache_data(ttl=config.NEWS_CACHE_TTL, show_spinner=False)
def load_stock_social() -> dict | None:
    return lunarcrush.stock_social()


# --- Formatting helpers ----------------------------------------------------
def fmt_price(value: float) -> str:
    if value is None:
        return "—"
    if value >= 100:
        return f"${value:,.2f}"
    if value >= 1:
        return f"${value:,.4f}"
    return f"${value:.8f}".rstrip("0").rstrip(".")


def fmt_volume(value: float) -> str:
    """Human-readable money amount — billions / millions / thousands.

    Avoids the '$0.0B' problem where dividing every coin by a billion hides
    anything that does not trade in the billions.
    """
    if value is None or value != value:   # None or NaN
        return "—"
    if value >= 1e9:
        return f"${value / 1e9:.2f}B"
    if value >= 1e6:
        return f"${value / 1e6:.1f}M"
    if value >= 1e3:
        return f"${value / 1e3:.0f}K"
    return f"${value:,.0f}"


def md_safe(text: str) -> str:
    """Escape `$` so Streamlit markdown does not parse price text as LaTeX."""
    return str(text).replace("$", "\\$")


def label_badge(label: str) -> str:
    color = LABEL_COLORS.get(label, "#8e8e93")
    return (f"<span style='background:{color};color:#fff;padding:3px 12px;"
            f"border-radius:7px;font-weight:700;font-size:0.78rem;"
            f"letter-spacing:0.04em;display:inline-block'>{label}</span>")


def tradingview_chart(symbol: str, interval: str, height: int = 540) -> None:
    """Embed TradingView's interactive Advanced Chart widget for a symbol."""
    tv_interval = {"15m": "15", "1h": "60", "4h": "240",
                   "1d": "D"}.get(interval, "240")
    components.html(
        f"""
        <div class="tradingview-widget-container" style="height:{height}px">
          <div id="tv_chart" style="height:100%;width:100%"></div>
          <script src="https://s3.tradingview.com/tv.js"></script>
          <script>
          new TradingView.widget({{
            "autosize": true,
            "symbol": "BINANCE:{symbol}",
            "interval": "{tv_interval}",
            "timezone": "Etc/UTC",
            "theme": "dark",
            "style": "1",
            "locale": "en",
            "hide_side_toolbar": false,
            "allow_symbol_change": true,
            "studies": ["RSI@tv-basicstudies", "MACD@tv-basicstudies"],
            "container_id": "tv_chart"
          }});
          </script>
        </div>
        """,
        height=height + 12,
    )


def style_scan(df: pd.DataFrame):
    def color_label(val):
        return f"background-color:{LABEL_COLORS.get(val, '#8e8e93')};color:white;"

    def color_change(val):
        try:
            return "color:#34c759;" if float(val) >= 0 else "color:#ff6b5b;"
        except (TypeError, ValueError):
            return ""

    return (df.style
            .map(color_label, subset=["Bias", "Action", "TradingView"])
            .map(color_change, subset=["24h %"]))


def confidence_gauge(value: float, suffix: str = "%"):
    """Plotly gauge for a 0-100 score (confidence, Galaxy Score, etc.)."""
    color = ("#0b8a3e" if value >= 70
             else "#f5a623" if value >= 45 else "#ff6b5b")
    fig = go.Figure(go.Indicator(
        mode="gauge+number",
        value=value,
        number={"suffix": suffix, "font": {"size": 30}},
        gauge={
            "axis": {"range": [0, 100], "tickwidth": 1, "tickcolor": "#888"},
            "bar": {"color": color, "thickness": 0.32},
            "borderwidth": 0,
            "steps": [
                {"range": [0, 45], "color": "rgba(255,107,91,0.18)"},
                {"range": [45, 70], "color": "rgba(245,166,35,0.18)"},
                {"range": [70, 100], "color": "rgba(11,138,62,0.22)"},
            ],
        }))
    fig.update_layout(height=200, margin=dict(l=26, r=26, t=14, b=8),
                      template="plotly_dark")
    return fig


def pressure_bar(buy_pct: float, height: int = 30) -> str:
    """HTML horizontal buy-vs-sell pressure bar."""
    buy = max(0.0, min(100.0, buy_pct))
    sell = 100 - buy
    return (
        f"<div style='display:flex;height:{height}px;border-radius:7px;"
        f"overflow:hidden;font-weight:700;font-size:0.82rem'>"
        f"<div style='width:{buy}%;background:#34c759;color:#04331a;"
        f"display:flex;align-items:center;justify-content:center'>"
        f"BUY {buy:.0f}%</div>"
        f"<div style='width:{sell}%;background:#ff6b5b;color:#3d0a05;"
        f"display:flex;align-items:center;justify-content:center'>"
        f"SELL {sell:.0f}%</div></div>")


def _analysis_sections(agg: dict, detail: dict, per_tf: dict,
                       tv_rating: dict | None, flow_snap: dict,
                       lc_metrics: dict | None) -> list[tuple[str, str]]:
    """Build the detailed written analysis as (heading, prose) sections."""
    secs: list[tuple[str, str]] = []
    bd = {b["indicator"]: b for b in detail["breakdown"]}

    t = (f"Directional bias is {agg['bias_label']} "
         f"(score {agg['bias_score']:+.0f}). {detail.get('trend', '')}. ")
    adx, regime = detail.get("adx"), detail["regime"]
    if adx is not None:
        if regime == "Trending":
            t += (f"ADX at {adx:.0f} confirms a genuine trend — "
                  f"trend-following signals are reliable and targets can be "
                  f"held toward the second take-profit.")
        elif regime == "Ranging":
            t += (f"ADX at {adx:.0f} is low: the market is ranging and "
                  f"choppy, so favour mean-reversion, bank profit earlier "
                  f"and distrust breakouts.")
        else:
            t += (f"ADX at {adx:.0f} shows a developing — not yet "
                  f"established — trend; wait for confirmation.")
    secs.append(("Trend & market structure", t))

    r = detail["rsi"]
    m = (f"Entry timing reads {agg['action_label']} "
         f"(score {agg['action_score']:+.0f}). RSI at {r:.0f} is "
         + ("overbought — a pullback is increasingly likely" if r >= 70
            else "oversold — a bounce is increasingly likely" if r <= 30
            else "in positive-momentum territory" if r >= 55
            else "in weak-momentum territory" if r <= 45 else "neutral")
         + ". ")
    for ind in ("MACD", "Stochastic", "Volume"):
        if ind in bd:
            m += bd[ind]["detail"] + ". "
    secs.append(("Momentum & entry timing", m))

    flow = flow_snap.get("flow")
    if flow:
        o = (f"Right now {flow['pressure'].lower()} — {flow['buy_pct']:.0f}% "
             f"of the last {flow['trades']:,} trades by value were aggressive "
             f"buys (${flow['buy_quote']:,.0f} bought vs "
             f"${flow['sell_quote']:,.0f} sold). ")
        book = flow_snap.get("book")
        if book:
            o += book["verdict"] + "."
        secs.append(("Live order flow", o))

    dv = detail.get("derivatives")
    if dv and dv.get("funding") is not None:
        f = dv["funding"]
        d = (f"Perpetual funding is {f * 100:+.3f}% — "
             + ("longs are crowded and over-paying, a contrarian warning"
                if f >= config.FUNDING_HOT
                else "shorts are crowded — squeeze fuel for a move higher"
                if f <= -config.FUNDING_HOT
                else "balanced, with no leverage extreme") + ". ")
        if dv.get("long_short_ratio") is not None:
            d += f"Trader long/short ratio is {dv['long_short_ratio']:.2f}. "
        if dv.get("oi_change_pct") is not None:
            d += f"Open interest has moved {dv['oi_change_pct']:+.1f}%."
        secs.append(("Derivatives & positioning", d))

    if lc_metrics and lc_metrics.get("sentiment") is not None:
        sv = lc_metrics["sentiment"]
        s = (f"LunarCrush social: Galaxy Score "
             f"{lc_metrics.get('galaxy_score', '—')}, sentiment {sv:.0f}% "
             f"positive")
        if lc_metrics.get("alt_rank") is not None:
            s += f", AltRank #{lc_metrics['alt_rank']:,.0f}"
        s += (". Social attention is "
              + ("supportive of the move." if sv >= 55
                 else "weak or negative — a headwind." if sv <= 45
                 else "neutral."))
        secs.append(("Social sentiment", s))

    if tv_rating:
        secs.append((
            "TradingView cross-check",
            f"TradingView's independent engine rates this "
            f"{tv_rating['recommendation']} — {tv_rating['buy']} buy, "
            f"{tv_rating['neutral']} neutral and {tv_rating['sell']} sell "
            f"indicators (oscillators {tv_rating['oscillators']}, moving "
            f"averages {tv_rating['moving_averages']})."))

    longs = sum(1 for a in per_tf.values() if a["bias_score"] > 5)
    shorts = sum(1 for a in per_tf.values() if a["bias_score"] < -5)
    tf_list = ", ".join(f"{tf} {a['bias_label']}"
                        for tf, a in per_tf.items())
    aligned = longs == len(per_tf) or shorts == len(per_tf)
    secs.append((
        "Across timeframes",
        f"{longs} of {len(per_tf)} timeframes lean long and {shorts} lean "
        f"short ({tf_list}). " + (
            "All timeframes agree — this is a higher-conviction setup."
            if aligned else
            "Timeframes disagree — lower conviction; trade smaller or wait "
            "for them to align.")))
    return secs


def _action_steps(plan: dict | None, agg: dict,
                  nearest_sup: float | None,
                  nearest_res: float | None) -> list[str]:
    """Concrete, numbered trading actions for the current setup."""
    if not plan:
        steps = [
            "The composite signal is NEUTRAL — there is no high-probability "
            "trade right now, so do not force one.",
            "Wait for the directional bias and entry timing to agree — both "
            "clearly bullish, or both clearly bearish.",
        ]
        if nearest_sup:
            steps.append(f"Watch support at {fmt_price(nearest_sup)} — a "
                         f"clean bounce there could set up a long.")
        if nearest_res:
            steps.append(f"Watch resistance at {fmt_price(nearest_res)} — a "
                         f"clear rejection there could set up a short.")
        return steps

    side = plan["side"]
    other = "short" if side == "LONG" else "long"
    steps = [
        f"Trade {side} only — ignore {other} setups while this bias holds.",
        f"Place a limit {side} order in the entry zone "
        f"{fmt_price(plan['entry_low'])} – {fmt_price(plan['entry_high'])}; "
        f"do not chase price outside that zone.",
    ]
    if side == "LONG" and nearest_sup:
        steps.append(f"Best entries are near support {fmt_price(nearest_sup)} "
                     f"— a pullback there gives a tighter, safer stop.")
    if side == "SHORT" and nearest_res:
        steps.append(f"Best entries are near resistance "
                     f"{fmt_price(nearest_res)}.")
    steps += [
        f"As soon as you are filled, set a stop-loss at "
        f"{fmt_price(plan['stop_loss'])} ({plan['risk_pct']:.2f}% away, placed "
        f"on {plan.get('stop_basis', 'volatility')}). A candle close beyond it "
        f"invalidates the trade — exit, no exceptions.",
        f"Scale out: ~40% at Target 1 {fmt_price(plan['take_profit'])} "
        f"({plan['risk_reward']:.1f}R), ~35% at Target 2 "
        f"{fmt_price(plan['take_profit_2'])} ({plan['risk_reward_2']:.1f}R), "
        f"the rest at Target 3 {fmt_price(plan['take_profit_3'])} "
        f"({plan['risk_reward_3']:.1f}R). Each target is a real swing level.",
        "Once Target 1 fills, move the stop to your entry price "
        "(break-even) — the rest of the trade is then risk-free.",
    ]
    if plan.get("mode") == "spot":
        steps.append(
            f"Spot sizing — buy ≈{plan.get('position_pct', 0):.0f}% of your "
            f"account capital so a stop-out costs only "
            f"~{signals.RISK_PER_TRADE_PCT:g}% of the account (no leverage).")
    else:
        steps.append(
            f"Futures sizing — ≈{plan.get('leverage', 1):g}× leverage on a "
            f"≈{plan.get('position_pct', 0):.0f}% margin allocation; a stop-out "
            f"then costs ~{signals.RISK_PER_TRADE_PCT:g}% of the account.")
    return steps


def _trade_decision(row, timeframe: str) -> dict:
    """Derive a buy/hold/sell decision, hold horizon and entry timing."""
    score = row["score"]
    plan = row.get("trade_plan")
    regime = row.get("regime", "Unknown")

    if score >= 40:
        decision, color = "BUY", "#2ed47a"
    elif score >= 15:
        decision, color = "ACCUMULATE", "#7bd88f"
    elif score > -15:
        decision, color = "HOLD / WAIT", "#c9a227"
    elif score > -40:
        decision, color = "REDUCE", "#ff8a7a"
    else:
        decision, color = "SELL / AVOID", "#ff5c5c"

    base = {"15m": "a few hours (intraday)", "1h": "1–3 days",
            "4h": "several days to ~2 weeks",
            "1d": "several weeks to months"}.get(timeframe, "a few days")
    if regime == "Trending":
        hold = f"{base} — trend intact; hold while the structure holds"
    elif regime == "Ranging":
        hold = f"shorter than {base} — ranging market, bank profit quickly"
    else:
        hold = base

    if decision in ("BUY", "ACCUMULATE") and isinstance(plan, dict):
        when = (f"Enter on a pullback into {fmt_price(plan['entry_low'])}–"
                f"{fmt_price(plan['entry_high'])}, stop "
                f"{fmt_price(plan['stop_loss'])}.")
    elif decision == "BUY":
        when = "Momentum is live — enter now or on the first shallow dip."
    elif decision == "HOLD / WAIT":
        when = "No clean setup — wait for a stronger signal before buying."
    else:
        when = "Avoid new longs; trim or exit existing exposure."

    if score >= 15 and isinstance(plan, dict):
        outlook = (f"Bullish bias — scope toward "
                   f"{fmt_price(plan['take_profit'])} while price holds "
                   f"above {fmt_price(plan['stop_loss'])}.")
    elif score <= -15 and isinstance(plan, dict):
        outlook = (f"Bearish bias — downside risk toward "
                   f"{fmt_price(plan['take_profit'])} while price stays "
                   f"below {fmt_price(plan['stop_loss'])}.")
    else:
        outlook = ("Rangebound / no directional edge — wait for a breakout "
                   "or a stronger signal before acting.")
    return {"decision": decision, "color": color, "hold": hold,
            "when": when, "outlook": outlook}


def render_action_plan(plan: dict, regime: str, confidence: int,
                       symbol: str, agg: dict,
                       nearest_sup: float | None,
                       nearest_res: float | None) -> None:
    """Render the prominent trade action-plan card."""
    side = plan["side"]
    accent = "#34c759" if side == "LONG" else "#ff6b5b"
    coin = symbol.replace("USDT", "")
    mode = plan.get("mode", "futures")
    mat = plan.get("maturity") or {}
    mat_color = {"EARLY": "#34c759", "RE-RUN": "#6e8bff",
                 "EXTENDED": "#ff8a3d"}.get(mat.get("stage"), "#8e8e93")
    mat_label = {"EARLY": "EARLY — room to run",
                 "RE-RUN": "RE-RUN SETUP — second-leg entry",
                 "EXTENDED": "EXTENDED — move already ran"}.get(
                     mat.get("stage"), "MOVE STAGE UNKNOWN")
    risk_unit = signals.RISK_PER_TRADE_PCT
    with st.container(border=True):
        st.markdown(
            f"<h4 style='margin:0 0 6px 0'>📋 Action Plan &nbsp;"
            f"<span style='color:{accent}'>{side} {coin}</span>"
            f"<span style='float:right;color:#888;font-size:0.8rem'>"
            f"{mode.upper()} · regime: {regime}</span></h4>",
            unsafe_allow_html=True)
        if mat:
            st.markdown(
                f"<div style='background:{mat_color}1f;border-left:3px solid "
                f"{mat_color};padding:6px 11px;border-radius:4px;"
                f"margin:2px 0 12px 0'>"
                f"<b style='color:{mat_color}'>{mat_label}</b>"
                f"<span style='color:#888'> · {mat.get('confidence', 0)}% "
                f"confidence</span><br><span style='font-size:0.85rem;"
                f"color:#bbb'>{mat.get('note', '')}</span></div>",
                unsafe_allow_html=True)
        c1, c2, c3, c4 = st.columns(4)
        c1.metric("Entry zone", fmt_price(plan["entry"]),
                  f"{fmt_price(plan['entry_low'])} – "
                  f"{fmt_price(plan['entry_high'])}")
        c2.metric("Stop loss", fmt_price(plan["stop_loss"]),
                  f"-{plan['risk_pct']:.2f}% · {plan.get('stop_basis', '')}")
        c3.metric("Target 1", fmt_price(plan["take_profit"]),
                  f"{plan['risk_reward']:.1f}R")
        c4.metric("Target 2", fmt_price(plan["take_profit_2"]),
                  f"{plan['risk_reward_2']:.1f}R")
        t1, t2 = st.columns([1, 3])
        t1.metric("Target 3", fmt_price(plan["take_profit_3"]),
                  f"{plan['risk_reward_3']:.1f}R")
        pos = plan.get("position_pct", 0.0)
        lev = plan.get("leverage", 1.0)
        if mode == "spot":
            t2.markdown(
                f"**Position sizing** — risking **{risk_unit:g}%** of your "
                f"account: with the stop **{plan['risk_pct']:.2f}%** away, buy "
                f"**≈{pos:.0f}%** of account capital (spot, no leverage). "
                f"R:R is built from real swing structure, so a wider stop "
                f"gives a smaller position — that is why every coin differs.")
        else:
            t2.markdown(
                f"**Position sizing** — risking **{risk_unit:g}%** of account: "
                f"suggested **{lev:g}× leverage** on a margin allocation of "
                f"**≈{pos:.0f}%** of account. Leverage scales with signal "
                f"confidence and is capped on volatile (wide-stop) coins, so "
                f"each coin gets its own size — never a copy-paste.")
        st.caption(plan["regime_fit"])
        st.progress(int(confidence), text=f"Signal confidence · {confidence}%")

        market = ("tradeable on Spot or Futures" if side == "LONG"
                  else "tradeable on Futures / Margin only — you cannot "
                       "short on a spot account")
        st.caption(f"This is a {side} setup, {market}.")
        st.markdown("**✅ Trading actions — follow in order**")
        for _i, _step in enumerate(
                _action_steps(plan, agg, nearest_sup, nearest_res), 1):
            st.markdown(f"{_i}. {_step}")
        st.caption("Educational walkthrough — not financial advice. Price "
                   "can gap straight through stops in fast markets.")


def render_orderflow(snap: dict) -> None:
    """Render the live order-flow panel (recent trades + book depth)."""
    flow, book = snap.get("flow"), snap.get("book")
    with st.container(border=True):
        st.markdown("#### 🟢🔴 Live Order Flow")
        if flow:
            st.markdown(pressure_bar(flow["buy_pct"]), unsafe_allow_html=True)
            f1, f2, f3 = st.columns(3)
            f1.metric("Aggressive buys", f"${flow['buy_quote']:,.0f}")
            f2.metric("Aggressive sells", f"${flow['sell_quote']:,.0f}")
            f3.metric("Net flow", f"${flow['net_quote']:,.0f}",
                      flow["pressure"])
            st.caption(f"Last {flow['trades']:,} executed trades over "
                       f"~{flow['window_seconds'] / 60:.1f} min · "
                       f"{flow['pressure']}.")
            if flow["large_trades"]:
                lt = pd.DataFrame([
                    {"Side": t["side"], "Price": fmt_price(t["price"]),
                     "Size (USDT)": f"${t['quote']:,.0f}",
                     "Time": t["time"].strftime("%H:%M:%S")}
                    for t in flow["large_trades"]])
                st.dataframe(
                    lt.style.map(
                        lambda v: ("color:#34c759;font-weight:700;"
                                   if v == "BUY" else
                                   "color:#ff6b5b;font-weight:700;"
                                   if v == "SELL" else ""),
                        subset=["Side"]),
                    use_container_width=True, hide_index=True)
        else:
            st.caption("Live trade feed unavailable for this symbol.")
        if book:
            st.markdown(f"**Order book** · ±{config.DEPTH_BAND_PCT:.1f}% band")
            b1, b2, b3 = st.columns(3)
            b1.metric("Bid depth", f"${book['bid_quote']:,.0f}")
            b2.metric("Ask depth", f"${book['ask_quote']:,.0f}")
            b3.metric("Book imbalance", f"{book['imbalance_pct']:.0f}% bid")
            sup, res = book.get("support"), book.get("resistance")
            if sup and res:
                st.caption(
                    f"{book['verdict']} · nearest support wall "
                    f"{fmt_price(sup['price'])} (${sup['quote']:,.0f}) · "
                    f"resistance wall {fmt_price(res['price'])} "
                    f"(${res['quote']:,.0f}).")


def render_history(symbol: str, df1d, ticker_row, detail: dict,
                   levels: tuple) -> None:
    """Render the price-history, key-levels and trend-context panel."""
    with st.container(border=True):
        st.markdown("#### 📜 Price History & Key Levels")
        price = detail["price"]
        cols = st.columns(4)
        if ticker_row is not None:
            hi, lo = ticker_row["highPrice"], ticker_row["lowPrice"]
            pos = (price - lo) / (hi - lo) * 100 if hi > lo else 50.0
            cols[0].metric("24h change",
                           f"{ticker_row['priceChangePercent']:+.2f}%")
            cols[1].metric("24h range position", f"{pos:.0f}%",
                           help="0% = at the 24h low, 100% = at the 24h high")
        if df1d is not None and len(df1d) >= 30:
            d30 = df1d.tail(30)
            h30, l30 = d30["high"].max(), d30["low"].min()
            pos30 = (price - l30) / (h30 - l30) * 100 if h30 > l30 else 50.0
            cols[2].metric("30d range position", f"{pos30:.0f}%")
        if df1d is not None and len(df1d) >= 90:
            perf90 = (price / df1d["close"].iloc[-90] - 1) * 100
            cols[3].metric("90d performance", f"{perf90:+.1f}%")

        nearest_sup, nearest_res = levels
        lv = st.columns(2)
        lv[0].metric(
            "Nearest support",
            fmt_price(nearest_sup) if nearest_sup else "—",
            f"{(nearest_sup / price - 1) * 100:+.2f}% away"
            if nearest_sup else None, delta_color="off")
        lv[1].metric(
            "Nearest resistance",
            fmt_price(nearest_res) if nearest_res else "—",
            f"{(nearest_res / price - 1) * 100:+.2f}% away"
            if nearest_res else None, delta_color="off")

        bits = [f"Market regime **{detail['regime']}**"]
        if detail.get("adx") is not None:
            bits.append(f"ADX {detail['adx']} (+DI {detail['plus_di']} / "
                        f"-DI {detail['minus_di']})")
        if detail.get("vwap"):
            bits.append("price "
                        + ("above" if price >= detail["vwap"] else "below")
                        + " VWAP")
        if df1d is not None and not pd.isna(df1d["ema_trend"].iloc[-1]):
            above = price >= df1d["ema_trend"].iloc[-1]
            bits.append(("above" if above else "below")
                        + " the 200-day EMA — long-term "
                        + ("uptrend" if above else "downtrend"))
        if detail.get("atr_pct"):
            bits.append(f"volatility {detail['atr_pct']}% ATR")
        st.caption(" · ".join(bits))


def render_lunarcrush(metrics: dict | None, base_asset: str) -> None:
    """Render the LunarCrush social-intelligence panel."""
    with st.container(border=True):
        st.markdown("#### 🌙 LunarCrush Social Intelligence")
        if metrics is None:
            if not lunarcrush.is_configured():
                st.info(
                    "LunarCrush is not configured. It is a paid API that "
                    "aggregates X/Twitter and other social platforms into "
                    "Galaxy Score, AltRank and sentiment. To enable it: "
                    "subscribe at lunarcrush.com, copy `.env.example` to "
                    "`.env`, add your `LUNARCRUSH_API_KEY`, then restart.")
            else:
                st.caption(
                    f"No LunarCrush data for {base_asset}. Your API key is "
                    f"loaded, but the LunarCrush API needs an **active "
                    f"Individual (or higher) subscription** — a free account "
                    f"returns no data. Activate a plan at lunarcrush.com.")
            return

        gs = metrics.get("galaxy_score")
        col1, col2 = st.columns([1, 2])
        with col1:
            if gs is not None:
                st.plotly_chart(
                    confidence_gauge(float(gs), suffix=""),
                    use_container_width=True,
                    config={"displayModeBar": False})
                st.caption("Galaxy Score — combined social + market "
                           "health (0-100)")
            else:
                st.caption("Galaxy Score unavailable")
        with col2:
            mc = st.columns(2)
            ar = metrics.get("alt_rank")
            ar_prev = metrics.get("alt_rank_prev")
            if ar is not None:
                delta = (f"{ar_prev - ar:+.0f} vs prev"
                         if ar_prev is not None else None)
                mc[0].metric(
                    "AltRank", f"#{ar:,.0f}", delta,
                    help="Combined price + social rank — lower is better")
            sent = metrics.get("sentiment")
            if sent is not None:
                mc[1].metric("Social sentiment", f"{sent:.0f}%",
                             help="Share of social posts that are positive")
            sd = metrics.get("social_dominance")
            if sd is not None:
                mc[0].metric("Social dominance", f"{sd:.2f}%")
            iv = metrics.get("interactions_24h")
            if iv is not None:
                mc[1].metric("Interactions 24h", f"{iv:,.0f}")
        st.caption("Source: LunarCrush — social data aggregated from "
                   "X/Twitter and other platforms.")


def render_bottom_line(agg: dict, detail: dict, per_tf: dict,
                       tv_rating: dict | None, flow_snap: dict,
                       lc_metrics: dict | None) -> None:
    """Synthesise every data source into one expert bottom-line verdict."""
    reads: list[tuple[str, str, str]] = []
    reads.append((
        "Trend & momentum",
        "bull" if agg["bias_score"] > 8
        else "bear" if agg["bias_score"] < -8 else "neutral",
        f"{agg['bias_label']} bias · {agg['action_label']} timing"))
    if tv_rating:
        reads.append((
            "TradingView", "bull" if tv_rating["score"] > 10
            else "bear" if tv_rating["score"] < -10 else "neutral",
            tv_rating["recommendation"]))
    flow = flow_snap.get("flow")
    if flow:
        reads.append((
            "Live order flow", "bull" if flow["buy_pct"] >= 55
            else "bear" if flow["buy_pct"] <= 45 else "neutral",
            f"{flow['buy_pct']:.0f}% aggressive buys"))
    dv = detail.get("derivatives")
    if dv and dv.get("long_short_ratio") is not None:
        ls = dv["long_short_ratio"]
        reads.append((
            "Derivatives positioning",
            "bear" if ls >= 2.2 else "bull" if ls <= 0.9 else "neutral",
            f"long/short ratio {ls:.2f}"))
    if lc_metrics and lc_metrics.get("sentiment") is not None:
        s = lc_metrics["sentiment"]
        reads.append((
            "Social (LunarCrush)", "bull" if s >= 60
            else "bear" if s <= 40 else "neutral",
            f"Galaxy {lc_metrics.get('galaxy_score', '—')} · "
            f"sentiment {s:.0f}%"))

    bulls = sum(1 for _, s, _ in reads if s == "bull")
    bears = sum(1 for _, s, _ in reads if s == "bear")
    score, conf = agg["score"], detail["confidence"]

    if score >= 30 and bulls >= bears:
        head, col = "Bullish — the edge favours longs", "#2ed47a"
    elif score <= -30 and bears >= bulls:
        head, col = "Bearish — the edge favours shorts", "#ff5c5c"
    elif abs(score) < 15 or abs(bulls - bears) <= 1:
        head, col = "Mixed / Neutral — no clear edge, stand aside", "#c9a227"
    elif score > 0:
        head, col = "Leaning bullish — partial confirmation only", "#7bd88f"
    else:
        head, col = "Leaning bearish — partial confirmation only", "#ff8a7a"

    dot = {"bull": "#2ed47a", "bear": "#ff5c5c", "neutral": "#8b8d98"}
    with st.container(border=True):
        st.markdown(
            f"<div style='font-size:0.72rem;letter-spacing:0.09em;"
            f"color:#8b8d98;font-weight:700'>THE BOTTOM LINE</div>"
            f"<div style='font-size:1.35rem;font-weight:800;color:{col};"
            f"margin:3px 0 4px 0'>{head}</div>"
            f"<div style='color:#8b8d98;font-size:0.85rem'>"
            f"{bulls} bullish · {bears} bearish signals · composite score "
            f"{score:+.0f} · {conf}% confidence</div>",
            unsafe_allow_html=True)
        rows = "".join(
            f"<div style='display:flex;gap:9px;align-items:center;"
            f"margin:5px 0'><span style='width:8px;height:8px;border-radius:"
            f"50%;background:{dot[s]};display:inline-block;flex:none'></span>"
            f"<span style='color:#c9cbd4;font-weight:600;min-width:185px'>"
            f"{src}</span><span style='color:#8b8d98'>{note}</span></div>"
            for src, s, note in reads)
        st.markdown(rows, unsafe_allow_html=True)

        st.markdown("---")
        st.markdown("**🔬 Detailed analysis**")
        for _heading, _text in _analysis_sections(
                agg, detail, per_tf, tv_rating, flow_snap, lc_metrics):
            st.markdown(f"**{_heading}.** {_text}")
        st.markdown("---")

        plan = detail.get("trade_plan")
        if plan and abs(score) >= 15:
            st.caption(
                f"Expert read — act on the {plan['side']} plan below only "
                f"once price reaches the entry zone and the timing signal "
                f"agrees; otherwise wait. Always keep the stop.")
        else:
            st.caption(
                "Expert read — signals conflict or are weak; the "
                "highest-probability action right now is to wait for "
                "alignment rather than force a trade.")


def render_lunarcrush_leaderboard(rows: list) -> None:
    """Render a LunarCrush social leaderboard across the major coins."""
    with st.container(border=True):
        st.markdown("#### 🌙 LunarCrush Social Leaderboard")
        if not rows:
            if not lunarcrush.is_configured():
                st.info("LunarCrush is not configured — add your API key to "
                        "the `.env` file to enable social intelligence.")
            else:
                st.caption("LunarCrush data is unavailable right now.")
            return

        coins = [r for r in rows
                 if r.get("market_cap_rank")
                 and r.get("galaxy_score") is not None]
        coins = sorted(coins, key=lambda r: r["market_cap_rank"])[:150]
        if not coins:
            st.caption("No ranked LunarCrush coins available.")
            return

        sents = [r["sentiment"] for r in coins
                 if r.get("sentiment") is not None]
        top = max(coins, key=lambda r: r["galaxy_score"])
        c1, c2, c3 = st.columns(3)
        c1.metric("Coins tracked", len(coins))
        c2.metric("Top Galaxy Score",
                  f"{top['symbol']} · {top['galaxy_score']:.0f}")
        if sents:
            c3.metric("Avg social sentiment",
                      f"{sum(sents) / len(sents):.0f}%")

        board = sorted(coins, key=lambda r: r["galaxy_score"],
                       reverse=True)[:25]
        df = pd.DataFrame([{
            "Coin": r["symbol"],
            "Galaxy": r["galaxy_score"],
            "Galaxy Δ": (round(r["galaxy_score"] - r["galaxy_score_previous"],
                               1)
                         if r.get("galaxy_score_previous") is not None
                         else None),
            "AltRank": r.get("alt_rank"),
            "Sentiment": r.get("sentiment"),
            "Social Dom %": (round(r["social_dominance"], 2)
                             if r.get("social_dominance") is not None
                             else None),
            "24h %": (round(r["percent_change_24h"], 2)
                      if r.get("percent_change_24h") is not None else None),
        } for r in board])
        st.dataframe(
            df, use_container_width=True, hide_index=True, height=460,
            column_config={
                "Galaxy": st.column_config.ProgressColumn(
                    "Galaxy", min_value=0, max_value=100, format="%d"),
                "Sentiment": st.column_config.ProgressColumn(
                    "Sentiment", min_value=0, max_value=100, format="%d%%"),
                "24h %": st.column_config.NumberColumn(
                    "24h %", format="%.2f%%"),
                "Galaxy Δ": st.column_config.NumberColumn(
                    "Galaxy Δ", format="%+.1f"),
            })
        st.caption("Ranked by Galaxy Score — LunarCrush's 0-100 social + "
                   "market health metric — among the top 150 coins by market "
                   "cap. AltRank: lower is better. Galaxy Δ is the change vs "
                   "the previous reading.")


def breakout_accent(row: dict) -> str:
    """Pick the accent colour for a Breakout Radar card."""
    if row["chasing_risk"]:
        return "#e0a92b"                       # amber — extended / chasing risk
    if row["dir_word"] == "BULLISH":
        return "#2ed47a"
    if row["dir_word"] == "BEARISH":
        return "#ff5c5c"
    return "#8b8d98"


def render_breakout_card(row: dict, rank: int) -> None:
    """Render one Breakout Radar candidate card."""
    accent = breakout_accent(row)
    idea = row["idea"]
    strength = oracle.signal_strength(row)
    ignite = (
        "&nbsp;<span style='background:rgba(255,138,43,0.16);"
        "border:1px solid rgba(255,138,43,0.55);color:#ff9d3d;padding:3px 9px;"
        "border-radius:7px;font-size:0.68rem;font-weight:800'>🔥 VOLUME "
        "SURGING</span>" if row.get("ignited") else "")
    with st.container(border=True):
        st.markdown(
            f"<div style='display:flex;justify-content:space-between;"
            f"align-items:baseline;flex-wrap:wrap;gap:6px'>"
            f"<div style='font-size:1.16rem;font-weight:800'>"
            f"<span style='color:#6b7080'>#{rank}</span>&nbsp; "
            f"{row['emoji']} {row['base']} / USDT &nbsp;"
            f"<span style='background:{accent};color:#06121f;padding:3px 12px;"
            f"border-radius:7px;font-size:0.72rem;font-weight:800;"
            f"letter-spacing:0.03em'>{row['verdict']}</span>{ignite}</div>"
            f"<div style='color:#8b8d98;font-size:0.82rem;font-weight:600'>"
            f"radar score {row['opportunity']:.0f}/100 · "
            f"{row['confidence']}% confidence · "
            f"signal {strength['label'].lower()} ({strength['score']})"
            f"</div></div>",
            unsafe_allow_html=True)

        if row["chasing_risk"]:
            st.markdown(
                "<div style='background:rgba(224,169,43,0.12);"
                "border:1px solid rgba(224,169,43,0.45);border-radius:9px;"
                "padding:7px 12px;margin:8px 0;font-size:0.84rem;"
                "color:#e9c66b;font-weight:600'>⚠️ This coin has already made "
                "its big move — it is too late to enter safely. Don't chase "
                "it: wait for it to pull back, or just manage a position you "
                "already hold.</div>",
                unsafe_allow_html=True)

        m = st.columns(6)
        m[0].metric("Price", fmt_price(row["price"]))
        m[1].metric("1h", f"{row['chg_1h']:+.2f}%")
        m[2].metric("24h", f"{row['chg_24h']:+.2f}%")
        m[3].metric("24h Vol", fmt_volume(row.get("quoteVolume")),
                    help="24h traded value — a liquidity check")
        m[4].metric("Surge", f"{row['vol_peak']:.1f}x",
                    help="Peak recent volume vs its 20-candle average")
        m[5].metric("RSI", f"{row['rsi']:.0f}")

        st.progress(min(int(row["opportunity"]), 100),
                    text=f"🎯 Radar score {row['opportunity']:.0f}/100  ·  "
                         f"{_STAGE_WORD.get(row['stage'], row['stage'])}")

        st.markdown(f"**Why it's on the radar** — {md_safe(row['summary'])}")
        st.markdown(f"**📰 News** — {md_safe(row['news_read'])}")
        st.caption(f"⏱️ Timing — {row['window']} · {row['regime_4h']} backdrop")

        # --- Entry & exit plan, shown prominently in the card body ---------
        st.markdown(f"**🎯 The play** — {md_safe(idea['play'])}")
        if idea["side"] != "EITHER":
            tc = st.columns(4)
            tc[0].metric("Entry zone", md_safe(
                f"{fmt_price(idea['entry_low'])} – "
                f"{fmt_price(idea['entry_high'])}"))
            tc[1].metric("Stop loss", fmt_price(idea["stop"]))
            tc[2].metric("Exit 1", fmt_price(idea["target_1"]))
            tc[3].metric("Exit 2", fmt_price(idea["target_2"]))
        else:
            tc = st.columns(3)
            tc[0].metric("Long trigger", fmt_price(row["win_high"]))
            tc[1].metric("Short trigger", fmt_price(row["win_low"]))
            tc[2].metric("Stay flat inside", md_safe(
                f"{fmt_price(row['win_low'])} – "
                f"{fmt_price(row['win_high'])}"))
        st.caption(f"Exit plan — {md_safe(idea['exit_note'])}")

        chips = ""
        for d in row["drivers"]:
            sc = d["score"]
            if d["signed"]:
                col = ("#2ed47a" if sc >= 15 else "#ff5c5c" if sc <= -15
                       else "#8b8d98")
                val = f"{sc:+d}"
            else:
                col = ("#6e8bff" if sc >= 55 else "#9aa0b4" if sc >= 25
                       else "#5b5f6e")
                val = f"{sc}"
            chips += (f"<span style='display:inline-block;margin:3px 6px 3px 0;"
                      f"padding:4px 10px;border-radius:7px;font-size:0.76rem;"
                      f"background:#1a1c24;border:1px solid {col}55'>"
                      f"<span style='color:#c9cbd4;font-weight:600'>"
                      f"{d['force']}</span> "
                      f"<span style='color:{col};font-weight:800'>{val}</span>"
                      f"</span>")
        st.markdown(chips, unsafe_allow_html=True)

        with st.expander("🔬 Full breakdown — every signal explained"):
            for d in row["drivers"]:
                tag = (f"{d['score']:+d}" if d["signed"]
                       else f"{d['score']} / 100")
                st.markdown(f"- **{d['force']}** ({tag}) — "
                            f"{md_safe(d['note'])}")
        st.caption("Educational — algorithmic detection, not financial "
                   "advice. Fast moves can gap straight through stops.")


_STAGE_WORD = {"COILED": "Building Up", "FRESH": "Just Started",
               "EXTENDED": "Already Ran"}


def breakout_side_table(df_side: pd.DataFrame, side: str) -> None:
    """Render a compact ranked table for one side — 'UP' (long) or 'DOWN'
    (short). Entry and Target are computed for that side's trade."""
    if df_side.empty:
        st.caption("No coins on this side right now.")
        return

    def _entry(r: dict) -> float:
        idea = r["idea"]
        if idea["side"] != "EITHER":
            return idea["entry_low"]
        return r["win_high"] if side == "UP" else r["win_low"]

    def _target(r: dict) -> float:
        idea = r["idea"]
        if idea["side"] != "EITHER":
            return idea["target_1"]
        return idea["target_1"] if side == "UP" else idea["target_2"]

    tbl = pd.DataFrame({
        "Coin": df_side["base"],
        "Status": df_side.apply(
            lambda r: ("🔥 " if r["ignited"] else "")
            + _STAGE_WORD.get(r["stage"], r["stage"]), axis=1),
        "Score": df_side["opportunity"],
        "Confidence": df_side["confidence"],
        "Entry": df_side.apply(lambda r: fmt_price(_entry(r)), axis=1),
        "Target": df_side.apply(lambda r: fmt_price(_target(r)), axis=1),
        "24h Vol": (df_side["quoteVolume"].map(fmt_volume)
                    if "quoteVolume" in df_side.columns else "—"),
    })
    st.dataframe(
        tbl, use_container_width=True, hide_index=True,
        height=min((len(tbl) + 1) * 36 + 3, 760),
        column_config={
            "Score": st.column_config.ProgressColumn(
                "Score", min_value=0, max_value=100, format="%d",
                help="0-100 radar rank — higher is a stronger setup"),
            "Confidence": st.column_config.NumberColumn(
                "Confidence", format="%d%%",
                help="How sure the engine is of the direction"),
        })


def render_oracle_answer(result: dict) -> None:
    """Render the Oracle's answer — a headline panel plus matching cards."""
    accent = {"bullish": "#2ed47a", "bearish": "#ff5c5c",
              "mixed": "#e0a92b", "empty": "#8b8d98"}.get(
                  result.get("tone", "mixed"), "#6e8bff")
    with st.container(border=True):
        st.markdown(
            f"<div style='font-size:0.72rem;letter-spacing:0.09em;"
            f"color:#8b8d98;font-weight:700'>🤖 THE ORACLE SAYS</div>"
            f"<div style='font-size:1.22rem;font-weight:800;color:{accent};"
            f"margin:4px 0 6px 0'>{md_safe(result['headline'])}</div>"
            f"<div style='color:#c9cbd4;font-size:0.9rem'>"
            f"{md_safe(result['detail'])}</div>",
            unsafe_allow_html=True)
    coins = result.get("coins")
    if coins is not None and not coins.empty:
        for _i, (_, _r) in enumerate(coins.iterrows(), 1):
            render_breakout_card(_r.to_dict(), _i)


def render_buy_zone_board(radar: pd.DataFrame, backdrop: dict,
                          mcap_map: dict) -> None:
    """Render the bullish-accumulation buy-zone board."""
    st.markdown("### 🟢 Bullish Buy Zones — where to accumulate")
    zones = oracle.buy_zones(radar, mcap_map)
    if zones is None or zones.empty:
        st.info("No clean bullish accumulation setups on the radar right "
                "now — nothing is coiled or freshly breaking to the upside. "
                "Try the other horizon, or check back after the next "
                "candles close.")
        return

    if backdrop:
        score = backdrop.get("score", 0) or 0
        tape = ("a tailwind for these longs" if score >= 22
                else "a headwind — size these down" if score <= -22
                else "broadly neutral for these longs")
        st.caption(f"🌍 **Worldwide backdrop** — {backdrop.get('label', '—')}: "
                   f"{backdrop.get('note', '')}. That is {tape}.")

    table = pd.DataFrame({
        "Coin": zones["base"],
        "Signal": zones.apply(
            lambda r: f"{r['strength_label']} · {r['strength']:.0f}", axis=1),
        "Status": zones.apply(
            lambda r: ("🔥 " if r["ignited"] else "")
            + _STAGE_WORD.get(r["stage"], r["stage"]), axis=1),
        "Buy zone": zones.apply(
            lambda r: f"{fmt_price(r['buy_low'])} – {fmt_price(r['buy_high'])}",
            axis=1),
        "Trigger": zones["trigger"].map(fmt_price),
        "Stop": zones["bz_stop"].map(
            lambda v: fmt_price(v) if v is not None and v == v else "—"),
        "Target 1": zones.apply(
            lambda r: f"{fmt_price(r['bz_t1'])}  (+{r['bz_gain1']:.1f}%)",
            axis=1),
        "Target 2": zones.apply(
            lambda r: f"{fmt_price(r['bz_t2'])}  (+{r['bz_gain2']:.1f}%)",
            axis=1),
        "Target 3": zones.apply(
            lambda r: f"{fmt_price(r['bz_t3'])}  (+{r['bz_gain3']:.1f}%)",
            axis=1),
        "R : R": zones.apply(
            lambda r: (f"{r['bz_rr1']:.1f}–{r['bz_rr3']:.1f}"
                       if r['bz_rr1'] > 0 else "—"), axis=1),
        "Score": zones["opportunity"],
        "Conf": zones["confidence"],
        "Cap tier": zones["cap_tier"],
        "Circulating": zones["circ_pct"].map(
            lambda v: f"{v:.0f}%" if v is not None and v == v else "—"),
    })
    st.dataframe(
        table, use_container_width=True, hide_index=True,
        height=min((len(table) + 1) * 36 + 3, 520),
        column_config={
            "Score": st.column_config.ProgressColumn(
                "Score", min_value=0, max_value=100, format="%d",
                help="Radar opportunity rank — rewards early, coiled setups."),
            "Conf": st.column_config.NumberColumn(
                "Conf", format="%d%%",
                help="How sure the engine is of the bullish direction."),
            "Signal": st.column_config.TextColumn(
                "Signal",
                help="Signal strength — the breadth and force of the ~11 "
                     "detection signals backing this breakout "
                     "(Weak / Moderate / Strong / Very Strong, 0-100). "
                     "Trade the strongest rows first."),
            "R : R": st.column_config.TextColumn(
                "R : R",
                help="Reward-to-risk from the buy zone, Target 1 through "
                     "Target 3 — e.g. '1.8–5.4' means Target 1 pays 1.8x "
                     "the risked amount and Target 3 pays 5.4x."),
            "Circulating": st.column_config.TextColumn(
                "Circulating",
                help="Circulating supply as a % of max supply — a high % "
                     "means little future dilution; a low % means many "
                     "tokens are still to be unlocked."),
        })
    st.caption(
        "**How to use this** — **Signal** is how forcefully the breakout is "
        "backed: how many of the ~11 detection forces (volume, momentum, "
        "order flow, trend, strength vs BTC, social, news…) pull the same "
        "way, and how hard — trade the **Strong** and **Very Strong** rows "
        "first. The **Buy zone** is where to accumulate: inside the range "
        "for *Building Up* coins (positioned **before** the break), the "
        "retest of the broken level for *Just Started* coins. A clean "
        "candle close above the **Trigger** confirms the move; always set "
        "the **Stop**. **R : R** is reward-to-risk measured from the buy "
        "zone — the three targets carry +% gains; only take rows where "
        "Target 1 already pays more than 1.0x the risk. A low "
        "**Circulating** % flags dilution as more tokens unlock. "
        "Educational only — not financial advice.")

    st.markdown("#### 📋 Top 3 — full read & trade plan")
    for _i, (_, _r) in enumerate(zones.head(3).iterrows(), 1):
        render_breakout_card(_r.to_dict(), _i)


def _render_alert_setup(s: dict, is_new: bool) -> None:
    """One high-confidence setup line inside the Trade Alerts strip."""
    color = "#2ed47a" if s["side"] == "LONG" else "#ff5c5c"
    word = "BULLISH" if s["side"] == "LONG" else "BEARISH"
    proof = " · ".join(s["proof"]) if s["proof"] else "multiple signals aligned"
    new_tag = " 🆕" if is_new else ""
    st.markdown(
        f"<div style='border-left:3px solid {color};padding:6px 11px;"
        f"margin:6px 0;background:{color}14;border-radius:5px'>"
        f"<span style='font-weight:800'>{s['base']}</span> "
        f"<span style='color:{color};font-weight:800'>{word}</span> · "
        f"{s['confidence']}% confidence · R:R {s['rr']:.1f}{new_tag}<br>"
        f"<span style='font-size:0.8rem;color:#aab'>proof — "
        f"{md_safe(proof)}</span><br>"
        f"<span style='font-size:0.8rem;color:#889'>entry "
        f"{fmt_price(s['entry_low'])}–{fmt_price(s['entry_high'])} · stop "
        f"{fmt_price(s['stop'])} · target {fmt_price(s['target'])}</span>"
        f"</div>",
        unsafe_allow_html=True)


def _render_alert_surge(s: dict, is_new: bool) -> None:
    """One volume-surge line inside the Trade Alerts strip."""
    chg = s.get("change_24h")
    chg_txt = (f" · {chg:+.1f}% 24h" if chg is not None and chg == chg else "")
    lab = s["label"]
    lab_col = ("#2ed47a" if "LONG" in lab else "#ff5c5c" if "SHORT" in lab
               else "#8b8d98")
    new_tag = " 🆕" if is_new else ""
    st.markdown(
        f"<div style='padding:5px 11px;margin:6px 0;background:#1a1c24;"
        f"border-radius:5px;border:1px solid #ff8a3d44'>"
        f"🔥 <span style='font-weight:800'>{s['base']}</span> — volume "
        f"<span style='color:#ff9d3d;font-weight:800'>{s['vol_ratio']:.1f}×</span>"
        f" average{chg_txt} · <span style='color:{lab_col};font-weight:700'>"
        f"{lab}</span>{new_tag}</div>",
        unsafe_allow_html=True)


_BROWSER_ALERT_JS = """
<script>
(function(){
  try {
    var P = window.parent || window;
    var N = P.Notification || window.Notification;
    var items = __PAYLOAD__;
    var KEY = '__KEY__';
    function fire(){
      var raw = null;
      try { raw = P.localStorage.getItem(KEY); } catch(e){}
      var firstEver = (raw === null);
      var prev = {};
      if (!firstEver) {
        try { (JSON.parse(raw) || []).forEach(function(id){ prev[id]=1; }); }
        catch(e){}
      }
      items.forEach(function(a){
        if (!firstEver && !prev[a.id]) {
          try { new N(a.title, {body:a.body, tag:a.id, renotify:true}); }
          catch(e){}
        }
      });
      try {
        P.localStorage.setItem(KEY,
          JSON.stringify(items.map(function(a){ return a.id; })));
      } catch(e){}
    }
    if (N) {
      if (N.permission === 'granted') { fire(); }
      else if (N.permission !== 'denied') {
        N.requestPermission().then(function(p){ if(p==='granted') fire(); });
      }
    }
    var secs = __REFRESH__;
    if (secs > 0 && !P.__tiAutoReload) {
      P.__tiAutoReload = 1;
      setTimeout(function(){ try { P.location.reload(); } catch(e){} },
                 secs * 1000);
    }
  } catch(e){}
})();
</script>
"""


def _inject_browser_alerts(items: list[dict], refresh_secs: int,
                           key: str = "ti_notified_alerts") -> None:
    """Inject the JS that fires browser desktop notifications for new alerts
    and (when refresh_secs > 0) auto-refreshes the page so scanning continues
    in the background.

    De-duplication is client-side (localStorage under `key`), so it survives
    the auto-refresh — a full page reload resets Python state, but the
    browser remembers what it has already notified about and never repeats
    itself. The very first load only seeds that memory; it never fires a
    burst. A distinct `key` keeps separate alert streams independent."""
    html = (_BROWSER_ALERT_JS
            .replace("__PAYLOAD__", json.dumps(items))
            .replace("__REFRESH__", str(int(refresh_secs)))
            .replace("__KEY__", key))
    components.html(html, height=0)


def render_alerts(merged: pd.DataFrame, timeframe: str) -> None:
    """Global Trade Alerts strip — the few high-confidence setups and volume
    surges worth acting on for the *currently selected* timeframe, each shown
    with its proof, plus toast pop-ups when a brand-new one appears."""
    data = alerts.build_alerts(merged, timeframe)
    setups, surges = data["setups"], data["surges"]

    # New-since-last-view tracking, kept separately per timeframe.
    seen_all = st.session_state.setdefault("alert_seen", {})
    first_visit = timeframe not in seen_all
    prev = seen_all.get(timeframe, set())
    new_setup_syms = {s["symbol"] for s in setups
                      if s["symbol"] not in prev}
    new_surge_syms = {s["symbol"] for s in surges
                      if ("vol:" + s["symbol"]) not in prev}
    seen_all[timeframe] = ({s["symbol"] for s in setups}
                           | {"vol:" + s["symbol"] for s in surges})

    # Toast only genuinely new alerts — never on the first visit (which would
    # pop the whole board at once).
    if not first_visit:
        for s in [x for x in setups if x["symbol"] in new_setup_syms][:3]:
            st.toast(f"{s['base']} — {s['side']} setup, "
                     f"{s['confidence']}% confidence", icon="🚨")
        for s in [x for x in surges if x["symbol"] in new_surge_syms][:2]:
            st.toast(f"{s['base']} — volume surging {s['vol_ratio']:.1f}×",
                     icon="🔊")

    with st.container(border=True):
        st.markdown(
            f"<div style='display:flex;justify-content:space-between;"
            f"align-items:baseline'><span style='font-size:1.06rem;"
            f"font-weight:800'>🚨 Trade Alerts</span>"
            f"<span style='color:#8b8d98;font-size:0.8rem;font-weight:600'>"
            f"{timeframe} timeframe · {trade_mode.upper()} mode</span></div>",
            unsafe_allow_html=True)

        if not setups and not surges:
            st.info(
                f"No high-confidence setup on the **{timeframe}** timeframe "
                f"right now — nothing crosses the bar to act on. That is a "
                f"valid, useful answer: wait, don't force a trade.")
        else:
            ac1, ac2 = st.columns(2)
            with ac1:
                st.markdown(f"**🟢 High-confidence setups** ({len(setups)})")
                if not setups:
                    st.caption("None clear the confidence bar right now.")
                for s in setups[:5]:
                    _render_alert_setup(s, s["symbol"] in new_setup_syms)
            with ac2:
                st.markdown(f"**🔥 Volume surging** ({len(surges)})")
                if not surges:
                    st.caption("No coin's volume is surging right now.")
                for s in surges[:6]:
                    _render_alert_surge(s, s["symbol"] in new_surge_syms)

        st.caption(
            f"Alerts are built only from **{timeframe}** data — 15m, 1h, 4h "
            f"and 1d each have their own setups, so a coin can be a buy on "
            f"one timeframe and not another; that is expected, not a glitch. "
            f"A setup that stays on this list across refreshes is more "
            f"trustworthy than one that just appeared. 🆕 marks alerts new "
            f"since you last looked; pop-ups fire when a fresh one lands.")

    # Browser desktop notifications + background auto-refresh (opt-in).
    if alerts_on:
        notify_items: list[dict] = []
        for s in setups:
            bullish = s["side"] == "LONG"
            notify_items.append({
                "id": f"{s['symbol']}:{s['side']}",
                "title": (f"{'🟢' if bullish else '🔴'} {s['base']} "
                          f"{'BULLISH' if bullish else 'BEARISH'} setup"),
                "body": (f"{s['confidence']}% confidence · R:R "
                         f"{s['rr']:.1f} · {timeframe} · entry "
                         f"{fmt_price(s['entry_low'])}–"
                         f"{fmt_price(s['entry_high'])}"),
            })
        for s in surges:
            notify_items.append({
                "id": f"vol:{s['symbol']}",
                "title": f"🔥 {s['base']} volume surge",
                "body": (f"Volume {s['vol_ratio']:.1f}× average · "
                         f"{timeframe} timeframe"),
            })
        _inject_browser_alerts(notify_items, alert_every * 60)


def render_forecast(fc_df: pd.DataFrame) -> None:
    """Render the multi-timeframe forecast board with its alert callout."""
    st.subheader("🔮 Multi-Timeframe Forecast")
    st.caption(
        "Where each coin is projected to head over the next 15m, 1h and 4h "
        "candle. Each call fuses that timeframe's own technicals with the "
        "Breakout Radar read — news catalysts, the macro / geopolitical "
        "backdrop, volume ignition, social heat and funding. A forecast is "
        "a probabilistic lean with an expected move sized from the "
        "timeframe's ATR — not a guaranteed price.")
    if fc_df is None or fc_df.empty:
        st.warning("No forecast data right now — try refreshing.")
        return

    # --- Forecast alerts — aligned, high-conviction calls ------------------
    fa = alerts.build_forecast_alerts(fc_df)
    prev = st.session_state.get("forecast_seen")
    first_visit = prev is None
    new_syms = {a["symbol"] for a in fa
                if not first_visit and a["symbol"] not in prev}
    st.session_state["forecast_seen"] = {a["symbol"] for a in fa}
    for a in [x for x in fa if x["symbol"] in new_syms][:3]:
        st.toast(f"Forecast: {a['base']} {a['outlook'].lower()} across "
                 f"15m / 1h / 4h ({a['confidence']}%)", icon="🔮")

    with st.container(border=True):
        st.markdown("**🚨 Forecast Alerts** — coins projected the same way "
                    "across all three horizons with strong confidence")
        if not fa:
            st.caption("No coin is aligned across 15m, 1h and 4h with strong "
                       "confidence right now — the tape is mixed; wait.")
        else:
            for a in fa[:6]:
                color = "#2ed47a" if a["outlook"] == "Bullish" else "#ff5c5c"
                fire = " &nbsp;🔥 volume igniting" if a["ignited"] else ""
                tag = " 🆕" if a["symbol"] in new_syms else ""
                st.markdown(
                    f"<div style='border-left:3px solid {color};"
                    f"padding:5px 11px;margin:5px 0;background:{color}14;"
                    f"border-radius:5px'><b>{a['base']}</b> "
                    f"<span style='color:{color};font-weight:800'>"
                    f"{a['outlook'].upper()}</span> across 15m / 1h / 4h · "
                    f"{a['confidence']}% confidence · 4h move "
                    f"<b>{a['proj_4h_pct']:+.2f}%</b>{fire}{tag}</div>",
                    unsafe_allow_html=True)

    # Browser desktop notifications for forecast alerts — only when the user
    # has Desktop alerts switched on. Own localStorage key, no extra refresh.
    if alerts_on and fa:
        _inject_browser_alerts(
            [{"id": f"fc:{a['symbol']}:{a['outlook']}",
              "title": f"🔮 {a['base']} — {a['outlook']} forecast",
              "body": (f"Aligned across 15m / 1h / 4h · {a['confidence']}% "
                       f"confidence · 4h move {a['proj_4h_pct']:+.2f}%")}
             for a in fa],
            0, key="ti_notified_forecast")

    aligned_up = int(((fc_df["outlook_word"] == "Bullish")
                      & fc_df["aligned"]).sum())
    aligned_down = int(((fc_df["outlook_word"] == "Bearish")
                        & fc_df["aligned"]).sum())
    st.markdown(
        f"**{aligned_up}** coin(s) projected **up across all three "
        f"horizons**, **{aligned_down}** projected **down across all "
        f"three**. The full board is below, ranked by total expected move.")

    arrow = {"Up": "▲", "Down": "▼", "Sideways": "▬"}

    def cell(h: dict | None) -> str:
        if not h:
            return "—"
        return f"{arrow.get(h['direction'], '·')} {h['move_pct']:+.2f}%"

    rows = []
    for _, r in fc_df.iterrows():
        hz = r["horizons"] or {}
        h4 = hz.get("4h")
        rows.append({
            "Coin": ("🔥 " if r["ignited"] else "") + r["base"],
            "Price now": fmt_price(r["price"]),
            "Next 15m": cell(hz.get("15m")),
            "Next 1h": cell(hz.get("1h")),
            "Next 4h": cell(hz.get("4h")),
            "Projected 4h": fmt_price(h4["projected"]) if h4 else "—",
            "Outlook": r["outlook_word"],
            "Conf": int(r["confidence"]),
            "_lean": float(r["net_lean"]),
        })
    table = pd.DataFrame(rows).sort_values(
        "_lean", ascending=False).drop(columns=["_lean"])

    def _cell_color(v):
        if isinstance(v, str):
            if v.startswith("▲"):
                return "color:#2ed47a;font-weight:700"
            if v.startswith("▼"):
                return "color:#ff5c5c;font-weight:700"
            if v.startswith("▬"):
                return "color:#8b8d98"
        return ""

    def _outlook_color(v):
        return {"Bullish": "color:#2ed47a;font-weight:700",
                "Bearish": "color:#ff5c5c;font-weight:700"}.get(
                    v, "color:#8b8d98")

    styled = (table.style
              .map(_cell_color, subset=["Next 15m", "Next 1h", "Next 4h"])
              .map(_outlook_color, subset=["Outlook"]))
    st.dataframe(
        styled, use_container_width=True, hide_index=True,
        height=min((len(table) + 1) * 36 + 3, 720),
        column_config={
            "Conf": st.column_config.NumberColumn(
                "Conf", format="%d%%",
                help="Average confidence across the three horizons, with a "
                     "bonus when all three agree."),
        })

    with st.expander("📋 Why these forecasts — news, key drivers & backdrop"):
        bd = fc_df.iloc[0].get("backdrop_label", "")
        if bd:
            st.markdown(f"🌍 **Macro / geopolitical backdrop** — {md_safe(bd)}")
        ranked = fc_df.reindex(
            fc_df["net_lean"].abs().sort_values(ascending=False).index)
        for _, r in ranked.head(6).iterrows():
            drivers = " · ".join(r["drivers"]) if r["drivers"] else "—"
            news = r["news_read"] or "no specific news catalyst"
            fire = " · 🔥 volume igniting" if r["ignited"] else ""
            st.markdown(
                f"**{r['base']}** — {r['outlook_word']} "
                f"({r['confidence']}%){fire}  \n"
                f"Key drivers: {md_safe(drivers)}  \n"
                f"News: {md_safe(news)}")

    st.caption(
        "Each cell shows the projected direction (▲ up · ▼ down · ▬ "
        "sideways) and the expected NET move for that candle. The call "
        "fuses the timeframe's technicals with news, the macro backdrop, "
        "volume ignition, social heat and funding — every input tilts the "
        "read within bounds, none overrides it. 'Projected 4h' applies the "
        "4h expected move to the current price. Probabilistic projections, "
        "not guarantees. Educational only, not financial advice.")


def _relative_time(dt) -> str:
    """Return a short 'X min ago' / 'X h ago' / 'X d ago' string from a
    datetime — used by the news-impact panel to show how fresh each
    headline is. Falls back to '' when the input is missing/invalid."""
    if dt is None:
        return ""
    try:
        # Coerce strings / pandas timestamps to a tz-aware UTC datetime.
        if hasattr(dt, "to_pydatetime"):
            dt = dt.to_pydatetime()
        if dt.tzinfo is None:
            dt = dt.replace(tzinfo=timezone.utc)
        now = datetime.now(timezone.utc)
        secs = (now - dt).total_seconds()
    except Exception:
        return ""
    if secs < 0:
        return "just now"
    if secs < 60:
        return f"{int(secs)}s ago"
    if secs < 3600:
        return f"{int(secs // 60)} min ago"
    if secs < 86400:
        return f"{int(secs // 3600)}h ago"
    return f"{int(secs // 86400)}d ago"


def _inject_autorefresh(seconds: int) -> None:
    """Reload the whole app after `seconds` — used for the live forecast."""
    components.html(
        "<script>(function(){var P=window.parent||window;"
        "if(!P.__tiFcReload){P.__tiFcReload=1;setTimeout(function(){"
        "try{P.location.reload();}catch(e){}}," + str(int(seconds * 1000))
        + ");}})();</script>", height=0)


def render_btc_outlook(o: dict,
                       impactful_news: list[dict] | None = None) -> None:
    """Prominent BTC 24h Outlook banner — shown above every tab. BTC leads the
    market; the banner tells the user which way it leans, with the evidence
    and the caution flags surfaced so they can size accordingly. When
    `impactful_news` is supplied, a 'Why this is happening' panel shows the
    headlines moving the tape — and new ones fire toasts and desktop
    notifications when Desktop alerts is enabled."""
    if not o:
        return
    direction = o.get("direction", "Neutral")
    color = {"Up": "#2ed47a", "Down": "#ff5c5c",
             "Neutral": "#e0a92b"}.get(direction, "#8b8d98")
    label = {"Up": "LEANING UP", "Down": "LEANING DOWN",
             "Neutral": "NEUTRAL"}.get(direction, direction.upper())
    with st.container(border=True):
        st.markdown(
            f"<div style='display:flex;justify-content:space-between;"
            f"align-items:center;flex-wrap:wrap;gap:8px'>"
            f"<div><span style='font-size:1.08rem;font-weight:800'>"
            f"₿ BTC — Next 24 Hours</span> &nbsp;"
            f"<span style='background:{color};color:#06121f;padding:4px 13px;"
            f"border-radius:7px;font-size:0.78rem;font-weight:800;"
            f"letter-spacing:0.04em'>{label}</span></div>"
            f"<div style='color:#8b8d98;font-size:0.85rem;font-weight:600'>"
            f"{o.get('confidence', 0)}% confidence · "
            f"{o.get('aligned_categories', 0)}/"
            f"{o.get('total_categories', 0)} categories agree · "
            f"expected range ±{o.get('expected_range_pct', 0):.1f}%"
            f"</div></div>"
            f"<div style='color:{color};font-size:0.94rem;font-weight:700;"
            f"margin:6px 0 4px 0'>{md_safe(o.get('takeaway', ''))}</div>",
            unsafe_allow_html=True)

        # --- Trading-desk briefing: synthesis + concrete next steps -------
        briefing = o.get("briefing") or {}
        if briefing.get("summary"):
            st.markdown(
                f"<div style='background:#11141c;border-radius:6px;"
                f"padding:11px 14px;margin:10px 0 6px 0;"
                f"border:1px solid #1f2330'>"
                f"<div style='font-size:0.74rem;letter-spacing:0.10em;"
                f"color:#8b8d98;font-weight:800;margin-bottom:5px'>"
                f"🧭 WHAT THIS MEANS</div>"
                f"<div style='color:#d8dae3;font-size:0.9rem;"
                f"line-height:1.55'>{md_safe(briefing['summary'])}</div>"
                + (f"<div style='font-size:0.78rem;color:#9aa0b4;"
                   f"margin-top:7px;font-style:italic'>"
                   f"{md_safe(briefing.get('conviction_note', ''))}</div>"
                   if briefing.get("conviction_note") else "")
                + "</div>",
                unsafe_allow_html=True)
        if briefing.get("next_steps"):
            steps_html = "".join(
                f"<div style='color:#cfd2dc;font-size:0.86rem;"
                f"margin:5px 0;padding-left:18px;text-indent:-18px;"
                f"line-height:1.5'>"
                f"<span style='color:#6e8bff;font-weight:800'>→</span> "
                f"{md_safe(step)}</div>"
                for step in briefing["next_steps"])
            st.markdown(
                f"<div style='background:#0e1118;border-left:3px solid "
                f"#6e8bff;padding:9px 14px;margin:6px 0 10px 0;"
                f"border-radius:5px'>"
                f"<div style='font-size:0.74rem;letter-spacing:0.10em;"
                f"color:#6e8bff;font-weight:800;margin-bottom:6px'>"
                f"📋 NEXT STEPS — HOW TO TRADE IT</div>"
                f"{steps_html}</div>",
                unsafe_allow_html=True)

        # --- WHY THIS IS HAPPENING — high-impact headlines moving the tape
        if impactful_news:
            # Toast + browser-notification dedup tracking.
            prev_titles = st.session_state.get("impactful_seen")
            first_visit = prev_titles is None
            current_titles = {it["title"] for it in impactful_news}
            new_items = ([it for it in impactful_news
                          if it["title"] not in prev_titles]
                         if not first_visit else [])
            st.session_state["impactful_seen"] = current_titles
            for it in new_items[:3]:
                icon = ("📈" if it["direction"] == "Bullish"
                        else "📉" if it["direction"] == "Bearish"
                        else "📰")
                st.toast(f"{it['direction'].upper()} impact news — "
                         f"{it['title'][:90]}", icon=icon)

            items_html = ""
            # Cap to 5 — keep the panel focused on the highest-impact news,
            # not flooded with marginal mentions.
            for it in impactful_news[:5]:
                dir_color = {"Bullish": "#2ed47a",
                             "Bearish": "#ff5c5c"}.get(
                                 it["direction"], "#e0a92b")
                fresh_tag = (" 🆕" if it["title"] in
                             {x["title"] for x in new_items} else "")
                kw_chip = ""
                if it.get("keywords"):
                    kw_chip = (f"<span style='background:#1a1c24;"
                               f"color:#aab;padding:1px 6px;border-radius:4px;"
                               f"font-size:0.7rem;margin-left:6px'>"
                               f"{it['keywords'][0]}</span>")
                time_ago = _relative_time(it.get("published"))
                time_chip = (f" · <span style='color:#6e8bff'>{time_ago}</span>"
                             if time_ago else "")
                link = it.get("link") or ""
                if link:
                    title_html = (
                        f"<a href='{link}' target='_blank' rel='noopener' "
                        f"style='color:#d5d7e0;text-decoration:none;"
                        f"border-bottom:1px dotted #4a4f60'>"
                        f"{md_safe(it['title'])}</a>")
                else:
                    title_html = (f"<span style='color:#d5d7e0'>"
                                  f"{md_safe(it['title'])}</span>")
                items_html += (
                    f"<div style='border-left:3px solid {dir_color};"
                    f"padding:6px 12px;margin:5px 0;background:{dir_color}10;"
                    f"border-radius:4px;font-size:0.86rem'>"
                    f"<span style='color:{dir_color};font-weight:800'>"
                    f"{it['direction'].upper()}</span>{kw_chip} "
                    f"<span style='color:#9aa0b4;font-size:0.76rem'>"
                    f"· {md_safe(it.get('source', ''))} "
                    f"· impact {it['score']:.2f}{time_chip}</span>"
                    f"{fresh_tag}<br>{title_html}</div>")
            st.markdown(
                f"<div style='background:#0e1118;border-left:3px solid "
                f"#e0a92b;padding:10px 14px;margin:6px 0 10px 0;"
                f"border-radius:5px'>"
                f"<div style='font-size:0.74rem;letter-spacing:0.10em;"
                f"color:#e0a92b;font-weight:800;margin-bottom:6px'>"
                f"📰 WHY THIS IS HAPPENING — high-impact news right now</div>"
                f"{items_html}</div>",
                unsafe_allow_html=True)

            # Live browser notifications for impactful news (only when the
            # user has Desktop alerts switched on). Own localStorage key so
            # it never duplicates with the trade-alert stream.
            if alerts_on:
                _inject_browser_alerts(
                    [{"id": f"news:{it['title'][:80]}",
                      "title": f"📰 {it['direction']} impact news",
                      "body": (f"{it['title']} — "
                               f"{it.get('source', '')}")}
                     for it in impactful_news[:8]],
                    0, key="ti_notified_news")

        for flag in o.get("flags", []):
            st.markdown(
                f"<div style='background:#e0a92b1f;border-left:3px solid "
                f"#e0a92b;padding:5px 11px;margin:4px 0;border-radius:4px;"
                f"font-size:0.85rem'>⚠️ {md_safe(flag)}</div>",
                unsafe_allow_html=True)
        if o.get("strategies"):
            with st.expander("🎯 Trading strategies currently firing on BTC"):
                st.caption(
                    "Classic technical patterns the engine sees right now. "
                    "Confirming patterns add a small confidence bonus; "
                    "contradicting ones flag uncertainty.")
                for s in o["strategies"]:
                    direction = s.get("direction", "")
                    sc = ("#2ed47a" if direction == "Bullish"
                          else "#ff5c5c" if direction == "Bearish"
                          else "#8b8d98")
                    st.markdown(
                        f"- **{md_safe(s.get('name', ''))}** on "
                        f"<span style='color:#bbb'>"
                        f"{md_safe(s.get('tf', ''))}</span> — "
                        f"<span style='color:{sc};font-weight:700'>"
                        f"{direction}</span>", unsafe_allow_html=True)
        if o.get("drivers"):
            with st.expander("Full drivers — what's pulling BTC each way"):
                for d in o["drivers"]:
                    lean = float(d.get("lean", 0))
                    lc = ("#2ed47a" if lean > 0.05
                          else "#ff5c5c" if lean < -0.05
                          else "#8b8d98")
                    st.markdown(
                        f"- **{d.get('force', '')}** "
                        f"<span style='color:{lc}'>(category "
                        f"{d.get('category', '—')}, lean {lean:+.2f}, "
                        f"weight {d.get('weight', 0)})</span> — "
                        f"{md_safe(d.get('note', ''))}",
                        unsafe_allow_html=True)


# ===========================================================================
# Sidebar
# ===========================================================================
st.sidebar.title("📈 Crypto Indicator")
st.sidebar.caption("Live technical analysis & sentiment — Binance USDT pairs")

# --- Persistent state — survives full page refresh via URL query params --
_qp = st.query_params
_qp_tf = _qp.get("tf", config.DEFAULT_TIMEFRAME)
if _qp_tf not in config.TIMEFRAMES:
    _qp_tf = config.DEFAULT_TIMEFRAME
_qp_mode = _qp.get("mode", "Futures")
if _qp_mode not in ("Futures", "Spot"):
    _qp_mode = "Futures"

# Section navigation lives on the LEFT side as the user requested.
SECTIONS = [
    "🔍 Market Scanner", "🔮 Forecast", "🚀 Breakout Radar",
    "🤖 Ask the Oracle", "🪙 Coin Analysis", "📰 News & Sentiment",
    "🧭 Decision Mode", "🧪 Paper Trader", "💸 Live Trading",
    "💎 Spot Long-Term",
]
_qp_section = _qp.get("section", SECTIONS[0])
if _qp_section not in SECTIONS:
    _qp_section = SECTIONS[0]
active_section = st.sidebar.radio(
    "📂 Section", SECTIONS, index=SECTIONS.index(_qp_section),
    help="Switch between the dashboard's sections. Your choice persists "
         "across page refreshes.")

st.sidebar.divider()

timeframe = st.sidebar.selectbox(
    "Timeframe", config.TIMEFRAMES,
    index=config.TIMEFRAMES.index(_qp_tf),
)
trade_mode_label = st.sidebar.radio(
    "Trade mode", ["Futures", "Spot"], horizontal=True,
    index=["Futures", "Spot"].index(_qp_mode),
    help="Futures — trades both long & short, sizes leverage from "
         "conviction. Spot — long-only (no shorting), no leverage, "
         "wider swing-horizon targets and stops.")
trade_mode = trade_mode_label.lower()

# Persist current choices back to the URL so they survive a refresh.
st.query_params["tf"] = timeframe
st.query_params["mode"] = trade_mode_label
st.query_params["section"] = active_section

top_n = st.sidebar.slider("Coins to track", 10, config.TOP_N, config.TOP_N, 5)

alerts_on = st.sidebar.checkbox(
    "🔔 Desktop alerts", value=False,
    help="Browser desktop notifications for new high-confidence setups and "
         "volume surges. Keep this dashboard tab open and allow "
         "notifications when the browser asks — the page auto-refreshes so "
         "it keeps scanning in the background.")
alert_every = 5
if alerts_on:
    alert_every = st.sidebar.selectbox(
        "Check for new signals every", [3, 5, 10], index=1,
        format_func=lambda m: f"{m} minutes")
    st.sidebar.caption(
        f"🔔 Desktop alerts ON — re-scanning every {alert_every} min. Keep "
        f"this tab open (a background tab is fine); allow notifications when "
        f"the browser prompts.")

if st.sidebar.button("🔄 Refresh data", use_container_width=True):
    st.cache_data.clear()
    st.rerun()

st.sidebar.caption(
    f"Updated {datetime.now(timezone.utc):%H:%M:%S} UTC · "
    f"market cache {config.MARKET_CACHE_TTL}s")
st.sidebar.info(
    "Educational tool. Signals are algorithmic, not financial advice. "
    "Always manage your own risk.")


# ===========================================================================
# Header — global market sentiment
# ===========================================================================
st.markdown(
    """
    <div style='display:flex;align-items:center;gap:14px;margin:0 0 14px 0'>
      <div style='font-size:2.2rem;line-height:1'>📈</div>
      <div>
        <div style='font-size:1.95rem;font-weight:800;letter-spacing:-0.025em;
             background:linear-gradient(90deg,#6e8bff,#9d8bff);
             -webkit-background-clip:text;background-clip:text;
             -webkit-text-fill-color:transparent;line-height:1.15'>
          Crypto Trading Indicator</div>
        <div style='color:#8a93a6;font-size:0.9rem;margin-top:2px'>
          Live technical, derivatives &amp; social analysis across the top
          Binance USDT pairs</div>
      </div>
    </div>
    """,
    unsafe_allow_html=True,
)

try:
    fg = load_fear_greed()
except Exception:
    fg = None

try:
    glob = load_global_market()
except Exception:
    glob = None

try:
    news_df = load_news()
except Exception:
    news_df = pd.DataFrame()

# Columns 3-4 adapt: LunarCrush social mood when available, else news mood.
crypto_soc = stock_soc = None
if lunarcrush.is_configured():
    try:
        crypto_soc = load_crypto_social()
    except Exception:
        crypto_soc = None
    try:
        stock_soc = load_stock_social()
    except Exception:
        stock_soc = None

hcol1, hcol2, hcol3, hcol4 = st.columns(4)

if fg:
    delta = fg["value"] - (fg["yesterday"] or fg["value"])
    hcol1.metric("Fear & Greed", f"{fg['value']} · {fg['label']}",
                 f"{delta:+d} vs yesterday")
else:
    hcol1.metric("Fear & Greed", "unavailable")

if glob:
    hcol2.metric("BTC Dominance", f"{glob['btc_dominance']:.1f}%",
                 f"{glob['market_cap_change_24h']:+.2f}% total cap 24h")
else:
    hcol2.metric("BTC Dominance", "unavailable")

if crypto_soc:
    hcol3.metric("Crypto Social Mood", crypto_soc["mood"],
                 f"{crypto_soc['sentiment']:.0f}% positive · LunarCrush")
elif not news_df.empty:
    _cm = news_mod.category_mood(news_df, "Crypto")
    hcol3.metric("Crypto News Mood", _cm["mood"], f"{_cm['score']:+.2f} avg")
else:
    hcol3.metric("Crypto Mood", "unavailable")

if stock_soc:
    hcol4.metric("Equities Social Mood", stock_soc["mood"],
                 f"{stock_soc['sentiment']:.0f}% positive · LunarCrush")
elif not news_df.empty:
    _mm = news_mod.category_mood(news_df, "Macro / Politics")
    hcol4.metric("Macro News Mood", _mm["mood"], f"{_mm['score']:+.2f} avg")
else:
    hcol4.metric("Macro Mood", "unavailable")

if glob:
    _eth = glob.get("eth_dominance") or 0.0
    _eth_txt = f" / ETH {_eth:.1f}%" if _eth else ""
    st.caption(
        f"Total crypto market cap ${glob['market_cap_usd'] / 1e12:.2f}T · "
        f"24h volume ${glob['volume_usd'] / 1e9:.0f}B · "
        f"BTC {glob['btc_dominance']:.1f}%{_eth_txt} dominance · "
        f"via {glob.get('source', '—')}")

# --- BTC 24h Outlook — the headline directional read above every tab --------
try:
    _bo_tickers = load_top_symbols(top_n)
    _btc_row = _bo_tickers[_bo_tickers["symbol"] == "BTCUSDT"]
    _btc_change = (float(_btc_row["priceChangePercent"].iloc[0])
                   if not _btc_row.empty else 0.0)
    _alts = _bo_tickers[~_bo_tickers["symbol"].isin(
        ["BTCUSDT", "ETHUSDT"])]
    _alt_median = (float(_alts["priceChangePercent"].head(30).median())
                   if not _alts.empty else 0.0)
    try:
        _impactful_news = load_impactful_news()
    except Exception:
        _impactful_news = []
    render_btc_outlook(btc_outlook_now(_btc_change, _alt_median),
                       impactful_news=_impactful_news)
except Exception:
    pass  # never let the BTC banner block the rest of the dashboard

# --- Global Trade Alerts strip — high-confidence setups & volume surges,
# computed for the selected timeframe and shown above every tab. -------------
_alert_merged = pd.DataFrame()    # so later tabs can rely on it being defined
try:
    _alert_tickers = load_top_symbols(top_n)
    with st.spinner(f"Scanning {len(_alert_tickers)} coins for alerts…"):
        _alert_scan = scan_market(
            tuple(_alert_tickers["symbol"]), timeframe, trade_mode)
    _alert_merged = _alert_scan.merge(
        _alert_tickers[["symbol", "priceChangePercent", "quoteVolume"]],
        on="symbol", how="left")
    render_alerts(_alert_merged, timeframe)
except Exception:
    pass  # never let the alerts strip block the rest of the dashboard

# Compute the alerts dict ONCE here at module scope so every section
# (Paper Trader AND Live Trading) can reference it. Without this,
# Live Trading hits NameError on `auto_ad` when the user navigates
# straight to it without visiting Paper Trader first.
auto_ad = (alerts.build_alerts(_alert_merged, timeframe)
           if not _alert_merged.empty
           else {"setups": [], "surges": [], "timeframe": timeframe})

# Per-symbol price lookup at module scope so every section
# (Paper Trader, Live Trading) shares the same dict. Sections that
# need live-price overrides for their own open positions can still
# layer them on top of this base dict locally.
prices: dict[str, float] = {}
if not _alert_merged.empty:
    prices = dict(zip(_alert_merged["symbol"], _alert_merged["price"]))

# Section is selected from the sidebar radio above — no horizontal tab bar.


# ===========================================================================
# Tab 1 — Market Scanner
# ===========================================================================
if active_section == "🔍 Market Scanner":
    st.subheader(f"Market Scanner · {timeframe} timeframe")
    st.caption(f"Top {top_n} USDT pairs by 24h volume, ranked by signal score.")

    try:
        tickers = load_top_symbols(top_n)
    except Exception as exc:
        st.error(f"Could not load Binance market data: {exc}")
        st.stop()

    with st.spinner(f"Analysing {len(tickers)} coins on {timeframe}…"):
        scan_df = scan_market(tuple(tickers["symbol"]), timeframe, trade_mode)

    if scan_df.empty:
        st.warning("No analysis results — try refreshing.")
    else:
        merged = scan_df.merge(
            tickers[["symbol", "priceChangePercent", "quoteVolume"]],
            on="symbol", how="left")
        merged = merged.sort_values("score", ascending=False)

        # TradingView ratings for all scanned coins in one batched request.
        try:
            tv_map = load_tv_ratings(tuple(merged["symbol"]), timeframe)
        except Exception:
            tv_map = {}
        merged["tv"] = merged["symbol"].map(
            lambda s: tv_map.get(s, {}).get("recommendation", "—").upper())

        # LunarCrush Galaxy Score for every coin (one request; skipped when
        # no API key is configured).
        lc_top: dict = {}
        if lunarcrush.is_configured():
            try:
                lc_top = load_lunarcrush_top()
            except Exception:
                lc_top = {}

        # Summary counts on the actionable BUY / SELL verdict.
        counts = merged["action_label"].value_counts()
        s1, s2, s3, s4, s5 = st.columns(5)
        for col, lbl in zip(
                [s1, s2, s3, s4, s5],
                ["STRONG BUY", "BUY", "NEUTRAL", "SELL", "STRONG SELL"]):
            col.metric(lbl.title(), int(counts.get(lbl, 0)))

        table = pd.DataFrame({
            "Coin": merged["symbol"].str.replace("USDT", "", regex=False),
            "Bias": merged["bias_label"],
            "Action": merged["action_label"],
            "TradingView": merged["tv"],
            "Score": merged["score"],
            "Confidence": merged["confidence"],
            "Price": merged["price"].map(fmt_price),
            "24h %": merged["priceChangePercent"].round(2),
            "RSI": merged["rsi"],
            "Regime": merged["regime"],
            "Funding": merged["funding"].map(
                lambda f: f"{f * 100:+.3f}%" if pd.notna(f) else "—"),
        })
        if lc_top:
            table["Galaxy"] = merged["symbol"].map(
                lambda s: lc_top.get(s.replace("USDT", ""), {}).get(
                    "galaxy_score"))

        col_cfg = {
            "Score": st.column_config.ProgressColumn(
                "Score", min_value=-100, max_value=100, format="%d"),
            "Confidence": st.column_config.NumberColumn(
                "Confidence", format="%d%%"),
            "24h %": st.column_config.NumberColumn("24h %", format="%.2f%%"),
        }
        if "Galaxy" in table.columns:
            col_cfg["Galaxy"] = st.column_config.ProgressColumn(
                "Galaxy", min_value=0, max_value=100, format="%d")

        st.dataframe(
            style_scan(table),
            use_container_width=True, hide_index=True, height=560,
            column_config=col_cfg,
        )
        st.caption(
            "Bias = directional positioning (LONG / SHORT). "
            "Action = entry timing (BUY / SELL / NEUTRAL). "
            "TradingView = TradingView's own rating, an independent "
            "cross-check. Score blends bias & action: -100 bearish → "
            "+100 bullish. Funding positive means longs pay shorts.")

        st.markdown("### 🎯 Live Trade Signals")
        st.caption(f"High-conviction setups on the {timeframe} timeframe — "
                   f"entry zone, protective stop and scale-out targets.")
        sig = merged[merged["trade_plan"].apply(
            lambda p: isinstance(p, dict))]
        sig = sig[sig["confidence"] >= 55].sort_values(
            "confidence", ascending=False)
        if sig.empty:
            st.info("No high-conviction setups right now — the market is "
                    "mostly neutral on this timeframe. Try another timeframe "
                    "or check back after the next candles close.")
        else:
            sig_table = pd.DataFrame([{
                "Coin": r["symbol"].replace("USDT", ""),
                "Direction": r["trade_plan"]["side"],
                "Move": (r["trade_plan"].get("maturity") or {}).get(
                    "stage", "—"),
                "Entry zone": f"{fmt_price(r['trade_plan']['entry_low'])} – "
                              f"{fmt_price(r['trade_plan']['entry_high'])}",
                "Stop loss": fmt_price(r["trade_plan"]["stop_loss"]),
                "Target 1": fmt_price(r["trade_plan"]["take_profit"]),
                "Target 2": fmt_price(r["trade_plan"]["take_profit_2"]),
                "Target 3": fmt_price(r["trade_plan"]["take_profit_3"]),
                "R : R": f"{r['trade_plan']['risk_reward']:.1f}–"
                         f"{r['trade_plan']['risk_reward_3']:.1f}R",
                "Confidence": r["confidence"],
            } for _, r in sig.head(20).iterrows()])
            st.dataframe(
                sig_table.style.map(
                    lambda v: f"background-color:"
                              f"{LABEL_COLORS.get(v, '#8e8e93')};"
                              f"color:#fff;font-weight:700;",
                    subset=["Direction"]),
                use_container_width=True, hide_index=True, height=420,
                column_config={
                    "Confidence": st.column_config.NumberColumn(
                        "Confidence", format="%d%%"),
                })
            st.caption(
                "How to trade a signal — place a **limit order** in the "
                "entry zone, set a **stop-market** order at the stop loss, "
                "and exit in two parts: close ~50% at Target 1, the rest at "
                "Target 2, moving the stop to break-even once Target 1 fills. "
                "Open the Coin Analysis tab for the full plan and "
                "step-by-step order guide. Educational only — not financial "
                "advice.")


# ===========================================================================
# Tab 2 — Forecast
# ===========================================================================
if active_section == "🔮 Forecast":
    _fc_live = st.checkbox(
        "🔴 Live forecast — keep it auto-refreshing every 5 min",
        value=False, key="forecast_live",
        help="Re-runs the forecast on an interval so the predictions and "
             "their alerts stay current without you refreshing the page.")
    try:
        _fc_tickers = load_top_symbols(top_n)
        _fc_syms = tuple(_fc_tickers["symbol"].head(40))
        with st.spinner(f"Forecasting {len(_fc_syms)} coins across "
                        f"15m / 1h / 4h with full news & macro context…"):
            _fc_df = forecast_market(_fc_syms)
        render_forecast(_fc_df)
    except Exception as exc:
        st.error(f"Could not build the forecast right now: {exc}")
    if _fc_live:
        _inject_autorefresh(300)


# ===========================================================================
# Tab 3 — Breakout Radar
# ===========================================================================
if active_section == "🚀 Breakout Radar":
    st.subheader("🚀 Breakout Radar — predict the next coins to blow out")
    st.caption(
        "A self-contained intelligence engine. It scans every coin across "
        "three charts and fuses price action, volume surges, volatility, "
        "live buying/selling, the bigger trend, strength versus Bitcoin, "
        "futures funding, social attention and fresh news into one plain "
        "verdict — set inside the overall market mood. It tells you which "
        "coins look ready to move and **how early you are**: coins that "
        "haven't moved yet (the safest entries), coins just starting to move, "
        "and coins that have already run (too late to chase).")

    hz_label = st.radio(
        "Horizon", ["⚡ Imminent — next 15m–4h move  (scans 15m · 1h · 4h)",
                    "📅 Next 24 hours  (scans 1h · 4h · 1d)"],
        horizontal=True, label_visibility="collapsed")
    horizon = "24h" if hz_label.startswith("📅") else "imminent"
    tf_note = ("1h · 4h · 1d charts" if horizon == "24h"
               else "15m · 1h · 4h charts")

    try:
        b_tickers = load_top_symbols(top_n)
    except Exception as exc:
        st.error(f"Could not load Binance market data: {exc}")
        st.stop()

    try:
        with st.spinner(f"Scanning {len(b_tickers)} coins across {tf_note}…"):
            radar, backdrop = scan_breakouts(
                tuple(b_tickers["symbol"]), horizon)
    except Exception as exc:
        import traceback as _tb
        st.error(f"The Breakout Radar hit an error — "
                 f"{type(exc).__name__}: {exc}")
        with st.expander("Technical details"):
            st.code(_tb.format_exc())
        radar, backdrop = pd.DataFrame(), {}

    # Attach each coin's 24h USDT volume for a liquidity read on the cards.
    if not radar.empty:
        radar = radar.merge(
            b_tickers[["symbol", "quoteVolume"]], on="symbol", how="left")

    if radar.empty:
        st.warning("No analysis available right now — try refreshing.")
    else:
        bd_color = {"Risk-on": "#2ed47a", "Risk-off": "#ff5c5c"}.get(
            backdrop["label"], "#e0a92b")
        st.markdown(
            f"<div style='background:rgba(110,139,255,0.05);border:1px solid "
            f"rgba(255,255,255,0.07);border-left:3px solid {bd_color};"
            f"border-radius:10px;padding:10px 15px;margin:2px 0 14px 0'>"
            f"<span style='font-size:0.7rem;letter-spacing:0.09em;"
            f"color:#8b8d98;font-weight:700'>MARKET BACKDROP — THE TAPE EVERY "
            f"SETUP SITS INSIDE</span><br>"
            f"<span style='font-size:1.08rem;font-weight:800;color:{bd_color}'>"
            f"{backdrop['label']}</span>"
            f"<span style='color:#8b8d98;font-size:0.84rem'> &nbsp;·&nbsp; "
            f"score {backdrop['score']:+.0f} &nbsp;·&nbsp; "
            f"{backdrop['note']}</span><br>"
            f"<span style='color:#9aa0b4;font-size:0.79rem'>Bullish setups get "
            f"a small tailwind when the tape is risk-on and a headwind when "
            f"it is risk-off — and the reverse for shorts. It tilts the "
            f"scores, never overrides them.</span></div>",
            unsafe_allow_html=True)

        # Decision board: the top 30 coins by radar score.
        shortlist = radar.head(30)

        loading = int((shortlist["stage"] == "COILED").sum())
        fresh = int((shortlist["stage"] == "FRESH").sum())
        extended = int((shortlist["stage"] == "EXTENDED").sum())
        # Split by the direction score's sign so every coin is a long or a
        # short call — no coin is left without a decision.
        up_df = shortlist[shortlist["direction"] >= 0]
        down_df = shortlist[shortlist["direction"] < 0]

        k1, k2, k3, k4 = st.columns(4)
        k1.metric("🔋 Building Up", loading,
                  help="Hasn't moved yet — the earliest, safest entries")
        k2.metric("🚀 Just Started", fresh,
                  help="Already moving but still early — room to run")
        k3.metric("⚠️ Already Ran", extended,
                  help="Move mostly done — too late, risky to chase")
        k4.metric("🟢 Long / 🔴 Short", f"{len(up_df)} / {len(down_df)}")

        st.caption(
            "**The summary above counts the 30 coins by status.** "
            "🔋 **Building Up** = coiled, has not moved yet — the earliest and "
            "safest entry. 🚀 **Just Started** = the move just began, still "
            "early. ⚠️ **Already Ran** = the move is mostly done — too late, "
            "risky to chase.")

        # --- The decision board: LONG vs SHORT ----------------------------
        st.markdown("### 🎯 Top 30 coins — your long / short decision board")
        bc, sc = st.columns(2)
        with bc:
            st.markdown(
                f"<h4 style='color:#2ed47a;border-color:#2ed47a'>🟢 GO LONG "
                f"&nbsp;<span style='font-size:0.8rem;color:#8b8d98'>"
                f"buy — price likely to rise ({len(up_df)})</span></h4>",
                unsafe_allow_html=True)
            breakout_side_table(up_df, "UP")
        with sc:
            st.markdown(
                f"<h4 style='color:#ff5c5c;border-color:#ff5c5c'>🔴 GO SHORT "
                f"&nbsp;<span style='font-size:0.8rem;color:#8b8d98'>"
                f"sell — price likely to fall ({len(down_df)})</span></h4>",
                unsafe_allow_html=True)
            breakout_side_table(down_df, "DOWN")
        st.caption(
            "**How to read this:** coins on the **left → open a LONG** (buy, "
            "betting price goes up); coins on the **right → open a SHORT** "
            "(sell, betting price goes down). **Entry** = the price to act at, "
            "**Target** = the first place to take profit. Prefer high "
            "**Score** and high **Confidence**; **Building Up** is the safest "
            "timing, **Already Ran** is the riskiest. 🔥 = volume surging. "
            "Full plan and reasoning for every coin below.")

        st.divider()

        # --- Full read & trade plan per coin ------------------------------
        st.markdown("### 📋 Full read & trade plan for each coin")
        fc1, fc2 = st.columns([3, 2])
        stage_flt = fc1.radio(
            "Status", ["All", "🔋 Building up", "🚀 Just started",
                       "⚠️ Already ran"],
            horizontal=True, label_visibility="collapsed")
        dir_flt = fc2.radio(
            "Direction", ["Long & short", "🟢 Long only", "🔴 Short only"],
            horizontal=True, label_visibility="collapsed")

        view = shortlist
        if stage_flt.startswith("🔋"):
            view = view[view["stage"] == "COILED"]
        elif stage_flt.startswith("🚀"):
            view = view[view["stage"] == "FRESH"]
        elif stage_flt.startswith("⚠️"):
            view = view[view["stage"] == "EXTENDED"]
        if dir_flt.startswith("🟢"):
            view = view[view["direction"] >= 0]
        elif dir_flt.startswith("🔴"):
            view = view[view["direction"] < 0]

        if view.empty:
            st.info("No coins match that filter right now.")
        else:
            for _, r in view.iterrows():
                render_breakout_card(r.to_dict(), int(r.name) + 1)

        st.caption("The radar is algorithmic — it flags where the conditions "
                   "for a violent move are stacking up; it does not promise "
                   "one will happen. Educational only, not financial advice.")


# ===========================================================================
# Tab 4 — Ask the Oracle
# ===========================================================================
if active_section == "🤖 Ask the Oracle":
    st.subheader("🤖 Ask the Oracle — your trading-desk analyst")
    st.caption(
        "Ask in plain English which coin is next to blow out — up or down — "
        "and the Oracle answers straight from the live Breakout Radar. Below, "
        "a curated board of bullish coins with concrete buy zones, read "
        "against circulating supply and the worldwide market backdrop.")

    o_hz_label = st.radio(
        "Horizon",
        ["⚡ Imminent — next 15m–4h move", "📅 Next 24 hours"],
        horizontal=True, label_visibility="collapsed", key="oracle_horizon")
    o_horizon = "24h" if o_hz_label.startswith("📅") else "imminent"

    try:
        o_tickers = load_top_symbols(top_n)
        with st.spinner("Scanning the market for the Oracle…"):
            o_radar, o_backdrop = scan_breakouts(
                tuple(o_tickers["symbol"]), o_horizon)
        if not o_radar.empty:
            o_radar = o_radar.merge(
                o_tickers[["symbol", "quoteVolume"]], on="symbol", how="left")
    except Exception as exc:
        st.error(f"Could not load the radar: {exc}")
        o_radar, o_backdrop = pd.DataFrame(), {}

    # Market-cap / circulating-supply context for the buy zones.
    o_mcap_map: dict = {}
    if lunarcrush.is_configured():
        try:
            o_mcap_map = oracle.market_cap_map(load_lunarcrush_list())
        except Exception:
            o_mcap_map = {}

    st.markdown("#### 💬 Ask anything")
    o_question = st.text_input(
        "Your question", value="",
        placeholder="e.g. Which coin is about to blow out?",
        label_visibility="collapsed", key="oracle_question")
    st.caption("Try: “which coin is next for a bullish blowout?” · "
               "“safest long right now” · “what about SOL?” · "
               "“show me the next breakdown” · “volume igniting”")

    o_presets = ["Next bullish blowout", "Next bearish blowout",
                 "Safest long now", "Volume igniting"]
    o_cols = st.columns(len(o_presets))
    for _col, _preset in zip(o_cols, o_presets):
        if _col.button(_preset, use_container_width=True,
                       key=f"oracle_preset_{_preset}"):
            o_question = _preset

    if o_question:
        render_oracle_answer(oracle.answer(o_question, o_radar, o_backdrop))
    else:
        st.caption("Ask a question above, or tap a quick button — the Oracle "
                   "replies instantly from the live radar.")

    st.divider()
    render_buy_zone_board(o_radar, o_backdrop, o_mcap_map)
    st.caption("The Oracle reads only the live Breakout Radar — no "
               "predictions beyond what the engine sees. Educational only, "
               "not financial advice.")


# ===========================================================================
# Tab 5 — Coin Analysis
# ===========================================================================
if active_section == "🪙 Coin Analysis":
    try:
        tickers = load_top_symbols(top_n)
    except Exception as exc:
        st.error(f"Could not load Binance market data: {exc}")
        st.stop()

    symbols = list(tickers["symbol"])
    default_idx = symbols.index("BTCUSDT") if "BTCUSDT" in symbols else 0
    symbol = st.selectbox(
        "Select a coin", symbols, index=default_idx,
        format_func=lambda s: s.replace("USDT", " / USDT"))

    base_asset = symbol.replace("USDT", "")
    try:
        lc_metrics = load_lunarcrush_coin(base_asset)
    except Exception:
        lc_metrics = None

    # Multi-timeframe analysis — derivatives and social sentiment feed every
    # timeframe's signal.
    per_tf: dict[str, dict] = {}
    enriched_by_tf: dict[str, pd.DataFrame] = {}
    for tf in config.TIMEFRAMES:
        try:
            raw = load_klines(symbol, tf)
            enriched = indicators.enrich(raw)
            enriched_by_tf[tf] = enriched
            try:
                deriv = load_derivatives(symbol, tf)
            except Exception:
                deriv = None
            per_tf[tf] = signals.analyze(
                enriched, deriv, lc_metrics, trade_mode)
        except Exception:
            continue

    if not per_tf:
        st.error("Could not analyse this coin right now. Try refreshing.")
        st.stop()

    agg = signals.aggregate(per_tf)
    detail = per_tf.get(timeframe) or next(iter(per_tf.values()))
    detail_tf = timeframe if timeframe in per_tf else next(iter(per_tf))
    edf = enriched_by_tf[detail_tf]

    try:
        tv_rating = load_tv_rating(symbol, detail_tf)
    except Exception:
        tv_rating = None

    # ---- Verdict row: bias, action, TradingView, confidence gauge --------
    try:
        flow_snap = load_orderflow(symbol)
    except Exception:
        flow_snap = {"flow": None, "book": None}

    _trow = tickers[tickers["symbol"] == symbol]
    ticker_row = _trow.iloc[0] if not _trow.empty else None
    df1d = enriched_by_tf.get("1d")
    plan = detail.get("trade_plan")

    sup_levels, res_levels = indicators.swing_levels(edf)
    nearest_sup = max((s for s in sup_levels if s < detail["price"]),
                      default=None)
    nearest_res = min((r for r in res_levels if r > detail["price"]),
                      default=None)

    render_bottom_line(agg, detail, per_tf, tv_rating, flow_snap, lc_metrics)

    st.markdown(
        f"### {symbol.replace('USDT', ' / USDT')} — multi-timeframe verdict")
    vc1, vc2, vc3, vc4 = st.columns([1.1, 1.1, 1.1, 1.3])
    with vc1:
        st.caption("DIRECTIONAL BIAS — which side to hold")
        st.markdown(label_badge(agg["bias_label"]), unsafe_allow_html=True)
        st.caption(f"Score {agg['bias_score']:+.0f} · trend · MACD · derivatives")
    with vc2:
        st.caption("ENTRY ACTION — whether to act now")
        st.markdown(label_badge(agg["action_label"]), unsafe_allow_html=True)
        st.caption(f"Score {agg['action_score']:+.0f} · RSI · Stoch · Bollinger")
    with vc3:
        st.caption(f"TRADINGVIEW — independent rating ({detail_tf})")
        if tv_rating:
            st.markdown(label_badge(tv_rating["recommendation"].upper()),
                        unsafe_allow_html=True)
            st.caption(f"{tv_rating['buy']} buy · {tv_rating['neutral']} "
                       f"neutral · {tv_rating['sell']} sell")
        else:
            st.markdown(label_badge("NEUTRAL"), unsafe_allow_html=True)
            st.caption("rating unavailable")
    with vc4:
        st.caption(f"SIGNAL CONFIDENCE — {detail_tf}")
        st.plotly_chart(confidence_gauge(detail["confidence"]),
                        use_container_width=True,
                        config={"displayModeBar": False})

    _tf_long = sum(1 for a in per_tf.values() if a["bias_score"] > 5)
    _tf_short = sum(1 for a in per_tf.values() if a["bias_score"] < -5)
    _bd_bull = sum(1 for b in detail["breakdown"] if b["signal"] == "Bullish")
    _bd_bear = sum(1 for b in detail["breakdown"] if b["signal"] == "Bearish")
    st.caption(
        f"🔗 **Confluence** — {_tf_long}/{len(per_tf)} timeframes lean long, "
        f"{_tf_short} lean short · on {detail_tf}: {_bd_bull} bullish / "
        f"{_bd_bear} bearish across {len(detail['breakdown'])} indicators. "
        f"Bias and timing are scored separately, so a long bias can still "
        f"pair with a 'wait' on entry.")

    # ---- Action plan -----------------------------------------------------
    if plan:
        render_action_plan(plan, detail["regime"], detail["confidence"],
                            symbol, agg, nearest_sup, nearest_res)
    else:
        with st.container(border=True):
            if trade_mode == "spot" and "SHORT" in detail["label"]:
                st.markdown("#### 📋 Action Plan — NO SPOT TRADE")
                st.info(
                    f"The {detail_tf} bias is bearish ({detail['label']}). "
                    f"Spot is long-only — there is no trade to take here. "
                    f"Switch to Futures mode to see the short setup, or wait "
                    f"for the bias to turn bullish for a spot buy.")
            else:
                st.markdown("#### 📋 Action Plan — STAND ASIDE")
                st.info(
                    f"No high-conviction setup on the {detail_tf} timeframe — "
                    f"the composite signal is NEUTRAL. Wait for directional "
                    f"bias and entry timing to align before committing risk.")

    # ---- Live order flow + price history ---------------------------------
    oc1, oc2 = st.columns(2)
    with oc1:
        render_orderflow(flow_snap)
    with oc2:
        render_history(symbol, df1d, ticker_row, detail,
                       (nearest_sup, nearest_res))

    # ---- LunarCrush social intelligence ----------------------------------
    render_lunarcrush(lc_metrics, base_asset)

    # ---- Live, interactive TradingView chart -----------------------------
    st.markdown(f"#### 📈 Live TradingView chart · {detail_tf}")
    tradingview_chart(symbol, detail_tf)

    # ---- Per-timeframe signal cards --------------------------------------
    st.markdown("#### Signal by timeframe")
    tf_cols = st.columns(len(config.TIMEFRAMES))
    for col, tf in zip(tf_cols, config.TIMEFRAMES):
        with col:
            if tf in per_tf:
                a = per_tf[tf]
                st.markdown(f"**{tf}** · _{a['regime']}_")
                st.markdown(f"Bias {label_badge(a['bias_label'])}",
                            unsafe_allow_html=True)
                st.markdown(f"Action {label_badge(a['action_label'])}",
                            unsafe_allow_html=True)
                st.progress(int(a["confidence"]),
                            text=f"{a['confidence']}% confidence")
            else:
                st.markdown(f"**{tf}**")
                st.caption("no data")

    st.divider()

    left, right = st.columns([2, 1])

    with left:
        st.markdown(f"#### Indicator chart · {detail_tf}")
        plot = edf.tail(120)
        fig = make_subplots(
            rows=3, cols=1, shared_xaxes=True,
            row_heights=[0.6, 0.2, 0.2], vertical_spacing=0.03,
            subplot_titles=("", "RSI", "Volume"))

        fig.add_trace(go.Candlestick(
            x=plot.index, open=plot["open"], high=plot["high"],
            low=plot["low"], close=plot["close"], name="Price"),
            row=1, col=1)
        for col_name, color in [("ema_fast", "#f5a623"),
                                ("ema_slow", "#4a90d9")]:
            fig.add_trace(go.Scatter(
                x=plot.index, y=plot[col_name], name=col_name,
                line=dict(color=color, width=1)), row=1, col=1)
        fig.add_trace(go.Scatter(
            x=plot.index, y=plot["vwap"], name="VWAP",
            line=dict(color="#e056fd", width=1.2, dash="dash")), row=1, col=1)
        fig.add_trace(go.Scatter(
            x=plot.index, y=plot["bb_upper"], name="BB upper",
            line=dict(color="#999", width=1, dash="dot")), row=1, col=1)
        fig.add_trace(go.Scatter(
            x=plot.index, y=plot["bb_lower"], name="BB lower",
            line=dict(color="#999", width=1, dash="dot"),
            fill="tonexty", fillcolor="rgba(150,150,150,0.08)"), row=1, col=1)

        fig.add_trace(go.Scatter(
            x=plot.index, y=plot["rsi"], name="RSI",
            line=dict(color="#9b59b6", width=1.5)), row=2, col=1)
        fig.add_hline(y=70, line=dict(color="#ff6b5b", width=1, dash="dash"),
                      row=2, col=1)
        fig.add_hline(y=30, line=dict(color="#34c759", width=1, dash="dash"),
                      row=2, col=1)

        vol_colors = ["#34c759" if c >= o else "#ff6b5b"
                      for c, o in zip(plot["close"], plot["open"])]
        fig.add_trace(go.Bar(
            x=plot.index, y=plot["volume"], name="Volume",
            marker_color=vol_colors), row=3, col=1)

        fig.update_layout(
            height=620, margin=dict(l=10, r=10, t=20, b=10),
            xaxis_rangeslider_visible=False, showlegend=False,
            template="plotly_dark")
        st.plotly_chart(fig, use_container_width=True)
        st.caption("Price panel: candles · EMA fast/slow · VWAP (dashed "
                   "magenta) · Bollinger Bands. Lower panels: RSI & volume.")

    with right:
        st.markdown(f"#### Signal detail · {detail_tf}")
        b1, b2 = st.columns(2)
        b1.caption("Directional bias")
        b1.markdown(label_badge(detail["bias_label"]), unsafe_allow_html=True)
        b2.caption("Entry action")
        b2.markdown(label_badge(detail["action_label"]), unsafe_allow_html=True)

        m1, m2 = st.columns(2)
        m1.metric("Bias score", f"{detail['bias_score']:+.0f}")
        m2.metric("Action score", f"{detail['action_score']:+.0f}")
        m1.metric("ADX · trend strength",
                  f"{detail['adx']}" if detail["adx"] is not None else "—",
                  detail["regime"])
        m2.metric("Volatility (ATR)",
                  f"{detail['atr_pct']}%" if detail['atr_pct'] else "—")

        bd = pd.DataFrame(detail["breakdown"])
        bd_view = pd.DataFrame({
            "Group": bd["group"],
            "Indicator": bd["indicator"],
            "Signal": bd["signal"],
            "Score": bd["score"],
            "Notes": bd["detail"],
        })
        st.dataframe(
            bd_view.style.map(
                lambda v: f"color:{MOOD_COLORS.get(v, '#888')};font-weight:600;",
                subset=["Signal"]),
            use_container_width=True, hide_index=True,
            column_config={
                "Score": st.column_config.ProgressColumn(
                    "Score", min_value=-100, max_value=100, format="%d"),
            })

        if tv_rating:
            st.markdown("#### TradingView cross-check")
            t1, t2 = st.columns(2)
            t1.metric("Oscillators", tv_rating["oscillators"])
            t2.metric("Moving averages", tv_rating["moving_averages"])
            st.caption(
                f"TradingView consensus **{tv_rating['recommendation']}** — "
                f"{tv_rating['buy']} buy / {tv_rating['neutral']} neutral / "
                f"{tv_rating['sell']} sell indicators.")

        dv = detail.get("derivatives")
        if dv:
            st.markdown("#### Derivatives positioning")
            d1, d2 = st.columns(2)
            d1.metric("Funding rate", f"{dv['funding'] * 100:+.4f}%")
            if dv.get("long_short_ratio") is not None:
                d2.metric("Long / Short ratio", f"{dv['long_short_ratio']:.2f}")
            if dv.get("oi_change_pct") is not None:
                d1.metric("Open interest trend", f"{dv['oi_change_pct']:+.1f}%")
            st.caption("Perpetual funding, trader long/short ratio and "
                       "open-interest trend — leverage & positioning context.")


# ===========================================================================
# Tab 6 — News & Sentiment
# ===========================================================================
if active_section == "📰 News & Sentiment":
    st.subheader("Market Sentiment & Live News")

    sleft, sright = st.columns([1, 2])

    with sleft:
        if fg:
            gauge = go.Figure(go.Indicator(
                mode="gauge+number",
                value=fg["value"],
                title={"text": f"Fear & Greed<br><sup>{fg['label']}</sup>"},
                gauge={
                    "axis": {"range": [0, 100]},
                    "bar": {"color": "#222"},
                    "steps": [
                        {"range": [0, 25], "color": "#c1121f"},
                        {"range": [25, 45], "color": "#ff6b5b"},
                        {"range": [45, 55], "color": "#8e8e93"},
                        {"range": [55, 75], "color": "#34c759"},
                        {"range": [75, 100], "color": "#0b8a3e"},
                    ],
                }))
            gauge.update_layout(height=260, margin=dict(l=20, r=20, t=50, b=10),
                                template="plotly_dark")
            st.plotly_chart(gauge, use_container_width=True)
        else:
            st.warning("Fear & Greed index unavailable.")

    with sright:
        if fg is not None and not fg["history"].empty:
            hist = fg["history"]
            line = go.Figure(go.Scatter(
                x=hist["timestamp"], y=hist["value"],
                mode="lines", line=dict(color="#4a90d9", width=2),
                fill="tozeroy", fillcolor="rgba(74,144,217,0.15)"))
            line.update_layout(
                height=260, margin=dict(l=10, r=10, t=30, b=10),
                title="Fear & Greed — last 30 days",
                template="plotly_dark", yaxis_range=[0, 100])
            st.plotly_chart(line, use_container_width=True)

    st.divider()
    try:
        lc_rows = load_lunarcrush_list()
    except Exception:
        lc_rows = []
    render_lunarcrush_leaderboard(lc_rows)
    st.divider()

    if news_df.empty:
        st.warning("News feeds are unavailable right now. Try refreshing.")
    else:
        # Per-category mood strip.
        cats = list(config.NEWS_FEEDS.keys())
        mcols = st.columns(len(cats))
        for col, cat in zip(mcols, cats):
            mood = news_mod.category_mood(news_df, cat)
            col.metric(cat, mood["mood"],
                       f"{mood['score']:+.2f} · {mood['count']} stories")

        st.divider()

        fcol1, fcol2 = st.columns([2, 1])
        chosen = fcol1.multiselect(
            "Categories", cats, default=cats)
        mood_filter = fcol2.selectbox(
            "Sentiment", ["All", "Bullish", "Bearish", "Neutral"])

        view = news_df[news_df["category"].isin(chosen)]
        if mood_filter != "All":
            view = view[view["mood"] == mood_filter]

        st.caption(f"{len(view)} stories · newest first")
        for _, row in view.head(60).iterrows():
            color = MOOD_COLORS.get(row["mood"], "#888")
            when = row["published"].strftime("%b %d %H:%M UTC")
            st.markdown(
                f"<div style='border-left:3px solid {color};"
                f"padding:4px 12px;margin-bottom:8px'>"
                f"<a href='{row['link']}' target='_blank' "
                f"style='font-weight:600;text-decoration:none;color:inherit'>"
                f"{row['title']}</a><br>"
                f"<span style='color:#888;font-size:0.8rem'>"
                f"{row['source']} · {row['category']} · {when} · "
                f"<span style='color:{color}'>{row['mood']} "
                f"({row['sentiment']:+.2f})</span></span></div>",
                unsafe_allow_html=True)

    # --- Social buzz (Reddit) — free, ToS-compliant stand-in for X --------
    st.divider()
    st.subheader("Social Buzz · Reddit")
    st.caption("Retail/social sentiment from Reddit — a free, "
               "Terms-of-Service-compliant alternative to X/Twitter, which no "
               "longer offers free data access. Mood is upvote-weighted.")

    try:
        social_df = load_social()
    except Exception:
        social_df = pd.DataFrame()

    if social_df.empty:
        st.warning("Reddit social feed is unavailable right now. Try refreshing.")
    else:
        scats = list(config.SOCIAL_FEEDS.keys())
        sm_cols = st.columns(len(scats))
        for col, cat in zip(sm_cols, scats):
            mood = social_mod.social_mood(social_df, cat)
            col.metric(f"{cat} buzz", mood["mood"],
                       f"{mood['score']:+.2f} · {mood['count']} posts")

        st.caption(f"{len(social_df)} hot posts · most-upvoted first")
        for _, row in social_df.sort_values(
                "upvotes", ascending=False).head(40).iterrows():
            color = MOOD_COLORS.get(row["mood"], "#888")
            when = row["published"].strftime("%b %d %H:%M UTC")
            st.markdown(
                f"<div style='border-left:3px solid {color};"
                f"padding:4px 12px;margin-bottom:8px'>"
                f"<a href='{row['link']}' target='_blank' "
                f"style='font-weight:600;text-decoration:none;color:inherit'>"
                f"{row['title']}</a><br>"
                f"<span style='color:#888;font-size:0.8rem'>"
                f"{row['source']} · ▲{row['upvotes']:,} · "
                f"{row['comments']:,} comments · {when} · "
                f"<span style='color:{color}'>{row['mood']} "
                f"({row['sentiment']:+.2f})</span></span></div>",
                unsafe_allow_html=True)


# ===========================================================================
# Tab 7 — Decision Mode
# ===========================================================================
if active_section == "🧭 Decision Mode":
    st.subheader("🧭 Decision Mode — Top 30 Coins")
    st.caption(f"Buy / hold / sell calls for the 30 strongest opportunities "
               f"right now — ranked on a blend of signal strength, social "
               f"sentiment, recent performance and market size, on the "
               f"{timeframe} timeframe. Each call includes entry timing, "
               f"hold horizon, an outlook and the data behind it.")

    try:
        d_tickers = load_top_symbols(top_n)
        d_scan = scan_market(tuple(d_tickers["symbol"]), timeframe, trade_mode)
    except Exception as exc:
        st.error(f"Could not load market data: {exc}")
        d_scan = pd.DataFrame()

    if d_scan.empty:
        st.warning("No analysis available right now — try refreshing.")
    else:
        d_merged = d_scan.merge(
            d_tickers[["symbol", "priceChangePercent", "quoteVolume"]],
            on="symbol", how="left")

        # LunarCrush social data feeds the ranking, so fetch it first.
        d_lc = load_lunarcrush_top() if lunarcrush.is_configured() else {}

        # Blended rank: signal strength (dominant) + confidence + social
        # sentiment + 24h performance + a small market-size factor.
        _bases = d_merged["symbol"].str.replace("USDT", "", regex=False)
        d_merged["_sent"] = [
            float(d_lc.get(b, {}).get("sentiment") or 50.0) for b in _bases]
        d_merged["_perf"] = (
            d_merged["priceChangePercent"].clip(-15, 15) + 15) / 30 * 100
        d_merged["_size"] = (
            d_merged["quoteVolume"].rank(pct=True).fillna(0) * 100)
        d_merged["rank_score"] = (
            d_merged["score"].abs() * 0.40
            + d_merged["confidence"] * 0.20
            + d_merged["_sent"] * 0.20
            + d_merged["_perf"] * 0.15
            + d_merged["_size"] * 0.05)
        d_merged = d_merged.sort_values(
            "rank_score", ascending=False).head(30)

        try:
            d_tv = load_tv_ratings(tuple(d_merged["symbol"]), timeframe)
        except Exception:
            d_tv = {}

        decisions = [_trade_decision(r, timeframe)
                     for _, r in d_merged.iterrows()]
        s1, s2, s3, s4 = st.columns(4)
        s1.metric("Buy / Accumulate", sum(
            1 for d in decisions if d["decision"] in ("BUY", "ACCUMULATE")))
        s2.metric("Hold / Wait", sum(
            1 for d in decisions if d["decision"] == "HOLD / WAIT"))
        s3.metric("Reduce / Sell", sum(
            1 for d in decisions
            if d["decision"] in ("REDUCE", "SELL / AVOID")))
        s4.metric("Timeframe", timeframe)
        st.divider()

        for (_, r), dec in zip(d_merged.iterrows(), decisions):
            base_sym = r["symbol"].replace("USDT", "")
            tv = d_tv.get(r["symbol"], {})
            lc = d_lc.get(base_sym, {})
            with st.container(border=True):
                st.markdown(
                    f"<h4 style='margin:0 0 4px 0'>{base_sym} / USDT "
                    f"&nbsp;<span style='background:{dec['color']};"
                    f"color:#06121f;padding:3px 13px;border-radius:7px;"
                    f"font-size:0.8rem;font-weight:800'>{dec['decision']}"
                    f"</span><span style='float:right;color:#8b8d98;"
                    f"font-size:0.8rem;font-weight:600'>composite "
                    f"{r['score']:+.0f} · {r['confidence']}% confidence"
                    f"</span></h4>", unsafe_allow_html=True)

                m = st.columns(6)
                m[0].metric("Price", fmt_price(r["price"]))
                m[1].metric("24h", f"{r['priceChangePercent']:+.2f}%")
                m[2].metric("24h volume", fmt_volume(r["quoteVolume"]))
                m[3].metric("RSI", r["rsi"])
                m[4].metric("TradingView", tv.get("recommendation", "—"))
                _sent = lc.get("sentiment")
                m[5].metric("Social sentiment",
                            f"{_sent:.0f}%" if _sent is not None else "—")

                st.markdown(f"**Decision:** {dec['decision']} · "
                            f"**when to open:** {dec['when']}")
                st.markdown(f"**Hold duration:** {dec['hold']}")
                st.markdown(f"**Read:** {r['bias_label']} bias · "
                            f"{r['action_label']} timing · {r['regime']} "
                            f"market regime")
                _plan = r.get("trade_plan")
                if isinstance(_plan, dict):
                    st.markdown(
                        f"**Trade levels:** entry "
                        f"{fmt_price(_plan['entry_low'])}–"
                        f"{fmt_price(_plan['entry_high'])} · stop "
                        f"{fmt_price(_plan['stop_loss'])} · targets "
                        f"{fmt_price(_plan['take_profit'])} / "
                        f"{fmt_price(_plan['take_profit_2'])} · "
                        f"R:R {_plan['risk_reward']:.1f}")
                st.caption("📈 Prediction — " + dec["outlook"])

        st.caption("Decisions are algorithmic — derived from technicals, "
                   "derivatives, live order flow and social data. "
                   "Educational only, not financial advice.")


# ===========================================================================
# Tab 8 — Paper Trader (bot that tests the signals with virtual money)
# ===========================================================================
if active_section == "🧪 Paper Trader":
    st.subheader("🧪 Paper Trading Bot")
    st.caption(
        "Open trades on any coin from the left panel, or let the bot "
        "auto-trade from high-confidence alerts. The bot manages stops "
        "and targets every scan and tracks every trade. State persists "
        "to `.paper_bot.json` so a run survives refreshes and full app "
        "restarts.")

    pb_state = paper_bot.load_state(PAPER_BOT_FILE)

    # ---- One-time balance migration to $20k (per user request) -----------
    # If the user's state has the old $10k default AND has no closed trades
    # yet, auto-bump to the new $20k default. Skips migration if user has
    # any trading history (preserves their P&L curve).
    _old_default_balance = 10000.0
    _new_default_balance = 20000.0
    _has_history = bool(pb_state.get("closed")) or bool(pb_state.get("open"))
    _cur_start = float(pb_state.get("starting_balance") or 0)
    _cur_bal = float(pb_state.get("balance") or 0)
    if (not _has_history
            and abs(_cur_start - _old_default_balance) < 0.01
            and abs(_cur_bal - _old_default_balance) < 0.01):
        pb_state["starting_balance"] = _new_default_balance
        pb_state["balance"] = _new_default_balance
        paper_bot.save_state(PAPER_BOT_FILE, pb_state)

    # ---- Settings (collapsed so the trade UI is the focus) ---------------
    with st.expander("⚙️ Settings — balance, risk, leverage, auto-trade, live, reset"):
        c1, c2, c3, c4, c5 = st.columns([1.2, 1.2, 1.3, 1.1, 1.1])
        new_balance = c1.number_input(
            "Starting balance ($)", min_value=100.0, max_value=1_000_000.0,
            value=float(pb_state.get("starting_balance") or 20000.0),
            step=500.0, key="pb_start_balance")
        new_risk = c2.slider(
            "Risk per trade (%)", 0.25, 5.0,
            float(pb_state.get("risk_per_trade_pct") or 1.0), 0.25,
            key="pb_risk")
        auto_trade = c3.checkbox(
            "🟢 Auto-trade from alerts", value=False, key="pb_auto",
            help="When on, each scan the agent opens new positions for "
                 "every high-confidence trade alert (>= 72% confidence, "
                 "counter-trend setups require >= 85), long and short.")
        live_mode = c4.checkbox(
            "🔴 Live", value=True, key="pb_live",
            help="Auto-refresh every 3 minutes so the page stays "
                 "active, scanner cache (120s) refreshes between "
                 "loads, and new patterns / picks surface "
                 "automatically without you reloading. Pattern Scout "
                 "(10-min cache) re-scans every 3-4 cycles. Default ON.")
        if c5.button("🔄 Reset", type="secondary",
                     use_container_width=True):
            paper_bot.reset(PAPER_BOT_FILE, new_balance, new_risk)
            st.rerun()
        # Futures-style sizing controls (row 2 — added 2026-05-25 per
        # user request for leverage trading + max notional cap).
        cf1, cf2 = st.columns([1, 1])
        new_leverage = cf1.slider(
            "Leverage (×)", 1.0, 10.0,
            float(pb_state.get("leverage") or 3.0), 0.5,
            key="pb_leverage",
            help="Margin multiplier. With $5k notional at 3× leverage, "
                 "margin used = $1,667. Stronger signals can deploy "
                 "more leverage if you raise this; lower it for safety.")
        new_max_notional = cf2.number_input(
            "Max notional per trade ($)",
            min_value=200.0, max_value=100_000.0,
            value=float(pb_state.get("max_notional_per_trade") or 5000.0),
            step=500.0, key="pb_max_notional",
            help="Hard cap on $ size per single position. The risk model "
                 "still enforces the 'Risk per trade %' loss limit; this "
                 "cap stops a tight-stop setup from sizing up beyond "
                 "what you want exposed.")
        # Persist the leverage / cap settings into state so paper_bot
        # honours them on every new position.
        pb_state["leverage"] = float(new_leverage)
        pb_state["max_notional_per_trade"] = float(new_max_notional)

        # EARLY MOMENTUM filter REMOVED 2026-05-30. It was an A/B test
        # toggle that caused recurring "empty picks board" confusion.
        # With the new Pattern Scout + 💎 SURE SHOT + long_patterns
        # architecture, this filter is obsolete:
        #   - SURE SHOT already requires Pattern Scout confirmation
        #   - long_patterns provides validated LONG-side edge (67% @ 48b)
        #   - early_momentum LONG component backtested 38% win — kept
        #     only as a SHORT-side signal (which works at 71% win)
        # Force off in state so existing users don't inherit the filter.
        pb_state["em_filter_on"] = False

    # ---- Helpers used in this section ------------------------------------
    def _hold_horizon(tf):
        """Suggested holding period — capped at 1-2 days per user preference.

        The agent is a short-term swing/intraday trader; positions are not
        intended to be held longer than ~2 days regardless of timeframe."""
        return {"15m": "a few hours",
                "1h": "1 day",
                "4h": "1-2 days",
                "1d": "1-2 days"}.get(tf, "1-2 days")

    def _strength_label(conf):
        """Confidence → (label, colour) for a signal-strength badge."""
        if conf >= 80:
            return ("Very Strong", "#0b8a3e")
        if conf >= 70:
            return ("Strong", "#2ed47a")
        if conf >= 60:
            return ("Moderate", "#e0a92b")
        return ("Weak", "#8b8d98")

    def _enrich_position(pos, conf, tf, label_override=None):
        """Stamp a position with the metadata the UI shows back."""
        if pos is None:
            return None
        pos["hold_horizon"] = _hold_horizon(tf)
        pos["strength_label"] = (label_override
                                 if label_override is not None
                                 else _strength_label(conf)[0])
        pos["timeframe"] = tf
        return pos

    def _render_position_chart(symbol, side, entry, stop, target, cur_price):
        """Mini chart for one open position — recent 1h price line with
        Entry / Stop / Target levels and a live-price dot."""
        try:
            kdf = load_klines(symbol, "1h").tail(72)
        except Exception:
            return
        if kdf is None or kdf.empty:
            return
        line_color = "#2ed47a" if side == "LONG" else "#ff5c5c"
        fig = go.Figure()
        fig.add_trace(go.Scatter(
            x=kdf.index, y=kdf["close"], mode="lines",
            line=dict(color=line_color, width=2),
            showlegend=False, name="Price"))
        # Live price dot at the right edge.
        fig.add_trace(go.Scatter(
            x=[kdf.index[-1]], y=[cur_price], mode="markers",
            marker=dict(color="#fff", size=9,
                        line=dict(color=line_color, width=2)),
            showlegend=False, name="Now"))
        for level, lcol, name in (
                (entry,  "#6e8bff", f"Entry {fmt_price(entry)}"),
                (stop,   "#ff5c5c", f"Stop {fmt_price(stop)}"),
                (target, "#2ed47a", f"Target {fmt_price(target)}")):
            fig.add_hline(
                y=level, line_color=lcol,
                line_dash="dot" if name.startswith("Entry") else "dash",
                annotation_text=name, annotation_position="right",
                annotation=dict(font=dict(size=10, color=lcol)))
        fig.update_layout(
            height=180, margin=dict(l=0, r=90, t=10, b=10),
            plot_bgcolor="rgba(0,0,0,0)",
            paper_bgcolor="rgba(0,0,0,0)",
            xaxis=dict(showgrid=False, color="#888"),
            yaxis=dict(showgrid=False, color="#888"))
        st.plotly_chart(
            fig, use_container_width=True,
            config={"displayModeBar": False})

    # ------------------------------------------------------------------
    # Live-updating fragments — these refresh IN PLACE every 10 seconds
    # without reloading the whole page. They each re-read paper-bot state
    # from disk so a Close action or weekly reset is reflected immediately.
    # ------------------------------------------------------------------
    @st.fragment(run_every=10)
    def _live_paper_stats():
        """Bank + trade stats row, live-updating."""
        state = paper_bot.load_state(PAPER_BOT_FILE)
        live_p: dict[str, float] = {}
        for _p in state["open"]:
            _lp = live_price(_p["symbol"])
            live_p[_p["symbol"]] = (
                float(_lp) if _lp is not None and _lp > 0
                else float(_p["entry"]))

        bal = float(state["balance"])
        start_bal = float(state.get("starting_balance") or bal)
        margin_used = paper_bot.open_margin_used(state)
        unreal = paper_bot.unrealized_pnl(state, live_p)
        available = bal - margin_used
        equity = bal + unreal
        realized = bal - start_bal
        realized_pct = ((realized / start_bal * 100)
                        if start_bal else 0.0)

        bc = st.columns(5)
        bc[0].metric(
            "💰 Bank balance", f"${bal:,.2f}",
            f"{realized_pct:+.2f}% since start",
            help="Realised cash. Updates only when a trade closes.")
        bc[1].metric(
            "Available", f"${available:,.2f}",
            f"-${margin_used:,.0f} in trades" if margin_used > 0
            else "all free",
            help="Free to deploy — bank balance minus locked margin.")
        unr_arrow = "↑" if unreal >= 0 else "↓"
        bc[2].metric(
            "Unrealised P&L", f"${unreal:+,.2f}",
            f"{unr_arrow} from open positions",
            help="Live mark-to-market across open positions.")
        bc[3].metric(
            "📊 Equity", f"${equity:,.2f}",
            f"${realized:+,.0f} realised",
            help="Bank balance + unrealised P&L.")
        bc[4].metric(
            "Realised P&L", f"${realized:+,.2f}",
            f"{realized_pct:+.2f}% of start",
            help="Total realised since the period started.")

        st_stats = paper_bot.stats(state)
        _elapsed = max(0.0, time.time() - float(
            state.get("started_at") or time.time()))
        _days_left = (paper_bot.WEEKLY_RESET_DAYS
                      - _elapsed / 86400.0)
        _reset_txt = (f"{_days_left:.1f} days"
                      if _days_left > 0 else "next refresh")
        sc = st.columns(5)
        sc[0].metric("Trades closed", st_stats["trades"])
        sc[1].metric("Win rate",
                     f"{st_stats['win_rate']:.0f}%"
                     if st_stats["trades"] else "—")
        sc[2].metric("Best trade",
                     f"{st_stats['best_trade']:+.2f}%"
                     if st_stats["trades"] else "—")
        sc[3].metric("Worst trade",
                     f"{st_stats['worst_trade']:+.2f}%"
                     if st_stats["trades"] else "—")
        sc[4].metric("⏰ Resets in", _reset_txt,
                     f"to ${start_bal:,.0f}",
                     help=(f"Auto-restores to ${start_bal:,.0f} every "
                           f"{paper_bot.WEEKLY_RESET_DAYS} days."))

    @st.fragment(run_every=10)
    def _live_paper_positions():
        """Open-position cards, live-updating. Also re-runs the stop/target
        evaluator on every tick so a hit fires in seconds, not minutes."""
        state = paper_bot.load_state(PAPER_BOT_FILE)
        live_p: dict[str, float] = {}
        for _p in state["open"]:
            _lp = live_price(_p["symbol"])
            live_p[_p["symbol"]] = (
                float(_lp) if _lp is not None and _lp > 0
                else float(_p["entry"]))

        # Evaluate stops/targets on every fragment tick with live prices.
        closed_now = paper_bot.evaluate(state, live_p)
        for c in closed_now:
            emoji = "✅" if c["pnl_usd"] > 0 else "❌"
            st.toast(
                f"{emoji} {c['base']} closed at {c['exit_reason']} · "
                f"{c['pnl_pct']:+.2f}%", icon="🧪")
        if closed_now:
            paper_bot.save_state(PAPER_BOT_FILE, state)

        st.markdown(f"### 📂 Open positions ({len(state['open'])})")
        if not state["open"]:
            st.info(
                "No open positions. Use the panel on the left to open a "
                "trade, or toggle **Auto-trade** in Settings to let the "
                "bot trade alerts automatically.")
            return

        for p in state["open"]:
            cur = live_p.get(p["symbol"], p["entry"])
            long = (p["side"] == "LONG")
            entry_v = float(p["entry"])
            stop_v = float(p["stop"])
            target_v = float(p["target"])
            qty_v = float(p["qty"])
            notional_v = float(p.get("notional") or (qty_v * entry_v))
            lev_v = int(p.get("leverage") or 1)
            unreal_pos = (((cur - entry_v) if long
                           else (entry_v - cur)) * qty_v)
            unreal_pct_pos = (unreal_pos / state["balance"] * 100
                              if state["balance"] else 0.0)
            if entry_v > 0:
                pct_from_entry = ((cur - entry_v) / entry_v * 100)
                if not long:
                    pct_from_entry = -pct_from_entry
            else:
                pct_from_entry = 0.0
            color = "#2ed47a" if unreal_pos >= 0 else "#ff5c5c"
            side_color = "#2ed47a" if long else "#ff5c5c"
            if long:
                if cur >= entry_v:
                    prog = (((cur - entry_v) / (target_v - entry_v)
                             * 50 + 50)
                            if target_v != entry_v else 50)
                else:
                    prog = ((50 - (entry_v - cur) / (entry_v - stop_v)
                             * 50)
                            if entry_v != stop_v else 50)
            else:
                if cur <= entry_v:
                    prog = (((entry_v - cur) / (entry_v - target_v)
                             * 50 + 50)
                            if entry_v != target_v else 50)
                else:
                    prog = ((50 - (cur - entry_v) / (stop_v - entry_v)
                             * 50)
                            if stop_v != entry_v else 50)
            health = int(max(0, min(100, prog)))
            hold_txt = p.get("hold_horizon") or "—"
            str_label = p.get("strength_label", "")
            be_badge = (" · ✓ break-even"
                        if p.get("break_even_set") else "")
            lev_txt = f" · {lev_v}× lev" if lev_v > 1 else ""

            with st.container(border=True):
                info_col, pnl_col, btn_col = st.columns([2.4, 1.8, 0.8])
                info_col.markdown(
                    f"<div style='font-size:1.05rem;font-weight:800;"
                    f"margin-bottom:2px'>{p['base']} "
                    f"<span style='background:{side_color};color:#06121f;"
                    f"padding:2px 10px;border-radius:5px;font-size:"
                    f"0.72rem;font-weight:800;margin-left:6px'>"
                    f"{p['side']}</span></div>"
                    f"<div style='color:#d5d7e0;font-size:0.84rem;"
                    f"margin:3px 0'>"
                    f"<b>{qty_v:.6f} {p['base']}</b> · "
                    f"notional <b>${notional_v:,.2f}</b>{lev_txt}</div>"
                    f"<div style='color:#8b8d98;font-size:0.78rem'>"
                    f"Entry {fmt_price(entry_v)} · Stop "
                    f"{fmt_price(stop_v)} · Target {fmt_price(target_v)}"
                    f" · hold: {hold_txt}"
                    + (f" · {str_label}" if str_label else "")
                    + be_badge + "</div>",
                    unsafe_allow_html=True)
                pnl_col.markdown(
                    f"<div style='text-align:right;font-size:1.15rem;"
                    f"font-weight:800;color:#fff'>{fmt_price(cur)}</div>"
                    f"<div style='text-align:right;color:{color};"
                    f"font-size:1.1rem;font-weight:800;margin-top:2px'>"
                    f"${unreal_pos:+,.2f}</div>"
                    f"<div style='text-align:right;color:{color};"
                    f"font-size:0.78rem;font-weight:700;margin-top:1px'>"
                    f"{pct_from_entry:+.2f}% from entry · "
                    f"{unreal_pct_pos:+.2f}% balance</div>",
                    unsafe_allow_html=True)
                if btn_col.button(
                        "Close", key=f"pb_close_{p['symbol']}",
                        use_container_width=True):
                    cl = paper_bot.close_position_at(
                        state, p["symbol"], cur, reason="manual")
                    if cl:
                        paper_bot.save_state(PAPER_BOT_FILE, state)
                        emoji = "✅" if cl["pnl_usd"] > 0 else "❌"
                        st.toast(
                            f"{emoji} Closed {cl['base']} · "
                            f"{cl['pnl_pct']:+.2f}%", icon="🧪")
                        st.rerun(scope="fragment")
                st.progress(health, text=(
                    f"🎯 {health}% toward target"
                    if health >= 50
                    else f"⚠️ {100 - health}% toward stop"))
                _render_position_chart(
                    p["symbol"], p["side"],
                    entry_v, stop_v, target_v, cur)

    # Apply latest settings — only adopt new balance on a fresh book.
    pb_state["risk_per_trade_pct"] = float(new_risk)
    if not pb_state.get("closed") and not pb_state.get("open"):
        pb_state["starting_balance"] = float(new_balance)
        pb_state["balance"] = float(new_balance)

    # ---- Live price map for every open position ---------------------------
    # Start with the cached scanner prices, then OVERRIDE each open
    # position's price with a fresh live fetch (5-second cache). That way
    # the position cards, P&L and chart dot reflect a near-real-time price
    # even when the 120-second scanner cache is still warm.
    # `prices` is built at module scope from the alerts scan. Layer
    # live-price overrides on top for THIS paper-trader run's open
    # positions so card/P&L numbers stay near-real-time even when the
    # 120-second scanner cache is still warm.
    prices = dict(prices)  # local copy so paper overrides don't leak
    for _p in pb_state["open"]:
        _lp = live_price(_p["symbol"])
        if _lp is not None and _lp > 0:
            prices[_p["symbol"]] = float(_lp)

    # ---- ALWAYS evaluate stops/targets first (with live prices) ----------
    just_closed = paper_bot.evaluate(pb_state, prices)
    for c in just_closed:
        emoji = "✅" if c["pnl_usd"] > 0 else "❌"
        st.toast(
            f"{emoji} {c['base']} closed at {c['exit_reason']} · "
            f"{c['pnl_pct']:+.2f}%", icon="🧪")

    # ---- Auto-trade from alerts ------------------------------------------
    # `auto_ad` is built once at module scope (right after the alerts
    # strip) so both Paper Trader and Live Trading share the same dict.

    # ---- Forecast lookup (used by PREMIUM HUNT + picks board) -----------
    # Built once here, used by both the auto-trade loop and the picks
    # rendering below so we never pay for the forecast call twice.
    _fc_by_sym: dict[str, dict] = {}
    _radar_by_sym: dict[str, dict] = {}
    try:
        _fc_tickers_bot = load_top_symbols(top_n)
        _fc_syms_bot = tuple(_fc_tickers_bot["symbol"].head(40))
        _fc_df_bot = forecast_market(_fc_syms_bot)
        if _fc_df_bot is not None and not _fc_df_bot.empty:
            _fc_by_sym = {r["symbol"]: r.to_dict()
                          for _, r in _fc_df_bot.iterrows()}
    except Exception:
        pass

    # ---- Breakout Radar lookup (catches COILED pre-explosion setups) ----
    # Independent signal engine: looks at volume ignition, coil/expansion,
    # taker order flow, OBV accumulation, multi-TF trend, news/social
    # catalyst — and grades each coin by STAGE:
    #   COILED   — loaded but NOT fired yet (predictive low-risk entry)
    #   FRESH    — early breakout, room left to run
    #   EXTENDED — move spent, chase risk
    # This is the closest honest tool for "early signals on coins about
    # to explode" — wired into the picks score so COILED setups rise.
    try:
        _radar_syms = tuple(_fc_tickers_bot["symbol"].head(40))
        _radar_df, _radar_backdrop = scan_breakouts(
            _radar_syms, "imminent")
        if _radar_df is not None and not _radar_df.empty:
            _radar_by_sym = {r["symbol"]: r.to_dict()
                             for _, r in _radar_df.iterrows()}
    except Exception:
        pass

    def _mark_premium(setup: dict) -> dict:
        """Mark setups that QUALIFY for PREMIUM (conf >= 80 + forecast
        aligned 3/3 + direction matches). Does NOT change the target —
        paper trader defaults to TP1 for ALL setups. The mark just lets
        the card render a second "🏆 TP2" button as an OPT-IN deeper
        target the user can click when they explicitly want it.

        Per user feedback 2026-05-25: auto-promoting to TP2 caused too
        many reversals before exit. TP1 stays the default; TP2 becomes
        an explicit choice on the card."""
        conf = int(setup.get("confidence", 0) or 0)
        tgt2 = setup.get("target_2")
        if conf < 80 or not tgt2:
            return setup
        fc = _fc_by_sym.get(setup.get("symbol")) or {}
        if not fc.get("aligned"):
            return setup
        side = setup.get("side")
        word = fc.get("outlook_word")
        confirms = ((side == "LONG" and word == "Bullish")
                    or (side == "SHORT" and word == "Bearish"))
        if not confirms:
            return setup
        marked = dict(setup)
        marked["premium_eligible"] = True   # for the 🏆 TP2 button + chip
        return marked

    if auto_trade:
        for setup in auto_ad["setups"]:
            _setup_conf = int(setup.get("confidence", 0) or 0)
            # Auto-trade floor matches CONF_ALERT (72) — anything weaker
            # never makes the setups list anyway, but keep the explicit
            # gate so a future CONF_ALERT change doesn't silently let
            # weak setups auto-fire.
            if _setup_conf < 72:
                continue
            # Higher-TF trend filter — skip counter-trend setups unless the
            # signal is very strong (>=85). Trading against the weekly
            # trend has worse statistics than going with it.
            _setup_trend = htf_trend(setup["symbol"])
            _setup_align = htf_alignment(setup["side"], _setup_trend)
            if _setup_align == "counter" and _setup_conf < 85:
                continue
            # Default to TP1 for all setups. PREMIUM-eligible setups
            # ADDITIONALLY get the chase-TP2 trailing — if price hits
            # TP1, the stop moves up to TP1 (locking in the win) and
            # the target extends to TP2 so the trade can ride further
            # when the trend is still strong. Strictly better than
            # fixed TP1 — never worse, sometimes +1R better.
            _setup_for_open = _mark_premium(setup)
            if _setup_for_open.get("premium_eligible"):
                _setup_for_open = dict(_setup_for_open)
                _setup_for_open["chase_tp2_eligible"] = True
            # Strength-based notional scaling. The notional cap from
            # settings is multiplied by a factor derived from the
            # setup's scanner confidence — strong signals deploy
            # closer to the user's cap, weaker ones get a smaller
            # position. Auto-trade has no easy access to the combined
            # score here, so use raw scanner conf as the proxy
            # (combined - 72 mapped to 0.4-1.0 range).
            _strength = max(0.4, min(1.0, (_setup_conf - 72) / 23.0 + 0.4))
            _setup_for_open = dict(_setup_for_open)
            _setup_for_open["strength_factor"] = _strength
            opened = paper_bot.open_position(
                pb_state, _setup_for_open,
                prices.get(setup["symbol"]) or setup.get("entry_low"))
            if opened:
                _enrich_position(opened,
                                 setup.get("confidence", 0), timeframe)
                _icon = ("🏆" if _setup_for_open.get("chase_tp2_eligible")
                         else "🧪")
                st.toast(
                    f"📥 Auto-opened {opened['side']} {opened['base']} "
                    f"@ {fmt_price(opened['entry'])}"
                    + (" → TP1 (chase TP2 active)"
                       if _setup_for_open.get("chase_tp2_eligible")
                       else ""),
                    icon=_icon)

    # ---- Track persistence of bot suggestions ----------------------------
    # An alert that stays on the board for many minutes is more trustworthy
    # than one that just flickered in; show 'alive for X min' on each pick.
    now_ts = time.time()
    sp = pb_state.setdefault("suggestion_persistence", {})
    current_setup_ids: set[str] = set()
    for _s in auto_ad["setups"]:
        _sid = f"{_s['symbol']}:{_s['side']}"
        current_setup_ids.add(_sid)
        if _sid not in sp:
            sp[_sid] = now_ts
    for _sid in list(sp.keys()):
        if _sid not in current_setup_ids:
            del sp[_sid]

    # ---- Weekly auto-reset to the starting balance -----------------------
    _reset_info = paper_bot.check_weekly_reset(pb_state, prices)
    if _reset_info["reset"]:
        st.success(
            f"⏰ Weekly reset! Balance restored to "
            f"${pb_state['starting_balance']:,.0f}. "
            f"{len(_reset_info['closed_at_reset'])} open position(s) "
            f"were closed at market — the closed-trades history is "
            f"preserved so you can review the previous period.")

    paper_bot.save_state(PAPER_BOT_FILE, pb_state)

    # ---- Bank + trade stats — LIVE fragment (updates in place every 10s)
    _live_paper_stats()

    st.divider()

    # ---- Main two-column layout: LEFT = open new trade, RIGHT = positions
    left_col, right_col = st.columns([1, 2])

    with left_col:
        st.markdown("### 📥 Open a trade")
        if _alert_merged.empty:
            st.info("Scan data not ready — refresh and try again.")
        else:
            _syms = sorted(_alert_merged["symbol"].unique().tolist())
            _open_syms = {p["symbol"] for p in pb_state["open"]}
            _avail = [s for s in _syms if s not in _open_syms]
            if not _avail:
                st.warning("You already have a position in every tracked "
                           "coin — close one before opening another.")
            else:
                _sel = st.selectbox(
                    "Coin", _avail,
                    format_func=lambda s: s.replace("USDT", ""),
                    key="pb_open_sym")
                _side = st.radio(
                    "Side", ["LONG", "SHORT"], horizontal=True,
                    key="pb_open_side")
                _row_match = _alert_merged[_alert_merged["symbol"] == _sel]
                _row = (_row_match.iloc[0]
                        if not _row_match.empty else None)
                _cur = (float(_row["price"])
                        if _row is not None else 0.0)
                _chg = (float(_row.get("priceChangePercent") or 0.0)
                        if _row is not None else 0.0)
                _plan = (_row.get("trade_plan")
                         if _row is not None
                         and isinstance(_row.get("trade_plan"), dict)
                         else None)

                # ---- Live price card --------------------------------------
                _ch_color = "#2ed47a" if _chg >= 0 else "#ff5c5c"
                st.markdown(
                    f"<div style='background:#11141c;padding:10px 14px;"
                    f"border-radius:6px;margin:6px 0 10px 0;"
                    f"border:1px solid #1f2330'>"
                    f"<div style='font-size:0.7rem;color:#8b8d98;"
                    f"letter-spacing:0.08em;font-weight:700'>LIVE PRICE · "
                    f"{_sel.replace('USDT','')}/USDT</div>"
                    f"<div style='display:flex;align-items:baseline;"
                    f"gap:10px;flex-wrap:wrap'>"
                    f"<span style='font-size:1.4rem;font-weight:800;"
                    f"color:#fff'>{fmt_price(_cur)}</span>"
                    f"<span style='color:{_ch_color};font-size:0.85rem;"
                    f"font-weight:700'>{_chg:+.2f}% (24h)</span>"
                    f"</div></div>", unsafe_allow_html=True)

                # ---- Order type + entry -----------------------------------
                _order_type = st.radio(
                    "Order type", ["Market", "Limit"],
                    horizontal=True, key="pb_open_order_type")
                _combo = f"{_sel}_{_side}_{_order_type}"
                _step = (_cur * 0.001) if _cur > 0 else 0.01
                if _order_type == "Market":
                    _entry = _cur
                    st.caption(
                        f"Entry: **{fmt_price(_entry)}** (market price)")
                else:
                    _entry = st.number_input(
                        "Limit entry price", value=float(_cur),
                        format="%.8f", step=_step,
                        key=f"pb_entry_{_combo}")

                # ---- Stop & take-profit (editable) ------------------------
                if _plan and _plan.get("side") == _side:
                    _def_stop = float(_plan["stop_loss"])
                    _def_target = float(_plan["take_profit"])
                else:
                    _def_stop = _entry * (0.98 if _side == "LONG" else 1.02)
                    _def_target = _entry * (1.04 if _side == "LONG" else 0.96)
                _sc1, _sc2 = st.columns(2)
                _stop = _sc1.number_input(
                    "Stop loss", value=float(_def_stop), format="%.8f",
                    step=_step, key=f"pb_stop_{_combo}")
                _target = _sc2.number_input(
                    "Take profit", value=float(_def_target), format="%.8f",
                    step=_step, key=f"pb_target_{_combo}")

                if _entry > 0 and _stop != _entry:
                    _stop_pct = abs((_entry - _stop) / _entry * 100)
                    _target_pct = abs((_target - _entry) / _entry * 100)
                    _rr = abs(_target - _entry) / abs(_entry - _stop)
                else:
                    _stop_pct = _target_pct = _rr = 0.0
                st.caption(
                    f"Stop **{_stop_pct:.2f}%** away · Target "
                    f"**{_target_pct:.2f}%** away · R:R **{_rr:.2f}**")

                # ---- Leverage (futures only) ------------------------------
                if trade_mode == "futures":
                    _leverage = st.slider(
                        "Leverage", 1, 10, 1, key="pb_open_leverage")
                else:
                    _leverage = 1
                    st.caption("Spot mode — no leverage (1×)")

                # ---- Sizing method ----------------------------------------
                _sizing = st.radio(
                    "How to size", ["Risk-based", "Dollar amount",
                                    "Quantity", "% of balance"],
                    key="pb_sizing")
                _balance = float(pb_state["balance"])
                _available = _balance - paper_bot.open_margin_used(pb_state)

                if _sizing == "Risk-based":
                    _risk_pct_in = st.slider(
                        "Account risk per trade (%)", 0.25, 5.0,
                        float(pb_state.get("risk_per_trade_pct", 1.0)), 0.25,
                        key="pb_risk_pct_slider")
                    _risk_dollars = _balance * _risk_pct_in / 100
                    _risk_pu = (abs(_entry - _stop)
                                if _entry != _stop else 0.0)
                    _qty = (_risk_dollars / _risk_pu
                            if _risk_pu > 0 else 0.0)
                elif _sizing == "Dollar amount":
                    _max_notional = max(_balance * _leverage, _balance)
                    _notional_in = st.number_input(
                        "Notional ($) to deploy",
                        min_value=10.0, max_value=float(_max_notional),
                        value=float(min(1000.0, _balance)),
                        step=100.0, key="pb_notional_in")
                    _qty = _notional_in / _entry if _entry > 0 else 0.0
                elif _sizing == "Quantity":
                    _qty = st.number_input(
                        f"Quantity ({_sel.replace('USDT','')})",
                        min_value=0.0, value=1.0, step=0.001,
                        format="%.6f", key="pb_qty_in")
                else:                       # % of balance
                    _pct = st.slider(
                        "% of balance to allocate", 1, 100, 10,
                        key="pb_pct_alloc")
                    _qty = ((_balance * _pct / 100 * _leverage) / _entry
                            if _entry > 0 else 0.0)

                _qty = float(_qty)
                _notional_val = _qty * _entry
                _margin = (_notional_val / _leverage
                           if _leverage > 0 else _notional_val)
                _risk_dollars_final = _qty * abs(_entry - _stop)
                _risk_pct_final = (_risk_dollars_final / _balance * 100
                                   if _balance > 0 else 0.0)
                _potential_profit = _qty * abs(_target - _entry)
                _profit_pct = (_potential_profit / _balance * 100
                               if _balance > 0 else 0.0)

                # ---- Live order summary -----------------------------------
                _summary_lines = [
                    f"Position size: <b>{_qty:.6f} "
                    f"{_sel.replace('USDT','')}</b>",
                    f"Notional value: <b>${_notional_val:,.2f}</b>",
                ]
                if trade_mode == "futures" and _leverage > 1:
                    _summary_lines.append(
                        f"Margin required: <b>${_margin:,.2f}</b> "
                        f"(at {_leverage}× leverage)")
                _summary_lines.extend([
                    f"Risk if stopped: <b style='color:#ff5c5c'>"
                    f"${_risk_dollars_final:,.2f}</b> "
                    f"({_risk_pct_final:.2f}% of balance)",
                    f"Reward if target: <b style='color:#2ed47a'>"
                    f"${_potential_profit:,.2f}</b> "
                    f"({_profit_pct:.2f}% of balance)",
                    f"R:R = <b>{_rr:.2f}R</b> · Suggested hold: "
                    f"<b>{_hold_horizon(timeframe)}</b>",
                ])
                st.markdown(
                    f"<div style='background:#0e1118;border-left:3px solid "
                    f"#6e8bff;padding:10px 14px;border-radius:5px;"
                    f"margin:8px 0'>"
                    f"<div style='font-size:0.7rem;color:#6e8bff;"
                    f"letter-spacing:0.08em;font-weight:800;"
                    f"margin-bottom:6px'>📊 LIVE ORDER SUMMARY</div>"
                    f"<div style='color:#d5d7e0;font-size:0.85rem;"
                    f"line-height:1.6'>" + "<br>".join(_summary_lines)
                    + "</div></div>", unsafe_allow_html=True)

                # ---- Validation warnings ----------------------------------
                _warnings = []
                if _side == "LONG" and _stop >= _entry:
                    _warnings.append(
                        "Stop must be BELOW entry for a LONG trade.")
                if _side == "SHORT" and _stop <= _entry:
                    _warnings.append(
                        "Stop must be ABOVE entry for a SHORT trade.")
                if _side == "LONG" and _target <= _entry:
                    _warnings.append(
                        "Take profit must be ABOVE entry for a LONG trade.")
                if _side == "SHORT" and _target >= _entry:
                    _warnings.append(
                        "Take profit must be BELOW entry for a SHORT trade.")
                if _qty <= 0:
                    _warnings.append(
                        "Position size is zero — adjust sizing inputs.")
                if _margin > _available:
                    _warnings.append(
                        f"Margin required (${_margin:,.0f}) exceeds your "
                        f"AVAILABLE cash (${_available:,.0f}). Close a "
                        f"trade or size down.")
                if _risk_pct_final > 10:
                    _warnings.append(
                        f"Risking {_risk_pct_final:.1f}% of balance — that "
                        "is aggressive; size down.")
                for _w in _warnings:
                    st.warning(f"⚠️ {_w}")

                # ---- Open button ------------------------------------------
                _can_open = (not _warnings) and _qty > 0
                _btn_label = (
                    f"📥 Open {_side} {_sel.replace('USDT','')} "
                    f"@ {fmt_price(_entry)}")
                if st.button(_btn_label, use_container_width=True,
                             type="primary", key="pb_open_btn",
                             disabled=not _can_open):
                    _manual_alert = {
                        "symbol": _sel,
                        "base": _sel.replace("USDT", ""),
                        "side": _side,
                        "stop": _stop,
                        "target": _target,
                        "entry_low": _entry,
                        "confidence": 0,
                        "rr": _rr,
                    }
                    _opened = paper_bot.open_position(
                        pb_state, _manual_alert, _entry)
                    if _opened:
                        # Override the engine's risk-based qty with the
                        # user's chosen sizing.
                        _opened["qty"] = float(_qty)
                        _opened["notional"] = float(_notional_val)
                        _opened["leverage"] = int(_leverage)
                        _opened["margin"] = float(_margin)
                        _opened["order_type"] = _order_type
                        _enrich_position(_opened, 0, timeframe,
                                         label_override="Manual")
                        paper_bot.save_state(PAPER_BOT_FILE, pb_state)
                        st.toast(
                            f"📥 Opened {_side} {_opened['base']} @ "
                            f"{fmt_price(_opened['entry'])} · qty "
                            f"{_qty:.6f}", icon="🧪")
                        st.rerun()
                    else:
                        st.error(
                            "Could not open — already have a position in "
                            "this coin.")

    with right_col:
        # ---- 🏆 BEST TRADES NOW — multi-layer conviction board ---------
        # The single source of truth for what to trade. Combines:
        #   • Scanner conf (alerts engine multi-TF)
        #   • Forecast alignment (1h + 4h + 1d horizons)
        #   • Pattern Scout (backtested patterns: V-bottom, morning star,
        #     long_patterns_aligned, hammers, engulfings)
        #   • Setups Forming (pre-condition leading signals)
        #   • CONVERGENCE meta-filter (validated +6.8pp uplift)
        #   • SURE SHOT meta-filter (strict 88+ multi-confirm)
        #   • Breakout Radar stage (COILED / FRESH / EXTENDED)
        #   • Market Regime tilt (BULL/BEAR adaptive)
        #   • Weekly trend + BTC Outlook + Move maturity
        #   • Early Momentum (CVD, TTM, VWAP, SMC)
        #   • Relative Strength vs BTC
        #   • Derivatives Velocity (funding ROC + OI compression)
        # Each card shows a CONVICTION tier (MAX / HIGH / STRONG /
        # STANDARD) so you instantly see WHICH layers stacked.
        st.markdown(
            "<div style='display:flex;align-items:center;gap:12px;"
            "margin-top:14px;margin-bottom:4px'>"
            "<span style='font-size:1.5rem;font-weight:900;"
            "background:linear-gradient(135deg,#ffd700,#ff006e,#8b5cf6);"
            "-webkit-background-clip:text;-webkit-text-fill-color:"
            "transparent;background-clip:text;letter-spacing:-0.02em'>"
            "🏆 BEST TRADES NOW</span>"
            "<span style='color:#aab;font-size:0.82rem'>"
            "multi-layer conviction · click 📥 to open</span>"
            "</div>",
            unsafe_allow_html=True)
        st.caption(
            "Each pick stacks **scanner conf + forecast alignment + "
            "Pattern Scout + CONVERGENCE/SURE SHOT meta-filters + "
            "Breakout Radar + regime tilt + RS/DERIV/early-momentum**. "
            "The **CONVICTION badge** on each card tells you how many "
            "layers agree: ⚡⚡⚡ MAX (all top layers stacked) · "
            "⚡⚡ HIGH (most layers) · ⚡ STRONG (strong base) · "
            "⚪ STANDARD (passes floor).")

        # ---- 📊 Market Regime Banner — modern hero design --------------
        # Critical adaptive layer. Backtested edges are regime-dependent —
        # a LONG signal that scored 38% win in a bear sample MAY score
        # 60%+ in a bull regime. The regime detector tilts every pick's
        # combined_score so LONGs surface in bull markets and SHORTs
        # surface in bear markets, naturally adapting to current state.
        _regime = load_market_regime()
        _reg_lbl = _regime.get("regime", "UNKNOWN")
        _reg_conf = float(_regime.get("confidence") or 0)
        _reg_long_bias = float(_regime.get("long_bias") or 50)
        _reg_short_bias = float(_regime.get("short_bias") or 50)
        _reg_composite = float(_regime.get("composite") or 50)
        _reg_color = {
            "BULL": "#2ed47a", "BEAR": "#ff5c5c",
            "TRANSITION": "#e0a92b", "CHOP": "#8b8d98",
            "UNKNOWN": "#8b8d98",
        }.get(_reg_lbl, "#8b8d98")
        _reg_emoji = {
            "BULL": "🐂", "BEAR": "🐻", "TRANSITION": "🔁",
            "CHOP": "💤", "UNKNOWN": "❓",
        }.get(_reg_lbl, "❓")

        # Components for the stat row
        _reg_comps = _regime.get("components", {}) or {}
        _daily_lbl = (_reg_comps.get("daily") or {}).get("label", "—")
        _weekly_lbl = (_reg_comps.get("weekly") or {}).get("label", "—")
        _breadth_pct = (_reg_comps.get("breadth") or {}).get("pct_above", 50)
        _vol_lbl = (_reg_comps.get("volatility") or {}).get("label", "—")

        # Compact one-line regime pill (was a huge banner — user wanted
        # less noise).
        st.markdown(
            f"<div style='display:inline-flex;align-items:center;gap:10px;"
            f"padding:6px 14px;border-radius:20px;"
            f"background:rgba(255,255,255,0.03);"
            f"border:1px solid {_reg_color}44;margin-bottom:14px'>"
            f"<span style='color:{_reg_color};font-weight:800;font-size:0.9rem'>"
            f"{_reg_emoji} {_reg_lbl}</span>"
            f"<span style='color:#888;font-size:0.78rem'>·</span>"
            f"<span style='color:#2ed47a;font-size:0.78rem;font-weight:700'>"
            f"LONG {_reg_long_bias:.0f}</span>"
            f"<span style='color:#888;font-size:0.78rem'>·</span>"
            f"<span style='color:#ff5c5c;font-size:0.78rem;font-weight:700'>"
            f"SHORT {_reg_short_bias:.0f}</span>"
            f"<span style='color:#888;font-size:0.78rem'>·</span>"
            f"<span style='color:#aab;font-size:0.78rem'>"
            f"conf {_reg_conf:.0f}%</span>"
            f"</div>",
            unsafe_allow_html=True)

        # ====================================================================
        # 🏆 BEST TRADES NOW — Unified ranked picks (S/A/B/C tiers)
        # ====================================================================
        # Per user request: consolidate ALL discovery sections into ONE
        # ranked list, deduplicated by symbol. Highest tier wins per coin.
        # Mixed LONG + SHORT. Show top 8. Other source-specific sections
        # collapse into "Browse all sources" expander below.
        try:
            _best_picks = compute_unified_best_picks(timeframe, scan_n=50)
        except Exception:
            _best_picks = []

        # ====================================================================
        # 🔭 WHERE MONEY IS FORMING — Multi-Timeframe Watchlist
        # ====================================================================
        # User-driven: professional traders watch SAME coin across multiple
        # timeframes (15m, 1h, 4h). When 2+ timeframes show same-direction
        # setup forming, that's broad-market positioning shift — much
        # stronger than a single TF signal. Pure WATCHLIST — no trade
        # buttons. Watch for the actual fire candle, then act.
        # Multi-TF Watchlist expander REMOVED per user (too many segments).
        # The compute function still runs (cheap, cached 10 min) for any
        # internal use, but no UI block.
        if False:
            st.caption(
                "**The intelligence layer.** Coins where reversal setups "
                "are forming on **2+ timeframes simultaneously** (15m, 1h, "
                "and/or 4h). When multiple TFs agree, that's institutional "
                "positioning shift, not noise. **NO TRADE BUTTONS** here — "
                "this is watchlist intelligence. Watch these coins, and "
                "when the actual fire candle prints (caught by Bot's Top "
                "Picks below), THAT'S the trade.")
            try:
                _mtf_setups = compute_multi_tf_setups_forming(scan_n=30)
            except Exception:
                _mtf_setups = []

            if not _mtf_setups:
                st.info("No coins currently showing multi-timeframe "
                        "agreement. Market is choppy or directionless. "
                        "Check back in a few minutes.")
            else:
                st.markdown(
                    f"**{len(_mtf_setups)} coins** showing multi-TF setup "
                    f"convergence:")
                for _mtf in _mtf_setups[:8]:
                    _mtf_side = _mtf["side"]
                    _mtf_color = ("#ff3d57" if _mtf_side == "SHORT"
                                  else "#00e676")
                    _mtf_emoji = "🩸" if _mtf_side == "SHORT" else "🟢"
                    _mtf_pct = _mtf.get("pct_24h", 0)
                    _mtf_pct_color = ("#2ed47a" if _mtf_pct > 0
                                      else "#ff5c5c" if _mtf_pct < 0
                                      else "#888")
                    # Build per-TF chips
                    _tf_chips = ""
                    for _tf in ["15m", "1h", "4h"]:
                        _tf_data = _mtf["per_tf"].get(_tf, {})
                        _tf_in_agree = _tf in _mtf["agreeing_tfs"]
                        _tf_score = _tf_data.get("score", 50)
                        _tf_cond = _tf_data.get("conditions", 0)
                        if _tf_in_agree:
                            _tf_chip_color = _mtf_color
                            _tf_chip_bg = (f"rgba("
                                f"{int(_mtf_color[1:3], 16)},"
                                f"{int(_mtf_color[3:5], 16)},"
                                f"{int(_mtf_color[5:7], 16)},0.20)")
                        else:
                            _tf_chip_color = "#666"
                            _tf_chip_bg = "rgba(255,255,255,0.03)"
                        _tf_chips += (
                            f"<span style='background:{_tf_chip_bg};"
                            f"color:{_tf_chip_color};padding:3px 10px;"
                            f"border-radius:6px;font-size:0.74rem;"
                            f"font-weight:700;margin-right:6px'>"
                            f"{_tf} · {_tf_cond}/7"
                            f"</span>")
                    with st.container(border=True):
                        st.markdown(
                            f"<div style='display:flex;align-items:center;"
                            f"gap:10px;flex-wrap:wrap'>"
                            f"<span style='font-weight:800;"
                            f"font-size:1.05rem;font-family:"
                            f"Space Grotesk,Inter,sans-serif'>"
                            f"{_mtf['base']}</span>"
                            f"<span style='background:{_mtf_color};"
                            f"color:#06121f;padding:3px 12px;"
                            f"border-radius:6px;font-size:0.74rem;"
                            f"font-weight:800'>{_mtf_emoji} "
                            f"{_mtf_side} forming</span>"
                            f"<span style='background:linear-gradient(135deg,"
                            f"#5b8eff,#8b5cf6);color:#fff;padding:3px 10px;"
                            f"border-radius:6px;font-size:0.72rem;"
                            f"font-weight:800;box-shadow:0 0 8px "
                            f"rgba(91,142,255,0.4)'>"
                            f"🔭 {_mtf['tf_count']}/3 TFs agree</span>"
                            f"<span style='color:#888;font-size:0.78rem'>"
                            f"now ${_mtf['price']:.4g} · "
                            f"<span style='color:{_mtf_pct_color}'>"
                            f"{_mtf_pct:+.2f}% 24h</span></span>"
                            f"</div>"
                            f"<div style='margin-top:10px'>{_tf_chips}</div>"
                            f"<div style='color:#aab;font-size:0.78rem;"
                            f"margin-top:8px;line-height:1.5'>"
                            f"<b>Watch for:</b> "
                            + (f"bearish reversal candle (shooting star, "
                               f"evening star, bearish engulfing) on any "
                               f"of these timeframes. When it prints, "
                               f"check the regular picks below for the "
                               f"confirmed entry."
                               if _mtf_side == "SHORT" else
                               f"bullish reversal candle (hammer, morning "
                               f"star, bullish engulfing) on any of these "
                               f"timeframes. When it prints, check the "
                               f"regular picks below for the entry.")
                            + f"</div>",
                            unsafe_allow_html=True)

        st.markdown(
            "<div style='height:1px;background:linear-gradient(90deg,"
            "transparent,rgba(91,142,255,0.3),transparent);"
            "margin:18px 0'></div>",
            unsafe_allow_html=True)

        # === Safety rails always active (across both old + new picks) ===
        # Daily loss circuit + max concurrent check (research-driven)
        _ds_start = float(pb_state.get("starting_balance") or 20000)
        _ds_today_pnl = 0.0
        _ds_today_cutoff = now_ts - 86400  # last 24h
        for _c in pb_state.get("closed", []):
            if (_c.get("exit_at") or 0) >= _ds_today_cutoff:
                _ds_today_pnl += float(_c.get("pnl_usd") or 0)
        _ds_daily_loss_pct = (_ds_today_pnl / _ds_start * 100
                              if _ds_start > 0 else 0)
        _ds_circuit_tripped = _ds_daily_loss_pct <= -3.0
        _ds_open_count = len(pb_state.get("open") or [])
        _ds_max_concurrent = 3
        _ds_concurrent_full = _ds_open_count >= _ds_max_concurrent

        if _ds_circuit_tripped:
            st.error(
                f"🛑 **DAILY LOSS CIRCUIT TRIPPED** · today's realised "
                f"P&L: **${_ds_today_pnl:,.2f}** ({_ds_daily_loss_pct:.2f}%) "
                f"· auto-trade BLOCKED for 24h. Wait, don't force trades.")
        if _ds_concurrent_full:
            st.warning(
                f"⚠ **{_ds_open_count}/{_ds_max_concurrent} concurrent "
                f"positions used.** Close one before opening another.")

        # NOTE: BEST TRADES NOW + tier legend rendering REMOVED entirely.
        # The OLD Bot's Top Picks below (with PREMIUM, COILED, FRESH,
        # aligned 3/3, RS LEADER chips and a 📥 button) is now the SOLE
        # primary action board. Per user: "too many segments, I get lost".
        # Convergence picks are surfaced as a ⚡ chip on Bot's Top Picks
        # cards when they qualify (compute_convergence_picks set lookup).
        if False:  # disabled — Bot's Top Picks is now the only board
            st.info("No high-conviction picks right now. The system is "
                    "waiting for stronger signals. Check the **🔭 Browse "
                    "all sources** expander below for lower-tier setups, "
                    "or check back in a few minutes.")
        if False:  # rendering also disabled (was the else: branch)
            # Render each best pick with tier badge
            for _bp in _best_picks:
                _bp_side = _bp["side"]
                _bp_side_color = "#00d4ff" if _bp_side == "LONG" else "#ff3d57"
                _bp_side_emoji = "🟢" if _bp_side == "LONG" else "🩸"
                _bp_tier = _bp["tier"]
                _bp_tier_label = _bp["tier_label"]
                _bp_tier_gradient = _bp["tier_gradient"]
                _bp_tier_color = _bp["tier_color"]
                _bp_score = _bp["score"]
                _bp_entry = float(_bp.get("entry") or 0)
                _bp_stop = float(_bp.get("stop") or 0)
                _bp_tgt = float(_bp.get("target") or 0)
                _bp_tgt2 = float(_bp.get("target_2") or 0)
                _bp_rr = float(_bp.get("rr") or 0)
                _bp_cur = float(_bp.get("price") or _bp_entry)
                _bp_pct24h = _bp.get("pct_24h", 0)
                _bp_pct_color = ("#2ed47a" if _bp_pct24h > 0
                                 else "#ff5c5c" if _bp_pct24h < 0 else "#888")
                _bp_has_plan = bool(_bp.get("has_plan", False)) and (
                    _bp_entry > 0 and _bp_stop > 0 and _bp_tgt > 0)
                _bp_sid = f"bp_{_bp['symbol']}"

                # Position size — conviction-scaled
                _bp_target_notional = 1000.0 + (
                    (_bp_score - 65) / 30.0) * 1500.0
                _bp_target_notional = max(1000.0, min(2500.0, _bp_target_notional))
                _bp_bal = float(pb_state.get("balance") or 0)
                _bp_risk_pct = float(pb_state.get("risk_per_trade_pct") or 1.0)
                _bp_lev = float(pb_state.get("leverage") or 3.0)
                if _bp_has_plan and _bp_entry > 0:
                    _bp_riskd = _bp_bal * _bp_risk_pct / 100
                    _bp_stopdist = abs(_bp_stop - _bp_entry) or 1.0
                    _bp_qty_risk = _bp_riskd / _bp_stopdist
                    _bp_notional_risk = _bp_qty_risk * _bp_entry
                    _bp_notional = min(_bp_notional_risk,
                                       _bp_target_notional, 3000.0)
                    _bp_qty = (_bp_notional / _bp_entry
                               if _bp_entry > 0 else 0.0)
                    _bp_margin = (_bp_notional / _bp_lev
                                  if _bp_lev > 0 else _bp_notional)
                    _bp_loss = _bp_qty * abs(_bp_stop - _bp_entry)
                    _bp_profit = _bp_qty * abs(_bp_tgt - _bp_entry)
                    _bp_sf = _bp_notional / 3000.0
                else:
                    _bp_qty = _bp_notional = _bp_margin = 0.0
                    _bp_loss = _bp_profit = 0.0
                    _bp_sf = 0.4

                # Reasons line (for S-tier convergence picks)
                _bp_reasons_html = ""
                if _bp_tier == "S" and _bp.get("reasons"):
                    _bp_reasons_html = (
                        f"<div style='color:#c8d2ed;font-size:0.78rem;"
                        f"line-height:1.55;margin-top:8px;"
                        f"padding:6px 10px;background:rgba(255,215,0,0.06);"
                        f"border-radius:6px;border-left:2px solid #ffd700'>"
                        f"<b style='color:#ffd700'>Why this stacks:</b> "
                        f"{' · '.join(_bp['reasons'])}"
                        f"</div>")
                elif _bp_tier == "B" and _bp.get("conditions_met"):
                    _bp_reasons_html = (
                        f"<div style='color:#aab;font-size:0.78rem;"
                        f"margin-top:6px'>"
                        f"<b>{_bp['conditions_met']}/7</b> pre-conditions "
                        f"met · anticipatory entry (lower win rate, "
                        f"better entry)"
                        f"</div>")

                with st.container(border=True):
                    _bp_txt, _bp_btn = st.columns([6, 1])
                    _bp_txt.markdown(
                        # Tier badge + symbol + side
                        f"<div style='display:flex;align-items:center;"
                        f"gap:8px;flex-wrap:wrap'>"
                        f"<span style='font-size:1.15rem;font-weight:800;"
                        f"font-family:Space Grotesk,Inter,sans-serif'>"
                        f"{_bp['base']}</span>"
                        f"<span style='background:{_bp_side_color};"
                        f"color:#06121f;padding:3px 12px;border-radius:"
                        f"6px;font-size:0.76rem;font-weight:800'>"
                        f"{_bp_side_emoji} {_bp_side}</span>"
                        f"<span style='background:{_bp_tier_gradient};"
                        f"color:#001122;padding:3px 12px;border-radius:"
                        f"7px;font-size:0.78rem;font-weight:800;"
                        f"box-shadow:0 0 10px {_bp_tier_color}55'>"
                        f"{_bp_tier_label} · {_bp_score:.0f}</span>"
                        f"<span style='color:#8b8d98;font-size:0.78rem'>"
                        f"now ${_bp_cur:.4g} · "
                        f"<span style='color:{_bp_pct_color}'>"
                        f"{_bp_pct24h:+.2f}% 24h</span></span>"
                        f"</div>"
                        # Reasons (S-tier or B-tier)
                        + _bp_reasons_html
                        # Trade plan
                        + (
                            f"<div style='color:#aab;font-size:0.80rem;"
                            f"margin-top:8px;line-height:1.6'>"
                            f"entry <b>${_bp_entry:.4g}</b> · "
                            f"stop <b>${_bp_stop:.4g}</b> · "
                            f"TP1 <b>${_bp_tgt:.4g}</b> · "
                            + (f"TP2 <b>${_bp_tgt2:.4g}</b> · "
                               if _bp_tgt2 > 0 else "")
                            + f"R:R <b>{_bp_rr:.2f}</b></div>"
                            # Size preview
                            f"<div style='background:rgba(0,212,255,0.05);"
                            f"border:1px solid rgba(0,212,255,0.15);"
                            f"border-radius:8px;padding:8px 12px;"
                            f"margin-top:8px;color:#c8d2ed;"
                            f"font-size:0.78rem;line-height:1.6'>"
                            f"<b style='color:#00d4ff'>📥 If you click NOW:</b> "
                            f"<b>{_bp_qty:.4f}</b> {_bp['base']} "
                            f"{_bp_side.lower()} · notional "
                            f"<b>${_bp_notional:,.0f}</b> · "
                            f"<b>{_bp_lev:.0f}x</b> lev · "
                            f"margin <b>${_bp_margin:,.0f}</b> · "
                            f"risk <b style='color:#ff5c5c'>"
                            f"-${_bp_loss:,.2f}</b> · "
                            f"profit <b style='color:#2ed47a'>"
                            f"+${_bp_profit:,.2f}</b>"
                            f"</div>"
                            if _bp_has_plan else
                            f"<div style='color:#e0a92b;font-size:0.78rem;"
                            f"margin-top:8px'>⚠ Trade plan unavailable</div>"
                        ),
                        unsafe_allow_html=True)
                    # 📥 Open Trade — ONLY for S-tier (validated edge)
                    # A/B/C tiers backtested NEGATIVE after costs, no button
                    _bp_can_open = (
                        _bp_has_plan
                        and _bp_tier == "S"
                        and not _ds_circuit_tripped
                        and not _ds_concurrent_full
                    )
                    if not _bp_has_plan:
                        _bp_btn.markdown(
                            "<div style='color:#888;font-size:0.7rem;"
                            "text-align:center;padding:6px'>"
                            "No plan</div>",
                            unsafe_allow_html=True)
                    elif _bp_tier != "S":
                        # A/B/C tiers — WATCH ONLY, no button
                        _bp_btn.markdown(
                            "<div style='color:#e0a92b;font-size:0.65rem;"
                            "text-align:center;padding:6px;background:"
                            "rgba(224,169,43,0.08);border-radius:6px;"
                            "border:1px solid rgba(224,169,43,0.2)'>"
                            "👁<br>WATCH<br>ONLY</div>",
                            unsafe_allow_html=True)
                    elif _ds_circuit_tripped:
                        _bp_btn.markdown(
                            "<div style='color:#ff5c5c;font-size:0.65rem;"
                            "text-align:center;padding:6px'>"
                            "🛑<br>HALTED</div>",
                            unsafe_allow_html=True)
                    elif _ds_concurrent_full:
                        _bp_btn.markdown(
                            "<div style='color:#e0a92b;font-size:0.65rem;"
                            "text-align:center;padding:6px'>"
                            "⚠<br>3/3<br>OPEN</div>",
                            unsafe_allow_html=True)
                    elif _bp_can_open:
                        if _bp_btn.button(
                                "📥", key=f"pb_{_bp_sid}",
                                help=(f"Open {_bp_side} {_bp['base']} · "
                                      f"{_bp_tier_label} · score {_bp_score:.0f}"),
                                use_container_width=True):
                            _bp_setup = {
                                "symbol": _bp["symbol"],
                                "base": _bp["base"],
                                "side": _bp_side,
                                "entry": _bp_entry,
                                "entry_low": _bp_entry,
                                "entry_high": _bp_entry,
                                "stop": _bp_stop,
                                "target": _bp_tgt,
                                "target_2": _bp_tgt2 if _bp_tgt2 > 0 else None,
                                "rr": _bp_rr,
                                "confidence": int(min(99, _bp_score)),
                                "strength_factor": _bp_sf,
                            }
                            _bp_opened = paper_bot.open_position(
                                pb_state, _bp_setup,
                                prices.get(_bp["symbol"]) or _bp_entry)
                            if _bp_opened:
                                _enrich_position(
                                    _bp_opened, int(min(99, _bp_score)),
                                    timeframe)
                                paper_bot.save_state(PAPER_BOT_FILE, pb_state)
                                st.toast(
                                    f"🏆 Opened {_bp_side} "
                                    f"{_bp_opened['base']} @ "
                                    f"{fmt_price(_bp_opened['entry'])} · "
                                    f"{_bp_tier_label} {_bp_score:.0f}",
                                    icon="🏆")
                                st.rerun()
                            else:
                                st.warning(
                                    f"Could not open {_bp['base']} — "
                                    "check balance/concurrency/already-open.")

        # Tier legend + divider also disabled (was for the killed
        # BEST TRADES NOW board). Bot's Top Picks below has its own
        # self-explanatory chips so no legend needed.
        if False:
            st.markdown(
                "<div style='color:#aab;font-size:0.74rem;margin-top:10px;"
                "padding:8px 12px;background:rgba(255,255,255,0.02);"
                "border-radius:6px'>"
                "<b>Tier legend:</b> "
                "<span style='color:#ffd700'>⚡ CONVERGENCE</span> "
                "<span style='color:#00d4ff'>🎯 STRONG PATTERN</span> "
                "<span style='color:#ff9500'>🔭 SETUP FORMING</span> "
                "<span style='color:#5b8eff'>🎯 WATCH</span>"
                "</div>",
                unsafe_allow_html=True)

        # ====================================================================
        # ⚡ CONVERGENCE — collapsed by default. Convergence-qualified picks
        # also surface as a ⚡ chip on Bot's Top Picks cards below.
        # ====================================================================
        # The crown of the system. Surfaces picks where MULTIPLE independent
        # signals AGREE on the same coin + same direction:
        #   1. Pattern Scout confirmed pattern (validated 60-75% backtest edge)
        #   2. Setups Forming pre-conditions had warned of this setup
        #   3. Market Regime favors the side
        #   4. 4h trend supports the direction (not just 1h noise)
        #   5. BTC correlation doesn't fight the signal
        # Score threshold: 88 (very strict). Expected 0-3 fires per day.
        # The rarity is the edge — when ALL signals agree, conviction is real.
        try:
            _convergence_picks = compute_convergence_picks(timeframe, scan_n=50)
        except Exception:
            _convergence_picks = []
        # Build symbol set so Bot's Top Picks below can render a ⚡ chip
        _convergence_syms = {p.get("symbol") for p in (_convergence_picks or [])}
        # Standalone CONVERGENCE rendering DISABLED — convergence picks
        # still surface via their high combined_score in Bot's Top Picks
        # and get a ⚡ CONVERGENCE chip there. Per user: no more duplicate
        # segments. Set to True to restore the standalone section.
        if False and _convergence_picks:
            st.markdown(
                "<div style='display:flex;align-items:center;gap:12px;"
                "margin-top:18px;margin-bottom:10px'>"
                "<span style='font-size:1.5rem;font-weight:900;"
                "background:linear-gradient(135deg,#ffd700,#ff006e,#8b5cf6);"
                "-webkit-background-clip:text;-webkit-text-fill-color:"
                "transparent;background-clip:text;letter-spacing:-0.02em'>"
                "⚡ CONVERGENCE</span>"
                "<span style='color:#aab;font-size:0.84rem'>"
                f"signals stacking · {len(_convergence_picks)} firing now</span>"
                "</div>",
                unsafe_allow_html=True)
            st.caption(
                "**Highest-conviction picks across the entire signal stack.** "
                "ALL of these conditions hold: ✅ Pattern Scout pattern fired, "
                "✅ Setups Forming pre-warned, ✅ Market Regime aligned, "
                "✅ 4h trend supports, ✅ BTC correlation favorable. "
                "**Expected 0-3 per day.** Empty = nothing this strong. "
                "Full = rare alignment of all validated edges — these are "
                "the bets the system has the highest conviction in.")
            for _cv in _convergence_picks[:5]:
                _cv_side = _cv.get("side", "LONG")
                _cv_color = "#00d4ff" if _cv_side == "LONG" else "#ff3d57"
                _cv_emoji = "🟢" if _cv_side == "LONG" else "🩸"
                _cv_entry = float(_cv.get("entry") or 0)
                _cv_stop = float(_cv.get("stop") or 0)
                _cv_tgt = float(_cv.get("target") or 0)
                _cv_tgt2 = float(_cv.get("target_2") or 0)
                _cv_rr = float(_cv.get("rr") or 0)
                _cv_cur = float(_cv.get("price") or _cv_entry)
                _cv_pct24h = _cv.get("pct_24h", 0)
                _cv_pct_color = ("#2ed47a" if _cv_pct24h > 0
                                 else "#ff5c5c" if _cv_pct24h < 0
                                 else "#888")
                _cv_sid = f"cv_{_cv['symbol']}"
                # Position size — use Pattern Scout's $1k-$2.5k range
                _cv_score = _cv["convergence_score"]
                _cv_target_notional = 1000.0 + (
                    (_cv_score - 65) / 30.0) * 1500.0
                _cv_target_notional = max(1000.0, min(2500.0, _cv_target_notional))
                _cv_bal = float(pb_state.get("balance") or 0)
                _cv_risk_pct = float(pb_state.get("risk_per_trade_pct") or 1.0)
                _cv_lev = float(pb_state.get("leverage") or 3.0)
                _cv_riskd = _cv_bal * _cv_risk_pct / 100
                _cv_stopdist = abs(_cv_stop - _cv_entry) or 1.0
                _cv_qty_risk = _cv_riskd / _cv_stopdist
                _cv_notional_risk = _cv_qty_risk * _cv_entry
                _cv_notional = min(_cv_notional_risk, _cv_target_notional, 3000.0)
                _cv_qty = (_cv_notional / _cv_entry if _cv_entry > 0 else 0.0)
                _cv_margin = (_cv_notional / _cv_lev if _cv_lev > 0
                              else _cv_notional)
                _cv_loss = _cv_qty * abs(_cv_stop - _cv_entry)
                _cv_profit = _cv_qty * abs(_cv_tgt - _cv_entry)
                _cv_sf = _cv_notional / 3000.0
                with st.container(border=True):
                    _cv_txt_col, _cv_btn_col = st.columns([6, 1])
                    _cv_txt_col.markdown(
                        # Premium gradient header
                        f"<div style='background:linear-gradient(135deg,"
                        f"rgba(255,215,0,0.10),rgba(255,0,110,0.06),"
                        f"rgba(139,92,246,0.08));padding:10px 14px;"
                        f"border-radius:10px;border:1px solid "
                        f"rgba(255,215,0,0.25);'>"
                        f"<div style='display:flex;align-items:center;"
                        f"gap:10px;flex-wrap:wrap;margin-bottom:8px'>"
                        f"<span style='font-size:1.3rem;font-weight:800'>⚡</span>"
                        f"<span style='font-size:1.15rem;font-weight:800;"
                        f"font-family:Space Grotesk,Inter,sans-serif'>"
                        f"{_cv['base']}</span>"
                        f"<span style='background:{_cv_color};color:#06121f;"
                        f"padding:3px 12px;border-radius:6px;font-size:"
                        f"0.78rem;font-weight:800'>{_cv_emoji} {_cv_side}</span>"
                        f"<span style='background:linear-gradient(90deg,"
                        f"#ffd700,#ff006e);color:#001122;padding:3px 14px;"
                        f"border-radius:7px;font-size:0.82rem;font-weight:"
                        f"800;box-shadow:0 0 12px rgba(255,215,0,0.5)'>"
                        f"⚡ CONVERGENCE · {_cv_score:.0f}</span>"
                        f"<span style='color:#aab;font-size:0.82rem'>"
                        f"now ${_cv_cur:.4g} · "
                        f"<span style='color:{_cv_pct_color}'>"
                        f"{_cv_pct24h:+.2f}% 24h</span></span>"
                        f"</div>"
                        # Why this is convergence (the reasons)
                        f"<div style='color:#c8d2ed;font-size:0.82rem;"
                        f"line-height:1.55;margin-bottom:10px'>"
                        f"<b style='color:#ffd700'>Why this is CONVERGENCE:</b><br>"
                        f"{' · '.join(_cv.get('convergence_reasons', []))}"
                        f"</div>"
                        # Trade plan
                        f"<div style='color:#aab;font-size:0.80rem;"
                        f"line-height:1.6;margin-top:8px'>"
                        f"entry <b>${_cv_entry:.4g}</b> · "
                        f"stop <b>${_cv_stop:.4g}</b> · "
                        f"TP1 <b>${_cv_tgt:.4g}</b> · "
                        + (f"TP2 <b>${_cv_tgt2:.4g}</b> · "
                           if _cv_tgt2 > 0 else "")
                        + f"plan R:R <b>{_cv_rr:.2f}</b></div>"
                        # Size preview
                        f"<div style='background:rgba(255,215,0,0.05);"
                        f"border:1px solid rgba(255,215,0,0.15);"
                        f"border-radius:8px;padding:8px 12px;margin-top:8px;"
                        f"color:#c8d2ed;font-size:0.78rem;line-height:1.6'>"
                        f"<b style='color:#ffd700'>📥 If you click NOW:</b> "
                        f"<b>{_cv_qty:.4f}</b> {_cv['base']} "
                        f"{_cv_side.lower()} · notional "
                        f"<b>${_cv_notional:,.0f}</b> · "
                        f"<b>{_cv_lev:.0f}x</b> lev · "
                        f"margin <b>${_cv_margin:,.0f}</b> · "
                        f"risk <b style='color:#ff5c5c'>"
                        f"-${_cv_loss:,.2f}</b> · "
                        f"profit at TP <b style='color:#2ed47a'>"
                        f"+${_cv_profit:,.2f}</b>"
                        f"</div>"
                        f"</div>",
                        unsafe_allow_html=True)
                    # 📥 Open trade
                    if _cv_btn_col.button(
                            "📥", key=f"pb_{_cv_sid}",
                            help=f"Open {_cv_side} {_cv['base']} — CONVERGENCE pick",
                            use_container_width=True):
                        _cv_setup = {
                            "symbol": _cv["symbol"],
                            "base": _cv["base"],
                            "side": _cv_side,
                            "entry": _cv_entry,
                            "entry_low": _cv_entry,
                            "entry_high": _cv_entry,
                            "stop": _cv_stop,
                            "target": _cv_tgt,
                            "target_2": _cv_tgt2 if _cv_tgt2 > 0 else None,
                            "rr": _cv_rr,
                            "confidence": int(min(99, _cv_score)),
                            "strength_factor": _cv_sf,
                        }
                        _cv_opened = paper_bot.open_position(
                            pb_state, _cv_setup,
                            prices.get(_cv["symbol"]) or _cv_entry)
                        if _cv_opened:
                            _enrich_position(_cv_opened,
                                             int(min(99, _cv_score)),
                                             timeframe)
                            paper_bot.save_state(PAPER_BOT_FILE, pb_state)
                            st.toast(
                                f"⚡ Opened {_cv_side} "
                                f"{_cv_opened['base']} @ "
                                f"{fmt_price(_cv_opened['entry'])} · "
                                f"CONVERGENCE {_cv_score:.0f}",
                                icon="⚡")
                            st.rerun()
                        else:
                            st.warning(
                                f"Could not open {_cv['base']} — "
                                "check balance/concurrency/already-open.")
            st.markdown(
                "<div style='height:1px;background:linear-gradient(90deg,"
                "transparent,rgba(255,215,0,0.3),transparent);"
                "margin:20px 0'></div>",
                unsafe_allow_html=True)

        # ---- 🔭 SETUPS FORMING — leading-indicator watchlist ----------
        # Predicts reversal candles (shooting stars / hammers) BEFORE
        # they print by detecting pre-conditions:
        #   1. Approach to resistance/support
        #   2. RSI extreme + trending toward it
        #   3. Volume waning on dominant-color bars
        #   4. Body shrinkage (consecutive smaller bodies)
        #   5. Extension from EMA20 (>1.5 ATR)
        #   6. Bearish/bullish CVD divergence
        #   7. Intra-bar rejection forming
        # When 3+ conditions met → WATCH. 5+ → STRONG WATCH (reversal
        # likely within 1-5 bars).
        # HONEST CAVEAT: leading signals are less reliable than
        # confirmed candles (~40-55% vs ~60-65%). Use as a WATCHLIST.
        # Setups Forming expander REMOVED per user (too many segments).
        if False:
            st.caption(
                "Coins where REVERSAL pre-conditions are forming. "
                "By the time a shooting star or hammer prints, the "
                "rejection already happened. This scan finds coins "
                "approaching those setups — gives you a 1-5 bar "
                "head start. **Watchlist, not a trade signal.** When "
                "the actual fire candle prints (caught by Pattern "
                "Scout below), THAT's the trade.")
            try:
                _approach_results = run_reversal_approach_scan(
                    timeframe, scan_n=30)
            except Exception:
                _approach_results = []
            _approach_top = sorted(_approach_results,
                                   key=lambda r: r["score"],
                                   reverse=True)[:6]
            if not _approach_top:
                st.info("No coins currently show 3+ pre-conditions for a "
                        "reversal setup. Check back as conditions develop.")
            else:
                st.markdown(
                    f"**{len(_approach_results)} coins showing setup "
                    f"formation · top 6 below:**")
                for _ar in _approach_top:
                    _ar_side = _ar["side"]
                    _ar_side_color = ("#ff3d57" if _ar_side == "SHORT"
                                      else "#00e676")
                    _ar_side_emoji = "🩸" if _ar_side == "SHORT" else "🟢"
                    _ar_tier = ("STRONG WATCH" if _ar["score"] >= 80
                                else "WATCH")
                    _ar_tier_color = ("#ff9500" if _ar["score"] >= 80
                                      else "#5b8eff")
                    _ar_score = _ar["score"]
                    # Trade plan from the new openable scan
                    _ar_has_plan = bool(_ar.get("has_plan", False))
                    _ar_entry = float(_ar.get("entry") or 0)
                    _ar_stop = float(_ar.get("stop") or 0)
                    _ar_tgt = float(_ar.get("target") or 0)
                    _ar_tgt2 = float(_ar.get("target_2") or 0)
                    _ar_rr = float(_ar.get("rr") or 0)
                    _ar_cur = float(_ar.get("price") or 0)
                    _ar_sid = f"ar_{_ar['symbol']}"
                    # Position size — conviction-scaled $1k-$2.5k
                    _ar_target_notional = 1000.0 + (
                        (_ar_score - 65) / 30.0) * 1500.0
                    _ar_target_notional = max(
                        1000.0, min(2500.0, _ar_target_notional))
                    _ar_bal = float(pb_state.get("balance") or 0)
                    _ar_risk_pct = float(
                        pb_state.get("risk_per_trade_pct") or 1.0)
                    _ar_lev = float(pb_state.get("leverage") or 3.0)
                    if _ar_has_plan and _ar_entry > 0 and _ar_stop > 0:
                        _ar_riskd = _ar_bal * _ar_risk_pct / 100
                        _ar_stopdist = abs(_ar_stop - _ar_entry) or 1.0
                        _ar_qty_risk = _ar_riskd / _ar_stopdist
                        _ar_notional_risk = _ar_qty_risk * _ar_entry
                        _ar_notional = min(_ar_notional_risk,
                                           _ar_target_notional, 3000.0)
                        _ar_qty = (_ar_notional / _ar_entry
                                   if _ar_entry > 0 else 0.0)
                        _ar_margin = (_ar_notional / _ar_lev
                                      if _ar_lev > 0 else _ar_notional)
                        _ar_loss = _ar_qty * abs(_ar_stop - _ar_entry)
                        _ar_profit = _ar_qty * abs(_ar_tgt - _ar_entry)
                        _ar_sf = _ar_notional / 3000.0
                    else:
                        _ar_qty = _ar_notional = _ar_margin = 0.0
                        _ar_loss = _ar_profit = 0.0
                        _ar_sf = 0.4
                    # Build condition chips for the ones that hit
                    _cond_chips = ""
                    _condition_labels = {
                        "approach": "📏 Approaching level",
                        "rsi": "📊 RSI extreme",
                        "vol_waning": "📉 Volume waning",
                        "body_shrink": "🎢 Body shrinking",
                        "extension": "🎯 EMA stretched",
                        "cvd_div": "💱 CVD diverging",
                        "intra_bar": "⚡ Live rejection",
                    }
                    for _ck, _cv_comp in _ar["components"].items():
                        if _cv_comp.get("hit"):
                            _label = _condition_labels.get(_ck, _ck)
                            _cond_chips += (
                                f"<span style='background:rgba("
                                f"{_ar_side_color[1:3]},{_ar_side_color[3:5]},"
                                f"{_ar_side_color[5:7]},0.10);"
                                f"color:{_ar_side_color};padding:2px 8px;"
                                f"border-radius:5px;font-size:0.7rem;"
                                f"font-weight:700;margin-left:4px'>"
                                f"{_label}</span>")
                    with st.container(border=True):
                        _ar_txt, _ar_btn = st.columns([6, 1])
                        _ar_txt.markdown(
                            # Header
                            f"<div style='display:flex;align-items:center;"
                            f"gap:8px;flex-wrap:wrap'>"
                            f"<span style='font-weight:800;font-size:1.05rem'>"
                            f"{_ar['base']}</span>"
                            f"<span style='background:{_ar_side_color};"
                            f"color:#06121f;padding:2px 10px;"
                            f"border-radius:5px;font-size:0.72rem;"
                            f"font-weight:800'>{_ar_side_emoji} "
                            f"{_ar_side} forming</span>"
                            f"<span style='background:{_ar_tier_color}33;"
                            f"color:{_ar_tier_color};padding:2px 8px;"
                            f"border-radius:5px;font-size:0.72rem;"
                            f"font-weight:700'>🔭 {_ar_tier} · "
                            f"{_ar_score:.0f}</span>"
                            f"<span style='color:#8b8d98;font-size:0.78rem'>"
                            f"now ${_ar['price']:.4g} · "
                            f"{_ar['conditions_met']}/7 conditions</span>"
                            f"</div>"
                            # Condition chips
                            f"<div style='margin-top:8px'>{_cond_chips}</div>"
                            # Trade plan + size preview (if available)
                            + (
                                f"<div style='color:#aab;font-size:0.80rem;"
                                f"margin-top:10px;line-height:1.6'>"
                                f"<b>Anticipatory entry:</b> "
                                f"entry <b>${_ar_entry:.4g}</b> · "
                                f"stop <b>${_ar_stop:.4g}</b> · "
                                f"TP1 <b>${_ar_tgt:.4g}</b> · "
                                + (f"TP2 <b>${_ar_tgt2:.4g}</b> · "
                                   if _ar_tgt2 > 0 else "")
                                + f"R:R <b>{_ar_rr:.2f}</b>"
                                + f"</div>"
                                f"<div style='background:rgba(91,142,255,0.05);"
                                f"border:1px solid rgba(91,142,255,0.15);"
                                f"border-radius:8px;padding:8px 12px;"
                                f"margin-top:8px;color:#c8d2ed;"
                                f"font-size:0.78rem;line-height:1.6'>"
                                f"<b style='color:#5b8eff'>📥 If you click NOW:</b> "
                                f"<b>{_ar_qty:.4f}</b> {_ar['base']} "
                                f"{_ar_side.lower()} · "
                                f"notional <b>${_ar_notional:,.0f}</b> · "
                                f"<b>{_ar_lev:.0f}x</b> lev · "
                                f"margin <b>${_ar_margin:,.0f}</b> · "
                                f"risk <b style='color:#ff5c5c'>"
                                f"-${_ar_loss:,.2f}</b> · "
                                f"profit <b style='color:#2ed47a'>"
                                f"+${_ar_profit:,.2f}</b>"
                                f"</div>"
                                if _ar_has_plan else
                                f"<div style='color:#e0a92b;font-size:0.78rem;"
                                f"margin-top:8px'>⚠ No trade plan generated</div>"
                            ),
                            unsafe_allow_html=True)
                        # 📥 Open button — anticipatory entry (lower
                        # probability than confirmed signal, hence the
                        # WATCH tier instead of STRONG)
                        if _ar_has_plan:
                            if _ar_btn.button(
                                    "📥", key=f"pb_{_ar_sid}",
                                    help=(f"Open {_ar_side} {_ar['base']} "
                                          f"ANTICIPATORY — Setups Forming "
                                          f"pick (leading signal, ~40-55% "
                                          f"win expected vs ~60% for "
                                          f"confirmed)"),
                                    use_container_width=True):
                                _ar_setup = {
                                    "symbol": _ar["symbol"],
                                    "base": _ar["base"],
                                    "side": _ar_side,
                                    "entry": _ar_entry,
                                    "entry_low": _ar_entry,
                                    "entry_high": _ar_entry,
                                    "stop": _ar_stop,
                                    "target": _ar_tgt,
                                    "target_2": _ar_tgt2 if _ar_tgt2 > 0 else None,
                                    "rr": _ar_rr,
                                    "confidence": int(min(99, _ar_score)),
                                    "strength_factor": _ar_sf,
                                }
                                _ar_opened = paper_bot.open_position(
                                    pb_state, _ar_setup,
                                    prices.get(_ar["symbol"]) or _ar_entry)
                                if _ar_opened:
                                    _enrich_position(
                                        _ar_opened, int(min(99, _ar_score)),
                                        timeframe)
                                    paper_bot.save_state(PAPER_BOT_FILE,
                                                         pb_state)
                                    st.toast(
                                        f"🔭 Opened {_ar_side} "
                                        f"{_ar_opened['base']} @ "
                                        f"{fmt_price(_ar_opened['entry'])} · "
                                        f"Setups Forming",
                                        icon="🔭")
                                    st.rerun()
                                else:
                                    st.warning(
                                        f"Could not open {_ar['base']} — "
                                        "check balance/concurrency/already-open.")

        # ---- 🎯 PATTERN SCOUT — scans 50 coins for validated patterns -
        # Independent of the alerts.build_alerts() CONF_ALERT=72 gate.
        # Surfaces coins where high-edge individual patterns fire but
        # may not have multi-TF aggregated confidence to make the
        # standard picks board. Cached 10 min so the scan only runs
        # rarely. User explicitly asked for this — "you should read
        # through all 150+ Binance coins their patterns etc to indicate
        # me the best outcomes and top picks accordingly".
        # Pattern Scout expander REMOVED per user (too many segments).
        # Pattern Scout picks still surface inline in Bot's Top Picks via
        # combined_score + the validated CONVERGENCE/SURE SHOT chips.
        if False:
            st.caption(
                "Scans the top 50 coins for these **backtested-edge** "
                "patterns INDEPENDENT of the regular picks gate: "
                "🔄 V-bottom recovery (75% win @ 12bar), 🟢 long_patterns "
                "aligned (67.4% win @ 48bar), 🌅 morning star + RSI<35 + "
                "downtrend (60-75%), 🔨 hammer at confirmed support "
                "(60-65%). 24h freshness filter active — coins already "
                "+8% in 24h are downgraded so picks board surfaces EARLY "
                "setups, not chases. Cached 10 minutes.")
            _scout = run_pattern_scout(timeframe, scan_n=50)
            _scout_top = sorted(_scout, key=lambda r: r["score"],
                                reverse=True)[:6]
            if not _scout_top:
                st.info("No coins scored ≥65 in the last scan. Either "
                        "the regime is genuinely quiet OR a fresh scan "
                        "is loading — wait 30-60 sec and refresh.")
            else:
                st.markdown(
                    f"**Found {len(_scout)} qualifying setups · top 6 below:**")
                for _sc in _scout_top:
                    _score = _sc["score"]
                    _color = ("#2ed47a" if _score >= 80
                              else "#00d4ff" if _score >= 75
                              else "#e0a92b")
                    _tier = ("STRONG" if _score >= 80
                             else "ALIGNED" if _score >= 75
                             else "WATCH")
                    # === Distinct badge per signal type ===
                    # Each pattern gets its own visual identity so the user
                    # can read the card at a glance and know WHICH pattern
                    # fired. Each badge: emoji + short name + score +
                    # backtested win rate, with a gradient unique to the
                    # signal type. SHORT-side patterns use red/orange palettes.
                    _badge_styles = {
                        "v_bottom_recovery": {
                            "emoji": "🔄", "label": "V-BOTTOM",
                            "win": "75%/12bar",
                            "gradient": "linear-gradient(135deg,#00d4ff,#ffd700)",
                            "text_color": "#001122",
                            "glow": "rgba(0,212,255,0.4)",
                        },
                        "long_patterns_aligned": {
                            "emoji": "🟢", "label": "LONG PATTERNS",
                            "win": "67%/48bar",
                            "gradient": "linear-gradient(135deg,#0b8a3e,#34c759)",
                            "text_color": "#06121f",
                            "glow": "rgba(52,199,89,0.35)",
                        },
                        "morning_star": {
                            "emoji": "🌅", "label": "MORNING STAR",
                            "win": "60-75% w/ filters",
                            "gradient": "linear-gradient(135deg,#ff9500,#ffcc66)",
                            "text_color": "#1a0f00",
                            "glow": "rgba(255,149,0,0.35)",
                        },
                        "hammer_at_support": {
                            "emoji": "🔨", "label": "HAMMER",
                            "win": "60-65% at support",
                            "gradient": "linear-gradient(135deg,#5b8eff,#8b5cf6)",
                            "text_color": "#fff",
                            "glow": "rgba(91,142,255,0.35)",
                        },
                        # SHORT-side patterns
                        "evening_star": {
                            "emoji": "🌃", "label": "EVENING STAR",
                            "win": "mirror of morning",
                            "gradient": "linear-gradient(135deg,#d62845,#ff6b6b)",
                            "text_color": "#fff",
                            "glow": "rgba(255,107,107,0.35)",
                        },
                        "shooting_star_at_resistance": {
                            "emoji": "💫", "label": "SHOOTING STAR",
                            "win": "at resistance",
                            "gradient": "linear-gradient(135deg,#8b00ff,#ff006e)",
                            "text_color": "#fff",
                            "glow": "rgba(255,0,110,0.35)",
                        },
                        "bearish_rsi_divergence": {
                            "emoji": "📉", "label": "BEARISH RSI DIV",
                            "win": "textbook reversal",
                            "gradient": "linear-gradient(135deg,#c93030,#e0a92b)",
                            "text_color": "#fff",
                            "glow": "rgba(201,48,48,0.35)",
                        },
                    }
                    _signal_chips = ""
                    for _sig in _sc["signals"][:3]:
                        _sn = _sig["name"]
                        _style = _badge_styles.get(_sn, {
                            "emoji": "📊", "label": _sn.upper(),
                            "win": "n/a",
                            "gradient": "rgba(0,212,255,0.10)",
                            "text_color": "#00d4ff",
                            "glow": "rgba(0,212,255,0.2)",
                        })
                        _signal_chips += (
                            f"<span title='Backtested edge: {_style['win']}' "
                            f"style='background:{_style['gradient']};"
                            f"color:{_style['text_color']};padding:4px 12px;"
                            f"border-radius:7px;font-size:0.72rem;"
                            f"font-weight:800;margin-left:6px;"
                            f"box-shadow:0 0 8px {_style['glow']};"
                            f"display:inline-block;letter-spacing:0.02em'>"
                            f"{_style['emoji']} {_style['label']} "
                            f"<span style='opacity:0.7'>· {_sig['score']:.0f}</span>"
                            f"</span>")
                    _pct_24h = _sc.get("pct_24h", 0)
                    _pct_color = ("#2ed47a" if _pct_24h > 0
                                  else "#ff5c5c" if _pct_24h < 0 else "#888")
                    _ps_sid = f"ps_{_sc['symbol']}"
                    _ps_side_str = _sc.get("side", "LONG")  # NEW: side-aware
                    # Pull trade plan (entry/stop/TP) if available
                    _ps_entry = float(_sc.get("entry_low")
                                      or _sc.get("entry") or 0)
                    _ps_stop = float(_sc.get("stop") or 0)
                    _ps_tgt = float(_sc.get("target") or 0)
                    _ps_tgt2 = float(_sc.get("target_2") or 0)
                    _ps_rr = float(_sc.get("rr") or 0)
                    _ps_rr2 = float(_sc.get("rr_2") or 0)
                    _ps_has_plan = (_ps_entry > 0 and _ps_stop > 0
                                    and _ps_tgt > 0)
                    _ps_cur = _sc["price"]
                    # Live R:R from current price — side-aware
                    if _ps_side_str == "LONG":
                        _ps_live_risk = ((_ps_cur - _ps_stop) / _ps_cur * 100
                                         if _ps_cur > 0 and _ps_stop > 0
                                         else 0.0)
                        _ps_live_reward = ((_ps_tgt - _ps_cur) / _ps_cur * 100
                                           if _ps_cur > 0 and _ps_tgt > 0
                                           else 0.0)
                    else:  # SHORT
                        _ps_live_risk = ((_ps_stop - _ps_cur) / _ps_cur * 100
                                         if _ps_cur > 0 and _ps_stop > 0
                                         else 0.0)
                        _ps_live_reward = ((_ps_cur - _ps_tgt) / _ps_cur * 100
                                           if _ps_cur > 0 and _ps_tgt > 0
                                           else 0.0)
                    _ps_live_rr = (_ps_live_reward / _ps_live_risk
                                   if _ps_live_risk > 0 else 0.0)
                    # === CONVICTION-SCALED NOTIONAL SIZING ===
                    # User-set targets: $1000-$2500 typical, $3000 hard cap.
                    # Position size scales LINEARLY with conviction score:
                    #   Score 65 (floor)  → target $1,000 notional
                    #   Score 80 (mid)    → target $1,750 notional
                    #   Score 95 (top)    → target $2,500 notional
                    #   Hard ceiling      → $3,000 (no matter what)
                    # Risk-based qty still calculated but USED ONLY if it's
                    # LOWER than the target (e.g. very wide stop). This way
                    # actual $ risk is always ≤ risk_per_trade_pct budget.
                    _ps_bal = float(pb_state.get("balance") or 0)
                    _ps_risk_pct = float(
                        pb_state.get("risk_per_trade_pct") or 1.0)
                    _ps_lev = float(pb_state.get("leverage") or 3.0)
                    if _ps_has_plan and _ps_entry > 0:
                        # 1. Risk-based notional ceiling (don't exceed risk budget)
                        _ps_riskd = _ps_bal * _ps_risk_pct / 100
                        _ps_stopdist = abs(_ps_stop - _ps_entry) or 1.0
                        _ps_qty_riskbased = _ps_riskd / _ps_stopdist
                        _ps_notional_riskbased = _ps_qty_riskbased * _ps_entry
                        # 2. Conviction-scaled target ($1000-$2500)
                        _ps_target_notional = 1000.0 + (
                            (_score - 65) / 30.0) * 1500.0
                        _ps_target_notional = max(
                            1000.0, min(2500.0, _ps_target_notional))
                        # 3. Hard cap $3000
                        _ps_hard_cap = 3000.0
                        # 4. Final: LOWER of (risk-based, target, hard cap)
                        _ps_notional = min(
                            _ps_notional_riskbased,
                            _ps_target_notional,
                            _ps_hard_cap)
                        _ps_qty = (_ps_notional / _ps_entry
                                   if _ps_entry > 0 else 0.0)
                        _ps_margin = (_ps_notional / _ps_lev
                                      if _ps_lev > 0 else _ps_notional)
                        _ps_loss = _ps_qty * abs(_ps_stop - _ps_entry)
                        _ps_profit = _ps_qty * abs(_ps_tgt - _ps_entry)
                        # strength_factor for the open-position call (kept
                        # as ratio of notional to hard cap for compatibility)
                        _ps_sf = _ps_notional / _ps_hard_cap
                    else:
                        _ps_qty = _ps_notional = _ps_margin = 0.0
                        _ps_loss = _ps_profit = 0.0
                        _ps_sf = 0.4

                    with st.container(border=True):
                        _ps_text_col, _ps_btn_col = st.columns([6, 1])
                        _ps_text_col.markdown(
                            # Header
                            f"<div style='display:flex;align-items:center;"
                            f"gap:8px;flex-wrap:wrap'>"
                            f"<span style='font-weight:800;font-size:1.05rem'>"
                            f"{_sc['base']}</span>"
                            f"<span style='background:{_color};color:#06121f;"
                            f"padding:2px 10px;border-radius:5px;font-size:"
                            f"0.72rem;font-weight:800'>"
                            f"🎯 {_tier} · {_score:.0f}</span>"
                            f"{_signal_chips}"
                            f"<span style='color:#8b8d98;font-size:0.78rem'>"
                            f"now ${_ps_cur:.4g} · "
                            f"<span style='color:{_pct_color}'>"
                            f"{_pct_24h:+.2f}% 24h</span></span>"
                            f"</div>"
                            # Trade plan row (only if we have one)
                            + (
                                f"<div style='color:#aab;font-size:0.80rem;"
                                f"margin-top:8px;line-height:1.6'>"
                                f"entry <b>${_ps_entry:.4g}</b> · "
                                f"stop <b>${_ps_stop:.4g}</b> "
                                f"<span style='color:#ff5c5c'>"
                                f"(-{abs(_ps_stop - _ps_entry) / _ps_entry * 100:.1f}%)</span> · "
                                f"TP1 <b>${_ps_tgt:.4g}</b> "
                                f"<span style='color:#2ed47a'>"
                                f"(+{abs(_ps_tgt - _ps_entry) / _ps_entry * 100:.1f}%)</span>"
                                + (f" · TP2 <b>${_ps_tgt2:.4g}</b> "
                                   f"<span style='color:#e0a92b'>"
                                   f"(+{abs(_ps_tgt2 - _ps_entry) / _ps_entry * 100:.1f}%)</span>"
                                   if _ps_tgt2 > 0 else "")
                                + f" · plan R:R <b>{_ps_rr:.2f}</b>"
                                + (f" · live R:R <b>{_ps_live_rr:.2f}</b>"
                                   if _ps_live_rr > 0 else "")
                                + f"</div>"
                                # Position-size preview box
                                f"<div style='background:rgba(0,212,255,0.05);"
                                f"border:1px solid rgba(0,212,255,0.15);"
                                f"border-radius:8px;padding:8px 12px;"
                                f"margin-top:8px;color:#c8d2ed;"
                                f"font-size:0.78rem;line-height:1.6'>"
                                f"<b style='color:#00d4ff'>📥 If you click NOW:</b> "
                                f"<b>{_ps_qty:.4f}</b> {_sc['base']} "
                                f"{_ps_side_str.lower()} · "
                                f"notional <b>${_ps_notional:,.0f}</b> · "
                                f"<b>{_ps_lev:.0f}x</b> lev · "
                                f"margin <b>${_ps_margin:,.0f}</b> · "
                                f"risk <b style='color:#ff5c5c'>"
                                f"-${_ps_loss:,.2f}</b> · "
                                f"profit at TP <b style='color:#2ed47a'>"
                                f"+${_ps_profit:,.2f}</b> · "
                                f"strength factor <b>{_ps_sf:.2f}</b>"
                                f"</div>"
                                if _ps_has_plan else
                                f"<div style='color:#e0a92b;font-size:0.78rem;"
                                f"margin-top:8px'>"
                                f"⚠ Trade plan unavailable for this coin "
                                f"(scanner couldn't generate one) — open "
                                f"manually via Open a trade form on left."
                                f"</div>"
                            )
                            + (
                                f"<div style='color:#aab;font-size:0.76rem;"
                                f"margin-top:6px'>"
                                f"<b>Best signal:</b> {_sc['best_signal']} · "
                                f"{_sc['signals'][0]['detail'][:100]}"
                                f"</div>"
                            ),
                            unsafe_allow_html=True)
                        # 📥 Open Trade button
                        if _ps_has_plan:
                            if _ps_btn_col.button(
                                    "📥", key=f"pb_ps_{_ps_sid}",
                                    help=(f"Open {_ps_side_str} {_sc['base']} "
                                          f"paper trade at TP1 — Pattern "
                                          f"Scout pick (validated edge, NOT "
                                          f"alerts-gated)"),
                                    use_container_width=True):
                                _ps_open_setup = {
                                    "symbol": _sc["symbol"],
                                    "base": _sc["base"],
                                    "side": _ps_side_str,
                                    "entry": _ps_entry,
                                    "entry_low": _ps_entry,
                                    "entry_high": _sc.get("entry_high") or _ps_entry,
                                    "stop": _ps_stop,
                                    "target": _ps_tgt,
                                    "target_2": _ps_tgt2 if _ps_tgt2 > 0 else None,
                                    "rr": _ps_rr,
                                    "confidence": int(min(99, _score)),
                                    "strength_factor": _ps_sf,
                                }
                                _ps_opened = paper_bot.open_position(
                                    pb_state, _ps_open_setup,
                                    prices.get(_sc["symbol"]) or _ps_entry)
                                if _ps_opened:
                                    _enrich_position(
                                        _ps_opened, int(min(99, _score)),
                                        timeframe)
                                    paper_bot.save_state(PAPER_BOT_FILE,
                                                         pb_state)
                                    st.toast(
                                        f"📥 Opened {_ps_side_str} "
                                        f"{_ps_opened['base']} @ "
                                        f"{fmt_price(_ps_opened['entry'])} · "
                                        f"Pattern Scout · score {_score:.0f}",
                                        icon="🎯")
                                    st.rerun()
                                else:
                                    st.warning(
                                        f"Could not open {_sc['base']} — "
                                        "check balance/concurrency/already-open.")

        # Old "Adaptive unified picks board" caption removed — replaced
        # by the concise caption attached to the new BEST TRADES NOW
        # header above.

        # _fc_by_sym was built earlier (right after auto_ad) and is shared
        # with the auto-trade loop, so no additional forecast call here.


        def _combined_score(setup, fc):
            """Combined strength score: scanner confidence + forecast bonus
            when the forecast confirms, minus a penalty when it disagrees.

            Returns the RAW (uncapped) score — the caller caps to 99 for
            display but uses the raw value for ranking, so a conf-85 setup
            with full forecast boost (raw 113) ranks above a conf-72 setup
            with the same boost (raw 100) instead of tying at 99."""
            score = float(setup.get("confidence") or 0)
            if not fc:
                return score, "no forecast"
            fc_word = fc.get("outlook_word")
            fc_conf = float(fc.get("confidence") or 0)
            aligned = bool(fc.get("aligned"))
            side = setup["side"]
            confirms = ((side == "LONG" and fc_word == "Bullish")
                        or (side == "SHORT" and fc_word == "Bearish"))
            disagrees = ((side == "LONG" and fc_word == "Bearish")
                         or (side == "SHORT" and fc_word == "Bullish"))
            if confirms:
                score += 10
                if aligned:
                    score += 8        # all three horizons agree
                if fc_conf >= 70:
                    score += 5        # high-confidence forecast
                label = (f"forecast confirms · aligned 3/3"
                         if aligned else f"forecast confirms")
            elif disagrees:
                score -= 8
                label = "forecast disagrees"
            else:
                label = "forecast neutral"
            return score, label    # uncapped — caller decides what to do

        _open_syms = {p["symbol"] for p in pb_state["open"]}
        # Mark PREMIUM-eligible setups (for the chip and the optional TP2
        # button). Target is NOT promoted here — TP1 stays the default.
        _all_picks = [_mark_premium(s) for s in auto_ad["setups"]
                      if s["symbol"] not in _open_syms]

        # Pull the BTC 24h outlook once for the macro-context tilt.
        # Calls hit the underlying caches so this is near-free even
        # though the function isn't memoised itself. When BTC's read
        # is strongly directional, alt longs/shorts that align with it
        # have a measurably higher win rate (real edge — the macro tide
        # matters more for alts than any single coin's technicals).
        _picks_btc: dict = {}
        try:
            _picks_btc = btc_outlook_now(_btc_change, _alt_median)
        except Exception:
            _picks_btc = {}
        _btc_dir = (_picks_btc.get("direction") or "").lower()
        _btc_conf = float(_picks_btc.get("confidence") or 0)
        # Only apply the tilt when BTC outlook has real conviction
        # (confidence >= 60). A weak / neutral outlook stays neutral.
        _btc_tilt_active = _btc_conf >= 60 and _btc_dir in (
            "bullish", "bearish")

        # Score every candidate then re-rank by the combined score, with a
        # weekly-trend bonus or penalty (with-trend = +5, counter = -8 — a
        # small, honest tilt, not a confidence-inflating multiplier).
        # IMPORTANT: store the RAW score (uncapped) so an excellent setup
        # truly ranks above a merely good one when both would otherwise
        # cap at 99. Display caps to 99 separately for the chip text.
        _scored = []
        for s in _all_picks:
            base, fc_label = _combined_score(
                s, _fc_by_sym.get(s["symbol"]))
            trend = htf_trend(s["symbol"])
            align = htf_alignment(s["side"], trend)
            if align == "aligned":
                base += 5
            elif align == "counter":
                base -= 8

            # --- BTC 24h Outlook tilt (macro context, independent edge) -
            # When BTC has a high-conviction directional view, alt
            # setups aligning with it are more reliable. Tilt is small
            # and capped: +4 aligned, -4 against, 0 neutral.
            if _btc_tilt_active:
                side = s.get("side")
                btc_aligned = (
                    (_btc_dir == "bullish" and side == "LONG")
                    or (_btc_dir == "bearish" and side == "SHORT"))
                btc_opposed = (
                    (_btc_dir == "bullish" and side == "SHORT")
                    or (_btc_dir == "bearish" and side == "LONG"))
                if btc_aligned:
                    base += 4
                elif btc_opposed:
                    base -= 4

            # --- Move maturity tilt (room-to-run, independent edge) ----
            # EARLY  = +6 (move just started, full room to target)
            # RE-RUN = 0  (continuation setup, partial room)
            # EXTENDED = -10 (move already extended, less room to run,
            #                more likely to reverse — what the user is
            #                experiencing on the trades that reverse).
            _mat = (s.get("maturity") or {})
            _mat_label = str(_mat.get("label") or "").upper()
            if _mat_label == "EARLY":
                base += 6
            elif _mat_label == "EXTENDED":
                base -= 10

            # --- Breakout Radar STAGE tilt (catches COILED pre-explosion)
            # The radar fuses 11 forces (volume ignition, coil
            # compression, taker flow, OBV, news, social, etc.) and
            # produces a STAGE label (COILED / FRESH / EXTENDED) — the
            # stage info is GENUINELY INDEPENDENT of the forecast
            # because the forecast only uses radar's DIRECTION signal,
            # not its stage classification.
            # Refined 2026-05-25 per honest audit: flat stage tilts only
            # (no direction-alignment bonus and no direction-only path).
            # The radar's direction signal already feeds into the
            # forecast above, so re-using it here would double-count.
            _radar = _radar_by_sym.get(s.get("symbol")) or {}
            _stage = str(_radar.get("stage") or "").upper()
            if _stage == "COILED":
                base += 6     # loaded but not fired — predictive entry
            elif _stage == "FRESH":
                base += 3     # early breakout, room left
            elif _stage == "EXTENDED":
                base -= 8     # move spent, chase risk

            # --- Phase A/B/C signal fusion (added 2026-05-29) -----------
            # Pull all the new backtested signals and tilt the combined
            # score by whether they agree with the setup direction.
            # Weights based on per-component backtest edge:
            #   early_momentum aligned: +5 (chip already shows)
            #   early_momentum opposes (em-SHORT vs LONG setup): -10
            #     (per backtest: when CVD SHORT 67% wins, the LONG it
            #     was supposed to confirm is likely to fail)
            #   RS leader for LONG: +5 / RS laggard for LONG: -3
            #   derivatives_velocity aligned: +3 (mild — Phase C edge
            #     was modest in snapshot)
            _setup_side = s["side"]
            _em_pick = load_early_momentum(s["symbol"], timeframe)
            _em_pick_score = float(_em_pick.get("score") or 50)
            _em_pick_side = str(_em_pick.get("side") or "NEUTRAL")
            # Align means em side matches setup side AND em is firing
            # decisively (>= 70 LONG or <= 30 SHORT)
            if _em_pick_side == _setup_side and (
                    (_setup_side == "LONG" and _em_pick_score >= 70)
                    or (_setup_side == "SHORT" and _em_pick_score <= 30)):
                base += 5
            elif _em_pick_side != "NEUTRAL" \
                    and _em_pick_side != _setup_side and (
                    (_em_pick_side == "SHORT" and _em_pick_score <= 30)
                    or (_em_pick_side == "LONG" and _em_pick_score >= 70)):
                # Strong opposing early-momentum signal — the backtested
                # 67%-win SHORT is saying "this LONG will fail" (or vice
                # versa). Heavy penalty.
                base -= 10

            # RS vs BTC
            _rs_pick = load_rs_vs_btc(s["symbol"], timeframe)
            _rs_pick_score = float(_rs_pick.get("score") or 50)
            _rs_pick_side = str(_rs_pick.get("side") or "NEUTRAL")
            if _setup_side == "LONG":
                if _rs_pick_side == "LONG" and _rs_pick_score >= 65:
                    base += 5
                elif _rs_pick_side == "SHORT" and _rs_pick_score <= 35:
                    base -= 3
            elif _setup_side == "SHORT":
                if _rs_pick_side == "SHORT" and _rs_pick_score <= 35:
                    base += 5
                elif _rs_pick_side == "LONG" and _rs_pick_score >= 65:
                    base -= 3

            # Derivatives velocity
            _dv_pick = load_derivatives_velocity(s["symbol"], timeframe)
            _dv_pick_score = float(_dv_pick.get("score") or 50)
            _dv_pick_side = str(_dv_pick.get("side") or "NEUTRAL")
            if _dv_pick_side == _setup_side and (
                    (_setup_side == "LONG" and _dv_pick_score >= 70)
                    or (_setup_side == "SHORT" and _dv_pick_score <= 30)):
                base += 3

            # 🟢 PROVEN LONG PATTERNS (replaces broken bullish CVD) ------
            # Only applies to LONG setups. Bullish RSI divergence + trend
            # reclaim + higher-low structure + bullish engulfing at
            # support. These are textbook patterns with documented edge
            # across decades — replaces the per-bar "bullish CVD" that
            # backtested at 3.6% win rate.
            if _setup_side == "LONG":
                _lp_pick = load_long_patterns(s["symbol"], timeframe)
                _lp_pick_score = float(_lp_pick.get("score") or 50)
                _lp_n_aligned = int(_lp_pick.get("n_aligned") or 0)
                if _lp_pick_score >= 75 and _lp_n_aligned >= 2:
                    base += 8     # 2+ proven patterns agreeing — strong LONG
                elif _lp_pick_score >= 70:
                    base += 5     # single strong pattern
                elif _lp_pick_score >= 60:
                    base += 2     # mild lift

                # 🔄 V-BOTTOM RECOVERY — rare-fire but high-edge signal.
                # Backtest: 75% win, +2.26% avg over 12 bars. Big bonus
                # when it fires because (a) the pattern is rare so it
                # WON'T over-promote junk picks, and (b) the win rate is
                # meaningfully above baseline. The signal catches the
                # JTO/INJ-style V-bottom setup at the first 1-3 strong
                # green candles after capitulation — exactly when the
                # user wanted picks to surface.
                _rec_pick = load_recovery(s["symbol"], timeframe)
                _rec_pick_score = float(_rec_pick.get("score") or 50)
                if _rec_pick_score >= 80:
                    base += 12    # STRONG V-bottom catch — top of board
                elif _rec_pick_score >= 70:
                    base += 8     # VALID V-bottom — strong tilt up

            # --- Market Regime tilt (adaptive layer) --------------------
            # In a BULL regime, push every score TOWARD LONG. In BEAR,
            # push TOWARD SHORT. The tilt magnitude is capped by regime
            # confidence so a low-conviction regime read doesn't dominate.
            # On 0-100 scoring: LONG setup uses base directly; SHORT
            # setup we invert before tilt then re-invert so the tilt
            # is applied to the directional bias not the raw number.
            # Regime tilt reduced to ±8 (was ±12) so SIGNAL STRENGTH
            # dominates over regime context. Per user direction:
            # "the idea is to make money — doesn't matter short or long".
            # A strong LONG signal in a BEAR regime should still surface
            # because dead-cat bounces are real trades. A strong SHORT
            # in BULL should still surface because overheated alts dump.
            # The tilt is a context nudge, not a filter.
            if _setup_side == "LONG":
                base = market_regime.regime_tilt(
                    base, "LONG", _regime, max_tilt=8.0)
            elif _setup_side == "SHORT":
                _inv = 100.0 - base
                _inv = market_regime.regime_tilt(
                    _inv, "SHORT", _regime, max_tilt=8.0)
                base = 100.0 - _inv

            _scored.append((base, fc_label, trend, align, s))
        _scored.sort(key=lambda t: t[0], reverse=True)
        # Quality floor: combined score >= 65 (was 72).
        # Lowered so the user ALWAYS sees picks even in low-conviction
        # markets (BEAR / CHOP / TRANSITION with sub-50 regime conf).
        # The CONVICTION TIER badge on each card is the safety:
        #   ⚡⚡⚡ MAX (>=90)  → trade with full size
        #   ⚡⚡ HIGH (>=85)   → trade meaningful
        #   ⚡ STRONG (>=80)  → trade small
        #   ⚪ STANDARD (65-79) → information only, very small or skip
        # User reads the tier to decide — the floor just guarantees the
        # board is never empty when there's any signal at all.
        _scored = [t for t in _scored if t[0] >= 65]

        # 🔥 EARLY-MOMENTUM A/B filter — strict mode that hides any
        # pick lacking an aligned early-momentum confirmation. Off by
        # default; user toggles it in Paper Trader settings. Paper
        # trader only — does NOT affect the Live Trading section.
        if bool(pb_state.get("em_filter_on", False)):
            def _em_passes(setup_dict: dict) -> bool:
                """Aligned early-momentum: score >= 75 AND side matches."""
                em = load_early_momentum(setup_dict["symbol"], timeframe)
                return (float(em.get("score") or 50) >= 75
                        and str(em.get("side") or "") == setup_dict["side"])
            _pre_filter_count = len(_scored)
            _scored = [t for t in _scored if _em_passes(t[4])]
            if _scored:
                st.caption(
                    f"🔥 Early-momentum filter ON — showing "
                    f"{len(_scored)} of {_pre_filter_count} picks "
                    f"(only setups with aligned leading-indicator "
                    f"confirmation).")
            else:
                st.caption(
                    f"🔥 Early-momentum filter ON — 0 of "
                    f"{_pre_filter_count} picks have aligned "
                    f"leading-indicator confirmation right now.")

        # GUARANTEE BOTH-DIRECTION PICKS — per user direction "the idea
        # is to make money, doesn't matter short or long". Take the top
        # 5 LONGs by combined score AND the top 3 SHORTs by combined
        # score, then re-rank by score. This means even in a BEAR
        # regime, the strongest LONG setups still surface (dead-cat
        # bounces are real trades). And in a BULL regime, the strongest
        # SHORTs still appear (overheated alts dump).
        _longs_scored = sorted(
            [t for t in _scored if t[4]["side"] == "LONG"],
            key=lambda t: t[0], reverse=True)
        _shorts_scored = sorted(
            [t for t in _scored if t[4]["side"] == "SHORT"],
            key=lambda t: t[0], reverse=True)
        # Mix: top 5 longs + top 3 shorts, then re-rank by combined.
        # If one side has fewer, fill in with the other side.
        # Show up to 12 picks (was 8) — user wants more options when
        # the market is active. Top 7 LONGs + top 5 SHORTs, then re-rank
        # by score. Floor at combined >=72 already filters out weak ones,
        # so this only shows additional picks IF they qualify.
        _mixed = (_longs_scored[:7] + _shorts_scored[:5])
        if len(_mixed) < 12:
            _used = set(id(t) for t in _mixed)
            _extras = [t for t in (_longs_scored + _shorts_scored)
                       if id(t) not in _used]
            _mixed = _mixed + _extras[:12 - len(_mixed)]
        _mixed.sort(key=lambda t: t[0], reverse=True)
        _bot_picks = _mixed[:12]

        # Header + caption removed per user (too noisy). The earlier
        # "### 🤖 Bot's top picks" header above already labels the board.

        # Re-entry detection — if a coin you JUST closed (within 60 min) is
        # back in the setups list, the scanner thinks it qualifies again
        # (pullback into the entry zone, or a fresh continuation setup).
        # We flag these so you don't miss the re-entry opportunity.
        _recent_close_syms = {
            c["symbol"] for c in pb_state.get("closed", [])[-30:]
            if (now_ts - (c.get("exit_at") or 0)) < 3600
        }

        # ====================================================================
        # 💎 SURE SHOT META-FILTER — Highest-Conviction Picks Only
        # ====================================================================
        # User request: "one solid system, no false trades, concrete top picks
        # that wont make me lose money". Honest reality: no system gives 100%
        # wins. What we CAN do is stack ALL validated signals together so
        # only the highest-conviction setups make this list.
        #
        # ALL of these conditions must hold to make SURE SHOT:
        #   1. combined_score >= 88 (top 10% of board)
        #   2. Pattern Scout fires on same coin with aligned side, score >= 70
        #   3. At least 2 strong chips fire (PREMIUM / V-BOTTOM /
        #      LONG_PATTERNS aligned / COILED / FRESH)
        #   4. Regime is favorable to the setup side (composite > 50 for
        #      LONG, < 50 for SHORT) OR live R:R >= 1.5 overrides
        #   5. NOT extended in 24h (|24h change| < 10%)
        #
        # Expected fire rate: 0-3 per day in most conditions. Rarity is the
        # edge — when SURE SHOT lights up, you'd be hard-pressed to find a
        # higher-conviction setup the system can see.
        try:
            _scout_results = run_pattern_scout(timeframe, scan_n=50)
        except Exception:
            _scout_results = []
        _scout_by_sym = {r["symbol"]: r for r in _scout_results}

        def _is_sure_shot(combined, fc_label, trend, align, s):
            """Strict meta-filter returning (is_sure_shot, reasons_list)."""
            reasons = []
            symbol = s["symbol"]
            side = s["side"]
            conf = int(s.get("confidence", 0) or 0)

            # 1. Combined score >= 88
            if combined < 88:
                return False, []
            reasons.append(f"combined {combined:.0f}/100")

            # 2. Pattern Scout aligned on same coin
            scout = _scout_by_sym.get(symbol)
            scout_aligned = (
                scout is not None
                and scout.get("score", 50) >= 70
                and scout.get("side") == side
            )
            if scout_aligned:
                reasons.append(f"Pattern Scout {scout['best_signal']}")
            else:
                return False, []

            # 3. At least 2 strong chips
            strong_chips = 0
            chip_names = []
            if (conf >= 80
                    and fc_label == "forecast confirms · aligned 3/3"):
                strong_chips += 1
                chip_names.append("🏆 PREMIUM")
            radar_info = _radar_by_sym.get(symbol) or {}
            stage = str(radar_info.get("stage") or "").upper()
            if stage in ("COILED", "FRESH"):
                strong_chips += 1
                chip_names.append(f"🌀 {stage}")
            # long_patterns aligned
            if side == "LONG":
                try:
                    lp = load_long_patterns(symbol, timeframe)
                    if (float(lp.get("score") or 50) >= 70
                            and int(lp.get("n_aligned") or 0) >= 2):
                        strong_chips += 1
                        chip_names.append("🟢 LONG PATTERNS")
                except Exception:
                    pass
                # V-bottom
                try:
                    rec = load_recovery(symbol, timeframe)
                    if float(rec.get("score") or 50) >= 75:
                        strong_chips += 1
                        chip_names.append("🔄 V-BOTTOM")
                except Exception:
                    pass
            # RS aligned with side
            try:
                rs = load_rs_vs_btc(symbol, timeframe)
                rs_score = float(rs.get("score") or 50)
                rs_side = str(rs.get("side") or "")
                if rs_side == side and (
                        (side == "LONG" and rs_score >= 65)
                        or (side == "SHORT" and rs_score <= 35)):
                    strong_chips += 1
                    chip_names.append("⚡ RS aligned")
            except Exception:
                pass

            if strong_chips < 2:
                return False, []
            reasons.append(f"{strong_chips} confirming chips ({', '.join(chip_names)})")

            # 4. Regime favorable OR live R:R >= 1.5 overrides
            regime_composite = float(_regime.get("composite") or 50)
            regime_favorable = (
                (side == "LONG" and regime_composite >= 50)
                or (side == "SHORT" and regime_composite <= 50)
            )
            # Need live R:R from current price
            _entry_low_now = float(s.get("entry_low") or 0)
            _stop_now = float(s.get("stop") or 0)
            _tgt_now = float(s.get("target") or 0)
            _cur_now = prices.get(symbol) or _entry_low_now
            _live_rr_now = 0.0
            if _cur_now > 0 and _stop_now > 0 and _tgt_now > 0:
                if side == "LONG":
                    risk = (_cur_now - _stop_now) / _cur_now
                    reward = (_tgt_now - _cur_now) / _cur_now
                else:
                    risk = (_stop_now - _cur_now) / _cur_now
                    reward = (_cur_now - _tgt_now) / _cur_now
                _live_rr_now = reward / risk if risk > 0 else 0.0
            if _live_rr_now >= 1.5:
                reasons.append(f"live R:R {_live_rr_now:.2f}")
            elif regime_favorable:
                reasons.append(f"regime favorable for {side}")
            else:
                return False, []

            # 5. Not extended in 24h (|change| < 10%)
            pct_24h_setup = scout.get("pct_24h", 0) if scout else 0
            if abs(pct_24h_setup) >= 10:
                return False, []
            reasons.append(f"24h {pct_24h_setup:+.1f}% (fresh)")

            return True, reasons

        _sure_shots = []
        for combined, fc_label, trend, align, s in _bot_picks:
            is_ss, ss_reasons = _is_sure_shot(combined, fc_label, trend, align, s)
            if is_ss:
                _sure_shots.append((combined, fc_label, trend, align, s, ss_reasons))

        # SURE SHOT rendering DISABLED — picks that qualify already
        # appear at the TOP of Bot's Top Picks (sorted by combined score).
        # Per user: "too many segments". Build a set so we can chip-tag
        # them in the main rendering loop instead.
        _sure_shot_syms = {s.get("symbol")
                           for _, _, _, _, s, _ in _sure_shots}
        if False and _sure_shots:
            st.markdown(
                "<div style='display:flex;align-items:center;gap:10px;"
                "margin-top:18px;margin-bottom:10px'>"
                "<span style='font-size:1.3rem;font-weight:900;"
                "background:linear-gradient(135deg,#00d4ff,#ffd700);"
                "-webkit-background-clip:text;-webkit-text-fill-color:"
                "transparent;background-clip:text;letter-spacing:-0.02em'>"
                "💎 SURE SHOT</span>"
                "<span style='color:#aab;font-size:0.84rem'>"
                f"highest-conviction picks · {len(_sure_shots)} firing now</span>"
                "</div>",
                unsafe_allow_html=True)
            st.caption(
                "**Strict meta-filter:** combined score ≥88, Pattern Scout "
                "fires on same coin (aligned side), 2+ confirming chips, "
                "regime-favorable OR live R:R ≥1.5, NOT extended in 24h. "
                "**Honest expectation:** 0-3 per day in normal conditions. "
                "The rarity is the edge — when this fires, every validated "
                "signal in the system agrees. **No system gives 100% wins** "
                "— even SURE SHOT will lose ~25-35% of trades. The R:R "
                "≥1.5 means you stay profitable at 50%+ win rate.")
            for combined, fc_label, trend, align, s, ss_reasons in _sure_shots:
                _ss_side = s["side"]
                _ss_color = "#00d4ff" if _ss_side == "LONG" else "#ff3d57"
                _ss_emoji = "🟢" if _ss_side == "LONG" else "🩸"
                _ss_cur = prices.get(s["symbol"]) or float(
                    s.get("entry_low") or 0)
                with st.container(border=True):
                    st.markdown(
                        f"<div style='background:linear-gradient(135deg,"
                        f"rgba(0,212,255,0.10),rgba(255,215,0,0.06));"
                        f"padding:10px 14px;border-radius:10px;"
                        f"border:1px solid rgba(0,212,255,0.25);'>"
                        f"<div style='display:flex;align-items:center;"
                        f"gap:10px;flex-wrap:wrap;margin-bottom:8px'>"
                        f"<span style='font-size:1.3rem;font-weight:800'>"
                        f"💎</span>"
                        f"<span style='font-size:1.1rem;font-weight:800;"
                        f"font-family:Space Grotesk,Inter,sans-serif'>"
                        f"{s['base']}</span>"
                        f"<span style='background:{_ss_color};color:#06121f;"
                        f"padding:3px 12px;border-radius:6px;font-size:"
                        f"0.78rem;font-weight:800'>"
                        f"{_ss_emoji} {_ss_side}</span>"
                        f"<span style='background:linear-gradient(90deg,"
                        f"#00d4ff,#ffd700);color:#001122;padding:3px 12px;"
                        f"border-radius:6px;font-size:0.78rem;font-weight:"
                        f"800;box-shadow:0 0 10px rgba(0,212,255,0.4)'>"
                        f"💎 SURE SHOT · {combined:.0f}</span>"
                        f"<span style='color:#aab;font-size:0.82rem'>"
                        f"now ${_ss_cur:.4g}</span></div>"
                        f"<div style='color:#c8d2ed;font-size:0.82rem;"
                        f"line-height:1.6'>"
                        f"<b style='color:#00d4ff'>Why this is a SURE SHOT:</b><br>"
                        f"{' · '.join(ss_reasons)}"
                        f"</div></div>",
                        unsafe_allow_html=True)
            st.markdown(
                "<div style='height:1px;background:linear-gradient(90deg,"
                "transparent,rgba(0,212,255,0.3),transparent);"
                "margin:20px 0'></div>",
                unsafe_allow_html=True)
            st.markdown(
                "<div style='color:#aab;font-size:0.84rem;margin-bottom:8px'>"
                "<b>↓ Other strong picks (didn't meet SURE SHOT bar but still tradeable):</b>"
                "</div>",
                unsafe_allow_html=True)

        if not _bot_picks:
            st.warning(
                "**No qualifying picks right now** — the multi-layer "
                "scoring is below the floor (combined < 65) for every "
                "coin on this timeframe. This usually means market "
                "regime is choppy/low-conviction. **Try:**\n"
                "• Switch timeframe (top bar): 1h is most reliable, "
                "4h gives the bigger-picture setups.\n"
                "• Check **🔭 SETUPS FORMING** below — coins about to "
                "trigger.\n"
                "• Wait. Forcing trades in low-conviction regimes is "
                "how you lose money.")
        else:
            for combined, fc_label, trend, align, s in _bot_picks:
                side = s["side"]
                side_color = "#2ed47a" if side == "LONG" else "#ff5c5c"
                conf = int(s.get("confidence", 0) or 0)
                # Cap to 99 for the visible chip — the raw (uncapped)
                # value above already did its job in the sort, so the
                # truly excellent setup is at the top of the list. The
                # chip text just keeps the UI within 0-99.
                combined_display = int(min(99, max(0, combined)))
                str_label, str_color = _strength_label(combined_display)
                # --- Live R:R from CURRENT price ------------------------
                # The plan's R:R assumes a fill at entry_low. If price
                # has drifted past the entry zone, the actual R:R when
                # opening at current price is degraded. Compute and
                # display the LIVE numbers so the user sees what they
                # will actually get, not the idealised plan.
                _cur = prices.get(s["symbol"]) or float(
                    s.get("entry_low") or 0)
                _stop = float(s.get("stop") or 0)
                # target = TP1 (default exit for ALL setups now)
                # target_2 = TP2 (deeper, shown on PREMIUM cards as an
                #            opt-in via the second button)
                _tgt = float(s.get("target") or 0)
                _tgt_2 = float(s.get("target_2") or 0)
                _show_tp2 = bool(s.get("premium_eligible")) and _tgt_2 > 0
                _live_risk_pct = 0.0
                _live_reward_pct = 0.0
                _live_rr = 0.0
                _live_reward_pct_2 = 0.0
                _live_rr_2 = 0.0
                if _cur and _stop and _tgt:
                    if side == "LONG":
                        _live_risk_pct = (_cur - _stop) / _cur * 100
                        _live_reward_pct = (_tgt - _cur) / _cur * 100
                        if _show_tp2:
                            _live_reward_pct_2 = (_tgt_2 - _cur) / _cur * 100
                    else:  # SHORT
                        _live_risk_pct = (_stop - _cur) / _cur * 100
                        _live_reward_pct = (_cur - _tgt) / _cur * 100
                        if _show_tp2:
                            _live_reward_pct_2 = (_cur - _tgt_2) / _cur * 100
                    if _live_risk_pct > 0:
                        _live_rr = _live_reward_pct / _live_risk_pct
                        if _show_tp2:
                            _live_rr_2 = _live_reward_pct_2 / _live_risk_pct
                # Entry-zone chip — symmetric signal (user asked for the
                # red marker back, 2026-05-25 second pass — makes the
                # state immediately scannable on a card).
                #   Green "At entry zone" when live R:R >= 1.3 means the
                #     math from the plan is intact: open here = the R:R
                #     you see on the card.
                #   Red "Entry zone passed" when live R:R < 1.2 means
                #     price has drifted past the planned entry and the
                #     live R:R is degraded. NOT a "don't trade" — the
                #     setup can still profit if the rest of the data is
                #     clean — just a heads-up to check the live R:R
                #     number before clicking.
                _drift_chip = ""
                if _live_rr >= 1.3:
                    _drift_chip = (
                        f"<span style='background:#2ed47a33;color:#2ed47a;"
                        f"padding:2px 8px;border-radius:5px;font-size:"
                        f"0.7rem;font-weight:700;margin-left:4px'>"
                        f"✓ At entry zone · live R:R {_live_rr:.2f}"
                        f"</span>")
                elif 0 < _live_rr < 1.2:
                    _drift_chip = (
                        f"<span style='background:#ff5c5c33;color:#ff5c5c;"
                        f"padding:2px 8px;border-radius:5px;font-size:"
                        f"0.7rem;font-weight:700;margin-left:4px'>"
                        f"⚠ Entry zone passed · live R:R {_live_rr:.2f}"
                        f"</span>")
                sid = f"{s['symbol']}:{side}"
                alive_min = (now_ts - sp.get(sid, now_ts)) / 60.0
                alive_txt = (f"alive {alive_min:.0f} min"
                             if alive_min >= 1 else "just appeared")
                hold = _hold_horizon(timeframe)
                proof = (" · ".join(s.get("proof", [])[:2])
                         if s.get("proof") else "multiple signals align")
                rr = float(s.get("rr") or 0.0)
                fc = _fc_by_sym.get(s["symbol"]) or {}

                # 🏆 PREMIUM tier — scanner conf >= 80 AND forecast aligned
                # 3/3. Empirically the most reliable setups; the badge
                # exists so the user can spot them at a glance without
                # reading the scores. PREMIUM cards also get a second
                # button to open at the deeper TP2 target (optional).
                premium_chip = ""
                if (conf >= 80
                        and fc_label == "forecast confirms · aligned 3/3"):
                    premium_chip = (
                        f"<span style='background:linear-gradient(90deg,"
                        f"#e0a92b,#ffd700);color:#1a1a1a;"
                        f"padding:2px 10px;border-radius:5px;font-size:"
                        f"0.72rem;font-weight:800;margin-left:4px;"
                        f"box-shadow:0 0 8px #e0a92b66'>"
                        f"🏆 PREMIUM</span>")

                # ⚡ CONVERGENCE chip — pick qualifies under the validated
                # convergence formula (Pattern Scout + Setups Forming +
                # regime + 4h trend + BTC corr). Folded in here so the
                # standalone CONVERGENCE segment can stay hidden.
                # Backtest: +6.8pp uplift over baseline at 12bar.
                convergence_chip = ""
                if s["symbol"] in _convergence_syms:
                    convergence_chip = (
                        f"<span style='background:linear-gradient(90deg,"
                        f"#ffd700,#ff006e,#8b5cf6);color:#fff;"
                        f"padding:2px 10px;border-radius:5px;font-size:"
                        f"0.72rem;font-weight:800;margin-left:4px;"
                        f"box-shadow:0 0 10px rgba(255,215,0,0.5)'>"
                        f"⚡ CONVERGENCE</span>")

                # 💎 SURE SHOT chip — passed the strict meta-filter
                # (score >= 88, Pattern Scout agrees, 2+ confirming chips,
                # regime-OK or R:R >= 1.5, not extended).
                sure_shot_chip = ""
                if s["symbol"] in _sure_shot_syms:
                    sure_shot_chip = (
                        f"<span style='background:linear-gradient(90deg,"
                        f"#00d4ff,#ffd700);color:#001122;"
                        f"padding:2px 10px;border-radius:5px;font-size:"
                        f"0.72rem;font-weight:800;margin-left:4px;"
                        f"box-shadow:0 0 10px rgba(0,212,255,0.5)'>"
                        f"💎 SURE SHOT</span>")

                # ============================================================
                # 🏆 CONVICTION TIER — multi-layer fusion badge.
                # ============================================================
                # Tells the user at a glance how many top conviction
                # layers agree on this pick. The MOST important chip on
                # the card — it sits leftmost in render order below.
                #
                # MAX  (⚡⚡⚡): combined >=90 AND (CONVERGENCE OR SURE SHOT)
                #               — every top layer agrees, max conviction.
                # HIGH (⚡⚡)  : combined >=85 AND any one of (CONVERGENCE,
                #               SURE SHOT, PREMIUM)
                # STRONG (⚡) : combined >=80 AND forecast aligned 3/3
                # STANDARD  : combined >=72 (passes alert floor)
                _conv_score = combined  # combined score (multi-layer)
                _conv_in_convergence = s["symbol"] in _convergence_syms
                _conv_in_sureshot = s["symbol"] in _sure_shot_syms
                _conv_is_premium = bool(premium_chip)
                _conv_forecast_aligned = (
                    fc_label == "forecast confirms · aligned 3/3")

                if (_conv_score >= 90
                        and (_conv_in_convergence or _conv_in_sureshot)):
                    _conv_tier = "MAX"
                    _conv_emoji = "⚡⚡⚡"
                    _conv_grad = ("linear-gradient(90deg,"
                                  "#ffd700,#ff006e,#8b5cf6,#00d4ff)")
                    _conv_glow = "0 0 14px rgba(255,215,0,0.6)"
                    _conv_text = "#fff"
                elif (_conv_score >= 85
                        and (_conv_in_convergence
                             or _conv_in_sureshot or _conv_is_premium)):
                    _conv_tier = "HIGH"
                    _conv_emoji = "⚡⚡"
                    _conv_grad = "linear-gradient(90deg,#ff006e,#8b5cf6)"
                    _conv_glow = "0 0 10px rgba(139,92,246,0.5)"
                    _conv_text = "#fff"
                elif _conv_score >= 80 and _conv_forecast_aligned:
                    _conv_tier = "STRONG"
                    _conv_emoji = "⚡"
                    _conv_grad = "linear-gradient(90deg,#00d4ff,#2ed47a)"
                    _conv_glow = "0 0 8px rgba(0,212,255,0.4)"
                    _conv_text = "#001122"
                else:
                    _conv_tier = "STANDARD"
                    _conv_emoji = "⚪"
                    _conv_grad = "rgba(255,255,255,0.06)"
                    _conv_glow = "none"
                    _conv_text = "#aab"
                conviction_chip = (
                    f"<span style='background:{_conv_grad};"
                    f"color:{_conv_text};padding:3px 12px;"
                    f"border-radius:6px;font-size:0.74rem;font-weight:800;"
                    f"margin-left:0;letter-spacing:0.02em;"
                    f"box-shadow:{_conv_glow}'>"
                    f"{_conv_emoji} {_conv_tier} CONVICTION</span>")

                # Forecast confirmation chip
                fc_chip = ""
                if fc_label == "forecast confirms · aligned 3/3":
                    fc_chip = (
                        f"<span style='background:#2ed47a33;color:#2ed47a;"
                        f"padding:2px 8px;border-radius:5px;font-size:0.7rem;"
                        f"font-weight:700;margin-left:4px'>"
                        f"✓ Forecast aligned 3/3</span>")
                elif fc_label == "forecast confirms":
                    fc_chip = (
                        f"<span style='background:#6e8bff33;color:#6e8bff;"
                        f"padding:2px 8px;border-radius:5px;font-size:0.7rem;"
                        f"font-weight:700;margin-left:4px'>"
                        f"✓ Forecast confirms</span>")
                elif fc_label == "forecast disagrees":
                    fc_chip = (
                        f"<span style='background:#e0a92b33;color:#e0a92b;"
                        f"padding:2px 8px;border-radius:5px;font-size:0.7rem;"
                        f"font-weight:700;margin-left:4px'>"
                        f"⚠ Forecast disagrees</span>")

                # Higher-TF weekly trend is folded silently into the score
                # above (+5 aligned / -8 counter); no visual chip — the
                # ranking does the work without cluttering the card.

                # Re-entry badge — flag setups that re-qualified after a
                # recent close so the user can take the second leg.
                reentry_chip = ""
                if s["symbol"] in _recent_close_syms:
                    reentry_chip = (
                        f"<span style='background:#e0a92b33;color:#e0a92b;"
                        f"padding:2px 8px;border-radius:5px;font-size:"
                        f"0.7rem;font-weight:700;margin-left:4px'>"
                        f"↻ Re-entry available</span>")

                # 🌀 COILED chip — Breakout Radar says this setup is
                # "loaded but not fired yet". The closest honest signal
                # for "about to explode". Showing this visually so the
                # user can spot the pre-breakout candidates instantly.
                coiled_chip = ""
                _pick_radar = _radar_by_sym.get(s["symbol"]) or {}
                _pick_stage = str(_pick_radar.get("stage") or "").upper()
                if _pick_stage == "COILED":
                    coiled_chip = (
                        f"<span style='background:#6e8bff33;color:#6e8bff;"
                        f"padding:2px 8px;border-radius:5px;font-size:"
                        f"0.7rem;font-weight:800;margin-left:4px'>"
                        f"🌀 COILED · loaded</span>")
                elif _pick_stage == "FRESH":
                    coiled_chip = (
                        f"<span style='background:#2ed47a22;color:#2ed47a;"
                        f"padding:2px 8px;border-radius:5px;font-size:"
                        f"0.7rem;font-weight:700;margin-left:4px'>"
                        f"⚡ FRESH · breaking out</span>")
                elif _pick_stage == "EXTENDED":
                    coiled_chip = (
                        f"<span style='background:#8b8d9833;color:#8b8d98;"
                        f"padding:2px 8px;border-radius:5px;font-size:"
                        f"0.7rem;font-weight:700;margin-left:4px'>"
                        f"📉 EXTENDED · move spent</span>")

                # 🔥 EARLY MOMENTUM chip — Phase A MVP. Displays a
                # parallel leading-indicator score (CVD divergence,
                # TTM Squeeze fire, ROC-of-ROC, SMC liquidity sweep
                # gated by a Hurst regime check). Score >= 75 fires
                # when its side aligns with the setup's side. This is
                # DISPLAY-ONLY for now — does NOT feed combined_score
                # or the live broker gate. Lets the user A/B test
                # whether the new leading signals correlate with wins
                # before we trust them with the ranking.
                early_chip = ""
                _em = load_early_momentum(s["symbol"], timeframe)
                _em_score = float(_em.get("score") or 50)
                _em_side = str(_em.get("side") or "NEUTRAL")
                _em_flags = list(_em.get("flags") or [])
                if _em_score >= 75 and _em_side == side:
                    # Aligned with setup direction — strongest read
                    flag_text = ""
                    if "squeeze_fire" in _em_flags:
                        flag_text = " · 🌀 squeeze fired"
                    elif "liquidity_sweep" in _em_flags:
                        flag_text = " · 🎯 sweep"
                    elif "cvd_divergence" in _em_flags:
                        flag_text = " · 📊 CVD div"
                    elif "accel_inflection" in _em_flags:
                        flag_text = " · 📈 accel"
                    early_chip = (
                        f"<span style='background:linear-gradient(90deg,"
                        f"#ff6b35,#ffa657);color:#1a0c00;"
                        f"padding:2px 10px;border-radius:5px;font-size:"
                        f"0.72rem;font-weight:800;margin-left:4px;"
                        f"box-shadow:0 0 6px #ff6b3566'>"
                        f"🔥 EARLY · {_em_score:.0f}{flag_text}</span>")
                elif _em_score <= 25 and _em_side != side \
                        and _em_side != "NEUTRAL":
                    # Strong opposite-side early signal — warning chip
                    early_chip = (
                        f"<span style='background:#ff5c5c33;color:#ff5c5c;"
                        f"padding:2px 8px;border-radius:5px;font-size:"
                        f"0.7rem;font-weight:700;margin-left:4px'>"
                        f"⚠ Early-mom opposes ({_em_score:.0f})</span>")

                # 🔄 V-BOTTOM RECOVERY chip — fires on the rare-but-high-
                # edge setup (75% win, +2.26% avg per backtest). Catches
                # the JTO/INJ-style sharp drawdown → capitulation → strong
                # green reversal pattern. LONG setups only by design.
                recovery_chip = ""
                if side == "LONG":
                    _rec = load_recovery(s["symbol"], timeframe)
                    _rec_score = float(_rec.get("score") or 50)
                    _rec_flags = list(_rec.get("flags") or [])
                    if _rec_score >= 80:
                        # Strong V-bottom — distinctive cyan-gold gradient
                        recovery_chip = (
                            f"<span style='background:linear-gradient("
                            f"90deg,#00d4ff,#ffd700);color:#001122;"
                            f"padding:2px 10px;border-radius:5px;"
                            f"font-size:0.72rem;font-weight:800;"
                            f"margin-left:4px;box-shadow:0 0 10px "
                            f"#00d4ff66;'>"
                            f"🔄 V-BOTTOM · {_rec_score:.0f}</span>")
                    elif _rec_score >= 70:
                        recovery_chip = (
                            f"<span style='background:#00d4ff22;"
                            f"color:#00d4ff;padding:2px 8px;"
                            f"border-radius:5px;font-size:0.7rem;"
                            f"font-weight:700;margin-left:4px'>"
                            f"🔄 Recovery · {_rec_score:.0f}</span>")

                # 🟢 PROVEN LONG PATTERNS chip — only on LONG setups
                long_chip = ""
                if side == "LONG":
                    _lp = load_long_patterns(s["symbol"], timeframe)
                    _lp_score = float(_lp.get("score") or 50)
                    _lp_flags = list(_lp.get("flags") or [])
                    _lp_n = int(_lp.get("n_aligned") or 0)
                    if _lp_score >= 70 and _lp_n >= 1:
                        # Build flag short labels
                        flag_lbls = []
                        if "rsi_divergence" in _lp_flags:
                            flag_lbls.append("RSI div")
                        if "trend_reclaim" in _lp_flags:
                            flag_lbls.append("reclaim")
                        if "higher_low" in _lp_flags:
                            flag_lbls.append("HL")
                        if "engulfing_support" in _lp_flags:
                            flag_lbls.append("engulf")
                        flag_text = (" · " + " · ".join(flag_lbls[:2])
                                     if flag_lbls else "")
                        # Stronger colors for multi-pattern alignment
                        if _lp_n >= 2:
                            long_chip = (
                                f"<span style='background:linear-gradient("
                                f"90deg,#0b8a3e,#34c759);color:#06121f;"
                                f"padding:2px 10px;border-radius:5px;"
                                f"font-size:0.72rem;font-weight:800;"
                                f"margin-left:4px;box-shadow:0 0 6px "
                                f"#34c75966'>"
                                f"🟢 LONG · {_lp_score:.0f}{flag_text}</span>")
                        else:
                            long_chip = (
                                f"<span style='background:#2ed47a22;"
                                f"color:#2ed47a;padding:2px 8px;"
                                f"border-radius:5px;font-size:0.7rem;"
                                f"font-weight:700;margin-left:4px'>"
                                f"🟢 LONG · {_lp_score:.0f}{flag_text}</span>")

                # ⚡ RS LEADER chip (Phase B) — relative strength vs BTC.
                # When the alt is significantly out-performing BTC across
                # short/med/long windows (z-score >= +0.5), capital is
                # rotating in BEFORE the broader trend confirms. This is
                # a leading rotation signal — particularly useful when
                # BTC is chopping but specific alts are leading.
                # Mirror chip ⚠ RS LAGGARD fires when the alt is
                # significantly UNDER-performing BTC.
                rs_chip = ""
                _rs = load_rs_vs_btc(s["symbol"], timeframe)
                _rs_score = float(_rs.get("score") or 50)
                _rs_side = str(_rs.get("side") or "NEUTRAL")
                _rs_z = float(_rs.get("rs_z") or 0)
                if _rs_score >= 70 and _rs_side == "LONG" and side == "LONG":
                    rs_chip = (
                        f"<span style='background:linear-gradient(90deg,"
                        f"#6e8bff,#2ed47a);color:#06121f;"
                        f"padding:2px 10px;border-radius:5px;font-size:"
                        f"0.72rem;font-weight:800;margin-left:4px;"
                        f"box-shadow:0 0 6px #6e8bff66'>"
                        f"⚡ RS LEADER · z{_rs_z:+.1f}</span>")
                elif _rs_score <= 30 and _rs_side == "SHORT" and side == "SHORT":
                    rs_chip = (
                        f"<span style='background:linear-gradient(90deg,"
                        f"#ff5c5c,#e0a92b);color:#06121f;"
                        f"padding:2px 10px;border-radius:5px;font-size:"
                        f"0.72rem;font-weight:800;margin-left:4px;"
                        f"box-shadow:0 0 6px #ff5c5c66'>"
                        f"⚡ RS LAGGARD · z{_rs_z:+.1f}</span>")
                elif _rs_score >= 65 and _rs_side == "LONG" and side == "SHORT":
                    # Setup is SHORT but RS says the alt is leading — warn
                    rs_chip = (
                        f"<span style='background:#e0a92b33;color:#e0a92b;"
                        f"padding:2px 8px;border-radius:5px;font-size:"
                        f"0.7rem;font-weight:700;margin-left:4px'>"
                        f"⚠ RS opposes (z{_rs_z:+.1f})</span>")

                # 💱 DERIV chip (Phase C) — derivatives velocity. Funding
                # ROC + OI compression. Useful at sentiment turns: when
                # funding flips sharply, the contrarian read often catches
                # squeezes ahead of the price move.
                # Per backtest findings: SHORT-side derivatives signals
                # have edge; LONG-side does not. Chip styling reflects
                # this — SHORT fires get the strong gradient, LONG fires
                # only get a subtle hint chip.
                dv_chip = ""
                _dv = load_derivatives_velocity(s["symbol"], timeframe)
                _dv_score = float(_dv.get("score") or 50)
                _dv_side = str(_dv.get("side") or "NEUTRAL")
                _dv_flags = list(_dv.get("flags") or [])
                if _dv_score <= 30 and _dv_side == "SHORT" and side == "SHORT":
                    flag_text = ""
                    if "funding_flip" in _dv_flags:
                        flag_text = " · ⚡ funding flip"
                    elif "oi_compression" in _dv_flags:
                        flag_text = " · 🌀 OI coil"
                    dv_chip = (
                        f"<span style='background:linear-gradient(90deg,"
                        f"#ff5c5c,#e0a92b);color:#06121f;"
                        f"padding:2px 10px;border-radius:5px;font-size:"
                        f"0.72rem;font-weight:800;margin-left:4px;"
                        f"box-shadow:0 0 6px #ff5c5c66'>"
                        f"💱 DERIV · {_dv_score:.0f}{flag_text}</span>")
                elif _dv_score >= 70 and _dv_side == "LONG" and side == "LONG":
                    # LONG signals showed no edge in backtests — mute styling
                    dv_chip = (
                        f"<span style='background:#6e8bff22;color:#6e8bff;"
                        f"padding:2px 8px;border-radius:5px;font-size:"
                        f"0.7rem;font-weight:700;margin-left:4px'>"
                        f"💱 deriv {_dv_score:.0f} (long, weak edge)</span>")
                elif (_dv_score >= 70 and _dv_side == "LONG"
                      and side == "SHORT") or (
                      _dv_score <= 30 and _dv_side == "SHORT"
                      and side == "LONG"):
                    dv_chip = (
                        f"<span style='background:#e0a92b33;color:#e0a92b;"
                        f"padding:2px 8px;border-radius:5px;font-size:"
                        f"0.7rem;font-weight:700;margin-left:4px'>"
                        f"⚠ deriv opposes ({_dv_score:.0f})</span>")

                # Forecast per-horizon line
                fc_line = ""
                if fc.get("horizons"):
                    horizon_bits = []
                    arrow = {"Up": "▲", "Down": "▼", "Sideways": "▬"}
                    for _tf in ("15m", "1h", "4h"):
                        h = fc["horizons"].get(_tf)
                        if not h:
                            continue
                        ac = ("#2ed47a" if h["direction"] == "Up"
                              else "#ff5c5c" if h["direction"] == "Down"
                              else "#8b8d98")
                        horizon_bits.append(
                            f"<span style='color:#aab'>{_tf}</span> "
                            f"<span style='color:{ac};font-weight:700'>"
                            f"{arrow.get(h['direction'], '·')} "
                            f"{h['move_pct']:+.2f}%</span>")
                    if horizon_bits:
                        fc_line = (
                            f"<div style='color:#9aa0b4;font-size:0.76rem;"
                            f"margin-top:2px'>📈 forecast — "
                            + " · ".join(horizon_bits) + "</div>")

                with st.container(border=True):
                    pa, pb = st.columns([6, 1])
                    pa.markdown(
                        f"<div style='display:flex;align-items:center;"
                        f"gap:8px;flex-wrap:wrap'>"
                        f"<span style='font-weight:800;font-size:1rem'>"
                        f"{s['base']}</span>"
                        f"<span style='background:{side_color};color:#06121f;"
                        f"padding:2px 10px;border-radius:5px;font-size:"
                        f"0.72rem;font-weight:800'>{side}</span>"
                        f"<span style='background:{str_color}33;"
                        f"color:{str_color};padding:2px 8px;border-radius:"
                        f"5px;font-size:0.72rem;font-weight:700'>"
                        f"{str_label} · {combined_display}</span>"
                        f"{conviction_chip}"
                        f"{convergence_chip}{sure_shot_chip}{premium_chip}"
                        f"{recovery_chip}{coiled_chip}"
                        f"{early_chip}{long_chip}{rs_chip}{dv_chip}"
                        f"{fc_chip}{reentry_chip}{_drift_chip}"
                        f"<span style='color:#8b8d98;font-size:0.78rem'>"
                        f"scanner {conf}% · R:R {rr:.1f} · "
                        f"{alive_txt}</span></div>"
                        f"<div style='color:#aab;font-size:0.78rem;"
                        f"margin-top:4px'>"
                        f"hold: <b>{hold}</b> · now "
                        f"<b>{fmt_price(_cur)}</b> · entry zone "
                        f"{fmt_price(s.get('entry_low', 0))} · "
                        f"stop {fmt_price(_stop)} "
                        f"<span style='color:#ff5c5c'>"
                        f"(−{_live_risk_pct:.1f}%)</span> · "
                        # PREMIUM cards show TP1 (default exit, green)
                        # and TP2 (optional deeper target, gold).
                        # Non-PREMIUM cards show just TP1.
                        + (
                            f"target 1 {fmt_price(_tgt)} "
                            f"<span style='color:#2ed47a'>"
                            f"(+{_live_reward_pct:.1f}%)</span> · "
                            f"target 2 {fmt_price(_tgt_2)} "
                            f"<span style='color:#e0a92b'>"
                            f"(+{_live_reward_pct_2:.1f}%)</span> · "
                            f"R:R "
                            f"<b>{_live_rr:.2f}</b> "
                            f"/ <b>{_live_rr_2:.2f}</b>"
                            if _show_tp2 else
                            f"target {fmt_price(_tgt)} "
                            f"<span style='color:#2ed47a'>"
                            f"(+{_live_reward_pct:.1f}%)</span> · "
                            f"live R:R <b>{_live_rr:.2f}</b>"
                        )
                        + f"</div>"
                        f"<div style='color:#9aa0b4;font-size:0.78rem;"
                        f"margin-top:2px'>proof — {md_safe(proof)}</div>"
                        f"{fc_line}",
                        unsafe_allow_html=True)
                    # Default button — opens at TP1 (the standard target).
                    # On PREMIUM-eligible setups it also activates the
                    # chase-TP2 trailing: if price hits TP1 the stop
                    # trails up to lock in the win and the target
                    # extends to TP2 so the trade rides momentum.
                    _btn_help = (f"Open {side} {s['base']} at TP1 "
                                 f"(~5-7%, chase TP2 if trend holds)"
                                 if s.get("premium_eligible") else
                                 f"Open {side} {s['base']} at TP1 (~5-7%)")
                    if pb.button("📥", key=f"pb_pick_{sid}",
                                 help=_btn_help,
                                 use_container_width=True):
                        _open_setup = dict(s)
                        if s.get("premium_eligible"):
                            _open_setup["chase_tp2_eligible"] = True
                        # Strength factor scales the notional cap by
                        # the combined score — top picks deploy the
                        # full cap, weaker picks get less. Linear from
                        # 0.4 at combined 72 to 1.0 at combined 95+.
                        _open_setup["strength_factor"] = max(
                            0.4, min(1.0, (combined - 72) / 23.0 + 0.4))
                        _opened = paper_bot.open_position(
                            pb_state, _open_setup,
                            prices.get(s["symbol"])
                            or s.get("entry_low"))
                        if _opened:
                            _enrich_position(_opened, combined_display,
                                             timeframe)
                            paper_bot.save_state(PAPER_BOT_FILE, pb_state)
                            _msg_suffix = (
                                " → TP1 · chases TP2"
                                if s.get("premium_eligible") else
                                " → TP1")
                            st.toast(
                                f"📥 Opened {side} {_opened['base']} @ "
                                f"{fmt_price(_opened['entry'])}{_msg_suffix}",
                                icon="🏆" if s.get("premium_eligible")
                                     else "🧪")
                            st.rerun()
                    # Optional TP2 button — only on PREMIUM-eligible cards.
                    # Opens the same setup but with the target swapped to
                    # TP2 (~7.5-10%), for users who want to ride the
                    # deeper target on strong setups.
                    if _show_tp2:
                        if pb.button("🏆 TP2", key=f"pb_tp2_{sid}",
                                     help=f"Open {side} {s['base']} aiming "
                                          f"for TP2 (~7.5-10%) instead of "
                                          f"TP1. Strong setups only.",
                                     use_container_width=True):
                            _setup_tp2 = dict(s)
                            _setup_tp2["target"] = float(_tgt_2)
                            _setup_tp2["rr"] = float(
                                s.get("rr_2") or s.get("rr") or 0)
                            # Premium-only button → use full strength
                            # factor for the size allocation.
                            _setup_tp2["strength_factor"] = max(
                                0.4, min(1.0,
                                         (combined - 72) / 23.0 + 0.4))
                            _opened = paper_bot.open_position(
                                pb_state, _setup_tp2,
                                prices.get(s["symbol"])
                                or s.get("entry_low"))
                            if _opened:
                                _enrich_position(_opened, combined_display,
                                                 timeframe)
                                paper_bot.save_state(
                                    PAPER_BOT_FILE, pb_state)
                                st.toast(
                                    f"🏆 Opened {side} {_opened['base']} @ "
                                    f"{fmt_price(_opened['entry'])} → TP2",
                                    icon="🏆")
                                st.rerun()

        # ---- Movers right now — coins already running with volume --------
        # Top picks only show "setups at entry" (conf>=70 + valid plan).
        # Coins already up 5-10 percent on a volume surge often don't pass
        # that filter even though they are tradable. Surface them here so
        # the user does not miss INJ-style movers — clearly labelled as
        # chase candidates with momentum, NOT pristine entries.
        _pick_syms = {pk[4]["symbol"] for pk in _bot_picks}
        _surges_all = auto_ad.get("surges") or []
        _movers = [m for m in _surges_all
                   if m["symbol"] not in _open_syms
                   and m["symbol"] not in _pick_syms][:5]
        # Movers section DISABLED per user — too many sections. Volume
        # surges already factored into combined_score for picks. Flip
        # to True to restore the standalone Movers list.
        if False and _movers:
            st.markdown("#### 🔥 Movers right now")
            st.caption("Coins already running on a volume surge "
                       "(≥ 2× average). These don't have a fresh entry "
                       "zone like the top picks — they're chase candidates "
                       "with momentum, so use a tighter stop and don't "
                       "commit full risk.")
            for m in _movers:
                vr = float(m.get("vol_ratio") or 0)
                ch = float(m.get("change_24h") or 0)
                lbl = str(m.get("label") or "NEUTRAL")
                bias = ("LONG" if "LONG" in lbl
                        else "SHORT" if "SHORT" in lbl
                        else "—")
                bias_col = ("#2ed47a" if bias == "LONG"
                            else "#ff5c5c" if bias == "SHORT"
                            else "#8b8d98")
                ch_col = ("#2ed47a" if ch >= 0 else "#ff5c5c")
                mconf = int(m.get("confidence") or 0)
                with st.container(border=True):
                    st.markdown(
                        f"<div style='display:flex;align-items:center;"
                        f"gap:8px;flex-wrap:wrap'>"
                        f"<span style='font-weight:800;font-size:1rem'>"
                        f"{m['base']}</span>"
                        f"<span style='background:{bias_col};color:#06121f;"
                        f"padding:2px 10px;border-radius:5px;font-size:"
                        f"0.72rem;font-weight:800'>{bias}</span>"
                        f"<span style='background:#e0a92b33;color:#e0a92b;"
                        f"padding:2px 8px;border-radius:5px;font-size:"
                        f"0.7rem;font-weight:700'>"
                        f"🔥 {vr:.1f}× volume</span>"
                        f"<span style='color:{ch_col};font-weight:700;"
                        f"font-size:0.82rem'>{ch:+.2f}% 24h</span>"
                        f"<span style='color:#8b8d98;font-size:0.78rem'>"
                        f"· scanner conf {mconf}%</span></div>",
                        unsafe_allow_html=True)

        # ============================================================
        # 🔭 SETUPS FORMING — Compact directional intel (NOT openable)
        # ============================================================
        # User: "setups forming was good ... as it gives the direction".
        # This is the leading-indicator watchlist showing coins where
        # reversal pre-conditions are forming on the current timeframe.
        # By the time a hammer/shooting-star prints, the rejection
        # already happened — this catches the 1-5 bar lead-up so the
        # user knows WHERE direction is shifting and can position
        # accordingly. Compact one-line-per-coin format (NOT a card
        # board) so it doesn't bloat the page. NO trade buttons —
        # this is intel; when the actual fire candle lands it shows
        # up in BEST TRADES NOW above.
        try:
            _sf_results = run_reversal_approach_scan(timeframe, scan_n=30)
        except Exception:
            _sf_results = []
        # Show top 6 — only score >= 65 (3+ conditions). Skip coins that
        # are already in BEST TRADES NOW (avoid duplication).
        _btn_syms = {pk[4]["symbol"] for pk in _bot_picks}
        _sf_top = [r for r in sorted(_sf_results,
                                     key=lambda r: r["score"], reverse=True)
                   if r["score"] >= 65 and r["symbol"] not in _btn_syms][:6]
        if _sf_top:
            st.markdown(
                "<div style='display:flex;align-items:center;gap:10px;"
                "margin-top:18px;margin-bottom:6px'>"
                "<span style='font-size:1.15rem;font-weight:900;"
                "background:linear-gradient(135deg,#5b8eff,#8b5cf6);"
                "-webkit-background-clip:text;-webkit-text-fill-color:"
                "transparent;background-clip:text;letter-spacing:-0.02em'>"
                "🔭 SETUPS FORMING</span>"
                "<span style='color:#aab;font-size:0.78rem'>"
                f"direction intel · {len(_sf_top)} forming · NOT openable</span>"
                "</div>",
                unsafe_allow_html=True)
            st.caption(
                "Coins where reversal pre-conditions are forming "
                "(approach to level, RSI extreme, volume waning, body "
                "shrinkage, EMA extension, CVD divergence, intra-bar "
                "rejection). **Watch these** — when the actual candle "
                "prints, the coin moves into **BEST TRADES NOW** above.")
            for _sf in _sf_top:
                _sf_side = _sf["side"]
                _sf_color = ("#ff3d57" if _sf_side == "SHORT"
                             else "#00e676")
                _sf_emoji = "🩸" if _sf_side == "SHORT" else "🟢"
                _sf_tier = ("STRONG" if _sf["score"] >= 80 else "WATCH")
                _sf_tier_color = ("#ff9500" if _sf["score"] >= 80
                                  else "#5b8eff")
                _sf_watch = ("bearish reversal (shooting star, evening "
                             "star, engulfing)" if _sf_side == "SHORT"
                             else "bullish reversal (hammer, morning "
                                  "star, engulfing)")
                _sf_pct = _sf.get("pct_24h", 0)
                _sf_pct_color = ("#2ed47a" if _sf_pct > 0
                                 else "#ff5c5c" if _sf_pct < 0
                                 else "#888")
                st.markdown(
                    f"<div style='display:flex;align-items:center;"
                    f"gap:8px;flex-wrap:wrap;padding:6px 12px;"
                    f"background:rgba(255,255,255,0.02);"
                    f"border:1px solid rgba(91,142,255,0.10);"
                    f"border-radius:8px;margin-bottom:4px'>"
                    f"<span style='font-weight:800;font-size:0.94rem;"
                    f"min-width:60px'>{_sf['base']}</span>"
                    f"<span style='background:{_sf_color};color:#06121f;"
                    f"padding:2px 8px;border-radius:5px;font-size:"
                    f"0.7rem;font-weight:800'>{_sf_emoji} "
                    f"{_sf_side} forming</span>"
                    f"<span style='background:{_sf_tier_color}33;"
                    f"color:{_sf_tier_color};padding:2px 8px;"
                    f"border-radius:5px;font-size:0.7rem;font-weight:"
                    f"700'>🔭 {_sf_tier} · {_sf['score']:.0f}</span>"
                    f"<span style='color:#aab;font-size:0.74rem'>"
                    f"{_sf['conditions_met']}/7 conditions</span>"
                    f"<span style='color:#888;font-size:0.74rem'>·</span>"
                    f"<span style='color:#888;font-size:0.74rem'>"
                    f"${_sf['price']:.4g} · "
                    f"<span style='color:{_sf_pct_color}'>"
                    f"{_sf_pct:+.2f}%</span></span>"
                    f"<span style='flex:1;color:#888;font-size:0.72rem;"
                    f"text-align:right'>watch for: {_sf_watch}</span>"
                    f"</div>",
                    unsafe_allow_html=True)

        # ---- 🩸 Top SHORT setups DISABLED per user (folded into BEST TRADES) ---
        _short_universe = []
        _short_scored = []
        for s in _short_universe:
            try:
                em = load_early_momentum(s["symbol"], timeframe)
                dv = load_derivatives_velocity(s["symbol"], timeframe)
            except Exception:
                continue
            comps = em.get("components") or {}
            # Sum short-side strengths from components that backtest showed
            # have edge. Each "short strength" = max(0, 50 - component_score)
            # — so a CVD short at score 12 contributes 38 strength.
            short_signals = []
            short_strength = 0.0
            cvd = comps.get("cvd_divergence") or {}
            if cvd.get("side") == "SHORT" and cvd.get("score", 50) <= 35:
                s_str = max(0, 50 - float(cvd["score"]))
                short_strength += s_str * 0.30  # cvd has highest edge
                short_signals.append(f"CVD div ({cvd['score']:.0f})")
            sq = comps.get("ttm_squeeze") or {}
            if sq.get("side") == "SHORT" and sq.get("score", 50) <= 35:
                s_str = max(0, 50 - float(sq["score"]))
                short_strength += s_str * 0.20
                short_signals.append(f"Squeeze ({sq['score']:.0f})")
            vw = comps.get("vwap_reclaim") or {}
            if vw.get("side") == "SHORT" and vw.get("score", 50) <= 35:
                s_str = max(0, 50 - float(vw["score"]))
                short_strength += s_str * 0.25
                short_signals.append(f"VWAP loss ({vw['score']:.0f})")
            sm = comps.get("smc_sweep") or {}
            if sm.get("side") == "SHORT" and sm.get("score", 50) <= 35:
                # SMC SHORT was near-baseline in the backtest — small weight
                s_str = max(0, 50 - float(sm["score"]))
                short_strength += s_str * 0.10
                short_signals.append(f"SMC sweep ({sm['score']:.0f})")
            # Derivatives velocity bullish flip (contrarian short — funding
            # flipping positive means longs piling in → squeeze down).
            if dv.get("side") == "SHORT" and dv.get("score", 50) <= 35:
                d_str = max(0, 50 - float(dv["score"]))
                short_strength += d_str * 0.15
                short_signals.append(f"Funding flip ({dv['score']:.0f})")
            if short_strength >= 8 and len(short_signals) >= 2:
                _short_scored.append({
                    "symbol": s["symbol"], "base": s["base"],
                    "strength": short_strength,
                    "signals": short_signals,
                    "em_score": em.get("score", 50),
                    "price": prices.get(s["symbol"]),
                    "setup": s,
                })
        _short_scored.sort(key=lambda x: x["strength"], reverse=True)
        _top_shorts = _short_scored[:6]

        if not _top_shorts:
            st.info(
                "No SHORT setups with strong aligned signals right now. "
                "This is the normal state during early-up moves — the "
                "early-momentum SHORT components only fire at tops and "
                "failing rallies. Check back when BTC stalls or hits a "
                "key resistance.")
        else:
            st.caption(
                f"Found **{len(_top_shorts)}** SHORT candidates with "
                "multiple aligned signals.")
            st.caption(
                "**Strength tiers** — STRONG ≥20 (high conviction, "
                "click 📥 confidently), MODERATE 12-19 (mild conviction, "
                "lighter size), WEAK <12 (hidden from board). The number "
                "is total signal contribution (each firing signal adds "
                "weight × deviation from neutral).")
            for _s in _top_shorts:
                _str = _s["strength"]
                _str_color = ("#ff5c5c" if _str >= 20
                              else "#e0a92b" if _str >= 12 else "#8b8d98")
                _str_label = ("STRONG" if _str >= 20
                              else "MODERATE" if _str >= 12 else "WEAK")
                _short_sid = f"short_{_s['symbol']}"
                # --- Trade plan extraction (same data the main board uses)
                _setup = _s["setup"]
                _entry_plan = float(_setup.get("entry_low")
                                    or _setup.get("entry") or 0)
                _stop_plan = float(_setup.get("stop") or 0)
                _tgt_plan = float(_setup.get("target") or 0)
                _rr_plan = float(_setup.get("rr") or 0)
                _hold_horiz = _hold_horizon(timeframe)
                _cur_short = _s.get("price") or _entry_plan
                # SHORT math: stop ABOVE entry, target BELOW entry.
                # risk_pct = stop / entry - 1 (positive %)
                # reward_pct = 1 - target / entry (positive %)
                if _entry_plan > 0 and _stop_plan > 0 and _tgt_plan > 0:
                    _risk_pct_short = (_stop_plan - _entry_plan) / _entry_plan * 100
                    _reward_pct_short = (_entry_plan - _tgt_plan) / _entry_plan * 100
                else:
                    _risk_pct_short = 0.0
                    _reward_pct_short = 0.0
                # Live R:R from current price
                _live_risk_short = ((_stop_plan - _cur_short) / _cur_short * 100
                                    if _cur_short > 0 and _stop_plan > 0 else 0.0)
                _live_reward_short = ((_cur_short - _tgt_plan) / _cur_short * 100
                                      if _cur_short > 0 and _tgt_plan > 0 else 0.0)
                _live_rr_short = (_live_reward_short / _live_risk_short
                                  if _live_risk_short > 0 else 0.0)
                # Position-size preview — same conviction-scaled formula
                # as Pattern Scout cards. Notional $1000-$2500 by strength,
                # hard cap $3000. Strength here is the "strength" score
                # (0-50 range) — map to 0-100 equivalent for consistency.
                _str_as_score = 65.0 + (_str / 50.0) * 35.0  # str 0->65, str 50->100
                _strength_factor_preview = max(0.4, min(1.0, _str / 30.0))
                _bal = float(pb_state.get("balance") or 0)
                _risk_pct_setting = float(
                    pb_state.get("risk_per_trade_pct") or 1.0)
                _lev_setting = float(pb_state.get("leverage") or 3.0)
                _risk_dollars = _bal * _risk_pct_setting / 100.0
                _stop_dist = abs(_stop_plan - _entry_plan) or 1.0
                _qty_riskbased = _risk_dollars / _stop_dist if _stop_dist > 0 else 0.0
                _notional_riskbased = _qty_riskbased * _entry_plan
                # Conviction-scaled target
                _target_notional = 1000.0 + (
                    (_str_as_score - 65) / 30.0) * 1500.0
                _target_notional = max(1000.0, min(2500.0, _target_notional))
                # Hard cap $3000
                _notional_est = min(_notional_riskbased, _target_notional, 3000.0)
                _qty_est = (_notional_est / _entry_plan
                            if _entry_plan > 0 else 0.0)
                _margin_est = (_notional_est / _lev_setting
                               if _lev_setting > 0 else _notional_est)
                _profit_est = _qty_est * abs(_entry_plan - _tgt_plan)
                _loss_est = _qty_est * abs(_stop_plan - _entry_plan)

                # Live R:R chip
                _short_rr_chip = ""
                if _live_rr_short >= 1.3:
                    _short_rr_chip = (
                        f"<span style='background:#2ed47a33;color:#2ed47a;"
                        f"padding:2px 8px;border-radius:5px;font-size:"
                        f"0.7rem;font-weight:700;margin-left:4px'>"
                        f"✓ At entry zone · live R:R {_live_rr_short:.2f}"
                        f"</span>")
                elif 0 < _live_rr_short < 1.2:
                    _short_rr_chip = (
                        f"<span style='background:#ff5c5c33;color:#ff5c5c;"
                        f"padding:2px 8px;border-radius:5px;font-size:"
                        f"0.7rem;font-weight:700;margin-left:4px'>"
                        f"⚠ Entry passed · live R:R {_live_rr_short:.2f}"
                        f"</span>")
                with st.container(border=True):
                    _txt_col, _btn_col = st.columns([6, 1])
                    _txt_col.markdown(
                        # Header row
                        f"<div style='display:flex;align-items:center;"
                        f"gap:8px;flex-wrap:wrap'>"
                        f"<span style='font-weight:800;font-size:1.05rem'>"
                        f"{_s['base']}</span>"
                        f"<span style='background:#ff5c5c;color:#06121f;"
                        f"padding:2px 10px;border-radius:5px;font-size:"
                        f"0.72rem;font-weight:800'>🩸 SHORT</span>"
                        f"<span style='background:{_str_color}33;"
                        f"color:{_str_color};padding:2px 8px;border-radius:"
                        f"5px;font-size:0.72rem;font-weight:700'>"
                        f"{_str_label} · strength {_str:.0f}/50</span>"
                        f"{_short_rr_chip}"
                        f"<span style='color:#8b8d98;font-size:0.78rem'>"
                        f"em-score {_s['em_score']:.0f}</span>"
                        f"</div>"
                        # Trade plan row (entry/stop/target with %)
                        f"<div style='color:#aab;font-size:0.80rem;"
                        f"margin-top:8px;line-height:1.6'>"
                        f"hold: <b>{_hold_horiz}</b> · now "
                        f"<b>{fmt_price(_cur_short)}</b> · entry "
                        f"<b>{fmt_price(_entry_plan)}</b> · "
                        f"stop <b>{fmt_price(_stop_plan)}</b> "
                        f"<span style='color:#ff5c5c'>"
                        f"(+{_risk_pct_short:.1f}%)</span> · "
                        f"target <b>{fmt_price(_tgt_plan)}</b> "
                        f"<span style='color:#2ed47a'>"
                        f"(−{_reward_pct_short:.1f}%)</span> · "
                        f"plan R:R <b>{_rr_plan:.2f}</b>"
                        f"</div>"
                        # Position-size preview row
                        f"<div style='background:rgba(0,212,255,0.05);"
                        f"border:1px solid rgba(0,212,255,0.15);"
                        f"border-radius:8px;padding:8px 12px;"
                        f"margin-top:8px;color:#c8d2ed;"
                        f"font-size:0.78rem;line-height:1.6'>"
                        f"<b style='color:#00d4ff'>📥 If you click NOW:</b> "
                        f"<b>{_qty_est:.4f}</b> {_s['base']} short · "
                        f"notional <b>${_notional_est:,.0f}</b> · "
                        f"<b>{_lev_setting:.0f}x</b> leverage · "
                        f"margin <b>${_margin_est:,.0f}</b> · "
                        f"risk <b style='color:#ff5c5c'>"
                        f"-${_loss_est:,.2f}</b> · "
                        f"profit at TP <b style='color:#2ed47a'>"
                        f"+${_profit_est:,.2f}</b>"
                        f"</div>"
                        # Signals row
                        f"<div style='color:#aab;font-size:0.78rem;"
                        f"margin-top:6px'>"
                        f"<b>Signals firing:</b> "
                        + " · ".join(_s["signals"])
                        + "</div>",
                        unsafe_allow_html=True)
                    # 📥 Open trade button — opens the paper short trade
                    # directly from this card. Uses the underlying setup
                    # dict from the scanner (which has the same SHORT
                    # entry/stop/target plan as the main picks board
                    # would have used).
                    if _btn_col.button("📥", key=f"pb_short_{_short_sid}",
                                       help=(f"Open SHORT {_s['base']} "
                                             "paper trade at TP1"),
                                       use_container_width=True):
                        _open_setup = dict(_s["setup"])
                        # Strength factor scales position size — STRONG
                        # gets larger size, MODERATE smaller, mirroring
                        # the strength-tier semantics.
                        _strength_factor = max(0.4, min(1.0, _str / 30.0))
                        _open_setup["strength_factor"] = _strength_factor
                        _open_price = (prices.get(_s["symbol"])
                                       or _open_setup.get("entry_low"))
                        _opened = paper_bot.open_position(
                            pb_state, _open_setup, _open_price)
                        if _opened:
                            _enrich_position(
                                _opened,
                                int(min(99, max(0, _str * 4))),
                                timeframe)
                            paper_bot.save_state(PAPER_BOT_FILE, pb_state)
                            st.toast(
                                f"📥 Opened SHORT {_opened['base']} @ "
                                f"{fmt_price(_opened['entry'])} · "
                                f"strength {_str:.0f}",
                                icon="🩸")
                            st.rerun()
                        else:
                            st.warning(
                                f"Could not open SHORT {_s['base']} — "
                                "the paper bot rejected the position. "
                                "Usually means: insufficient balance, "
                                "max-concurrent hit, or symbol already "
                                "in open positions.")
                    st.caption(
                        f"💡 Historical edge of the proven SHORT components: "
                        f"CVD div 67% win, VWAP loss 62%, Squeeze SHORT 57% "
                        f"(over 12 bars, backtest n=131-92 across top-19 "
                        f"coins). Click 📥 to open as paper trade — "
                        f"position size scales with strength.")

        st.divider()
        # Open positions — LIVE fragment (updates in place every 10s).
        _live_paper_positions()

    st.divider()

    # ---- Equity curve ----------------------------------------------------
    if pb_state["closed"]:
        cs_sorted = sorted(pb_state["closed"],
                           key=lambda c: c.get("exit_at", 0))
        bal = float(pb_state["starting_balance"])
        eq_rows = [{"Time": datetime.fromtimestamp(
                        cs_sorted[0].get("exit_at", 0),
                        tz=timezone.utc),
                    "Equity": bal}]
        for c in cs_sorted:
            bal += float(c.get("pnl_usd") or 0.0)
            eq_rows.append({
                "Time": datetime.fromtimestamp(
                    c.get("exit_at", 0), tz=timezone.utc),
                "Equity": round(bal, 2),
            })
        st.markdown("#### 📈 Equity curve")
        st.line_chart(pd.DataFrame(eq_rows).set_index("Time"),
                      use_container_width=True, height=240)

    # ---- Closed trades history -------------------------------------------
    _ct_head, _ct_dl = st.columns([6, 1])
    _ct_head.markdown(
        f"#### 📜 Closed trades ({len(pb_state['closed'])})")
    if pb_state["closed"]:
        cs_recent = sorted(pb_state["closed"],
                           key=lambda c: c.get("exit_at", 0),
                           reverse=True)[:80]
        closed_rows = [{
            "Coin": c.get("base", ""),
            "Side": c.get("side", ""),
            "Entry": fmt_price(c.get("entry", 0)),
            "Exit": fmt_price(c.get("exit", 0)),
            "Qty": round(c.get("qty", 0) or 0, 6),
            "Notional $": round(
                (c.get("notional")
                 or (c.get("qty", 0) or 0) * (c.get("entry", 0) or 0)),
                2),
            "Reason": c.get("exit_reason", ""),
            "PnL $": c.get("pnl_usd", 0.0),
            "PnL %": c.get("pnl_pct", 0.0),
            "Conf": c.get("confidence", 0),
            "Closed (UTC)": datetime.fromtimestamp(
                c.get("exit_at", 0), tz=timezone.utc).strftime(
                    "%Y-%m-%d %H:%M"),
        } for c in cs_recent]
        _ct_df = pd.DataFrame(closed_rows)
        # Full-detail export (all trades, all fields including timeframe,
        # confidence, rr, original_stop, etc.) for analytical use. The
        # on-screen table above is a curated view; this CSV is the raw
        # log so I can analyse what actually worked.
        _ct_full = pd.DataFrame(pb_state["closed"])
        _ct_dl.download_button(
            "⬇ CSV", data=_ct_full.to_csv(index=False).encode("utf-8"),
            file_name="closed_trades.csv", mime="text/csv",
            use_container_width=True,
            help="Download every closed trade with all fields for "
                 "deeper analysis (win-rate per tier, R metrics, etc.)")
        st.dataframe(_ct_df, use_container_width=True, hide_index=True)
    else:
        st.caption("No closed trades yet — they appear here once a position "
                   "hits a stop, target, or you close it manually.")

    st.caption("Paper trading idealises execution — no slippage, fees or "
               "partial fills. Use it to gauge whether the signals tend to "
               "win in the current regime; real-money results will be a "
               "little worse. Educational only, not financial advice.")

    # ---- Live mode — only the 10-min hard refresh now -------------------
    # The Bank stats and Open positions sections already update in place
    # every 10s via st.fragment — no full page reload needed for live P&L.
    # Live mode triggers a 3-minute full page refresh — the sweet spot
    # between freshness and not hammering the API. Cadence:
    #   - Live fragments (P&L, positions): every 10 sec
    #   - Full page reload: every 180 sec
    #   - Scanner cache (120s) hits fresh on every other reload
    #   - Pattern Scout cache (600s) refreshes every ~3-4 reloads
    if live_mode:
        # Visual indicator with pulsing dot so user knows live mode is on
        st.markdown(
            "<div style='display:flex;align-items:center;gap:8px;"
            "padding:6px 14px;background:rgba(255,61,87,0.08);"
            "border:1px solid rgba(255,61,87,0.20);border-radius:10px;"
            "margin-top:8px;width:fit-content;'>"
            "<span class='pulse' style='display:inline-block;width:8px;"
            "height:8px;background:#ff3d57;border-radius:50%;'></span>"
            "<span style='color:#ff3d57;font-size:0.78rem;font-weight:700'>"
            "🔴 LIVE MODE</span>"
            "<span style='color:#aab;font-size:0.78rem'>"
            "page auto-refreshes every 3 min · Pattern Scout re-scans every "
            "10 min · live position P&amp;L updates every 10s</span>"
            "</div>",
            unsafe_allow_html=True)
        _inject_autorefresh(180)


# ===========================================================================
# Tab 9 — Live Trading (real money on Bybit)
# ===========================================================================
if active_section == "💸 Live Trading":
    st.subheader("💸 Live Trading — Bybit USDT-Perp")

    # --- Big red REAL MONEY banner + testnet mode notice ------------------
    if config.BYBIT_TESTNET:
        st.warning(
            "🟡 **TESTNET MODE** — orders route to Bybit's demo server. "
            "No real money is at stake. Flip `BYBIT_TESTNET=false` in "
            "your `.env` (and reboot) to switch to real-money live.")
    else:
        st.error(
            "⚠️ **REAL MONEY MODE** — every trade you open here uses real "
            "USDT on your Bybit account. The bot suggests; YOU confirm.")

    _live_ready, _live_info = lb.is_ready()

    # --- Missing-keys / dependency gate -----------------------------------
    if not _live_ready:
        st.info(
            "**Live Trading isn't connected yet.** This tab needs Bybit "
            "API credentials before it can place any orders.")
        with st.expander("📖 Setup steps (one-time)", expanded=True):
            st.markdown("""
1. **Sign up at [bybit.com](https://www.bybit.com)** (or
   [testnet.bybit.com](https://testnet.bybit.com) for paper-money plumbing
   tests). Complete KYC — required for derivatives.
2. **Deposit ≥ $100 USDT** to your Unified Trading Account (or claim
   demo funds from the testnet faucet).
3. **Account → API Management → Create New Key** — System-generated:
   - Permissions: **Contract → Orders + Positions ON**
   - **Wallet → Transfers OFF, Withdrawals OFF** (critical safety)
   - **IP whitelist** your home IP (or a VPS IP if dynamic).
4. **Paste into `.env`** (gitignored) at the project root:
   ```
   BYBIT_API_KEY=...
   BYBIT_API_SECRET=...
   BYBIT_TESTNET=true       # start on testnet, set to false later
   ```
5. **Reinstall deps** so `pybit` is available:
   `pip install -r requirements.txt`.
6. **Restart Streamlit** — the gate clears once keys are detected.

**Cost** — the Bybit API itself is **free** (no subscription). The only
real cost is trading fees: ~0.055% taker / 0.02% maker on USDT-perp,
plus funding rate every 8 hours on open positions.
""")
        st.caption(f"Status: **{_live_info}** — fix the above and reload.")
        st.stop()

    # --- Helpers used by this section (mirror paper-bot patterns) ---------
    def _live_hold_horizon(tf):
        return {"15m": "a few hours",
                "1h": "1 day",
                "4h": "1-2 days",
                "1d": "1-2 days"}.get(tf, "1-2 days")

    def _live_strength_label(conf):
        if conf >= 80:
            return ("Very Strong", "#0b8a3e")
        if conf >= 70:
            return ("Strong", "#2ed47a")
        if conf >= 60:
            return ("Moderate", "#e0a92b")
        return ("Weak", "#8b8d98")

    # --- Load state + settings --------------------------------------------
    lb_state = lb.load_state(config.LIVE_BOT_STATE_PATH)
    _settings = lb_state.setdefault("settings", dict(config.LIVE_DEFAULTS))

    # --- Settings expander ------------------------------------------------
    with st.expander("⚙️ Settings — guardrails, leverage cap, auto-trade"):
        sc1, sc2, sc3 = st.columns(3)
        _new_lev_cap = sc1.slider(
            "Leverage cap (max)", 1, 25,
            int(_settings.get("leverage_cap", 20)),
            key="lb_lev_cap",
            help="Hard ceiling. The scaler ladder always stays at or below "
                 "this. Recommend 5x for Phase-3 live launch.")
        _new_notional_cap = sc2.slider(
            "Per-trade margin cap (% of balance)", 5, 50,
            int(_settings.get("notional_cap_pct", 30)),
            key="lb_notional_cap")
        _new_daily_loss = sc3.slider(
            "Daily loss limit (%) — halts auto", 5, 25,
            int(_settings.get("daily_loss_pct", 10)),
            key="lb_daily_loss")

        sc4, sc5, sc6 = st.columns(3)
        _new_max_conc = sc4.slider(
            "Max concurrent positions", 1, 5,
            int(_settings.get("max_concurrent", 3)),
            key="lb_max_conc")
        _new_slip = sc5.slider(
            "Slippage tolerance (%)", 0.1, 2.0,
            float(_settings.get("slippage_tol_pct", 0.5)), 0.1,
            key="lb_slip")
        _new_confirm_n = sc6.slider(
            "Confirm-first-N trades", 0, 30,
            int(_settings.get("confirm_first_n", 10)),
            key="lb_confirm_n",
            help="Even with auto-trade ON, the first N live trades still "
                 "require a manual click. Sets to 0 once you trust it.")

        sc7, sc8, sc9 = st.columns(3)
        _live_auto_trade = sc7.checkbox(
            "🤖 Auto-trade ON", value=False, key="lb_auto",
            help="When on AND past confirm-first-N, the bot auto-opens "
                 "very-strong signals. Use with 💎 Premium-only ON below "
                 "for safest auto-trading.")
        _new_auto_thresh = sc8.slider(
            "Auto-trade confidence threshold", 70, 99,
            int(_settings.get("auto_threshold", 85)),
            key="lb_auto_thresh")
        if sc9.button("🔄 Reset live state",
                      type="secondary", use_container_width=True):
            lb.reset(config.LIVE_BOT_STATE_PATH,
                     starting_balance=100.0, risk_pct=1.0,
                     settings=_settings)
            st.rerun()

        # Strict premium-only auto-gate (the "sure shot" filter).
        _new_premium_only = st.checkbox(
            "💎 Auto-trade PREMIUM-ONLY (sure-shot filter)",
            value=bool(_settings.get("auto_premium_only", True)),
            key="lb_auto_premium",
            help="When ON: auto-trade fires ONLY on setups that meet ALL "
                 "five strict criteria — scanner conf>=90, forecast "
                 "aligned 3/3 (direction match), radar stage COILED or "
                 "FRESH (NOT EXTENDED), live R:R>=1.3 (green zone), AND "
                 "not counter-trend. Expect 0-2 auto-fires per day at "
                 "best. The 💎 PREMIUM TRADEABLE chip on the picks "
                 "board shows which manual picks also pass this bar.")
        _new_premium_mult = st.slider(
            "💎 Premium risk multiplier",
            min_value=1.0, max_value=2.0, step=0.05,
            value=float(
                _settings.get("premium_risk_multiplier", 1.5)),
            key="lb_premium_mult",
            help="When you fire a 💎 PREMIUM TRADEABLE setup (manual OR "
                 "auto), the risk_per_trade_pct gets multiplied by this "
                 "factor. 1.0 = same as regular. 1.5 = 50% bigger "
                 "position. 2.0 = double (max — anything higher risks "
                 "account ruin on losing streaks). Recommended 1.5 for "
                 "small accounts.")

        # Persist settings tweaks back to state.
        _settings.update({
            "leverage_cap": _new_lev_cap,
            "notional_cap_pct": _new_notional_cap,
            "daily_loss_pct": _new_daily_loss,
            "max_concurrent": _new_max_conc,
            "slippage_tol_pct": _new_slip,
            "confirm_first_n": _new_confirm_n,
            "auto_threshold": _new_auto_thresh,
            "auto_premium_only": _new_premium_only,
            "premium_risk_multiplier": _new_premium_mult,
        })

        st.markdown(
            "<div style='background:#3a1818;border:1px solid #ff5c5c;"
            "padding:8px 12px;border-radius:5px;margin:8px 0'>"
            "<b style='color:#ff5c5c'>🛑 EMERGENCY STOP</b><br>"
            "<span style='color:#d5d7e0;font-size:0.85rem'>Closes EVERY "
            "open Bybit position at market and cancels all open orders. "
            "Two-click confirm.</span></div>", unsafe_allow_html=True)
        ec1, ec2 = st.columns([1, 1])
        _emerg_armed = st.session_state.get("lb_emerg_armed", False)
        if not _emerg_armed:
            if ec1.button("🛑 Arm emergency stop", type="secondary",
                          use_container_width=True):
                st.session_state["lb_emerg_armed"] = True
                st.rerun()
        else:
            if ec1.button("🛑 CONFIRM CLOSE ALL", type="primary",
                          use_container_width=True):
                try:
                    res = lb.emergency_stop_all(lb_state)
                    lb.save_state(config.LIVE_BOT_STATE_PATH, lb_state)
                    st.session_state["lb_emerg_armed"] = False
                    st.success(
                        f"🛑 Emergency stop fired — closed {res['n']} "
                        "position(s) at market.")
                except Exception as _exc:
                    st.error(f"Emergency stop failed: {_exc}")
            if ec2.button("Cancel", use_container_width=True):
                st.session_state["lb_emerg_armed"] = False
                st.rerun()

    # Persist settings every render so user tweaks survive.
    lb.save_state(config.LIVE_BOT_STATE_PATH, lb_state)

    # --- Live fragments — update in place every 10s -----------------------
    @st.fragment(run_every=10)
    def _live_live_stats():
        """Bank + trade stats, queried live from Bybit on each tick."""
        state = lb.load_state(config.LIVE_BOT_STATE_PATH)
        # Live prices for open positions
        live_p: dict[str, float] = {}
        for _p in state["open"]:
            _lp = live_price(_p["symbol"])
            live_p[_p["symbol"]] = (
                float(_lp) if _lp is not None and _lp > 0
                else float(_p["entry"]))

        # Live Bybit equity snapshot — authoritative source.
        acct = lb.account_balance()
        ex_equity = float(acct.get("equity") or 0.0)
        ex_avail = float(acct.get("available") or 0.0)
        ex_used = float(acct.get("used_margin") or 0.0)

        local_bal = float(state.get("balance") or 0.0)
        unreal = lb.unrealized_pnl(state, live_p)
        local_equity = local_bal + unreal
        realised_24h = lb.daily_realised_pnl(state)

        bc = st.columns(5)
        bc[0].metric(
            "💼 Bybit equity", f"${ex_equity:,.2f}",
            f"avail ${ex_avail:,.2f}",
            help="Live wallet equity from Bybit (authoritative).")
        bc[1].metric(
            "Available", f"${ex_avail:,.2f}",
            f"${ex_used:,.0f} used margin" if ex_used > 0 else "all free",
            help="Cash free to deploy on Bybit.")
        bc[2].metric(
            "Unrealised P&L", f"${unreal:+,.2f}",
            help="Mark-to-market across local open positions.")
        bc[3].metric(
            "Local equity (estimate)", f"${local_equity:,.2f}",
            f"${realised_24h:+,.2f} realised 24h",
            help="Local snapshot. The Bybit equity above is the truth.")
        sync_state = lb.sync_positions(state)
        sync_icon = "✓" if sync_state["drift"] == 0 else "⚠"
        bc[4].metric(
            f"{sync_icon} Sync", f"{sync_state['exchange_count']} on Bybit",
            (f"drift {sync_state['drift']}"
             if sync_state["drift"] else "in sync"))
        lb.save_state(config.LIVE_BOT_STATE_PATH, state)

        st_stats = lb.stats(state)
        sc = st.columns(5)
        sc[0].metric("Trades closed", st_stats["trades"])
        sc[1].metric("Win rate",
                     f"{st_stats['win_rate']:.0f}%"
                     if st_stats["trades"] else "—")
        sc[2].metric("Best trade",
                     f"{st_stats['best_trade']:+.2f}%"
                     if st_stats["trades"] else "—")
        sc[3].metric("Worst trade",
                     f"{st_stats['worst_trade']:+.2f}%"
                     if st_stats["trades"] else "—")
        sc[4].metric(
            "Trades opened total",
            int(state.get("trades_opened_total") or 0),
            help=("First-N rule: until trades_opened_total ≥ confirm_first_n "
                  "every open requires a manual confirm even in auto mode."))


    @st.fragment(run_every=10)
    def _live_live_positions():
        """Open Bybit positions, live-updating every 10s."""
        state = lb.load_state(config.LIVE_BOT_STATE_PATH)
        live_p: dict[str, float] = {}
        for _p in state["open"]:
            _lp = live_price(_p["symbol"])
            live_p[_p["symbol"]] = (
                float(_lp) if _lp is not None and _lp > 0
                else float(_p["entry"]))

        # Local evaluate is a backup; Bybit's exchange-side SL/TP fires
        # primarily.
        closed_now = lb.evaluate(state, live_p)
        for c in closed_now:
            emoji = "✅" if c["pnl_usd"] > 0 else "❌"
            st.toast(
                f"{emoji} {c['base']} closed @ {c['exit_reason']} · "
                f"{c['pnl_pct']:+.2f}%", icon="💸")
        if closed_now:
            lb.save_state(config.LIVE_BOT_STATE_PATH, state)

        st.markdown(f"### 📂 Live positions on Bybit ({len(state['open'])})")
        if not state["open"]:
            st.info(
                "No live positions. Use the panel on the left to open one, "
                "or click 📥 on a Bot's-top-picks card.")
            return

        for p in state["open"]:
            cur = live_p.get(p["symbol"], p["entry"])
            long = (p["side"] == "LONG")
            entry_v = float(p["entry"])
            stop_v = float(p["stop"])
            target_v = float(p["target"])
            qty_v = float(p["qty"])
            notional_v = float(p.get("notional") or (qty_v * entry_v))
            lev_v = int(p.get("leverage") or 1)
            unreal_pos = (((cur - entry_v) if long
                           else (entry_v - cur)) * qty_v)
            if entry_v > 0:
                pct_from_entry = ((cur - entry_v) / entry_v * 100)
                if not long:
                    pct_from_entry = -pct_from_entry
            else:
                pct_from_entry = 0.0
            color = "#2ed47a" if unreal_pos >= 0 else "#ff5c5c"
            side_color = "#2ed47a" if long else "#ff5c5c"

            with st.container(border=True):
                info_col, pnl_col, btn_col = st.columns([2.4, 1.8, 0.8])
                info_col.markdown(
                    f"<div style='font-size:1.05rem;font-weight:800'>"
                    f"{p['base']} "
                    f"<span style='background:{side_color};color:#06121f;"
                    f"padding:2px 10px;border-radius:5px;font-size:"
                    f"0.72rem;font-weight:800;margin-left:6px'>"
                    f"{p['side']}</span></div>"
                    f"<div style='color:#d5d7e0;font-size:0.84rem;"
                    f"margin:3px 0'>"
                    f"<b>{qty_v:.6f} {p['base']}</b> · "
                    f"notional <b>${notional_v:,.2f}</b> · "
                    f"<b>{lev_v}× lev</b></div>"
                    f"<div style='color:#8b8d98;font-size:0.78rem'>"
                    f"Entry {fmt_price(entry_v)} · Stop "
                    f"{fmt_price(stop_v)} · Target {fmt_price(target_v)}"
                    f"</div>",
                    unsafe_allow_html=True)
                pnl_col.markdown(
                    f"<div style='text-align:right;font-size:1.15rem;"
                    f"font-weight:800;color:#fff'>{fmt_price(cur)}</div>"
                    f"<div style='text-align:right;color:{color};"
                    f"font-size:1.1rem;font-weight:800'>"
                    f"${unreal_pos:+,.2f}</div>"
                    f"<div style='text-align:right;color:{color};"
                    f"font-size:0.78rem;font-weight:700'>"
                    f"{pct_from_entry:+.2f}% from entry</div>",
                    unsafe_allow_html=True)
                if btn_col.button("Close",
                                  key=f"lb_close_{p['symbol']}",
                                  use_container_width=True):
                    try:
                        closed = lb.close_position_at(
                            state, p["symbol"], cur, reason="manual")
                        if closed:
                            lb.save_state(config.LIVE_BOT_STATE_PATH,
                                          state)
                            emoji = ("✅" if closed["pnl_usd"] > 0
                                     else "❌")
                            st.toast(
                                f"{emoji} Closed {closed['base']} · "
                                f"{closed['pnl_pct']:+.2f}%", icon="💸")
                            st.rerun(scope="fragment")
                    except Exception as _exc:
                        st.error(f"Close failed: {_exc}")

    _live_live_stats()

    st.divider()

    # --- Two-column body: open-a-trade + bot picks + live positions -------
    lt_left, lt_right = st.columns([1, 2])

    with lt_left:
        st.markdown("### 📥 Open a live trade")
        if _alert_merged.empty:
            st.info("Scanner data not ready — refresh and try again.")
        else:
            _syms = sorted(_alert_merged["symbol"].unique().tolist())
            _open_syms_lt = {p["symbol"] for p in lb_state["open"]}
            _avail_lt = [s for s in _syms if s not in _open_syms_lt]
            if not _avail_lt:
                st.warning(
                    "You already have a live position in every tracked "
                    "coin — close one before opening another.")
            else:
                _sel_lt = st.selectbox(
                    "Coin", _avail_lt,
                    format_func=lambda s: s.replace("USDT", ""),
                    key="lb_sym")
                _side_lt = st.radio(
                    "Side", ["LONG", "SHORT"], horizontal=True,
                    key="lb_side")
                _row_lt = _alert_merged[
                    _alert_merged["symbol"] == _sel_lt].iloc[0]
                _cur_lt = float(_row_lt["price"])
                _plan_lt = (_row_lt.get("trade_plan")
                            if isinstance(_row_lt.get("trade_plan"), dict)
                            else None)
                _live_lp = live_price(_sel_lt)
                if _live_lp:
                    _cur_lt = float(_live_lp)

                # Live price card
                _chg_lt = (float(_row_lt.get("priceChangePercent") or 0.0))
                _chc = "#2ed47a" if _chg_lt >= 0 else "#ff5c5c"
                st.markdown(
                    f"<div style='background:#11141c;padding:10px 14px;"
                    f"border-radius:6px;margin:6px 0;"
                    f"border:1px solid #1f2330'>"
                    f"<div style='font-size:0.7rem;color:#8b8d98;"
                    f"letter-spacing:0.08em;font-weight:700'>"
                    f"LIVE PRICE · {_sel_lt}</div>"
                    f"<div style='font-size:1.4rem;font-weight:800;"
                    f"color:#fff'>{fmt_price(_cur_lt)} "
                    f"<span style='color:{_chc};font-size:0.85rem;"
                    f"font-weight:700'>{_chg_lt:+.2f}% 24h</span></div>"
                    f"</div>", unsafe_allow_html=True)

                # Engine-suggested stop / target (capped to 3-4%)
                if _plan_lt and _plan_lt.get("side") == _side_lt:
                    _stop_lt = float(_plan_lt["stop_loss"])
                    _target_lt = float(_plan_lt["take_profit"])
                else:
                    _stop_lt = _cur_lt * (0.97 if _side_lt == "LONG" else 1.03)
                    _target_lt = _cur_lt * (
                        1.04 if _side_lt == "LONG" else 0.96)

                _conf_lt = int(_row_lt.get("confidence") or 0)
                _rr_lt = (abs(_target_lt - _cur_lt) / abs(_cur_lt - _stop_lt)
                          if _cur_lt != _stop_lt else 0.0)

                _alert_lt = {
                    "symbol": _sel_lt, "base": _sel_lt.replace("USDT", ""),
                    "side": _side_lt, "stop": _stop_lt, "target": _target_lt,
                    "entry_low": _cur_lt, "confidence": _conf_lt,
                    "rr": _rr_lt,
                    "forecast_aligned": False,
                    "forecast_disagrees": False,
                }
                ok, reason, preview = lb.preflight(
                    lb_state, _alert_lt, _cur_lt)
                if not ok:
                    st.warning(f"⚠️ {reason}")
                else:
                    _lev = preview["leverage"]
                    _qty = preview["qty"]
                    _notional = preview["notional"]
                    _margin = preview["margin"]
                    _est_fee = preview["est_fee_round_trip"]
                    _sl_pct = abs((_cur_lt - _stop_lt) / _cur_lt * 100)
                    _tp_pct = abs((_target_lt - _cur_lt) / _cur_lt * 100)
                    _color = ("#2ed47a" if _side_lt == "LONG"
                              else "#ff5c5c")
                    st.markdown(
                        f"<div style='background:{_color}14;"
                        f"border-left:3px solid {_color};padding:8px 12px;"
                        f"border-radius:5px;margin:4px 0 10px 0;"
                        f"font-size:0.86rem'>"
                        f"Entry (market): <b>{fmt_price(_cur_lt)}</b><br>"
                        f"Stop: <b>{fmt_price(_stop_lt)}</b> "
                        f"({_sl_pct:.2f}% away)<br>"
                        f"Target: <b>{fmt_price(_target_lt)}</b> "
                        f"({_rr_lt:.2f}R, {_tp_pct:.2f}% away)<br>"
                        f"Leverage: <b>{_lev}×</b> "
                        f"(scaled from conf {_conf_lt})<br>"
                        f"Quantity: <b>{_qty:.6f} "
                        f"{_sel_lt.replace('USDT','')}</b><br>"
                        f"Notional: <b>${_notional:,.2f}</b> · "
                        f"Margin: <b>${_margin:,.2f}</b><br>"
                        f"Est. round-trip fees: ~${_est_fee:.2f}</div>",
                        unsafe_allow_html=True)

                    # Preview → Confirm two-step
                    _armed_key = f"lb_armed_{_sel_lt}_{_side_lt}"
                    armed = st.session_state.get(_armed_key, False)
                    if not armed:
                        if st.button(
                                f"📋 Preview {_side_lt} "
                                f"{_sel_lt.replace('USDT','')} order",
                                use_container_width=True,
                                key=f"lb_preview_btn_{_sel_lt}_{_side_lt}"):
                            st.session_state[_armed_key] = True
                            st.rerun()
                    else:
                        st.markdown(
                            f"<div style='background:#3a2a18;"
                            f"border:1px solid #e0a92b;padding:8px 12px;"
                            f"border-radius:5px;margin:4px 0;"
                            f"font-size:0.84rem;color:#e0a92b;"
                            f"font-weight:700'>"
                            f"⚠️ Click CONFIRM to send this order to "
                            f"Bybit. This is real money "
                            f"{'(testnet)' if config.BYBIT_TESTNET else ''}."
                            f"</div>", unsafe_allow_html=True)
                        bc1, bc2 = st.columns(2)
                        if bc1.button(
                                f"✅ CONFIRM open {_lev}×",
                                type="primary",
                                use_container_width=True,
                                key=f"lb_confirm_btn_{_sel_lt}_{_side_lt}"):
                            try:
                                opened = lb.open_position(
                                    lb_state, _alert_lt, _cur_lt,
                                    confirmed=True)
                                if opened:
                                    lb.save_state(
                                        config.LIVE_BOT_STATE_PATH, lb_state)
                                    st.session_state[_armed_key] = False
                                    st.toast(
                                        f"📥 OPENED {_side_lt} "
                                        f"{opened['base']} @ "
                                        f"{fmt_price(opened['entry'])} · "
                                        f"{_lev}×", icon="💸")
                                    st.rerun()
                            except lb.ConfigError as _exc:
                                st.error(str(_exc))
                                st.session_state[_armed_key] = False
                            except Exception as _exc:
                                st.error(f"Order failed: {_exc}")
                                st.session_state[_armed_key] = False
                        if bc2.button("Cancel",
                                      use_container_width=True,
                                      key=f"lb_cancel_btn_{_sel_lt}_{_side_lt}"):
                            st.session_state[_armed_key] = False
                            st.rerun()

    with lt_right:
        st.markdown("### 🤖 Bot's top picks (live-eligible)")
        st.caption(
            "Same signals as the Paper Trader, filtered to only the "
            "very-strong setups suitable for real money. The Preview→"
            "Confirm flow applies even when auto-trade is ON for the "
            "first N trades.")
        # Pull forecast + radar lookups (cached) so the live picks use the
        # SAME intelligence stack as the paper trader picks board:
        # Scanner + Forecast + Weekly trend + BTC outlook + Maturity +
        # Radar stage. Real money deserves the full picture.
        _fc_by_sym_lt: dict[str, dict] = {}
        _radar_by_sym_lt: dict[str, dict] = {}
        try:
            _fc_tickers_lt = load_top_symbols(top_n)
            _fc_syms_lt = tuple(_fc_tickers_lt["symbol"].head(40))
            _fc_df_lt = forecast_market(_fc_syms_lt)
            if _fc_df_lt is not None and not _fc_df_lt.empty:
                _fc_by_sym_lt = {r["symbol"]: r.to_dict()
                                 for _, r in _fc_df_lt.iterrows()}
            _radar_df_lt, _ = scan_breakouts(_fc_syms_lt, "imminent")
            if _radar_df_lt is not None and not _radar_df_lt.empty:
                _radar_by_sym_lt = {r["symbol"]: r.to_dict()
                                    for _, r in _radar_df_lt.iterrows()}
        except Exception:
            pass

        # BTC outlook for the macro-context tilt (same as paper).
        _lt_btc: dict = {}
        try:
            _lt_btc = btc_outlook_now(_btc_change, _alt_median)
        except Exception:
            pass
        _lt_btc_dir = (_lt_btc.get("direction") or "").lower()
        _lt_btc_conf = float(_lt_btc.get("confidence") or 0)
        _lt_btc_tilt = _lt_btc_conf >= 60 and _lt_btc_dir in (
            "bullish", "bearish")

        def _live_combined_score(setup: dict, lt_align: str) -> float:
            """Mirror of the paper picks combined score so live testnet
            uses identical intelligence: scanner + forecast + weekly
            trend + BTC outlook + maturity + radar stage."""
            score = float(setup.get("confidence") or 0)
            # Forecast tilt
            fc = _fc_by_sym_lt.get(setup.get("symbol")) or {}
            fc_word = fc.get("outlook_word")
            fc_conf = float(fc.get("confidence") or 0)
            aligned = bool(fc.get("aligned"))
            side = setup["side"]
            confirms = ((side == "LONG" and fc_word == "Bullish")
                        or (side == "SHORT" and fc_word == "Bearish"))
            disagrees = ((side == "LONG" and fc_word == "Bearish")
                         or (side == "SHORT" and fc_word == "Bullish"))
            if confirms:
                score += 10
                if aligned:
                    score += 8
                if fc_conf >= 70:
                    score += 5
            elif disagrees:
                score -= 8
            # Weekly trend (already computed as lt_align)
            if lt_align == "aligned":
                score += 5
            elif lt_align == "counter":
                score -= 8
            # BTC outlook
            if _lt_btc_tilt:
                if ((_lt_btc_dir == "bullish" and side == "LONG")
                        or (_lt_btc_dir == "bearish" and side == "SHORT")):
                    score += 4
                elif ((_lt_btc_dir == "bullish" and side == "SHORT")
                      or (_lt_btc_dir == "bearish" and side == "LONG")):
                    score -= 4
            # Maturity
            _mat = (setup.get("maturity") or {})
            _mat_label = str(_mat.get("label") or "").upper()
            if _mat_label == "EARLY":
                score += 6
            elif _mat_label == "EXTENDED":
                score -= 10
            # Radar stage (flat, no direction overlap with forecast)
            _r = _radar_by_sym_lt.get(setup.get("symbol")) or {}
            _stg = str(_r.get("stage") or "").upper()
            if _stg == "COILED":
                score += 6
            elif _stg == "FRESH":
                score += 3
            elif _stg == "EXTENDED":
                score -= 8
            return score

        _open_syms_lt = {p["symbol"] for p in lb_state["open"]}
        # Re-entry detection — coins that closed within the last 60 min
        # AND re-qualify as setups now (price pulled back into entry
        # zone, or a fresh continuation). Same definition as paper.
        _now_ts_lt = time.time()
        _recent_close_syms_lt = {
            c["symbol"]
            for c in (lb_state.get("closed") or [])[-30:]
            if (_now_ts_lt - (c.get("exit_at") or 0)) < 3600
        }
        # Bybit-tradeable filter — signal data comes from Binance but
        # orders go to Bybit. Some Binance-listed coins aren't available
        # as USDT-perp on Bybit (or are delisted, e.g. LUNAUSDT). Drop
        # those from the picks board so the user never clicks a card
        # that can't actually trade.
        _bybit_tradeable = lb.tradeable_symbols()
        _live_eligible = []
        for s in auto_ad["setups"]:
            if s["symbol"] in _open_syms_lt:
                continue
            # Skip coins not actively trading on Bybit USDT-perp.
            if _bybit_tradeable and s["symbol"] not in _bybit_tradeable:
                continue
            # Higher-TF trend filter — real money is stricter than paper.
            # Counter-trend setups are dropped entirely unless they pack a
            # very high (>= 88) scanner confidence.
            _lt_trend = htf_trend(s["symbol"])
            _lt_align = htf_alignment(s["side"], _lt_trend)
            if (_lt_align == "counter"
                    and int(s.get("confidence", 0) or 0) < 88):
                continue
            ok_pf, _, _prev = lb.preflight(lb_state, s,
                                            prices.get(s["symbol"])
                                            or s.get("entry_low"))
            if not ok_pf:
                continue
            _combined_lt = _live_combined_score(s, _lt_align)
            # Combined-score gate is the quality filter on the live
            # board: only Very Strong (>= 80) picks pass. RED entry-
            # passed cards still show when their combined score clears
            # the bar — the chips on each card (entry-zone status,
            # COILED, live R:R) let the user judge per pick. The user
            # explicitly asked for this — entry-passed setups with
            # strong underlying scores can still be tradeable.
            if _combined_lt < 80:
                continue
            _live_eligible.append(
                (_prev["leverage"], _lt_align, s, _combined_lt))
        # Sort by combined score (uncapped) so the strongest fused
        # signal rises to the top — same ranking as paper picks.
        _live_eligible.sort(key=lambda t: t[3], reverse=True)

        if not _live_eligible:
            st.info(
                "No live-eligible picks right now (combined ≥ 80 "
                "required). The board waits for high-conviction setups. "
                "Check the Paper Trader tab for the broader signal "
                "universe, or wait for the next scan.")
        else:
            for _lev, _lt_align, s, _combined_lt in _live_eligible[:6]:
                side = s["side"]
                side_col = "#2ed47a" if side == "LONG" else "#ff5c5c"
                conf = int(s.get("confidence", 0) or 0)
                # Strength label uses the COMBINED score now (same as
                # paper) so cards reflect the full fused intelligence,
                # not just raw scanner conf. Display caps to 99.
                _combined_disp = int(min(99, max(0, _combined_lt)))
                str_label, str_col = _live_strength_label(_combined_disp)

                # 🏆 PREMIUM tier — conf >= 80 AND forecast aligned 3/3.
                _fc_lt = _fc_by_sym_lt.get(s["symbol"]) or {}
                _fc_word_lt = _fc_lt.get("outlook_word")
                _is_premium = (
                    conf >= 80
                    and bool(_fc_lt.get("aligned"))
                    and ((side == "LONG" and _fc_word_lt == "Bullish")
                         or (side == "SHORT" and _fc_word_lt == "Bearish")))
                _premium_chip_lt = ""
                if _is_premium:
                    _premium_chip_lt = (
                        f"<span style='background:linear-gradient(90deg,"
                        f"#e0a92b,#ffd700);color:#1a1a1a;"
                        f"padding:2px 10px;border-radius:5px;font-size:"
                        f"0.72rem;font-weight:800;margin-left:4px;"
                        f"box-shadow:0 0 8px #e0a92b66'>"
                        f"🏆 PREMIUM</span>")

                # Radar STAGE chip (same definition as paper).
                _r_lt = _radar_by_sym_lt.get(s["symbol"]) or {}
                _stg_lt = str(_r_lt.get("stage") or "").upper()
                _coiled_chip_lt = ""
                if _stg_lt == "COILED":
                    _coiled_chip_lt = (
                        f"<span style='background:#6e8bff33;color:#6e8bff;"
                        f"padding:2px 8px;border-radius:5px;font-size:"
                        f"0.7rem;font-weight:800;margin-left:4px'>"
                        f"🌀 COILED · loaded</span>")
                elif _stg_lt == "FRESH":
                    _coiled_chip_lt = (
                        f"<span style='background:#2ed47a22;color:#2ed47a;"
                        f"padding:2px 8px;border-radius:5px;font-size:"
                        f"0.7rem;font-weight:700;margin-left:4px'>"
                        f"⚡ FRESH · breaking out</span>")
                elif _stg_lt == "EXTENDED":
                    _coiled_chip_lt = (
                        f"<span style='background:#8b8d9833;color:#8b8d98;"
                        f"padding:2px 8px;border-radius:5px;font-size:"
                        f"0.7rem;font-weight:700;margin-left:4px'>"
                        f"📉 EXTENDED · move spent</span>")

                # ↻ Re-entry chip — coin closed within the last 60 min
                # and re-qualifies as a setup (second-leg opportunity).
                _reentry_chip_lt = ""
                if s["symbol"] in _recent_close_syms_lt:
                    _reentry_chip_lt = (
                        f"<span style='background:#e0a92b33;color:#e0a92b;"
                        f"padding:2px 8px;border-radius:5px;font-size:"
                        f"0.7rem;font-weight:700;margin-left:4px'>"
                        f"↻ Re-entry available</span>")

                # Live R:R from current price (mirror of paper logic).
                _cur_lt = (prices.get(s["symbol"])
                           or float(s.get("entry_low") or 0))
                _stop_lt = float(s.get("stop") or 0)
                _tgt_lt = float(s.get("target") or 0)
                _live_risk_lt = 0.0
                _live_reward_lt = 0.0
                _live_rr_lt = 0.0
                if _cur_lt and _stop_lt and _tgt_lt:
                    if side == "LONG":
                        _live_risk_lt = (_cur_lt - _stop_lt) / _cur_lt * 100
                        _live_reward_lt = (_tgt_lt - _cur_lt) / _cur_lt * 100
                    else:
                        _live_risk_lt = (_stop_lt - _cur_lt) / _cur_lt * 100
                        _live_reward_lt = (_cur_lt - _tgt_lt) / _cur_lt * 100
                    if _live_risk_lt > 0:
                        _live_rr_lt = _live_reward_lt / _live_risk_lt
                _drift_chip_lt = ""
                if _live_rr_lt >= 1.3:
                    _drift_chip_lt = (
                        f"<span style='background:#2ed47a33;color:#2ed47a;"
                        f"padding:2px 8px;border-radius:5px;font-size:"
                        f"0.7rem;font-weight:700;margin-left:4px'>"
                        f"✓ At entry zone · R:R {_live_rr_lt:.2f}</span>")
                elif 0 < _live_rr_lt < 1.2:
                    _drift_chip_lt = (
                        f"<span style='background:#ff5c5c33;color:#ff5c5c;"
                        f"padding:2px 8px;border-radius:5px;font-size:"
                        f"0.7rem;font-weight:700;margin-left:4px'>"
                        f"⚠ Entry passed · R:R {_live_rr_lt:.2f}</span>")

                # 💎 PREMIUM TRADEABLE chip — passes ALL 5 strict criteria
                # for the auto-trade "sure shot" filter. When this chip
                # is on, both auto-trade AND manual clicking are the
                # high-conviction choices. Most cards will NOT have it.
                _tradeable_chip_lt = ""
                _is_premium_trd = is_premium_tradeable(
                    conf, side, _fc_lt, _stg_lt, _live_rr_lt, _lt_align)
                if _is_premium_trd:
                    _tradeable_chip_lt = (
                        f"<span style='background:#9b59b6;color:#fff;"
                        f"padding:2px 10px;border-radius:5px;font-size:"
                        f"0.72rem;font-weight:800;margin-left:4px;"
                        f"box-shadow:0 0 8px #9b59b677'>"
                        f"💎 PREMIUM TRADEABLE</span>")

                with st.container(border=True):
                    aa, bb = st.columns([6, 1])
                    aa.markdown(
                        f"<div style='display:flex;align-items:center;"
                        f"gap:8px;flex-wrap:wrap'>"
                        f"<span style='font-weight:800;font-size:1rem'>"
                        f"{s['base']}</span>"
                        f"<span style='background:{side_col};color:#06121f;"
                        f"padding:2px 10px;border-radius:5px;font-size:"
                        f"0.72rem;font-weight:800'>{side}</span>"
                        f"<span style='background:{str_col}33;"
                        f"color:{str_col};padding:2px 8px;border-radius:"
                        f"5px;font-size:0.72rem;font-weight:700'>"
                        f"{str_label} · {_combined_disp}</span>"
                        f"{_premium_chip_lt}{_tradeable_chip_lt}"
                        f"{_coiled_chip_lt}"
                        f"{_reentry_chip_lt}{_drift_chip_lt}"
                        f"<span style='color:#6e8bff;font-weight:700;"
                        f"font-size:0.78rem'>{_lev}× lev</span>"
                        f"<span style='color:#8b8d98;font-size:0.78rem'>"
                        f"· conf {conf} · R:R "
                        f"{float(s.get('rr', 0)):.1f}</span></div>"
                        f"<div style='color:#aab;font-size:0.78rem;"
                        f"margin-top:4px'>"
                        f"now <b>{fmt_price(_cur_lt)}</b> · entry zone "
                        f"{fmt_price(s.get('entry_low', 0))} · stop "
                        f"{fmt_price(_stop_lt)} "
                        f"<span style='color:#ff5c5c'>"
                        f"(−{_live_risk_lt:.1f}%)</span> · target "
                        f"{fmt_price(_tgt_lt)} "
                        f"<span style='color:#2ed47a'>"
                        f"(+{_live_reward_lt:.1f}%)</span></div>",
                        unsafe_allow_html=True)
                    _pk = f"lb_pick_{s['symbol']}:{side}"
                    _pk_help = (
                        f"LIVE {side} {s['base']} → TP1 (~5-7%)"
                        + (
                            f" · 💎 {_settings.get('premium_risk_multiplier', 1.5):.2f}× risk"
                            if _is_premium_trd else ""
                        ))
                    if bb.button("📥", key=_pk,
                                 help=_pk_help,
                                 use_container_width=True):
                        try:
                            # Premium-tradeable trades deploy more risk per
                            # the user-set multiplier — flag in the alert.
                            _setup_for_open = dict(s)
                            if _is_premium_trd:
                                _setup_for_open["premium_tradeable"] = True
                            opened = lb.open_position(
                                lb_state, _setup_for_open,
                                prices.get(s["symbol"])
                                or s.get("entry_low"),
                                confirmed=True)
                            if opened:
                                lb.save_state(
                                    config.LIVE_BOT_STATE_PATH, lb_state)
                                st.toast(
                                    f"📥 LIVE {side} {opened['base']} @ "
                                    f"{fmt_price(opened['entry'])} → TP1 · "
                                    f"{_lev}×", icon="💸")
                                st.rerun()
                        except lb.ConfigError as _exc:
                            st.error(str(_exc))
                        except Exception as _exc:
                            st.error(f"Open failed: {_exc}")
                    # 🏆 TP2 button — only on PREMIUM-eligible cards.
                    # Opens the same setup but with target swapped to
                    # TP2 (~7.5-10%). Real money use this when you
                    # want to ride a strong setup further; live broker
                    # also has partial-take at +1.5R for protection.
                    _tgt2_lt = float(s.get("target_2") or 0)
                    if _is_premium and _tgt2_lt > 0:
                        if bb.button(
                                "🏆 TP2", key=f"lb_tp2_{s['symbol']}:{side}",
                                help=f"LIVE {side} {s['base']} → TP2 "
                                     f"(~7.5-10%). Original stop. Real "
                                     f"money — strong setups only.",
                                use_container_width=True):
                            try:
                                _s_tp2 = dict(s)
                                _s_tp2["target"] = _tgt2_lt
                                _s_tp2["rr"] = float(
                                    s.get("rr_2") or s.get("rr") or 0)
                                # TP2 path also flags premium when it
                                # meets the strict tradeable criteria.
                                if _is_premium_trd:
                                    _s_tp2["premium_tradeable"] = True
                                opened = lb.open_position(
                                    lb_state, _s_tp2,
                                    prices.get(s["symbol"])
                                    or s.get("entry_low"),
                                    confirmed=True)
                                if opened:
                                    lb.save_state(
                                        config.LIVE_BOT_STATE_PATH,
                                        lb_state)
                                    st.toast(
                                        f"🏆 LIVE {side} "
                                        f"{opened['base']} @ "
                                        f"{fmt_price(opened['entry'])} "
                                        f"→ TP2 · {_lev}×", icon="🏆")
                                    st.rerun()
                            except lb.ConfigError as _exc:
                                st.error(str(_exc))
                            except Exception as _exc:
                                st.error(f"Open failed: {_exc}")

        # ---- AUTO-TRADE FIRING LOOP (only if toggle ON) -----------------
        # Iterates the same live-eligible setups as the picks board above
        # and fires real orders on Bybit for setups that pass:
        #   1. lb.auto_trade_gate (confirm-first-N, daily loss cap,
        #      auto_threshold, max_concurrent)
        #   2. If auto_premium_only=True: ALL 5 strict criteria
        #      (conf>=90 + forecast 3/3 + COILED/FRESH + green zone +
        #      not counter-trend)
        # When all checks pass, fires via lb.open_position(confirmed=True).
        # Otherwise skips silently.
        if _live_auto_trade:
            _auto_premium_only = bool(
                _settings.get("auto_premium_only", True))
            _auto_fired_this_run = []
            for _lev, _lt_align, s, _combined_lt in _live_eligible:
                # Standard auto-gate
                ok_gate, gate_reason = lb.auto_trade_gate(
                    lb_state, s, _settings)
                if not ok_gate:
                    continue
                # Strict premium gate
                if _auto_premium_only:
                    _fc_a = _fc_by_sym_lt.get(s["symbol"]) or {}
                    _r_a = _radar_by_sym_lt.get(s["symbol"]) or {}
                    _stg_a = str(_r_a.get("stage") or "").upper()
                    # Recompute live R:R from current price
                    _cur_a = (prices.get(s["symbol"])
                              or float(s.get("entry_low") or 0))
                    _stop_a = float(s.get("stop") or 0)
                    _tgt_a = float(s.get("target") or 0)
                    _risk_a = (((_cur_a - _stop_a) / _cur_a * 100)
                               if s["side"] == "LONG" else
                               ((_stop_a - _cur_a) / _cur_a * 100))
                    _rew_a = (((_tgt_a - _cur_a) / _cur_a * 100)
                              if s["side"] == "LONG" else
                              ((_cur_a - _tgt_a) / _cur_a * 100))
                    _live_rr_a = (_rew_a / _risk_a) if _risk_a > 0 else 0
                    if not is_premium_tradeable(
                            int(s.get("confidence", 0) or 0),
                            s["side"], _fc_a, _stg_a,
                            _live_rr_a, _lt_align):
                        continue
                # FIRE — premium auto-fires use the premium risk
                # multiplier (default 1.5×) for bigger position size.
                _setup_auto = dict(s)
                if _auto_premium_only:
                    _setup_auto["premium_tradeable"] = True
                try:
                    opened = lb.open_position(
                        lb_state, _setup_auto,
                        prices.get(s["symbol"]) or s.get("entry_low"),
                        confirmed=True)
                    if opened:
                        lb.save_state(
                            config.LIVE_BOT_STATE_PATH, lb_state)
                        st.toast(
                            f"💎 AUTO-FIRED {s['side']} {opened['base']} "
                            f"@ {fmt_price(opened['entry'])} · "
                            f"{_lev}× lev", icon="💎")
                        _auto_fired_this_run.append(opened["symbol"])
                except Exception as _exc:
                    st.error(f"Auto-fire failed on {s['symbol']}: {_exc}")

        st.divider()
        _live_live_positions()

    st.divider()

    # --- Closed-trades history --------------------------------------------
    st.markdown(
        f"#### 📜 Closed live trades ({len(lb_state['closed'])})")
    if lb_state["closed"]:
        _cs = sorted(lb_state["closed"],
                     key=lambda c: c.get("exit_at", 0),
                     reverse=True)[:80]
        _rows = [{
            "Coin": c.get("base", ""),
            "Side": c.get("side", ""),
            "Entry": fmt_price(c.get("entry", 0)),
            "Exit": fmt_price(c.get("exit", 0)),
            "Qty": round(c.get("qty", 0) or 0, 6),
            "Notional $": round(
                (c.get("notional")
                 or (c.get("qty", 0) or 0) * (c.get("entry", 0) or 0)), 2),
            "Lev": int(c.get("leverage") or 1),
            "Reason": c.get("exit_reason", ""),
            "PnL $": c.get("pnl_usd", 0.0),
            "PnL %": c.get("pnl_pct", 0.0),
            "Closed (UTC)": datetime.fromtimestamp(
                c.get("exit_at", 0), tz=timezone.utc).strftime(
                    "%Y-%m-%d %H:%M"),
        } for c in _cs]
        st.dataframe(pd.DataFrame(_rows),
                     use_container_width=True, hide_index=True)
    else:
        st.caption("No closed live trades yet.")

    st.caption(
        "Real-money trading involves real loss. Bybit charges ~0.055% "
        "taker / 0.02% maker on USDT-perp plus funding every 8 hours. "
        "Slippage on market orders is real. Stops and take-profits are "
        "set on the exchange so they fire even if this app crashes. "
        "Educational use — not financial advice.")


# ===========================================================================
# Tab 10 — Spot Long-Term Picks  (Phase D MVP)
# ===========================================================================
# Long-term hold picks on a fundamentally different scoring engine than the
# short-term futures scanner. Uses WEEKLY bars and four classic long-entry
# filters (Weinstein Stage 2, Mayer Multiple, drawdown from ATH, weekly
# HH/HL structure). PURE DISPLAY — does NOT feed live_broker, paper_bot, or
# the existing futures picks. Build a watchlist here, then buy on spot
# manually if you like the read.
if active_section == "💎 Spot Long-Term":
    st.subheader("💎 Spot Long-Term Picks")
    st.caption(
        "Long-term hold candidates ranked by a fundamentally different "
        "scoring engine than the short-term futures scanner. Weekly bars, "
        "no leverage, weeks-to-months horizon. **This is a watchlist, "
        "not an auto-trader** — clicking a card does not open a position; "
        "use it to build conviction for manual spot buys.")

    # --- Macro overlay banner (Phase E) — BTC.D + FRED ----------------
    # Slow-moving regime context for ALT positioning. BTC-dominant regimes
    # mean alts under-perform BTC; risk-off macro environments (rising
    # DXY, falling M2, rising real yields) mean spot crypto under-performs
    # cash. Multipliers are applied to alt scores below.
    _btc_reg = load_btc_regime()
    _macro_reg = load_macro_regime()
    _alt_mult = float(_btc_reg.get("alt_multiplier") or 1.0)
    _risk_mult = float(_macro_reg.get("risk_multiplier") or 1.0)
    _reg_label = _btc_reg.get("regime", "UNKNOWN")
    _macro_label = _macro_reg.get("regime", "UNKNOWN")

    _reg_color = {"ALT_FAVOURABLE": "#2ed47a", "MIXED": "#e0a92b",
                  "BTC_DOMINANT": "#ff5c5c"}.get(_reg_label, "#8b8d98")
    _macro_color = {"RISK_ON": "#2ed47a", "MIXED": "#e0a92b",
                    "RISK_OFF": "#ff5c5c"}.get(_macro_label, "#8b8d98")

    mc1, mc2 = st.columns([1, 1])
    with mc1:
        st.markdown(
            f"<div style='background:{_reg_color}22;border-left:3px solid "
            f"{_reg_color};padding:10px 14px;border-radius:6px'>"
            f"<div style='font-weight:800;color:{_reg_color};font-size:0.9rem'>"
            f"📊 BTC Dominance · {_reg_label}</div>"
            f"<div style='color:#aab;font-size:0.78rem;margin-top:4px'>"
            f"{_btc_reg.get('detail', '—')}</div>"
            f"<div style='color:#8b8d98;font-size:0.72rem;margin-top:6px'>"
            f"alt-score multiplier: <b>{_alt_mult:.2f}×</b></div></div>",
            unsafe_allow_html=True)
    with mc2:
        st.markdown(
            f"<div style='background:{_macro_color}22;border-left:3px solid "
            f"{_macro_color};padding:10px 14px;border-radius:6px'>"
            f"<div style='font-weight:800;color:{_macro_color};font-size:0.9rem'>"
            f"🌍 Macro · {_macro_label}</div>"
            f"<div style='color:#aab;font-size:0.78rem;margin-top:4px'>"
            f"{_macro_reg.get('detail', '—')}</div>"
            f"<div style='color:#8b8d98;font-size:0.72rem;margin-top:6px'>"
            f"risk multiplier: <b>{_risk_mult:.2f}×</b></div></div>",
            unsafe_allow_html=True)
    st.markdown("")  # spacer

    st.markdown(
        "**How the score is built** — composite 0–100, weighted:\n"
        "- **35% Weinstein Stage** — only Stage 2 (markup) scores high. "
        "Stage 1 (basing) is neutral; Stage 3/4 (distribution/decline) "
        "score low.\n"
        "- **25% Structure** — last 2 swing highs AND 2 swing lows "
        "both ascending (no lookahead). Confirms an uptrend.\n"
        "- **20% Mayer Multiple** — close / 200-bar SMA. Only BTC and ETH "
        "get the zone scoring (deep value / accumulation / fair / "
        "extended); alts get a neutral Mayer (informational only).\n"
        "- **20% Drawdown from ATH** — % off all-time-high, with a "
        "capitulation bonus when current volume is < 50% of peak-area "
        "volume.\n\n"
        "**Floor: 65** (WATCH tier). **Strong: 80+** (STRONG tier). "
        "**Timeframe affects what the score MEANS:** 1d picks shift "
        "weekly, 3d picks shift monthly, 1w picks shift quarterly.")

    spot_col0, spot_col1, spot_col2, spot_col3 = st.columns([1, 1, 1, 1])
    with spot_col0:
        spot_tf = st.selectbox(
            "Timeframe", ["1d", "3d", "1w"], index=0,
            key="spot_tf_selector",
            help="1d (default) = daily bars, more responsive. 3d = "
                 "smoother trend filter. 1w = classic Weinstein cycle "
                 "read but slower.")
    with spot_col1:
        spot_min_score = st.slider(
            "Min score", 50, 95, 65, step=5,
            help="Filter floor. WATCH ≥65, STRONG ≥80.")
    with spot_col2:
        spot_max_picks = st.slider(
            "Max picks", 5, 30, 15, step=5)
    with spot_col3:
        spot_scan_n = st.slider(
            "Coins to scan", 20, 100, 30, step=10,
            help=f"Scans the top N coins by 24h volume on {spot_tf} bars. "
                 "30 is the auto-load default. Higher N = more "
                 "candidates but slower scan (~0.5-1s per coin).")

    # AUTO-LOAD on entry: kick off the scan if we don't have fresh
    # results for this timeframe. Cached for 10 min via load_spot_long_score.
    _spot_results = st.session_state.get("_spot_scan_results", [])
    _spot_scan_ts = st.session_state.get("_spot_scan_ts", 0)
    _spot_scan_tf = st.session_state.get("_spot_scan_tf", "")
    _spot_scan_n_cached = st.session_state.get("_spot_scan_n", 0)
    _need_scan = (
        not _spot_results
        or _spot_scan_tf != spot_tf
        or _spot_scan_n_cached != spot_scan_n
        or (time.time() - _spot_scan_ts) > 1800  # 30 min staleness
    )

    _b1, _b2 = st.columns([1, 5])
    if _b1.button(f"🔄 Rescan ({spot_tf})", use_container_width=True,
                  help="Force a fresh scan even if cached results exist.") \
            or _need_scan:
        with st.spinner(
                f"Scanning {spot_tf} bars for {spot_scan_n} coins..."):
            try:
                _top_df = load_top_symbols(spot_scan_n)
                _spot_results = []
                for _, row in _top_df.iterrows():
                    sym = row["symbol"]
                    base = row["base"]
                    sscore = load_spot_long_score(sym, spot_tf)
                    sscore["symbol"] = sym
                    sscore["base"] = base
                    sscore["price"] = float(row["lastPrice"])
                    sscore["volume_24h"] = float(row["quoteVolume"])
                    _spot_results.append(sscore)
                st.session_state["_spot_scan_results"] = _spot_results
                st.session_state["_spot_scan_ts"] = time.time()
                st.session_state["_spot_scan_tf"] = spot_tf
                st.session_state["_spot_scan_n"] = spot_scan_n
                _spot_scan_ts = st.session_state["_spot_scan_ts"]
            except Exception as exc:
                st.error(f"Spot scan failed: {exc}")
                st.session_state["_spot_scan_results"] = []
                _spot_results = []
    if _spot_results:
        st.caption(
            f"Last scan: {datetime.fromtimestamp(_spot_scan_ts, tz=timezone.utc).strftime('%H:%M:%S UTC')} "
            f"· {len(_spot_results)} coins scored")

        # Filter + rank
        _spot_visible = [r for r in _spot_results
                         if r["score"] >= spot_min_score]
        _spot_visible.sort(key=lambda r: r["score"], reverse=True)
        _spot_visible = _spot_visible[:spot_max_picks]

        if not _spot_visible:
            st.info(
                f"No coins scored ≥ {spot_min_score} in the last scan. "
                "Lower the minimum-score slider or try a different "
                "market regime — Stage 2 setups are rare in bear / chop "
                "markets by design.")
        else:
            # Tier summary
            n_strong = sum(1 for r in _spot_visible if r["tier"] == "STRONG")
            n_watch = sum(1 for r in _spot_visible if r["tier"] == "WATCH")
            colA, colB, colC = st.columns(3)
            colA.metric("STRONG picks", n_strong)
            colB.metric("WATCH picks", n_watch)
            colC.metric("Total shown", len(_spot_visible))

            # Picks
            for r in _spot_visible:
                _tier = r.get("tier", "WATCH")
                _stage = r.get("stage", "UNKNOWN")
                comps = r.get("components", {})
                _weinstein = comps.get("weinstein", {})
                _mayer = comps.get("mayer", {})
                _dd = comps.get("drawdown", {})
                _struct = comps.get("structure", {})

                _tier_color = "#2ed47a" if _tier == "STRONG" else (
                    "#e0a92b" if _tier == "WATCH" else "#8b8d98")
                _tier_label = (f"💎 {_tier}" if _tier == "STRONG"
                               else f"👀 {_tier}")

                # Stage chip
                _stage_chip = ""
                if _stage == "STAGE_2_MARKUP":
                    _stage_chip = (
                        f"<span style='background:#2ed47a33;color:#2ed47a;"
                        f"padding:2px 8px;border-radius:5px;font-size:"
                        f"0.7rem;font-weight:700;margin-left:4px'>"
                        f"📈 Stage 2 markup</span>")
                elif _stage == "STAGE_1_BASE":
                    _stage_chip = (
                        f"<span style='background:#6e8bff33;color:#6e8bff;"
                        f"padding:2px 8px;border-radius:5px;font-size:"
                        f"0.7rem;font-weight:700;margin-left:4px'>"
                        f"🟦 Stage 1 base</span>")
                elif _stage == "STAGE_3_DISTRIBUTION":
                    _stage_chip = (
                        f"<span style='background:#e0a92b33;color:#e0a92b;"
                        f"padding:2px 8px;border-radius:5px;font-size:"
                        f"0.7rem;font-weight:700;margin-left:4px'>"
                        f"📊 Stage 3 distribution</span>")
                elif _stage == "STAGE_4_DECLINE":
                    _stage_chip = (
                        f"<span style='background:#ff5c5c33;color:#ff5c5c;"
                        f"padding:2px 8px;border-radius:5px;font-size:"
                        f"0.7rem;font-weight:700;margin-left:4px'>"
                        f"📉 Stage 4 decline</span>")

                # Mayer chip (only meaningful for BTC/ETH)
                _mayer_chip = ""
                _mayer_val = _mayer.get("mayer")
                if _mayer_val is not None and r["symbol"] in (
                        "BTCUSDT", "ETHUSDT"):
                    _mc_color = (
                        "#2ed47a" if _mayer_val < 1.2
                        else "#e0a92b" if _mayer_val < 2.0
                        else "#ff5c5c")
                    _mayer_chip = (
                        f"<span style='background:{_mc_color}22;"
                        f"color:{_mc_color};padding:2px 8px;border-radius:"
                        f"5px;font-size:0.7rem;font-weight:700;"
                        f"margin-left:4px'>Mayer {_mayer_val:.2f}</span>")

                # Drawdown chip
                _dd_pct = _dd.get("dd_pct", 0)
                _dd_chip = ""
                if _dd_pct >= 40:
                    _ddc = "#2ed47a" if _dd_pct >= 60 else "#6e8bff"
                    _cap = " 💧" if _dd.get("capitulated") else ""
                    _dd_chip = (
                        f"<span style='background:{_ddc}22;color:{_ddc};"
                        f"padding:2px 8px;border-radius:5px;font-size:"
                        f"0.7rem;font-weight:700;margin-left:4px'>"
                        f"−{_dd_pct:.0f}% from ATH{_cap}</span>")

                # --- Phase E / F enrichment chips per pick -------------
                # Fetched lazily so the scan stays fast on the initial
                # weekly pass; per-pick enrichment is a few hundred ms
                # and only paid for the picks that actually displayed.
                _ch = load_cup_and_handle(r["symbol"])
                _onchain = load_onchain(r["symbol"])
                _tvl = load_tvl_growth(r["symbol"])
                _tok = load_tokenomics(r["symbol"])

                # Cup-and-handle chip
                _cup_chip = ""
                _cup_stage = _ch.get("stage", "NO_CUP")
                if _cup_stage == "BREAKOUT":
                    _cup_chip = (
                        f"<span style='background:linear-gradient(90deg,"
                        f"#2ed47a,#6e8bff);color:#06121f;padding:2px 10px;"
                        f"border-radius:5px;font-size:0.72rem;font-weight:"
                        f"800;margin-left:4px;box-shadow:0 0 6px #2ed47a66'>"
                        f"☕ CUP+HANDLE BREAKOUT</span>")
                elif _cup_stage == "HANDLE_FORMING":
                    _cup_chip = (
                        f"<span style='background:#6e8bff33;color:#6e8bff;"
                        f"padding:2px 8px;border-radius:5px;font-size:"
                        f"0.7rem;font-weight:700;margin-left:4px'>"
                        f"☕ handle forming</span>")
                elif _cup_stage == "CUP_NO_HANDLE":
                    _cup_chip = (
                        f"<span style='background:#8b8d9833;color:#aab;"
                        f"padding:2px 8px;border-radius:5px;font-size:"
                        f"0.7rem;font-weight:700;margin-left:4px'>"
                        f"☕ cup forming</span>")

                # On-chain chip (BTC/ETH only)
                _onchain_chip = ""
                if r["symbol"] in ("BTCUSDT", "ETHUSDT") \
                        and _onchain.get("mvrv") is not None:
                    _oc_score = float(_onchain.get("score") or 50)
                    _oc_color = ("#2ed47a" if _oc_score >= 75
                                 else "#e0a92b" if _oc_score >= 50
                                 else "#ff5c5c")
                    _onchain_chip = (
                        f"<span style='background:{_oc_color}22;"
                        f"color:{_oc_color};padding:2px 8px;border-radius:"
                        f"5px;font-size:0.7rem;font-weight:700;"
                        f"margin-left:4px'>🔗 {_onchain.get('detail', '')}</span>")

                # TVL chip (only if DefiLlama covers the protocol)
                _tvl_chip = ""
                _tvl_90d = _tvl.get("tvl_90d_growth_pct")
                if _tvl_90d is not None:
                    _tvl_color = ("#2ed47a" if _tvl_90d >= 20
                                  else "#e0a92b" if _tvl_90d >= 0
                                  else "#ff5c5c")
                    _tvl_chip = (
                        f"<span style='background:{_tvl_color}22;"
                        f"color:{_tvl_color};padding:2px 8px;border-radius:"
                        f"5px;font-size:0.7rem;font-weight:700;"
                        f"margin-left:4px'>📈 TVL 90d {_tvl_90d:+.0f}%</span>")

                # Tokenomics dilution chip (warning only — defensive)
                _tok_chip = ""
                _tok_score = float(_tok.get("score") or 50)
                _tok_circ = _tok.get("circulating_fraction")
                if _tok_score <= 40 and _tok_circ is not None:
                    _tok_chip = (
                        f"<span style='background:#ff5c5c33;color:#ff5c5c;"
                        f"padding:2px 8px;border-radius:5px;font-size:"
                        f"0.7rem;font-weight:700;margin-left:4px'>"
                        f"⚠ {_tok_circ * 100:.0f}% circulating</span>")
                elif _tok_score >= 80 and _tok_circ is not None:
                    _tok_chip = (
                        f"<span style='background:#2ed47a22;color:#2ed47a;"
                        f"padding:2px 8px;border-radius:5px;font-size:"
                        f"0.7rem;font-weight:700;margin-left:4px'>"
                        f"✓ {_tok_circ * 100:.0f}% circulating</span>")

                # Composite enhanced score — multiply alts by BTC.D and
                # FRED macro regime multipliers. BTC and ETH are not
                # affected by the alt-multiplier (they ARE BTC).
                _is_btc_eth = r["symbol"] in ("BTCUSDT", "ETHUSDT")
                _local_alt_mult = 1.0 if _is_btc_eth else _alt_mult
                _enhanced_score = (r["score"] * _local_alt_mult * _risk_mult)
                _enhanced_score = max(0.0, min(100.0, _enhanced_score))
                _delta = _enhanced_score - r["score"]
                _delta_chip = ""
                if abs(_delta) >= 5:
                    _dc = "#2ed47a" if _delta > 0 else "#ff5c5c"
                    _delta_chip = (
                        f"<span style='background:{_dc}22;color:{_dc};"
                        f"padding:2px 8px;border-radius:5px;font-size:"
                        f"0.7rem;font-weight:700;margin-left:4px'>"
                        f"⇢ regime-adjusted {_enhanced_score:.0f} "
                        f"({_delta:+.0f})</span>")

                with st.container(border=True):
                    st.markdown(
                        f"<div style='display:flex;align-items:center;"
                        f"gap:8px;flex-wrap:wrap'>"
                        f"<span style='font-weight:800;font-size:1.05rem'>"
                        f"{r['base']}</span>"
                        f"<span style='background:{_tier_color};"
                        f"color:#06121f;padding:2px 10px;border-radius:"
                        f"5px;font-size:0.72rem;font-weight:800'>"
                        f"{_tier_label} · {r['score']:.0f}</span>"
                        f"{_delta_chip}"
                        f"{_stage_chip}{_mayer_chip}{_dd_chip}"
                        f"{_cup_chip}{_onchain_chip}{_tvl_chip}{_tok_chip}"
                        f"<span style='color:#8b8d98;font-size:0.78rem'>"
                        f"price ${r['price']:,.4g} · "
                        f"24h vol ${r['volume_24h'] / 1e6:.1f}M</span>"
                        f"</div>"
                        f"<div style='color:#aab;font-size:0.78rem;"
                        f"margin-top:6px;line-height:1.5'>"
                        f"<b>Stage:</b> {_weinstein.get('detail', '—')}<br>"
                        f"<b>Structure:</b> {_struct.get('detail', '—')}<br>"
                        f"<b>Drawdown:</b> {_dd.get('detail', '—')}<br>"
                        f"<b>Mayer:</b> {_mayer.get('detail', '—')}<br>"
                        f"<b>Cup/Handle:</b> {_ch.get('detail', '—')}<br>"
                        f"<b>TVL/Fees:</b> {_tvl.get('detail', '—')}<br>"
                        f"<b>Tokenomics:</b> {_tok.get('detail', '—')}"
                        f"{('<br><b>On-chain:</b> ' + _onchain.get('detail', '—')) if _onchain.get('mvrv') is not None else ''}"
                        f"</div>",
                        unsafe_allow_html=True)

    else:
        st.info(
            "Click **🔄 Run weekly scan** to score the top coins on "
            "weekly bars. This is a slower scan (~1s per coin) because "
            "weekly klines aren't in the regular per-tick cache. "
            "Results stay cached for 2 minutes between scans.")

    st.caption(
        "⚠️ This module is **DISPLAY ONLY** in Phase D MVP. Picks here "
        "do NOT auto-open spot positions, do NOT influence the futures "
        "picks board, and do NOT feed live_broker. Manually buy on spot "
        "after doing your own due diligence on tokenomics, project "
        "fundamentals, and current macro regime. Long-term holds need "
        "more than a chart score.")
