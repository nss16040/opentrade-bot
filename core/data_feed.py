import yfinance as yf
from nsetools import Nse

def get_historical_data(symbol: str, period="3mo", interval="1h"):
    """Fetch historical NSE data (free)."""
    df = yf.download(f"{symbol}.NS", period=period, interval=interval)
    # yfinance may return MultiIndex columns when a ticker is provided; e.g.
    # ('Close', 'RELIANCE.NS'). Normalize to single-level column names
    # like 'Close', 'High', 'Low', 'Open', 'Volume' to match strategy code.
    try:
        if hasattr(df.columns, 'nlevels') and df.columns.nlevels > 1:
            df.columns = df.columns.get_level_values(0)
    except Exception:
        # if anything goes wrong, fall back to returning raw df
        pass
    return df

def get_live_price(symbol: str):
    """Get live NSE quote (delayed)."""
    nse = Nse()
    quote = nse.get_quote(symbol)
    return quote["lastPrice"]
