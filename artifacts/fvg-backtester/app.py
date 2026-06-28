import streamlit as st
import yfinance as yf
import pandas as pd
import numpy as np
import plotly.graph_objects as go
from plotly.subplots import make_subplots

st.set_page_config(
    page_title="FVG Backtester — XAUUSD",
    page_icon="📊",
    layout="wide"
)

# ─── Sidebar ────────────────────────────────────────────────────────────────
st.sidebar.title("⚙️ Settings")
period = st.sidebar.selectbox(
    "Lookback Period",
    ["6mo", "1y", "2y", "5y"],
    index=1,
    help="How far back to fetch XAUUSD 4H data"
)
rr_ratio = st.sidebar.number_input(
    "Risk : Reward Ratio (1 : X)",
    min_value=0.5,
    max_value=10.0,
    value=2.0,
    step=0.5,
    help="Target = Entry ± Risk × RR"
)
fvg_types = st.sidebar.multiselect(
    "FVG Types to Trade",
    ["Bullish", "Bearish"],
    default=["Bullish", "Bearish"]
)
min_gap_pct = st.sidebar.slider(
    "Minimum FVG size (% of price)",
    min_value=0.01,
    max_value=1.0,
    value=0.05,
    step=0.01,
    help="Filter out tiny gaps that are likely noise"
)
run = st.sidebar.button("▶  Run Backtest", type="primary", use_container_width=True)

# ─── Header ─────────────────────────────────────────────────────────────────
st.title("Fair Value Gap (FVG) Backtester")
st.markdown("**Instrument:** XAUUSD (Gold) &nbsp;|&nbsp; **Timeframe:** 4H &nbsp;|&nbsp; **Strategy:** Retracement into FVG zone")
st.divider()


# ─── Data ────────────────────────────────────────────────────────────────────
@st.cache_data(ttl=3600, show_spinner=False)
def load_data(period: str) -> pd.DataFrame:
    ticker = yf.Ticker("GC=F")
    raw = ticker.history(period=period, interval="1h", auto_adjust=True)
    if raw.empty:
        raise ValueError("No data returned from Yahoo Finance for GC=F.")
    # Resample 1H → 4H
    df = raw.resample("4h").agg({
        "Open": "first",
        "High": "max",
        "Low": "min",
        "Close": "last",
        "Volume": "sum"
    }).dropna()
    df.index = df.index.tz_localize(None)
    return df


# ─── FVG Detection ───────────────────────────────────────────────────────────
def detect_fvgs(df: pd.DataFrame, fvg_types: list, min_gap_pct: float) -> list:
    """
    Bullish FVG:  Candle 3 Low > Candle 1 High  →  zone = [c1_high, c3_low]
    Bearish FVG:  Candle 3 High < Candle 1 Low   →  zone = [c3_high, c1_low]
    """
    fvgs = []
    for i in range(1, len(df) - 1):
        c1 = df.iloc[i - 1]
        c3 = df.iloc[i + 1]

        # ── Bullish FVG ──────────────────────────────────────────────────────
        if "Bullish" in fvg_types:
            if c3["Low"] > c1["High"]:
                top = c3["Low"]
                bottom = c1["High"]
                size = top - bottom
                if size / bottom >= min_gap_pct / 100:
                    fvgs.append({
                        "formed_idx": i + 1,
                        "formed_time": df.index[i + 1],
                        "type": "Bullish",
                        "top": top,
                        "bottom": bottom,
                        "mid": (top + bottom) / 2,
                        "size": size,
                    })

        # ── Bearish FVG ──────────────────────────────────────────────────────
        if "Bearish" in fvg_types:
            if c3["High"] < c1["Low"]:
                top = c1["Low"]
                bottom = c3["High"]
                size = top - bottom
                if size / bottom >= min_gap_pct / 100:
                    fvgs.append({
                        "formed_idx": i + 1,
                        "formed_time": df.index[i + 1],
                        "type": "Bearish",
                        "top": top,
                        "bottom": bottom,
                        "mid": (top + bottom) / 2,
                        "size": size,
                    })
    return fvgs


