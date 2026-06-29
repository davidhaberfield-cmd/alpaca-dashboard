#!/usr/bin/env python3
"""
Alpaca Paper Portfolio Dashboard
Streamlit app — auto-updated after every rebalance and daily report.
"""

import json
import os
import hmac
import hashlib
import streamlit as st
import plotly.express as px
import plotly.graph_objects as go
from plotly.subplots import make_subplots
import pandas as pd
from datetime import datetime

# ── Page config ───────────────────────────────────────────────────────────────
st.set_page_config(
    page_title="Alpaca Paper Portfolio",
    page_icon="🚀",
    layout="wide",
    initial_sidebar_state="collapsed",
)

# ── Password gate ─────────────────────────────────────────────────────────────
def check_password():
    """Simple password gate using HMAC comparison."""
    stored_hash = os.environ.get("DASHBOARD_PASSWORD_HASH", "")

    if "authenticated" not in st.session_state:
        st.session_state.authenticated = False

    if st.session_state.authenticated:
        return True

    st.markdown("## 🚀 Alpaca Paper Portfolio")
    st.markdown("---")
    col1, col2, col3 = st.columns([1, 2, 1])
    with col2:
        password = st.text_input("Password", type="password", placeholder="Enter password...")
        if st.button("Login", use_container_width=True):
            entered_hash = hashlib.sha256(password.encode()).hexdigest()
            if hmac.compare_digest(entered_hash, stored_hash):
                st.session_state.authenticated = True
                st.rerun()
            else:
                st.error("Incorrect password.")
    return False

if not check_password():
    st.stop()

# ── Load data ─────────────────────────────────────────────────────────────────
DATA_FILE = os.path.join(os.path.dirname(__file__), "data", "portfolio.json")

@st.cache_data(ttl=300)
def load_data():
    try:
        with open(DATA_FILE) as f:
            return json.load(f)
    except Exception as e:
        st.error(f"Could not load portfolio data: {e}")
        return None

data = load_data()
if not data:
    st.warning("No portfolio data found. Check back after the next update.")
    st.stop()

# ── Parse data ────────────────────────────────────────────────────────────────
positions = data.get("positions", [])
account = data.get("account", {})
cooldowns = data.get("cooldowns", {})
history = data.get("history", [])
updated_at = data.get("updated_at", "unknown")

portfolio_value = account.get("portfolio_value", 0)
cash = account.get("cash", 0)
invested = portfolio_value - cash
start_value = 100_000.0
total_pl = portfolio_value - start_value
total_pl_pct = total_pl / start_value * 100
spy_total = data.get("spy_total_return", None)
alpha = (total_pl_pct / 100 - spy_total) * 100 if spy_total is not None else None

# ── Header ────────────────────────────────────────────────────────────────────
st.markdown(f"# 🚀 Alpaca Paper Portfolio")
st.caption(f"Last updated: {updated_at} · Paper account · $100,000 starting capital")
st.markdown("---")

# ── KPI strip ─────────────────────────────────────────────────────────────────
k1, k2, k3, k4, k5, k6 = st.columns(6)

pl_colour = "normal" if total_pl >= 0 else "inverse"
k1.metric("💼 Portfolio Value", f"${portfolio_value:,.2f}", f"${total_pl:+,.2f}")
k2.metric("📈 Total Return", f"{total_pl_pct:+.2f}%",
          f"vs S&P {spy_total*100:+.2f}%" if spy_total else None)
k3.metric("⚡ Alpha", f"{alpha:+.2f}%" if alpha is not None else "n/a")
k4.metric("💵 Cash", f"${cash:,.2f}")
k5.metric("📊 Invested", f"${invested:,.2f}")
k6.metric("🎯 Positions", len(positions))

st.markdown("---")

# ── Main layout ───────────────────────────────────────────────────────────────
left, right = st.columns([3, 2])

# ── Positions table ───────────────────────────────────────────────────────────
with left:
    st.subheader("📋 Positions")

    if positions:
        df = pd.DataFrame(positions)
        df["sl_level"] = df["avg_entry_price"] * 0.95
        df["dist_to_sl_pct"] = (df["current_price"] - df["sl_level"]) / df["sl_level"] * 100
        df["cooldown"] = df["symbol"].apply(lambda s: cooldowns.get(s, 0))

        def sl_status(row):
            if row["cooldown"] > 0:
                return f"⚠️ Cooldown {row['cooldown']}d"
            elif row["dist_to_sl_pct"] < 1.5:
                return "🔴 NEAR SL"
            elif row["dist_to_sl_pct"] < 3.0:
                return "🟡 Watch"
            else:
                return "🟢 OK"

        df["status"] = df.apply(sl_status, axis=1)
        df["pl_pct_display"] = df["unrealized_plpc"].apply(lambda x: f"{x*100:+.2f}%")
        df["pl_display"] = df["unrealized_pl"].apply(lambda x: f"${x:+,.2f}")
        df["sl_dist_display"] = df["dist_to_sl_pct"].apply(lambda x: f"{x:.1f}%")
        df["market_value_display"] = df["market_value"].apply(lambda x: f"${x:,.2f}")
        df["avg_display"] = df["avg_entry_price"].apply(lambda x: f"${x:.2f}")
        df["cur_display"] = df["current_price"].apply(lambda x: f"${x:.2f}")
        df["sl_display"] = df["sl_level"].apply(lambda x: f"${x:.2f}")

        display_df = df[[
            "symbol", "sector", "qty",
            "avg_display", "cur_display",
            "market_value_display",
            "pl_display", "pl_pct_display",
            "sl_display", "sl_dist_display", "status"
        ]].rename(columns={
            "symbol": "Symbol", "sector": "Sector", "qty": "Qty",
            "avg_display": "Avg Entry", "cur_display": "Current",
            "market_value_display": "Mkt Value",
            "pl_display": "P&L $", "pl_pct_display": "P&L %",
            "sl_display": "Stop-Loss", "sl_dist_display": "→ SL", "status": "Status"
        })

        st.dataframe(display_df, use_container_width=True, hide_index=True)
    else:
        st.info("No open positions.")

