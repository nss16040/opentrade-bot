def apply(df, lookback=20):
    df["High_Max"] = df["High"].rolling(lookback).max()
    df["Low_Min"] = df["Low"].rolling(lookback).min()
    df["Signal"] = 0
    df.loc[df["Close"] > df["High_Max"].shift(1), "Signal"] = 1
    df.loc[df["Close"] < df["Low_Min"].shift(1), "Signal"] = -1
    return df
