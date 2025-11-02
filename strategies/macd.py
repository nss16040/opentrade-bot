def apply(df):
    df["EMA12"] = df["Close"].ewm(span=12).mean()
    df["EMA26"] = df["Close"].ewm(span=26).mean()
    df["MACD"] = df["EMA12"] - df["EMA26"]
    df["SignalLine"] = df["MACD"].ewm(span=9).mean()
    df["Signal"] = 0
    df.loc[df["MACD"] > df["SignalLine"], "Signal"] = 1
    df.loc[df["MACD"] < df["SignalLine"], "Signal"] = -1
    return df
