def apply(df):
    df["SMA20"] = df["Close"].rolling(20).mean()
    df["SMA50"] = df["Close"].rolling(50).mean()
    df["Signal"] = 0
    df.loc[df["SMA20"] > df["SMA50"], "Signal"] = 1
    df.loc[df["SMA20"] < df["SMA50"], "Signal"] = -1
    return df
