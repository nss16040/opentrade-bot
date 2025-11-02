def apply(df):
    df["MA20"] = df["Close"].rolling(20).mean()
    df["STD20"] = df["Close"].rolling(20).std()
    df["Upper"] = df["MA20"] + (2 * df["STD20"])
    df["Lower"] = df["MA20"] - (2 * df["STD20"])
    df["Signal"] = 0
    df.loc[df["Close"] < df["Lower"], "Signal"] = 1
    df.loc[df["Close"] > df["Upper"], "Signal"] = -1
    return df
