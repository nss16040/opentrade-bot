import sys
from pathlib import Path

# Ensure project root is on sys.path so local packages like `core` and `strategies`
# can be imported even when Streamlit's runner uses a different Python
# environment (common cause of ModuleNotFoundError: No module named 'core').
repo_root = Path(__file__).resolve().parents[1]
if str(repo_root) not in sys.path:
    sys.path.insert(0, str(repo_root))

import streamlit as st
import plotly.graph_objects as go
import importlib
import pandas as pd
import io
from datetime import datetime, timedelta
from zoneinfo import ZoneInfo
from core.data_feed import get_historical_data, get_live_price
from core.trader import run_backtest
from core.news_sentiment import get_news_sentiment
import time

st.set_page_config(page_title="OpenTrade Bot", layout="wide")

theme = st.sidebar.radio("Theme", ["dark", "light"])
bg_color = "#0E1117" if theme == "dark" else "#FFFFFF"
text_color = "#FFFFFF" if theme == "dark" else "#000000"

st.markdown(f"<h1 style='color:{text_color}'>💳 OpenTrade Bot</h1>", unsafe_allow_html=True)

# Controls live in the sidebar for a cleaner main area
symbol = st.sidebar.text_input("Enter NSE Symbol (e.g., RELIANCE, INFY, TCS):", "RELIANCE")

strategy_name = st.sidebar.selectbox("Select Strategy:", [
    "moving_average", "rsi", "macd", "mean_reversion", "breakout", "momentum"
])

# Optionally auto-select strategy based on recent news sentiment
auto_strategy = st.sidebar.checkbox("Auto-select strategy using recent news sentiment", value=False)

# Morning capital input: amount of cash you used before market open
initial_capital = st.sidebar.number_input("Morning capital (₹):", value=100000.0, min_value=0.0, step=1000.0, format="%.2f")

# Summary placement option: Top or Bottom
summary_position = st.sidebar.selectbox("Summary position:", ["Top", "Bottom"], index=1)

# Live price options
use_live_price = st.sidebar.checkbox("Use live price for P&L", value=False)
refresh_interval = st.sidebar.number_input("Refresh interval (seconds)", min_value=1, value=30, step=1)
refresh_now = st.sidebar.button("Refresh price")

# Run controls: auto-run or manual-run
auto_run = st.sidebar.checkbox("Auto-run on change", value=True)
run_backtest_now = st.sidebar.button("Run backtest")

# Show the last auto-poll timestamp (small badge) in the sidebar so users
# can see when the app last refreshed live data automatically.
last_poll = st.session_state.get('last_poll_time')
if last_poll:
    try:
        lp_dt = datetime.fromtimestamp(float(last_poll), ZoneInfo('Asia/Kolkata'))
        st.sidebar.markdown(f"**Last auto-poll:** {lp_dt.strftime('%Y-%m-%d %H:%M:%S %Z')}")
    except Exception:
        st.sidebar.markdown(f"**Last auto-poll:** {last_poll}")
else:
    st.sidebar.markdown("**Last auto-poll:** Never")


# Helper to run the pipeline and render results
def _run_pipeline():
    df = get_historical_data(symbol)
    if df is None or df.empty:
        st.warning("No data returned for symbol. Check the symbol or network access.")
        # return five Nones so callers that unpack expect the same shape
        return None, None, None, None, None

    # Always fetch recent news sentiment (used for display). If auto-select
    # is enabled, use the sentiment to pick a strategy; otherwise just show it.
    sentiment_info = None
    applied_strategy = strategy_name
    with st.spinner('Fetching news sentiment...'):
        try:
            sentiment_info = get_news_sentiment(symbol)
        except Exception as e:
            st.warning(f"News sentiment check failed: {e}")
            sentiment_info = None

    if auto_strategy and sentiment_info is not None:
        label = sentiment_info.get('label')
        if label == 'positive':
            applied_strategy = 'momentum'
        elif label == 'negative':
            applied_strategy = 'mean_reversion'
        else:
            applied_strategy = strategy_name
    # sentiment_info is returned and will be rendered by the main UI so the
    # pipeline remains side-effect free (no direct st.* calls here).

    if applied_strategy != strategy_name:
        st.info(f"Strategy auto-selected based on news: {applied_strategy}")

    # Apply strategy and run backtest
    strategy = importlib.import_module(f"strategies.{applied_strategy}")
    df2 = strategy.apply(df)
    portfolio, final_value = run_backtest(df2, initial_capital=float(initial_capital))
    return df2, portfolio, final_value, sentiment_info, applied_strategy


