"""DEMA session-overlap strategy. Rules are defined in strategy_notes.md."""
import numpy as np
import pandas as pd

# ---------------- SETTINGS (keep in sync with strategy_notes.md) ----------------
DEMA_PERIOD = 9
SWING_N = 2                  # candles on each side needed to confirm a swing (15-min chart)
RR = 3.0                     # reward-to-risk ratio
SL_BUFFER_PIPS = 0.5         # stop sits this far beyond the signal candle
MIN_RISK_PIPS = 3.0          # skip trades whose stop is tiny (the spread would dominate)
PIP = 0.0001
SERVER_UTC_OFFSET_HOURS = 0  # MT5 server time minus UTC, in hours (0 = confirmed for this account)

# Session overlaps in UTC hours (start inclusive, end exclusive)
WINDOWS = {
    "Sydney/Tokyo": (0, 6),
    "Tokyo/London": (7, 9),
    "London/NewYork": (13, 16),
}


def dema(close, n=DEMA_PERIOD):
    """Double EMA: 2*EMA - EMA(EMA)."""
    e1 = close.ewm(span=n, adjust=False).mean()
    e2 = e1.ewm(span=n, adjust=False).mean()
    return 2 * e1 - e2


def to_utc(df):
    df = df.copy()
    df["time_utc"] = (df["time"] - pd.Timedelta(hours=SERVER_UTC_OFFSET_HOURS)).astype("datetime64[ns]")
    return df


def market_bias(m15, n=SWING_N, bias_minutes=15):
    """15-min market structure.
    Swing high/low: a candle whose high/low is the extreme of n candles on each side
    (only known n candles later, so there is no peeking into the future).
    A candle CLOSING beyond the last swing is a break:
      same direction as the current bias  -> BOS (continuation)
      opposite direction                  -> MSS (reversal)
    The bias becomes +1 (bullish) or -1 (bearish) after each break."""
    high, low, close = m15["high"].values, m15["low"].values, m15["close"].values
    size = len(m15)
    bias = np.zeros(size, dtype=int)
    event = [""] * size
    sw_high = np.full(size, np.nan)   # last unbroken swing high at each candle
    sw_low = np.full(size, np.nan)    # last unbroken swing low at each candle
    last_high = last_low = None
    current = 0
    for i in range(size):
        j = i - n  # candidate swing candle, now has n candles on its right
        if j - n >= 0:
            if high[j - n:i + 1].argmax() == n:
                last_high = high[j]
            if low[j - n:i + 1].argmin() == n:
                last_low = low[j]
        if last_high is not None and close[i] > last_high:
            event[i] = "START" if current == 0 else ("BOS" if current == 1 else "MSS")
            current, last_high = 1, None
        elif last_low is not None and close[i] < last_low:
            event[i] = "START" if current == 0 else ("BOS" if current == -1 else "MSS")
            current, last_low = -1, None
        bias[i] = current
        if last_high is not None:
            sw_high[i] = last_high
        if last_low is not None:
            sw_low[i] = last_low
    out = pd.DataFrame({"bias": bias, "event": event, "swing_high": sw_high, "swing_low": sw_low})
    out["avail"] = (m15["time_utc"] + pd.Timedelta(minutes=bias_minutes)).values  # known at candle close
    return out


def build_signals(m5, m15, entry_minutes=5, bias_minutes=15, use_windows=True):
    """Returns the entry-timeframe data with dema, bias, window and signal (+1 buy, -1 sell, 0 none).
    Defaults reproduce the original strategy (5-min entries, 15-min bias, session windows).
    m5 = entry-timeframe candles, m15 = bias-timeframe candles."""
    m5, m15 = to_utc(m5), to_utc(m15)
    m5["dema"] = dema(m5["close"])
    m5["close_time"] = (m5["time_utc"] + pd.Timedelta(minutes=entry_minutes)).astype("datetime64[ns]")
    b = market_bias(m15, bias_minutes=bias_minutes)
    b["avail"] = b["avail"].astype("datetime64[ns]")
    m5 = pd.merge_asof(
        m5.sort_values("close_time"),
        b[["avail", "bias", "event", "swing_high", "swing_low"]].sort_values("avail"),
        left_on="close_time", right_on="avail",
    )
    m5["bias"] = m5["bias"].fillna(0).astype(int)

    hour = m5["time_utc"].dt.hour
    m5["window"] = ""
    for name, (start, end) in WINDOWS.items():
        m5.loc[(hour >= start) & (hour < end), "window"] = name

    above = m5["close"] > m5["dema"]
    below = m5["close"] < m5["dema"]
    # "first candle that closes above/below the DEMA": the previous candle was on the other side
    cross_up = above & ~above.shift(1, fill_value=False)
    cross_dn = below & ~below.shift(1, fill_value=False)
    in_window = (m5["window"] != "") if use_windows else pd.Series(True, index=m5.index)
    if not use_windows:
        m5["window"] = ""
    m5["signal"] = 0
    m5.loc[cross_up & (m5["bias"] == 1) & in_window, "signal"] = 1
    m5.loc[cross_dn & (m5["bias"] == -1) & in_window, "signal"] = -1
    return m5.reset_index(drop=True)
