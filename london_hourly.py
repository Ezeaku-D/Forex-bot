"""London / Asian-range strategy on HOURLY candles, to get many more years of data than 15-minute candles allow.
Same rules as L1 and L2 in london_test.py. Fixed before running; do not add or tweak variants afterwards.
(L3 is dropped: it clearly lost in the 15-minute test.)"""
import os
import numpy as np
import pandas as pd
from strategy import to_utc
from london_test import run_variant, SYMBOLS, TRAIN_FRACTION, MIN_TRADES

VARIANTS = [
    ("L1H Breakout, target 2R (hourly)", dict(mode="breakout", rr=2.0, ema=False, min_asian=6)),
    ("L2H Breakout, target 2R, EMA50 trend filter (hourly)", dict(mode="breakout", rr=2.0, ema=True, min_asian=6)),
]


def prepare_h1(h1):
    m = to_utc(h1)
    m["ema"] = m["close"].ewm(span=50, adjust=False).mean()
    m["trend"] = np.sign(m["close"] - m["ema"])      # known at the close of each hourly candle
    m["date"] = m["time_utc"].dt.date
    m["hour"] = m["time_utc"].dt.hour
    return m


if __name__ == "__main__":
    os.makedirs("results", exist_ok=True)
    rows, yearly = [], []
    for symbol, spread in SYMBOLS.items():
        try:
            h1 = pd.read_csv(f"data/{symbol}_H1.csv", parse_dates=["time"])
        except FileNotFoundError:
            print(f"Skipping {symbol}: run data.py first"); continue
        df = prepare_h1(h1)
        days = df["date"].nunique()
        first, last = pd.Timestamp(df["date"].min()), pd.Timestamp(df["date"].max())
        split = (first + TRAIN_FRACTION * (last - first)).date()
        print(f"{symbol}: {days} days of data, {first:%Y-%m-%d} to {last:%Y-%m-%d}, split at {split}")
        for name, params in VARIANTS:
            t = run_variant(df, spread, **params)
            if t.empty:
                continue
            tr, te = t[t["date"] < split], t[t["date"] >= split]
            r1 = tr["r"].mean() if len(tr) else np.nan
            r2 = te["r"].mean() if len(te) else np.nan
            ok = len(tr) >= MIN_TRADES and len(te) >= MIN_TRADES and r1 > 0 and r2 > 0
            rows.append({"pair": symbol, "variant": name, "train trades": len(tr), "train avg R": round(r1, 2),
                         "test trades": len(te), "test avg R": round(r2, 2),
                         "per day": round(len(t) / days, 2), "passes": "YES" if ok else "no"})
            t["year"] = pd.to_datetime(t["date"]).dt.year
            y = t.groupby("year")["r"].agg(["count", "mean"]).round(2).reset_index()
            y.insert(0, "variant", name[:3]); y.insert(0, "pair", symbol)
            yearly.append(y)
            t.to_csv(f"results/{symbol}_{name[:3]}_hourly_trades.csv", index=False)
    out = pd.DataFrame(rows)
    pd.set_option("display.width", 250)
    print(f"\nTrain = first {TRAIN_FRACTION:.0%} of the days, test = the rest. Spreads: {SYMBOLS}")
    print(f"A variant passes only if positive in BOTH periods with at least {MIN_TRADES} trades in each.\n")
    print(out.to_string(index=False))
    print("\nResult by calendar year (trades, average R):")
    print(pd.concat(yearly).to_string(index=False))
    out.to_csv("results/london_hourly_results.csv", index=False)