# ─── Backtest ────────────────────────────────────────────────────────────────
def backtest(df: pd.DataFrame, fvgs: list, rr: float, max_bars_to_fill: int = 40) -> pd.DataFrame:
    """
    For each FVG, scan forward for the first candle that retraces into the zone.
    Entry = zone mid-point.  SL = opposite edge of zone.  TP = Entry ± risk × RR.
    Then scan forward for whichever target hits first (TP or SL).
    """
    trades = []

    for fvg in fvgs:
        idx = fvg["formed_idx"]
        top = fvg["top"]
        bottom = fvg["bottom"]
        mid = fvg["mid"]
        ftype = fvg["type"]

        fill_bar = None
        fill_price = None

        # ── Look for retracement into FVG zone ──────────────────────────────
        for j in range(idx + 1, min(idx + 1 + max_bars_to_fill, len(df))):
            c = df.iloc[j]
            if ftype == "Bullish":
                # Price dips into [bottom, top]
                if c["Low"] <= top and c["High"] >= bottom:
                    fill_bar = j
                    fill_price = mid  # Assume filled at zone midpoint
                    break
            else:  # Bearish
                # Price rises into [bottom, top]
                if c["High"] >= bottom and c["Low"] <= top:
                    fill_bar = j
                    fill_price = mid
                    break

        if fill_bar is None:
            continue  # FVG never filled — skip

        # ── Define trade levels ──────────────────────────────────────────────
        if ftype == "Bullish":
            entry = fill_price
            sl = bottom
            risk = entry - sl
            if risk <= 0:
                continue
            tp = entry + risk * rr
            direction = "Long"
        else:
            entry = fill_price
            sl = top
            risk = sl - entry
            if risk <= 0:
                continue
            tp = entry - risk * rr
            direction = "Short"

        # ── Scan for outcome ─────────────────────────────────────────────────
        outcome = None
        exit_bar = None
        for k in range(fill_bar + 1, len(df)):
            c = df.iloc[k]
            if ftype == "Bullish":
                if c["Low"] <= sl:
                    outcome = "Loss"
                    exit_bar = k
                    break
                if c["High"] >= tp:
                    outcome = "Win"
                    exit_bar = k
                    break
            else:
                if c["High"] >= sl:
                    outcome = "Loss"
                    exit_bar = k
                    break
                if c["Low"] <= tp:
                    outcome = "Win"
                    exit_bar = k
                    break

        if outcome is None:
            continue  # Trade still open at end of data — skip

        pnl_r = rr if outcome == "Win" else -1.0

        trades.append({
            "Entry Time": df.index[fill_bar],
            "Exit Time": df.index[exit_bar],
            "Direction": direction,
            "FVG Type": ftype,
            "Entry": round(entry, 2),
            "Stop Loss": round(sl, 2),
            "Take Profit": round(tp, 2),
            "Risk (pts)": round(risk, 2),
            "Reward (pts)": round(risk * rr, 2),
            "Outcome": outcome,
            "P&L (R)": round(pnl_r, 2),
        })

    return pd.DataFrame(trades)


# ─── Metrics ─────────────────────────────────────────────────────────────────
def compute_metrics(trades: pd.DataFrame, rr: float) -> dict:
    if trades.empty:
        return {}
    total = len(trades)
    wins = (trades["Outcome"] == "Win").sum()
    losses = total - wins
    win_rate = wins / total * 100

    gross_profit = wins * rr
    gross_loss = losses * 1.0
    profit_factor = gross_profit / gross_loss if gross_loss > 0 else float("inf")

    cumulative = trades["P&L (R)"].cumsum()
    running_max = cumulative.cummax()
    drawdown = cumulative - running_max
    max_dd = drawdown.min()

    net_r = trades["P&L (R)"].sum()
    avg_win_r = rr
    avg_loss_r = -1.0
    expectancy = (win_rate / 100) * avg_win_r + (1 - win_rate / 100) * avg_loss_r

    return {
        "Total Trades": total,
        "Wins": int(wins),
        "Losses": int(losses),
        "Win Rate": f"{win_rate:.1f}%",
        "Profit Factor": f"{profit_factor:.2f}" if profit_factor != float("inf") else "∞",
        "Net P&L": f"{net_r:+.2f} R",
        "Max Drawdown": f"{max_dd:.2f} R",
        "Expectancy / trade": f"{expectancy:+.3f} R",
    }


