import os
import MetaTrader5 as mt5
import pandas as pd
from dotenv import load_dotenv

load_dotenv()

if not mt5.initialize():
    raise SystemExit(f"MT5 failed to start: {mt5.last_error()}")

logged_in = mt5.login(
    int(os.getenv("MT5_LOGIN")),
    password=os.getenv("MT5_PASSWORD"),
    server=os.getenv("MT5_SERVER"),
)
if not logged_in:
    mt5.shutdown()
    raise SystemExit(f"Login failed: {mt5.last_error()}")

account = mt5.account_info()
print("Balance:", account.balance, account.currency)
print("Leverage:", account.leverage)

symbol = "EURUSD"
mt5.symbol_select(symbol, True)
tick = mt5.symbol_info_tick(symbol)
print(f"{symbol} bid: {tick.bid}  ask: {tick.ask}  spread: {tick.ask - tick.bid:.5f}")

rates = mt5.copy_rates_from_pos(symbol, mt5.TIMEFRAME_H1, 0, 100)
df = pd.DataFrame(rates)
df["time"] = pd.to_datetime(df["time"], unit="s")
print(df.tail())

mt5.shutdown()