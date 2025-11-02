from core.portfolio import Portfolio
import pandas as pd
import numpy as np

def run_backtest(df, initial_capital=100000):
    """Run a simple backtest over a DataFrame with a 'Signal' column.

    Signals should be 1 (buy), -1 (sell) or 0 (hold). NaNs are treated as 0.
    The function only updates last_signal when a non-zero signal occurs to avoid
    propagating NaN values.

    initial_capital: starting cash balance to seed the Portfolio (default 100000)
    """
    # pass the initial capital through to the Portfolio so callers (UI/tests)
    # can control the starting cash used by the backtest.
    portfolio = Portfolio(cash=initial_capital)
    last_signal = 0

    def _scalar_signal(val):
        """Normalize a signal value to a python scalar.

        If the value is a Series/ndarray/list/tuple with length 1, extract the
        single element. If it's a longer sequence, treat it as 0 (no-op).
        """
        # pandas Series
        if isinstance(val, pd.Series):
            if val.shape == ():  # scalar-like
                return val.item()
            if len(val) == 1:
                return val.iloc[0]
            return 0

        # numpy arrays, lists, tuples
        if isinstance(val, (np.ndarray, list, tuple)):
            try:
                if np.asarray(val).size == 1:
                    return np.asarray(val).item()
            except Exception:
                pass
            # non-scalar sequence -> treat as no signal
            return 0

        return val

    for i, row in df.iterrows():
        s = _scalar_signal(row["Signal"])
        # treat NaN as 0
        if pd.isna(s):
            s = 0

        if s == 1 and last_signal != 1:
            portfolio.buy(row["Close"], i)
            last_signal = 1
        elif s == -1 and last_signal != -1:
            portfolio.sell(row["Close"], i)
            last_signal = -1
        # if s == 0: keep last_signal unchanged

    final_value = portfolio.value(df["Close"].iloc[-1])
    return portfolio, final_value