# ─── Equity Curve Chart ───────────────────────────────────────────────────────
def equity_chart(trades: pd.DataFrame) -> go.Figure:
    cumpl = trades["P&L (R)"].cumsum().reset_index(drop=True)
    colors = ["#00c853" if v >= 0 else "#d50000" for v in cumpl]

    fig = go.Figure()
    fig.add_trace(go.Scatter(
        x=list(range(len(cumpl))),
        y=cumpl,
        mode="lines+markers",
        line=dict(color="#1565c0", width=2),
        marker=dict(size=5, color=colors),
        name="Equity (R)",
        hovertemplate="Trade #%{x}<br>Cumulative P&L: %{y:.2f}R<extra></extra>"
    ))
    fig.add_hline(y=0, line_dash="dash", line_color="gray", line_width=1)

    # Shade drawdown
    running_max = cumpl.cummax()
    dd = cumpl - running_max
    fig.add_trace(go.Scatter(
        x=list(range(len(dd))),
        y=dd,
        fill="tozeroy",
        fillcolor="rgba(213, 0, 0, 0.1)",
        line=dict(color="rgba(213, 0, 0, 0.3)", width=1),
        name="Drawdown (R)",
        hovertemplate="Trade #%{x}<br>Drawdown: %{y:.2f}R<extra></extra>"
    ))

    fig.update_layout(
        title="Equity Curve (R)",
        xaxis_title="Trade #",
        yaxis_title="Cumulative P&L (R)",
        height=380,
        plot_bgcolor="#0e1117",
        paper_bgcolor="#0e1117",
        font=dict(color="#fafafa"),
        legend=dict(orientation="h", yanchor="bottom", y=1.02, xanchor="right", x=1),
        margin=dict(l=40, r=20, t=50, b=40),
        xaxis=dict(gridcolor="#1e2130"),
        yaxis=dict(gridcolor="#1e2130"),
    )
    return fig


# ─── Win/Loss breakdown pie ───────────────────────────────────────────────────
def wl_pie(trades: pd.DataFrame) -> go.Figure:
    counts = trades["Outcome"].value_counts()
    fig = go.Figure(go.Pie(
        labels=counts.index,
        values=counts.values,
        marker_colors=["#00c853", "#d50000"],
        hole=0.45,
        textinfo="label+percent",
        hovertemplate="%{label}: %{value} trades<extra></extra>"
    ))
    fig.update_layout(
        title="Win / Loss Split",
        height=300,
        plot_bgcolor="#0e1117",
        paper_bgcolor="#0e1117",
        font=dict(color="#fafafa"),
        showlegend=False,
        margin=dict(l=10, r=10, t=50, b=10),
    )
    return fig


# ─── Monthly P&L bar chart ────────────────────────────────────────────────────
def monthly_pnl_chart(trades: pd.DataFrame) -> go.Figure:
    t = trades.copy()
    t["Month"] = pd.to_datetime(t["Entry Time"]).dt.to_period("M").astype(str)
    monthly = t.groupby("Month")["P&L (R)"].sum().reset_index()
    colors = ["#00c853" if v >= 0 else "#d50000" for v in monthly["P&L (R)"]]

    fig = go.Figure(go.Bar(
        x=monthly["Month"],
        y=monthly["P&L (R)"],
        marker_color=colors,
        hovertemplate="%{x}<br>P&L: %{y:.2f}R<extra></extra>"
    ))
    fig.add_hline(y=0, line_dash="dash", line_color="gray", line_width=1)
    fig.update_layout(
        title="Monthly P&L (R)",
        xaxis_title="Month",
        yaxis_title="P&L (R)",
        height=300,
        plot_bgcolor="#0e1117",
        paper_bgcolor="#0e1117",
        font=dict(color="#fafafa"),
        xaxis=dict(gridcolor="#1e2130", tickangle=-45),
        yaxis=dict(gridcolor="#1e2130"),
        margin=dict(l=40, r=20, t=50, b=60),
    )
    return fig


# ─── Main execution ──────────────────────────────────────────────────────────
if "trades" not in st.session_state:
    st.session_state.trades = None
    st.session_state.df = None
    st.session_state.fvgs = None
    st.session_state.metrics = None
    st.session_state.last_params = None

params = (period, rr_ratio, tuple(sorted(fvg_types)), min_gap_pct)

if run or (st.session_state.last_params is None):
    st.session_state.last_params = params

    with st.spinner("📥  Downloading XAUUSD 4H data from Yahoo Finance..."):
        try:
            df = load_data(period)
        except Exception as e:
            st.error(f"Data download failed: {e}")
            st.stop()

    with st.spinner(f"🔍  Detecting FVGs in {len(df)} candles..."):
        fvgs = detect_fvgs(df, fvg_types, min_gap_pct)

    with st.spinner(f"⚡  Backtesting {len(fvgs)} FVGs..."):
        trades = backtest(df, fvgs, rr_ratio)
        metrics = compute_metrics(trades, rr_ratio)

    st.session_state.df = df
    st.session_state.fvgs = fvgs
    st.session_state.trades = trades
    st.session_state.metrics = metrics

