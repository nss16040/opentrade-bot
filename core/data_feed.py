import yfinance as yf
from nsetools import Nse

# common index mappings for user-friendly inputs
_INDEX_MAP = {
    'NIFTY': '^NSEI',
    'NIFTY50': '^NSEI',
    'NSEI': '^NSEI',
    'NIFTYBANK': '^NSEBANK',
    'BANKNIFTY': '^NSEBANK',
    'SENSEX': '^BSESN',
}


def _normalize_ticker(symbol: str) -> str:
    """Return a ticker string that yfinance understands.

    - If user passed an index name like 'NIFTY' or 'NIFTYBANK' we'll map it to
      the yfinance index symbol (e.g. '^NSEI').
    - If symbol already contains a '.' (e.g. '.NS') or starts with '^', we
      assume the user supplied a full ticker and return it unchanged.
    - Otherwise, append the NSE suffix '.NS' for regular equity tickers.
    """
    s = symbol.strip().upper()
    if s in _INDEX_MAP:
        return _INDEX_MAP[s]
    if s.startswith('^') or '.' in s:
        return s
    return f"{s}.NS"


def get_historical_data(symbol: str, period="3mo", interval="1h"):
    """Fetch historical data (yfinance). Returns a DataFrame or None on failure."""
    ticker = _normalize_ticker(symbol)
    try:
        df = yf.download(ticker, period=period, interval=interval)
    except Exception:
        return None

    # yfinance may return MultiIndex columns when a ticker is provided; e.g.
    # ('Close', 'RELIANCE.NS'). Normalize to single-level column names
    # like 'Close', 'High', 'Low', 'Open', 'Volume' to match strategy code.
    try:
        if hasattr(df.columns, 'nlevels') and df.columns.nlevels > 1:
            df.columns = df.columns.get_level_values(0)
    except Exception:
        # if anything goes wrong, fall back to returning raw df
        pass

    if df is None or df.empty:
        return None
    return df


def get_live_price(symbol: str):
    """Get live NSE quote (delayed) via nsetools (returns last traded price).

    Note: for index symbols (e.g. '^NSEI') nsetools may not return a quote; in
    that case callers should handle exceptions or fall back to historical close.
    """
    nse = Nse()
    # nsetools expects the NSE symbol without suffixes (e.g. 'RELIANCE')
    # If user passed an index ticker like '^NSEI', map it back to a recognizable
    # index name where possible (best-effort).
    s = symbol.strip().upper()
    # reverse-lookup index short names
    rev_map = {v: k for k, v in _INDEX_MAP.items()}
    try:
        if s in rev_map:
            qsym = rev_map[s]
        elif s.endswith('.NS'):
            qsym = s.replace('.NS', '')
        else:
            qsym = s
        quote = nse.get_quote(qsym)
        return quote["lastPrice"]
    except Exception:
        # re-raise to let callers decide fallback behaviour
        raise