# ── P&L bar chart ─────────────────────────────────────────────────────────────
with right:
    st.subheader("📊 P&L by Position")

    if positions:
        df_chart = pd.DataFrame(positions).copy()
        df_chart["pl_pct"] = df_chart["unrealized_plpc"] * 100
        df_chart = df_chart.sort_values("pl_pct", ascending=True)
        colours = ["#ff5252" if x < 0 else "#00c853" for x in df_chart["pl_pct"]]

        fig_bar = go.Figure(go.Bar(
            x=df_chart["pl_pct"],
            y=df_chart["symbol"],
            orientation="h",
            marker_color=colours,
            text=[f"{v:+.1f}%" for v in df_chart["pl_pct"]],
            textposition="outside",
        ))
        fig_bar.update_layout(
            margin=dict(l=0, r=40, t=10, b=10),
            height=320,
            xaxis_title="P&L %",
            plot_bgcolor="#0e1117",
            paper_bgcolor="#0e1117",
            font_color="#fafafa",
            xaxis=dict(gridcolor="#333"),
            yaxis=dict(gridcolor="#333"),
        )
        st.plotly_chart(fig_bar, use_container_width=True)

st.markdown("---")

# ── Allocation + Sector ───────────────────────────────────────────────────────
col1, col2 = st.columns(2)

with col1:
    st.subheader("🥧 Allocation")
    if positions:
        df_alloc = pd.DataFrame(positions)
        cash_row = pd.DataFrame([{"symbol": "CASH", "market_value": cash, "sector": "Cash"}])
        df_alloc = pd.concat([df_alloc, cash_row], ignore_index=True)

        fig_pie = px.pie(
            df_alloc, values="market_value", names="symbol",
            hole=0.4,
            color_discrete_sequence=px.colors.qualitative.Set3,
        )
        fig_pie.update_layout(
            margin=dict(l=0, r=0, t=10, b=10),
            height=300,
            plot_bgcolor="#0e1117",
            paper_bgcolor="#0e1117",
            font_color="#fafafa",
            legend=dict(orientation="v", x=1, y=0.5),
        )
        fig_pie.update_traces(textposition="inside", textinfo="percent+label")
        st.plotly_chart(fig_pie, use_container_width=True)

with col2:
    st.subheader("🏭 Sector Breakdown")
    if positions:
        df_sect = pd.DataFrame(positions).groupby("sector")["market_value"].sum().reset_index()
        df_sect = df_sect.sort_values("market_value", ascending=False)
        df_sect["pct"] = df_sect["market_value"] / invested * 100

        fig_sect = px.bar(
            df_sect, x="sector", y="market_value",
            text=df_sect["pct"].apply(lambda x: f"{x:.1f}%"),
            color="sector",
            color_discrete_sequence=px.colors.qualitative.Set3,
        )
        fig_sect.update_layout(
            margin=dict(l=0, r=0, t=10, b=10),
            height=300,
            showlegend=False,
            xaxis_title="",
            yaxis_title="Market Value ($)",
            plot_bgcolor="#0e1117",
            paper_bgcolor="#0e1117",
            font_color="#fafafa",
            xaxis=dict(gridcolor="#333"),
            yaxis=dict(gridcolor="#333"),
        )
        fig_sect.update_traces(textposition="outside")
        st.plotly_chart(fig_sect, use_container_width=True)

st.markdown("---")

# ── Portfolio value history ───────────────────────────────────────────────────
st.subheader("📈 Portfolio Value History")

if history and len(history) >= 2:
    df_hist = pd.DataFrame(history)
    df_hist["date"] = pd.to_datetime(df_hist["date"])
    df_hist = df_hist.sort_values("date")

    fig_hist = go.Figure()
    fig_hist.add_trace(go.Scatter(
        x=df_hist["date"], y=df_hist["portfolio_value"],
        mode="lines+markers", name="Portfolio",
        line=dict(color="#00c853", width=2),
        fill="tozeroy", fillcolor="rgba(0,200,83,0.08)",
    ))
    fig_hist.add_hline(
        y=start_value, line_dash="dash",
        line_color="#888", annotation_text="$100k start",
        annotation_position="bottom right",
    )
    fig_hist.update_layout(
        height=280,
        margin=dict(l=0, r=0, t=10, b=10),
        plot_bgcolor="#0e1117",
        paper_bgcolor="#0e1117",
        font_color="#fafafa",
        xaxis=dict(gridcolor="#333"),
        yaxis=dict(gridcolor="#333", tickprefix="$"),
        legend=dict(orientation="h"),
    )
    st.plotly_chart(fig_hist, use_container_width=True)
else:
    st.info("Portfolio history will appear after a few daily reports have run.")

# ── Stop-loss cooldowns ───────────────────────────────────────────────────────
if cooldowns:
    st.markdown("---")
    st.subheader("🚫 Stop-Loss Cooldowns")
    st.caption("These symbols were stopped out and are excluded from the next rebalance.")
    cols = st.columns(min(len(cooldowns), 5))
    for i, (sym, days) in enumerate(cooldowns.items()):
        cols[i % 5].metric(sym, f"{days}d remaining", "excluded from rebalance")

# ── Footer ────────────────────────────────────────────────────────────────────
st.markdown("---")
st.caption(f"🤖 Auto-updated by Solen after every rebalance and daily report · {updated_at}")