df = st.session_state.df
fvgs = st.session_state.fvgs
trades = st.session_state.trades
metrics = st.session_state.metrics

if df is None:
    st.stop()

# ── Data info ────────────────────────────────────────────────────────────────
start_date = df.index[0].strftime("%d %b %Y")
end_date = df.index[-1].strftime("%d %b %Y")
st.caption(
    f"📅 Data: {start_date} → {end_date} &nbsp;|&nbsp; "
    f"🕯 {len(df)} candles &nbsp;|&nbsp; "
    f"🔎 {len(fvgs)} FVGs detected &nbsp;|&nbsp; "
    f"📝 {len(trades)} completed trades"
)

if trades.empty:
    st.warning("No completed trades found. Try increasing the lookback period or lowering the minimum FVG size.")
    st.stop()

# ─── Performance Summary ─────────────────────────────────────────────────────
st.subheader("Performance Summary")
cols = st.columns(len(metrics))
icons = ["📊", "✅", "❌", "🎯", "💹", "💰", "📉", "⚖️"]
for col, (label, value), icon in zip(cols, metrics.items(), icons):
    col.metric(label=f"{icon} {label}", value=value)

st.divider()

# ─── Charts ──────────────────────────────────────────────────────────────────
c1, c2, c3 = st.columns([3, 1.2, 1.8])
with c1:
    st.plotly_chart(equity_chart(trades), use_container_width=True)
with c2:
    st.plotly_chart(wl_pie(trades), use_container_width=True)
with c3:
    st.plotly_chart(monthly_pnl_chart(trades), use_container_width=True)

st.divider()

# ─── Trade Log ───────────────────────────────────────────────────────────────
st.subheader("📋 Trade Log")

# Filters
tf1, tf2, _ = st.columns([1, 1, 4])
with tf1:
    outcome_filter = st.selectbox("Filter by Outcome", ["All", "Win", "Loss"], index=0)
with tf2:
    dir_filter = st.selectbox("Filter by Direction", ["All", "Long", "Short"], index=0)

filtered = trades.copy()
if outcome_filter != "All":
    filtered = filtered[filtered["Outcome"] == outcome_filter]
if dir_filter != "All":
    filtered = filtered[filtered["Direction"] == dir_filter]

def color_outcome(val):
    if val == "Win":
        return "color: #00c853; font-weight: bold"
    elif val == "Loss":
        return "color: #ef5350; font-weight: bold"
    return ""

def color_pnl(val):
    if isinstance(val, (int, float)):
        return "color: #00c853" if val > 0 else "color: #ef5350"
    return ""

styled = (
    filtered.style
    .map(color_outcome, subset=["Outcome"])
    .map(color_pnl, subset=["P&L (R)"])
    .format({
        "Entry": "{:.2f}",
        "Stop Loss": "{:.2f}",
        "Take Profit": "{:.2f}",
        "Risk (pts)": "{:.2f}",
        "Reward (pts)": "{:.2f}",
        "P&L (R)": "{:+.2f}",
    })
)
st.dataframe(styled, use_container_width=True, height=400)

# ─── FVG Stats breakdown ─────────────────────────────────────────────────────
st.divider()
st.subheader("📊 Performance by FVG Type")

breakdown = (
    trades.groupby("FVG Type")
    .apply(lambda g: pd.Series({
        "Trades": len(g),
        "Wins": (g["Outcome"] == "Win").sum(),
        "Losses": (g["Outcome"] == "Loss").sum(),
        "Win Rate": f"{(g['Outcome'] == 'Win').mean() * 100:.1f}%",
        "Net P&L (R)": f"{g['P&L (R)'].sum():+.2f}",
    }))
    .reset_index()
)
st.dataframe(breakdown, use_container_width=True, hide_index=True)

# ─── Download ────────────────────────────────────────────────────────────────
st.divider()
csv = trades.to_csv(index=False).encode("utf-8")
st.download_button(
    label="⬇️  Export Trade Log as CSV",
    data=csv,
    file_name="fvg_backtest_XAUUSD.csv",
    mime="text/csv",
)

st.caption("Data source: Yahoo Finance (GC=F — Gold Futures) · Strategy: FVG Retracement · Not financial advice.")
