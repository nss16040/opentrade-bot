import pandas as pd
import numpy as np

def apply(df, period=14, low=30, high=70):
    delta = df["Close"].diff()
    gain = (delta.where(delta > 0, 0)).rolling(period).mean()
    loss = (-delta.where(delta < 0, 0)).rolling(period).mean()
    rs = gain / loss
    df["RSI"] = 100 - (100 / (1 + rs))
    df["Signal"] = 0
    df.loc[df["RSI"] < low, "Signal"] = 1
    df.loc[df["RSI"] > high, "Signal"] = -1
    return df