# Decide whether to run now
should_run = auto_run or run_backtest_now
if not should_run:
    st.info('Adjust inputs in the sidebar and click "Run backtest" or enable "Auto-run on change"')
    st.stop()

# Run the pipeline
df, portfolio, final_value, sentiment_info, applied_strategy = _run_pipeline()
if df is None:
    st.stop()


# Helper: detect NSE market open now (module-level so usable before rendering)
def _is_market_open_now(now_ts: datetime | None = None) -> bool:
    try:
        now = now_ts or datetime.now(ZoneInfo('Asia/Kolkata'))
    except Exception:
        now = datetime.now()
    if now.weekday() >= 5:
        return False
    open_time = now.replace(hour=9, minute=15, second=0, microsecond=0)
    close_time = now.replace(hour=15, minute=30, second=0, microsecond=0)
    return open_time <= now <= close_time


# Auto-polling behavior: when using live price and NSE is open, auto-rerun
# the app at intervals controlled by `refresh_interval`. We use a session
# key `last_poll_time` and call `st.experimental_rerun()` to trigger a re-run
# which will re-fetch live data. This avoids polling while the market is closed.
try:
    if use_live_price and _is_market_open_now():
        last = st.session_state.get('last_poll_time', 0.0)
        now_ts = time.time()
        # if enough time has passed, update timestamp and rerun
        if now_ts - float(last) >= float(refresh_interval):
            st.session_state['last_poll_time'] = now_ts
            # trigger a rerun so live data is refreshed
            try:
                st.experimental_rerun()
            except Exception:
                # if experimental_rerun is not available for some Streamlit envs,
                # fall back to a no-op (user can press Refresh)
                pass
except Exception:
    # be very defensive: never crash the dashboard over auto-refresh
    pass


# Helper to derive a small portfolio snapshot for the UI
def _portfolio_snapshot(portfolio, last_price):
    """Return position qty, entry price, unrealized and realized P&L.

    This is an MVP helper compatible with the simple `Portfolio` model used
    by the backtester (single, all-in position). It infers entry price from
    the most recent BUY and computes realized P&L by pairing BUY->SELL events
    approximately. For production use, expose explicit fields from Portfolio.
    """
    snapshot = {
        'last_price': None,
        'position_qty': 0.0,
        'entry_price': None,
        'unrealized_pl': 0.0,
        'realized_pl': 0.0,
        'last_update': None,
    }

    try:
        snapshot['last_price'] = float(last_price)
    except Exception:
        snapshot['last_price'] = None

    trades = list(getattr(portfolio, 'trade_log', []) or [])
    realized = 0.0
    open_buy_price = None
    for t in trades:
        try:
            _date, action, price = t[0], t[1], float(t[2])
        except Exception:
            continue
        if action == 'BUY':
            open_buy_price = price
        elif action == 'SELL' and open_buy_price is not None:
            # approximate implied qty from initial capital at buy time
            try:
                implied_qty = float(initial_capital) / open_buy_price
            except Exception:
                implied_qty = 1.0
            realized += (price - open_buy_price) * implied_qty
            open_buy_price = None

    snapshot['realized_pl'] = realized

    # open position -> derive entry and unrealized
    if getattr(portfolio, 'position', 0):
        last_buy = None
        for t in reversed(trades):
            try:
                if t[1] == 'BUY':
                    last_buy = float(t[2])
                    break
            except Exception:
                continue
        if last_buy is not None:
            qty = float(portfolio.position)
            snapshot['position_qty'] = qty
            snapshot['entry_price'] = last_buy
            if snapshot['last_price'] is not None:
                snapshot['unrealized_pl'] = (snapshot['last_price'] - last_buy) * qty

    if trades:
        try:
            snapshot['last_update'] = str(trades[-1][0])
        except Exception:
            snapshot['last_update'] = None

    return snapshot


