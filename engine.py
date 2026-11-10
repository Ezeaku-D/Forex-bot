import time
import os
import sys
import threading
from datetime import datetime, timezone
import MetaTrader5 as mt5
import pandas as pd
from dotenv import load_dotenv

class TradingEngine(threading.Thread):
    def __init__(self, symbols, mode="AUTO", lot_size=0.01, daily_risk_pct=3.0, weekly_risk_pct=7.0, max_trades=3, log_callback=None, metrics_callback=None):
        super().__init__(daemon=True)
        self.all_symbols = ["EURUSD", "GBPUSD", "USDJPY", "USDCHF", "USDCAD", "AUDUSD", "NZDUSD", "EURGBP"]
        self.symbols = symbols if mode == "MANUAL" else self.all_symbols
        self.mode = mode  # "AUTO" or "MANUAL"
        self.active_symbol = self.symbols[0] if self.symbols else "EURUSD"
        self.lot_size = lot_size
        self.daily_risk_pct = daily_risk_pct
        self.weekly_risk_pct = weekly_risk_pct
        self.max_trades = max_trades
        self.log_callback = log_callback or print
        self.metrics_callback = metrics_callback
        self.running = False

        self.start_balance = 0.0
        self.daily_start_equity = 0.0
        self.account_number = 0
        self.server_name = ""
        self.account_currency = "USD"
        self.leverage_val = 500

    def log(self, message):
        self.log_callback(f"[{time.strftime('%H:%M:%S')}] {message}")

    def set_active_symbol(self, symbol):
        self.active_symbol = symbol

    def connect(self):
        # Resolve .env path dynamically whether running as script or bundled PyInstaller .exe
        base_path = getattr(sys, '_MEIPASS', os.path.dirname(os.path.abspath(__file__)))
        env_path = os.path.join(base_path, '.env')
        
        if os.path.exists(env_path):
            load_dotenv(env_path)
        else:
            load_dotenv()

        if not mt5.initialize():
            self.log(f"MT5 Init Failed: {mt5.last_error()}")
            return False
        
        raw_login = os.getenv("MT5_LOGIN")
        if not raw_login:
            self.log("ERROR: MT5_LOGIN not found in .env file!")
            return False

        login = int(raw_login)
        password = os.getenv("MT5_PASSWORD", "")
        server = os.getenv("MT5_SERVER", "")
        
        if not mt5.login(login, password=password, server=server):
            self.log(f"MT5 Login Failed: {mt5.last_error()}")
            return False
            
        acc = mt5.account_info()
        if acc:
            self.start_balance = acc.balance
            self.daily_start_equity = acc.equity
            self.account_number = acc.login
            self.server_name = acc.server
            self.account_currency = acc.currency
            self.leverage_val = acc.leverage
            self.log(f"Connected as {acc.name} (Account #{acc.login})")
        return True

    def run(self):
        if not self.connect():
            return
        self.running = True
        self.log(f"Bot Engine Active | Mode: {self.mode}")
        if self.mode == "AUTO":
            self.log("Auto-Scanner Activated: Monitoring major pairs to pick the best setup.")
        else:
            self.log(f"Manual Mode Active: Trading user-selected pairs ({', '.join(self.symbols)}).")

        while self.running:
            self.check_account_and_push_metrics()
            
            if self.mode == "AUTO":
                best_pair = self.scan_most_promising_pair()
                if best_pair:
                    self.active_symbol = best_pair
                    self.process_symbol(best_pair)
            else:
                for symbol in self.symbols:
                    if not self.running:
                        break
                    self.process_symbol(symbol)
                    
            time.sleep(1)

    def stop(self, reason="User Stopped"):
        self.running = False
        mt5.shutdown()
        self.log(f"Engine Stopped: {reason}")

    def scan_most_promising_pair(self):
        best_pair = None
        highest_score = -1.0

        for symbol in self.all_symbols:
            if not mt5.symbol_select(symbol, True):
                continue

            rates = mt5.copy_rates_from_pos(symbol, mt5.TIMEFRAME_H1, 0, 30)
            if rates is None or len(rates) < 20:
                continue

            df = pd.DataFrame(rates)
            df['ema'] = df['close'].ewm(span=20, adjust=False).mean()
            
            latest_close = df['close'].iloc[-1]
            latest_ema = df['ema'].iloc[-1]
            trend_dist = abs(latest_close - latest_ema) / latest_close
            
            if trend_dist > highest_score:
                highest_score = trend_dist
                best_pair = symbol

        return best_pair

    def check_account_and_push_metrics(self):
        acc = mt5.account_info()
        if not acc:
            return

        balance = acc.balance
        equity = acc.equity
        profit = acc.profit

        # Active Positions Retrieval
        positions = mt5.positions_get()
        pos_data = []
        if positions:
            for pos in positions:
                pos_data.append({
                    "ticket": pos.ticket,
                    "symbol": pos.symbol,
                    "type": "BUY" if pos.type == mt5.ORDER_TYPE_BUY else "SELL",
                    "volume": pos.volume,
                    "price_open": pos.price_open,
                    "profit": pos.profit,
                })

        # Fetch H1 Candlestick History
        rates = mt5.copy_rates_from_pos(self.active_symbol, mt5.TIMEFRAME_H1, 0, 50)
        candles = []
        dema_vals = []
        rsi_vals = []

        if rates is not None and len(rates) > 0:
            df = pd.DataFrame(rates)
            
            # Real DEMA Calculation
            ema1 = df['close'].ewm(span=20, adjust=False).mean()
            ema2 = ema1.ewm(span=20, adjust=False).mean()
            df['dema'] = 2 * ema1 - ema2
            dema_vals = df['dema'].tolist()

            # Real RSI Calculation
            delta = df['close'].diff()
            gain = (delta.where(delta > 0, 0)).rolling(window=14).mean()
            loss = (-delta.where(delta < 0, 0)).rolling(window=14).mean()
            rs = gain / loss
            df['rsi'] = 100 - (100 / (1 + rs))
            df['rsi'] = df['rsi'].fillna(50)
            rsi_vals = df['rsi'].tolist()

            # Live Candle updates on the last bar using current live tick
            tick = mt5.symbol_info_tick(self.active_symbol)
            if tick and len(df) > 0:
                current_price = tick.bid
                df.at[len(df)-1, 'close'] = current_price
                if current_price > df.at[len(df)-1, 'high']:
                    df.at[len(df)-1, 'high'] = current_price
                if current_price < df.at[len(df)-1, 'low']:
                    df.at[len(df)-1, 'low'] = current_price

            for i, r in df.iterrows():
                candles.append((i, r['open'], r['close'], r['low'], r['high']))

        # Calculate H1 candle countdown
        now = datetime.now(timezone.utc)
        seconds_left = 3600 - (now.minute * 60 + now.second)

        # Drawdown Protection check
        daily_drawdown_pct = max(0.0, ((self.daily_start_equity - equity) / self.daily_start_equity) * 100) if self.daily_start_equity > 0 else 0.0

        if self.metrics_callback:
            account_details = {
                "name": acc.name,
                "login": acc.login,
                "server": acc.server,
                "currency": acc.currency,
                "leverage": acc.leverage,
                "balance": balance,
                "equity": equity,
                "profit": profit,
                "positions": pos_data,
                "candles": candles,
                "dema": dema_vals,
                "rsi": rsi_vals,
                "active_symbol": self.active_symbol,
                "daily_drawdown_pct": daily_drawdown_pct,
                "seconds_left": seconds_left,
                "mode": self.mode
            }
            self.metrics_callback(account_details)

        if daily_drawdown_pct >= self.daily_risk_pct:
            self.log(f"HARD STOP: Daily Max Loss Breach ({daily_drawdown_pct:.2f}%). Liquidating trades!")
            self.close_all_positions()
            self.stop(reason="Daily Risk Limit Breached")

    def process_symbol(self, symbol):
        if not mt5.symbol_select(symbol, True):
            return

    def close_all_positions(self):
        positions = mt5.positions_get()
        if not positions:
            return

        for pos in positions:
            tick = mt5.symbol_info_tick(pos.symbol)
            if not tick:
                continue
            
            order_type = mt5.ORDER_TYPE_SELL if pos.type == mt5.ORDER_TYPE_BUY else mt5.ORDER_TYPE_BUY
            price = tick.bid if pos.type == mt5.ORDER_TYPE_BUY else tick.ask

            req = {
                "action": mt5.TRADE_ACTION_DEAL,
                "position": pos.ticket,
                "symbol": pos.symbol,
                "volume": pos.volume,
                "type": order_type,
                "price": price,
                "deviation": 20,
                "magic": 999888,
                "comment": "Hard Risk Close",
                "type_time": mt5.ORDER_TIME_GTC,
                "type_filling": mt5.ORDER_FILLING_IOC,
            }
            mt5.order_send(req)