import os
import time
import MetaTrader5 as mt5
import pandas as pd
from dotenv import load_dotenv

load_dotenv()

SYMBOLS = ["EURUSD", "GBPUSD"]
# extra pairs, daily candles only (used by momentum_weekly.py)
DAILY_ONLY = ["USDJPY", "USDCHF", "USDCAD", "AUDUSD", "NZDUSD"]
FRAMES = {
    "M5": mt5.TIMEFRAME_M5, "M15": mt5.TIMEFRAME_M15, "H1": mt5.TIMEFRAME_H1,
    "H4": mt5.TIMEFRAME_H4, "D1": mt5.TIMEFRAME_D1,
}
# MT5 returns as many candles as the broker has, up to these limits
N_BARS = {"M5": 60000, "M15": 100000, "H1": 60000, "H4": 20000, "D1": 6000}


def connect():
    if not mt5.initialize():
        raise SystemExit(f"MT5 failed to start: {mt5.last_error()}")
    ok = mt5.login(
        int(os.getenv("MT5_LOGIN")),
        password=os.getenv("MT5_PASSWORD"),
        server=os.getenv("MT5_SERVER"),
    )
    if not ok:
        mt5.shutdown()
        raise SystemExit(f"Login failed: {mt5.last_error()}")


def get_candles(symbol, timeframe, n_bars):
    """Asks MT5 for n_bars candles. MT5 often needs a moment to sync a symbol's history, so this
    triggers a download first, waits, and retries with smaller sizes if the request is too big."""
    if not mt5.symbol_select(symbol, True):
        similar = [s.name for s in (mt5.symbols_get(f"*{symbol[:3]}*") or [])][:12]
        raise SystemExit(f"Symbol {symbol} not found on this account. Similar names: {similar}")
    sizes = [n for n in (n_bars, 50000, 30000, 20000, 10000, 6000, 5000, 3000, 2000) if n <= n_bars]
    for attempt in range(3):
        mt5.copy_rates_from_pos(symbol, timeframe, 0, 100)   # wakes up the history download
        time.sleep(3)
        for n in sizes:
            rates = mt5.copy_rates_from_pos(symbol, timeframe, 0, n)
            if rates is not None and len(rates) > 0:
                df = pd.DataFrame(rates)
                df["time"] = pd.to_datetime(df["time"], unit="s")
                return df
            print(f"  {symbol}: asked for {n} candles, MT5 said {mt5.last_error()}, trying fewer...")
        print(f"  {symbol}: no data yet (attempt {attempt + 1} of 3), waiting for MT5 to sync...")
        time.sleep(5)
    raise SystemExit(f"No data for {symbol}: {mt5.last_error()}")


def server_offset_hint(symbol="EURUSD"):
    """Rough server-time offset from UTC. Only valid while the market is open."""
    tick = mt5.symbol_info_tick(symbol)
    server_now = pd.to_datetime(tick.time, unit="s")
    utc_now = pd.Timestamp.now(tz="UTC").tz_localize(None)
    hours = round((server_now - utc_now).total_seconds() / 3600)
    print(f"Estimated server offset from UTC: {hours} hours "
          "(only trust this Monday-Friday while the market is open)")


if __name__ == "__main__":
    connect()
    os.makedirs("data", exist_ok=True)
    for symbol in SYMBOLS:
        for name, tf in FRAMES.items():
            df = get_candles(symbol, tf, N_BARS[name])
            df.to_csv(f"data/{symbol}_{name}.csv", index=False)
            print(f"{symbol} {name}: {len(df)} candles, "
                  f"{df['time'].min()} to {df['time'].max()}")
        info = mt5.symbol_info(symbol)
        m5 = pd.read_csv(f"data/{symbol}_M5.csv")
        avg = m5["spread"].mean() * info.point / 0.0001
        print(f"{symbol} average spread in candle data: {avg:.2f} pips")
    for symbol in DAILY_ONLY:
        try:
            df = get_candles(symbol, mt5.TIMEFRAME_D1, N_BARS["D1"])
        except RuntimeError as e:
            print(f"SKIPPED {symbol}: {e}. Check its exact name in MT5 Market Watch (right-click > Symbols).")
            continue
        df.to_csv(f"data/{symbol}_D1.csv", index=False)
        print(f"{symbol} D1: {len(df)} candles, {df['time'].min()} to {df['time'].max()}")
    server_offset_hint()
    mt5.shutdown()
