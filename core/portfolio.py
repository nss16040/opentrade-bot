class Portfolio:
    def __init__(self, cash=100000):
        self.cash = float(cash)
        self.position = 0.0
        self.trade_log = []

    def _to_scalar(self, v):
        """Coerce a price-like value to a Python float scalar.

        Accepts numbers, numpy scalars/arrays of size 1, and pandas Series of
        length 1. Raises ValueError for longer arrays/series.
        """
        import numbers
        try:
            # pandas Series
            from pandas import Series
        except Exception:
            Series = None

        try:
            import numpy as np
        except Exception:
            np = None

        # pandas Series
        if Series is not None and isinstance(v, Series):
            if v.shape == ():
                return float(v.item())
            if len(v) == 1:
                return float(v.iloc[0])
            raise ValueError("Expected scalar price, got Series with length>1")

        # numpy arrays / scalars
        if np is not None and isinstance(v, (np.ndarray,)):
            if v.size == 1:
                return float(v.item())
            raise ValueError("Expected scalar price, got ndarray with size>1")

        # plain numbers
        if isinstance(v, numbers.Number):
            return float(v)

        # try to coerce otherwise
        try:
            return float(v)
        except Exception:
            raise ValueError(f"Cannot convert price-like value to float: {type(v)!r}")

    def buy(self, price, date):
        p = self._to_scalar(price)
        if self.position == 0:
            self.position = self.cash / p
            self.cash = 0.0
            self.trade_log.append((date, "BUY", p))

    def sell(self, price, date):
        p = self._to_scalar(price)
        if self.position > 0:
            self.cash = self.position * p
            self.position = 0.0
            self.trade_log.append((date, "SELL", p))

    def value(self, current_price):
        p = self._to_scalar(current_price)
        return float(self.cash + self.position * p)
