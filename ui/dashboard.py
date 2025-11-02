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
from core.data_feed import get_historical_data
from core.trader import run_backtest

st.set_page_config(page_title="OpenTrade Bot", layout="wide")

theme = st.sidebar.radio("Theme", ["dark", "light"])
bg_color = "#0E1117" if theme == "dark" else "#FFFFFF"
text_color = "#FFFFFF" if theme == "dark" else "#000000"

st.markdown(f"<h1 style='color:{text_color}'>💹 OpenTrade Bot</h1>", unsafe_allow_html=True)
symbol = st.text_input("Enter NSE Symbol (e.g., RELIANCE, INFY, TCS):", "RELIANCE")

strategy_name = st.selectbox("Select Strategy:", [
    "moving_average", "rsi", "macd", "mean_reversion", "breakout", "momentum"
])

df = get_historical_data(symbol)
strategy = importlib.import_module(f"strategies.{strategy_name}")
df = strategy.apply(df)
portfolio, final_value = run_backtest(df)

fig = go.Figure()
fig.add_trace(go.Scatter(x=df.index, y=df["Close"], mode="lines", name="Price", line=dict(color="#00FFFF")))
fig.update_layout(template="plotly_dark" if theme == "dark" else "plotly_white",
                  paper_bgcolor=bg_color, plot_bgcolor=bg_color, font_color=text_color)
st.plotly_chart(fig, use_container_width=True)
st.write(f"**Final Portfolio Value:** ₹{final_value:,.2f}")
st.dataframe(portfolio.trade_log, use_container_width=True)
