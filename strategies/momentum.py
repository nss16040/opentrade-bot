def apply(df, window=10):
    df["Momentum"] = df["Close"] - df["Close"].shift(window)
    df["Signal"] = 0
    df.loc[df["Momentum"] > 0, "Signal"] = 1
    df.loc[df["Momentum"] < 0, "Signal"] = -1
    return df
