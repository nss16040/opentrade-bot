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
from core.data_feed import get_historical_data
from core.trader import run_backtest
from core.news_sentiment import get_news_sentiment

st.set_page_config(page_title="OpenTrade Bot", layout="wide")

theme = st.sidebar.radio("Theme", ["dark", "light"])
bg_color = "#0E1117" if theme == "dark" else "#FFFFFF"
text_color = "#FFFFFF" if theme == "dark" else "#000000"

st.markdown(f"<h1 style='color:{text_color}'>💹 OpenTrade Bot</h1>", unsafe_allow_html=True)

# Controls live in the sidebar for a cleaner main area
symbol = st.sidebar.text_input("Enter NSE Symbol (e.g., RELIANCE, INFY, TCS):", "RELIANCE")

strategy_name = st.sidebar.selectbox("Select Strategy:", [
    "moving_average", "rsi", "macd", "mean_reversion", "breakout", "momentum"
])

# Optionally auto-select strategy based on recent news sentiment
auto_strategy = st.sidebar.checkbox("Auto-select strategy using recent news sentiment", value=False)

# Morning capital input: amount of cash you used before market open
initial_capital = st.sidebar.number_input("Morning capital (₹):", value=100000.0, min_value=0.0, step=1000.0, format="%.2f")

# Run controls: auto-run or manual-run
auto_run = st.sidebar.checkbox("Auto-run on change", value=True)
run_backtest_now = st.sidebar.button("Run backtest")


# Helper to run the pipeline and render results
def _run_pipeline():
    df = get_historical_data(symbol)
    if df is None or df.empty:
        st.warning("No data returned for symbol. Check the symbol or network access.")
        return None, None, None

    sentiment_info = None
    applied_strategy = strategy_name
    if auto_strategy:
        with st.spinner('Fetching news sentiment...'):
            try:
                sentiment_info = get_news_sentiment(symbol)
                label = sentiment_info.get('label')
                if label == 'positive':
                    applied_strategy = 'momentum'
                elif label == 'negative':
                    applied_strategy = 'mean_reversion'
                else:
                    applied_strategy = strategy_name
            except Exception as e:
                st.warning(f"News sentiment check failed: {e}")
                applied_strategy = strategy_name

    # Display sentiment and headlines/events
    if sentiment_info is not None:
        st.write(f"**News sentiment:** {sentiment_info['label']} (score={sentiment_info['score']:.2f})")
        hs = sentiment_info.get('headline_scores') or []
        if hs:
            st.subheader('Headlines & scores')
            st.dataframe(pd.DataFrame(hs), use_container_width=True)
        else:
            if sentiment_info.get('headlines'):
                with st.expander('Headlines inspected'):
                    for h in sentiment_info['headlines']:
                        st.write('-', h)

        ev = sentiment_info.get('events') or []
        if ev:
            st.subheader('Major events')
            try:
                st.dataframe(pd.DataFrame(ev), use_container_width=True)
            except Exception:
                for e in ev:
                    st.write(f"- {e.get('event')}: {e.get('value')}")

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

# Page layout: chart at top, then two columns for trades and sentiment/events
st.plotly_chart(fig, use_container_width=True)

col1, col2 = st.columns([2, 1])

with col1:
    st.subheader('Trade log')
    if trades_df.empty:
        st.write('No trades executed in this backtest.')
    else:
        # format dates nicely
        try:
            trades_df['date'] = pd.to_datetime(trades_df['date']).dt.tz_localize(None)
        except Exception:
            pass
        st.dataframe(trades_df[['date', 'action', 'price']], use_container_width=True)

with col2:
    st.subheader('Summary')
    st.write(f"**Initial Morning Capital:** ₹{float(initial_capital):,.2f}")
    st.write(f"**Final Portfolio Value:** ₹{final_value:,.2f}")
    st.write(f"**Strategy used:** {applied_strategy}")
    # show events (if not already shown above in the pipeline)
    if sentiment_info is not None:
        ev = sentiment_info.get('events') or []
        if ev:
            st.subheader('Major events')
            try:
                st.dataframe(pd.DataFrame(ev), use_container_width=True)
            except Exception:
                for e in ev:
                    st.write(f"- {e.get('event')}: {e.get('value')}")