def _render_summary(df, portfolio, final_value, initial_capital, applied_strategy, sentiment_info, trades_df, symbol, use_live_price=False):
    """Render the Summary widget (KPIs, positions, trade log download/preview).

    This function is independent of page layout so we can place the summary
    at the top or bottom of the page.
    """
    # Top-line KPIs
    try:
        init_cap = float(initial_capital)
    except Exception:
        init_cap = None

    try:
        final_val = float(final_value)
    except Exception:
        final_val = None

    try:
        total_return = None if init_cap in (None, 0) or final_val is None else (final_val - init_cap) / init_cap * 100.0
    except Exception:
        total_return = None

    k1, k2, k3 = st.columns(3)
    k1.metric(label="Initial Capital (₹)", value=f"{init_cap:,.2f}" if init_cap is not None else "N/A")
    if final_val is not None:
        k2.metric(label="Final Portfolio Value (₹)", value=f"{final_val:,.2f}", delta=f"{(final_val - init_cap):+.2f}" if init_cap is not None else None)
    else:
        k2.metric(label="Final Portfolio Value (₹)", value="N/A")
    if total_return is not None:
        k3.metric(label="Total Return", value=f"{total_return:.2f}%", delta=f"{total_return:+.2f}%")
    else:
        k3.metric(label="Total Return", value="N/A")

    st.markdown("---")

    # Live positions & P&L card
    st.markdown("### Live positions & P&L")
    # Determine the price to use for P&L: live override or last historical close
    last_price = None
    last_update = None
    if use_live_price:
        try:
            # Attempt to fetch a live price. Note: may be delayed depending on provider.
            last_price = get_live_price(symbol)
            # record last update in IST
            last_update = datetime.now(ZoneInfo('Asia/Kolkata'))
        except Exception as e:
            # fallback to historical close
            try:
                last_price = df['Close'].iloc[-1]
            except Exception:
                last_price = None
    else:
        try:
            last_price = df['Close'].iloc[-1]
        except Exception:
            last_price = None

    snap = _portfolio_snapshot(portfolio, last_price)

    # Market open/closed helper (NSE 09:15-15:30 IST, Mon-Fri)
    def _is_market_open(now_ts: datetime | None = None) -> bool:
        try:
            now = now_ts or datetime.now(ZoneInfo('Asia/Kolkata'))
        except Exception:
            now = datetime.now()
        # weekend
        if now.weekday() >= 5:
            return False
        open_time = now.replace(hour=9, minute=15, second=0, microsecond=0)
        close_time = now.replace(hour=15, minute=30, second=0, microsecond=0)
        return open_time <= now <= close_time

    market_open = _is_market_open()

    if snap.get('position_qty') and snap.get('entry_price') is not None:
        pcol1, pcol2 = st.columns([1, 1])
        with pcol1:
            st.write(f"**Symbol:** {symbol}")
            st.write(f"**Qty:** {snap['position_qty']:.6f}")
            st.write(f"**Entry price:** ₹{snap['entry_price']:.2f}")
        with pcol2:
            if use_live_price and last_update is not None:
                st.write(f"**Last price (live):** ₹{snap['last_price']:.2f}   ")
                st.write(f"_Last update: {last_update.strftime('%Y-%m-%d %H:%M:%S %Z')}_")
                # show market status and staleness
                if not market_open:
                    st.warning("Market appears closed (NSE hours 09:15-15:30 IST). Showing last available quote.")
                else:
                    # if market open but last_update is old, warn
                    try:
                        age = datetime.now(ZoneInfo('Asia/Kolkata')) - last_update
                        if age > timedelta(seconds=refresh_interval * 2):
                            st.warning(f"Price appears stale (last update {int(age.total_seconds())}s ago).")
                    except Exception:
                        pass
            else:
                st.write(f"**Last price:** ₹{snap['last_price']:.2f}   ")
                # show a simple market-closed note if not using live price
                if not market_open:
                    st.info("Market is currently closed — values are from the last available close.")
            st.write(f"**Unrealized P&L:** ₹{snap['unrealized_pl']:.2f}")
            st.write(f"**Realized P&L:** ₹{snap['realized_pl']:.2f}")

        # Compact positions table
        pos_df = pd.DataFrame([{
            'symbol': symbol,
            'qty': snap['position_qty'],
            'entry_price': snap['entry_price'],
            'last_price': snap['last_price'],
            'unrealized_pl': snap['unrealized_pl']
        }])
        st.dataframe(pos_df, use_container_width=True)
    else:
        st.info('No open positions.')

    st.markdown('---')

    # Trade log download and compact preview
    # Headlines & Major events (show here above the trade log download)
    if sentiment_info is not None:
        st.subheader('Headlines & Major events')
        hs = sentiment_info.get('headline_scores') or []
        if hs:
            try:
                df_hs = pd.DataFrame(hs)
                if 'pubDate' in df_hs.columns:
                    cols = ['pubDate'] + [c for c in df_hs.columns if c != 'pubDate']
                    df_hs = df_hs[cols]
                st.dataframe(df_hs, use_container_width=True)
            except Exception:
                for item in hs:
                    title = item.get('headline') or item.get('title')
                    pub = item.get('pubDate')
                    if pub:
                        st.write(f"- {title} (score={item.get('score')}) — {pub}")
                    else:
                        st.write(f"- {title} (score={item.get('score')})")
        else:
            heads = sentiment_info.get('headlines') or []
            if heads:
                for h in heads:
                    if isinstance(h, dict):
                        title = h.get('title') or h.get('headline')
                        pub = h.get('pubDate')
                        if pub:
                            st.write(f"- {title} — {pub}")
                        else:
                            st.write(f"- {title}")
                    else:
                        st.write('-', h)

        ev = sentiment_info.get('events') or []
        if ev:
            st.markdown('---')
            try:
                st.dataframe(pd.DataFrame(ev), use_container_width=True)
            except Exception:
                for e in ev:
                    st.write(f"- {e.get('event')}: {e.get('value')}")

    if not trades_df.empty:
        try:
            csv_bytes = trades_df.to_csv(index=False).encode('utf-8')
            st.download_button(label="Download trade log (CSV)", data=csv_bytes, file_name=f"{symbol}_trade_log.csv", mime='text/csv')
        except Exception:
            st.write('Trade log available in-memory; download not available.')
        # Note: detailed trade log preview intentionally omitted from Summary
        # to keep the summary compact. Use the download button above to
        # retrieve the full trade log, or view it from the dedicated Trades
        # panel in the main app if available.
    else:
        st.write('No trades executed in this backtest.')

