"""Simple smoke test to exercise a strategy + backtester with synthetic data.

Run from the project root:
    python scripts/smoke_test.py

This script doesn't require network access.
"""
import sys
import os
from pathlib import Path

# ensure project root is on sys.path
repo_root = Path(__file__).resolve().parents[1]
if str(repo_root) not in sys.path:
    sys.path.insert(0, str(repo_root))

import numpy as np
import pandas as pd

from strategies.moving_average import apply as ma_apply
from core.trader import run_backtest
from core.portfolio import Portfolio


def make_prices(n=200, start=100.0, seed=0):
    np.random.seed(seed)
    returns = np.random.normal(loc=0.0005, scale=0.01, size=n)
    price = start * np.exp(np.cumsum(returns))
    return price


def main():
    dates = pd.date_range('2020-01-01', periods=200, freq='D')
    prices = make_prices(len(dates))
    df = pd.DataFrame({'Close': prices, 'High': prices * 1.001, 'Low': prices * 0.999}, index=dates)

    df = ma_apply(df)
    portfolio, final_value = run_backtest(df)

    print(f"Final portfolio value: {final_value:,.2f}")
    print("Trades:")
    for t in portfolio.trade_log:
        print(t)


if __name__ == '__main__':
    main()
