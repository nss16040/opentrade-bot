import numpy as np

def apply(df1, df2):
    """Pairs trading signal: returns df1 with a 'Signal' column.

    Positive signal (1) means go long df1 (spread low), -1 means short df1 (spread high).
    """
    spread = df1["Close"] - df2["Close"]
    mean = spread.rolling(20).mean()
    std = spread.rolling(20).std()
    z = (spread - mean) / std
    signal = np.where(z > 1, -1, np.where(z < -1, 1, 0))

    df = df1.copy()
    df["Signal"] = signal
    return df