# Build the price chart and annotate buys/sells
fig = go.Figure()
fig.add_trace(go.Scatter(x=df.index, y=df["Close"], mode="lines", name="Price", line=dict(color="#00FFFF")))

# convert trade_log to DataFrame for plotting and display
trade_rows = []
for t in getattr(portfolio, 'trade_log', []):
    # expect tuple(date, action, price)
    try:
        trade_rows.append({'date': t[0], 'action': t[1], 'price': t[2]})
    except Exception:
        pass

trades_df = pd.DataFrame(trade_rows)
if not trades_df.empty:
    buys = trades_df[trades_df['action'] == 'BUY']
    sells = trades_df[trades_df['action'] == 'SELL']
    if not buys.empty:
        fig.add_trace(go.Scatter(x=buys['date'], y=buys['price'], mode='markers', name='BUY', marker=dict(symbol='triangle-up', color='green', size=10)))
    if not sells.empty:
        fig.add_trace(go.Scatter(x=sells['date'], y=sells['price'], mode='markers', name='SELL', marker=dict(symbol='triangle-down', color='red', size=10)))

fig.update_layout(template="plotly_dark" if theme == "dark" else "plotly_white",
                  paper_bgcolor=bg_color, plot_bgcolor=bg_color, font_color=text_color)

# Render news sentiment as a static label (no click-to-open)
if sentiment_info is not None:
    label = sentiment_info.get('label', 'unknown')
    score = sentiment_info.get('score', 0.0)
    if label == 'no_news':
        st.write("**News sentiment:** No recent headlines found for this symbol.")
    else:
        st.write(f"**News sentiment:** **{label.capitalize()}** (score={score:.2f})")

# Main chart
st.plotly_chart(fig, use_container_width=True)

