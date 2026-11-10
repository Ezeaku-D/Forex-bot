"""London strategy with a weekly trade budget: 3 to 5 trades per week in TOTAL across EURUSD and GBPUSD.
Rules, fixed before running (hourly candles):
  1. Each day, for each pair, take the London breakout with the EMA50 trend filter (same as L2H):
     Asian range 20-60 pips, first hourly close outside it between 07:00 and 10:00 UTC,
     stop at the other side of the range, 2R target, everything closed by 16:00 UTC.
  2. MAXIMUM 5: once the week has 5 trades, no more are taken until next week.
  3. MINIMUM 3: on Thursday and Friday, if the week has fewer than 3 trades, add fallback trades
     (a pair with no trade that day): enter at 10:00 UTC in the direction of the EMA50 trend,
     30-pip stop, 2R target, closed by 16:00 UTC.
Days are handled in order; within a day EURUSD is handled before GBPUSD.
Do not tweak these rules after seeing the results."""
import os
import numpy as np
import pandas as pd
from london_hourly import prepare_h1
from london_test import trade_day, SYMBOLS, TRAIN_FRACTION, EXIT_HOUR
from strategy import PIP

MAX_PER_WEEK, MIN_PER_WEEK = 5, 3
FALLBACK_STOP_PIPS, RR = 30, 2.0


def fallback_trade(day, spread):
    hour = day["hour"].values
    h, l, c, trend = day["high"].values, day["low"].values, day["close"].values, day["trend"].values
    idx = np.where(hour == 9)[0]                 # the candle that closes at 10:00 UTC
    if len(idx) == 0 or trend[idx[0]] == 0:
        return None
    i, d, sp = idx[0], int(trend[idx[0]]), spread * PIP
    entry = c[i] + sp if d == 1 else c[i]
    risk = FALLBACK_STOP_PIPS * PIP
    stop, target = entry - d * risk, entry + d * RR * risk
    last = np.where((hour >= 7) & (hour < EXIT_HOUR))[0].max()
    exit_price, reason = None, "TIME"
    for k in range(i + 1, last + 1):
        if d == 1:
            if l[k] <= stop:
                exit_price, reason = stop, "SL"; break
            if h[k] >= target:
                exit_price, reason = target, "TP"; break
        else:
            if h[k] + sp >= stop:
                exit_price, reason = stop, "SL"; break
            if l[k] + sp <= target:
                exit_price, reason = target, "TP"; break
    if exit_price is None:
        exit_price = c[last] if d == 1 else c[last] + sp
    return {"date": day["date"].iat[0], "direction": "BUY" if d == 1 else "SELL", "range_pips": np.nan,
            "risk_pips": FALLBACK_STOP_PIPS, "exit": reason, "r": d * (exit_price - entry) / risk}


def run_weekly(days_by_pair):
    """days_by_pair = {pair: {date: day DataFrame}}. Returns all trades."""
    all_dates = sorted(set().union(*[set(d) for d in days_by_pair.values()]))
    weeks = {}
    for dt in all_dates:
        iso = pd.Timestamp(dt).isocalendar()
        weeks.setdefault((iso[0], iso[1]), []).append(dt)
    trades = []
    for week_dates in weeks.values():
        count = 0
        for dt in week_dates:
            taken = set()
            for pair, spread in SYMBOLS.items():
                day = days_by_pair[pair].get(dt)
                if day is None or count >= MAX_PER_WEEK:
                    continue
                t = trade_day(day, spread, mode="breakout", rr=RR, ema=True, min_asian=6)
                if t:
                    t.update(pair=pair, type="breakout"); trades.append(t); taken.add(pair); count += 1
            if dt.weekday() >= 3:                # Thursday or Friday: top up to the minimum
                for pair, spread in SYMBOLS.items():
                    day = days_by_pair[pair].get(dt)
                    if count >= MIN_PER_WEEK or day is None or pair in taken:
                        continue
                    t = fallback_trade(day, spread)
                    if t:
                        t.update(pair=pair, type="fallback"); trades.append(t); taken.add(pair); count += 1
    return pd.DataFrame(trades), weeks


if __name__ == "__main__":
    os.makedirs("results", exist_ok=True)
    pd.set_option("display.width", 250)
    days_by_pair = {}
    for symbol in SYMBOLS:
        try:
            df = prepare_h1(pd.read_csv(f"data/{symbol}_H1.csv", parse_dates=["time"]))
        except FileNotFoundError:
            raise SystemExit(f"Missing data/{symbol}_H1.csv: run data.py first")
        days_by_pair[symbol] = {dt: g.reset_index(drop=True) for dt, g in df.groupby("date")}
    t, weeks = run_weekly(days_by_pair)
    t["week"] = [pd.Timestamp(d).isocalendar()[:2] for d in t["date"]]
    per_week = t.groupby("week").size().reindex(list(weeks.keys()), fill_value=0)
    first, last = pd.Timestamp(t["date"].min()), pd.Timestamp(t["date"].max())
    split = (first + TRAIN_FRACTION * (last - first)).date()
    tr, te = t[t["date"] < split], t[t["date"] >= split]
    print(f"{first:%Y-%m-%d} to {last:%Y-%m-%d}: {len(weeks)} weeks, {len(t)} trades")
    print(f"Trades per week: average {per_week.mean():.2f}, min {per_week.min()}, max {per_week.max()}")
    print("Weeks by number of trades:"); print(per_week.value_counts().sort_index().to_string())
    print(f"\nAll trades:   average {t['r'].mean():+.3f} R, total {t['r'].sum():+.1f} R, "
          f"win rate {(t['r'] > 0).mean() * 100:.0f}%")
    print(f"Train / test: {tr['r'].mean():+.3f} R ({len(tr)} trades)  /  {te['r'].mean():+.3f} R ({len(te)} trades)")
    print("\nBy trade type:"); print(t.groupby("type")["r"].agg(["count", "mean"]).round(3).to_string())
    print("\nBy pair:"); print(t.groupby("pair")["r"].agg(["count", "mean"]).round(3).to_string())
    t["year"] = pd.to_datetime(t["date"]).dt.year
    print("\nBy year:"); print(t.groupby("year")["r"].agg(["count", "mean"]).round(3).to_string())
    t.drop(columns="week").to_csv("results/weekly_trades.csv", index=False)
