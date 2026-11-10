"""London / Asian-range strategy, tested like the earlier ones (train period, then test period).
Rules are fixed BEFORE running. Do not add or tweak variants after seeing the results.

Idea: the Asian session (00:00-07:00 UTC) builds a quiet range. London opens at 07:00 UTC and often
moves out of it. At most ONE trade per day, and zero on days that fail the filters.
"""
import os
import numpy as np
import pandas as pd
from strategy import to_utc, PIP

SYMBOLS = {"EURUSD": 2.7, "GBPUSD": 3.0}   # spread in pips, measured on the demo account
RANGE_MIN, RANGE_MAX = 20, 60               # skip days whose Asian range (pips) is outside this band
ENTRY_HOURS = (7, 10)                       # only enter on 15-min candles opening 07:00-10:00 UTC
EXIT_HOUR = 16                              # close any open trade at 16:00 UTC
BUFFER = 0.5 * PIP
TRAIN_FRACTION = 0.6
MIN_TRADES = 60                             # fewer trades than this in a period = not trusted

VARIANTS = [
    ("L1 Breakout, target 2R", dict(mode="breakout", rr=2.0, ema=False)),
    ("L2 Breakout, target 2R, H1 EMA50 trend filter", dict(mode="breakout", rr=2.0, ema=True)),
    ("L3 Failed breakout (sweep) reversal, target = far side of range", dict(mode="sweep", rr=None, ema=False)),
]


def prepare(m15, h1):
    m, h = to_utc(m15), to_utc(h1)
    h["ema"] = h["close"].ewm(span=50, adjust=False).mean()
    h["avail"] = (h["time_utc"] + pd.Timedelta(minutes=60)).astype("datetime64[ns]")
    h = h[["avail", "close", "ema"]].rename(columns={"close": "h1_close"}).sort_values("avail")
    m["close_time"] = (m["time_utc"] + pd.Timedelta(minutes=15)).astype("datetime64[ns]")
    m = pd.merge_asof(m.sort_values("close_time"), h, left_on="close_time", right_on="avail")
    m["trend"] = np.sign(m["h1_close"] - m["ema"]).fillna(0)
    m["date"] = m["time_utc"].dt.date
    m["hour"] = m["time_utc"].dt.hour
    return m.reset_index(drop=True)


def trade_day(day, spread, mode, rr, ema, min_asian=24):
    """Returns one trade (a dict) or None. Results are in R (1R = the amount risked)."""
    hour = day["hour"].values
    h, l, c, trend = day["high"].values, day["low"].values, day["close"].values, day["trend"].values
    asian = hour < 7
    if asian.sum() < min_asian:      # too many missing candles in the Asian session
        return None
    hi, lo = h[asian].max(), l[asian].min()
    width = (hi - lo) / PIP
    if not (RANGE_MIN <= width <= RANGE_MAX):
        return None
    sp = spread * PIP
    idx_window = np.where((hour >= ENTRY_HOURS[0]) & (hour < ENTRY_HOURS[1]))[0]
    for i in idx_window:
        if mode == "breakout":
            d = 1 if c[i] > hi else (-1 if c[i] < lo else 0)
            if d == 0:
                continue
            if ema and trend[i] != d:
                return None                      # first breakout was against the trend: no trade today
            entry = c[i] + sp if d == 1 else c[i]
            stop = (lo - BUFFER) if d == 1 else (hi + BUFFER)
            risk = d * (entry - stop)
            target = entry + d * rr * risk
        else:
            up = h[i] > hi + PIP and c[i] < hi   # poked above the range, closed back inside
            dn = l[i] < lo - PIP and c[i] > lo
            if up == dn:
                continue
            d = -1 if up else 1
            entry = c[i] + sp if d == 1 else c[i]
            stop = (l[i] - BUFFER) if d == 1 else (h[i] + BUFFER)
            target = hi if d == 1 else lo
            risk = d * (entry - stop)
            if d * (target - entry) < risk:      # reward smaller than risk: skip the day
                return None
        if risk <= 0:
            return None
        last = np.where((hour >= 7) & (hour < EXIT_HOUR))[0].max()
        exit_price, reason, k_end = None, "TIME", last
        for k in range(i + 1, last + 1):
            if d == 1:
                if l[k] <= stop:
                    exit_price, reason, k_end = stop, "SL", k; break
                if h[k] >= target:
                    exit_price, reason, k_end = target, "TP", k; break
            else:
                if h[k] + sp >= stop:
                    exit_price, reason, k_end = stop, "SL", k; break
                if l[k] + sp <= target:
                    exit_price, reason, k_end = target, "TP", k; break
        if exit_price is None:
            exit_price = c[last] if d == 1 else c[last] + sp
        return {"date": day["date"].iat[0], "direction": "BUY" if d == 1 else "SELL",
                "range_pips": width, "risk_pips": risk / PIP, "exit": reason,
                "r": d * (exit_price - entry) / risk}
    return None


def run_variant(df, spread, **params):
    trades = [t for _, day in df.groupby("date") if (t := trade_day(day.reset_index(drop=True), spread, **params))]
    return pd.DataFrame(trades)


if __name__ == "__main__":
    os.makedirs("results", exist_ok=True)
    rows = []
    for symbol, spread in SYMBOLS.items():
        try:
            m15 = pd.read_csv(f"data/{symbol}_M15.csv", parse_dates=["time"])
            h1 = pd.read_csv(f"data/{symbol}_H1.csv", parse_dates=["time"])
        except FileNotFoundError:
            print(f"Skipping {symbol}: run data.py first"); continue
        df = prepare(m15, h1)
        days = df["date"].nunique()
        first, last = pd.Timestamp(df["date"].min()), pd.Timestamp(df["date"].max())
        split = (first + TRAIN_FRACTION * (last - first)).date()
        print(f"{symbol}: {days} days of data, {first:%Y-%m-%d} to {last:%Y-%m-%d}, split at {split}")
        for name, params in VARIANTS:
            t = run_variant(df, spread, **params)
            if t.empty:
                rows.append({"pair": symbol, "variant": name, "train trades": 0, "train avg R": np.nan,
                             "test trades": 0, "test avg R": np.nan, "per day": 0, "passes": "no"}); continue
            tr, te = t[t["date"] < split], t[t["date"] >= split]
            r1 = tr["r"].mean() if len(tr) else np.nan
            r2 = te["r"].mean() if len(te) else np.nan
            ok = len(tr) >= MIN_TRADES and len(te) >= MIN_TRADES and r1 > 0 and r2 > 0
            rows.append({"pair": symbol, "variant": name, "train trades": len(tr), "train avg R": round(r1, 2),
                         "test trades": len(te), "test avg R": round(r2, 2),
                         "per day": round(len(t) / days, 2), "passes": "YES" if ok else "no"})
            t.to_csv(f"results/{symbol}_{name[:2]}_london_trades.csv", index=False)
    out = pd.DataFrame(rows)
    pd.set_option("display.width", 250)
    print(f"\nTrain = first {TRAIN_FRACTION:.0%} of the days, test = the rest. Spreads: {SYMBOLS}")
    print("'per day' = average trades per day (never more than 1). A variant passes only if it is")
    print(f"positive in BOTH periods with at least {MIN_TRADES} trades in each.\n")
    print(out.to_string(index=False))
    out.to_csv("results/london_results.csv", index=False)