# Render summary after the chart
_render_summary(df, portfolio, final_value, initial_capital, applied_strategy, sentiment_info, trades_df, symbol, use_live_price=use_live_price)

# (Headlines & events removed - UI now shows only the sentiment label)

# If the user requested the news modal via the top button, render a modal
if st.session_state.get(f"news_modal_{symbol}", False):
    # prefer native modal when available (Streamlit 1.24+)
    if hasattr(st, 'modal'):
        with st.modal(f"News & Sentiment — {symbol}"):
            # render content inside the native modal
            if sentiment_info is not None:
                st.markdown(f"### Sentiment: **{sentiment_info.get('label')}** (score={sentiment_info.get('score'):.2f})")
                hs = sentiment_info.get('headline_scores') or []
                if hs:
                    try:
                        df_hs = pd.DataFrame(hs)
                        if 'pubDate' in df_hs.columns:
                            cols = ['pubDate'] + [c for c in df_hs.columns if c != 'pubDate']
                            df_hs = df_hs[cols]
                        st.dataframe(df_hs, use_container_width=True)
                    except Exception:
                        for item in hs:
                            title = item.get('headline') or item.get('title')
                            pub = item.get('pubDate')
                            if pub:
                                st.write(f"- {title} (score={item.get('score')}) — {pub}")
                            else:
                                st.write(f"- {title} (score={item.get('score')})")
                else:
                    heads = sentiment_info.get('headlines') or []
                    if heads:
                        for h in heads:
                            if isinstance(h, dict):
                                title = h.get('title') or h.get('headline')
                                pub = h.get('pubDate')
                                if pub:
                                    st.write(f"- {title} — {pub}")
                                else:
                                    st.write(f"- {title}")
                            else:
                                st.write('-', h)
                ev = sentiment_info.get('events') or []
                if ev:
                    st.markdown('---')
                    try:
                        st.dataframe(pd.DataFrame(ev), use_container_width=True)
                    except Exception:
                        for e in ev:
                            st.write(f"- {e.get('event')}: {e.get('value')}")
            if st.button('Close', key=f'close_news_top_{symbol}'):
                st.session_state[f"news_modal_{symbol}"] = False
    else:
        # show a small sidebar notice suggesting an upgrade for a native modal
        st.sidebar.info("Tip: upgrade Streamlit to get a native popup modal (recommended).")

        # still render the details inline inside an expander so functionality
        # is preserved even without modern Streamlit.
        with st.expander(f"News & Sentiment — {symbol}", expanded=True):
            if sentiment_info is not None:
                st.markdown(f"### Sentiment: **{sentiment_info.get('label')}** (score={sentiment_info.get('score'):.2f})")
                hs = sentiment_info.get('headline_scores') or []
                if hs:
                    try:
                        df_hs = pd.DataFrame(hs)
                        if 'pubDate' in df_hs.columns:
                            cols = ['pubDate'] + [c for c in df_hs.columns if c != 'pubDate']
                            df_hs = df_hs[cols]
                        st.dataframe(df_hs, use_container_width=True)
                    except Exception:
                        for item in hs:
                            title = item.get('headline') or item.get('title')
                            pub = item.get('pubDate')
                            if pub:
                                st.write(f"- {title} (score={item.get('score')}) — {pub}")
                            else:
                                st.write(f"- {title} (score={item.get('score')})")
                else:
                    heads = sentiment_info.get('headlines') or []
                    if heads:
                        for h in heads:
                            if isinstance(h, dict):
                                title = h.get('title') or h.get('headline')
                                pub = h.get('pubDate')
                                if pub:
                                    st.write(f"- {title} — {pub}")
                                else:
                                    st.write(f"- {title}")
                            else:
                                st.write('-', h)
                ev = sentiment_info.get('events') or []
                if ev:
                    st.markdown('---')
                    try:
                        st.dataframe(pd.DataFrame(ev), use_container_width=True)
                    except Exception:
                        for e in ev:
                            st.write(f"- {e.get('event')}: {e.get('value')}")

        # (No popup overlay - details intentionally omitted per user preference)
        if st.button('Close', key=f'close_news_top_{symbol}'):
            st.session_state[f"news_modal_{symbol}"] = False
    
