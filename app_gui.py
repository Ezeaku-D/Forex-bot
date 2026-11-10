import sys
import numpy as np
import pyqtgraph as pg
from PyQt6.QtWidgets import (
    QApplication, QMainWindow, QWidget, QVBoxLayout, QHBoxLayout,
    QPushButton, QTextEdit, QLabel, QDoubleSpinBox, QSpinBox, QGroupBox,
    QCheckBox, QGridLayout, QFrame, QTabWidget, QTableWidget, QTableWidgetItem, QHeaderView,
    QSplitter, QScrollArea, QStackedWidget, QProgressBar, QRadioButton, QButtonGroup
)
from PyQt6.QtCore import pyqtSignal, QObject, Qt, QRectF, QPointF
from PyQt6.QtGui import QFont, QPalette, QColor, QPicture, QPainter, QPen, QBrush
from engine import TradingEngine

# High-Precision TradingView Style Candlestick Container
class ForexCandleContainer:
    def __init__(self, plot_widget):
        self.plot = plot_widget
        
        self.bull_bars = pg.BarGraphItem(x=[], y0=[], height=[], width=0.65, brush='#00e676', pen=pg.mkPen('#00e676', width=1))
        self.bear_bars = pg.BarGraphItem(x=[], y0=[], height=[], width=0.65, brush='#ff1744', pen=pg.mkPen('#ff1744', width=1))
        self.wicks = pg.PlotCurveItem(pen=pg.mkPen('#c0c5d5', width=1.2), connect='pairs')
        
        self.plot.addItem(self.wicks)
        self.plot.addItem(self.bull_bars)
        self.plot.addItem(self.bear_bars)

    def set_data(self, candles):
        if not candles:
            return

        x_vals = [c[0] for c in candles]
        open_p = [c[1] for c in candles]
        close_p = [c[2] for c in candles]
        low_p = [c[3] for c in candles]
        high_p = [c[4] for c in candles]

        bull_x, bull_y0, bull_h = [], [], []
        bear_x, bear_y0, bear_h = [], [], []
        wick_pts = []

        for i in range(len(candles)):
            x = x_vals[i]
            o, c, l, h = open_p[i], close_p[i], low_p[i], high_p[i]
            
            wick_pts.extend([x, l, x, h])
            bottom = min(o, c)
            height = max(abs(c - o), 0.00008)
            
            if c >= o:
                bull_x.append(x)
                bull_y0.append(bottom)
                bull_h.append(height)
            else:
                bear_x.append(x)
                bear_y0.append(bottom)
                bear_h.append(height)

        self.bull_bars.setOpts(x=bull_x, y0=bull_y0, height=bull_h)
        self.bear_bars.setOpts(x=bear_x, y0=bear_y0, height=bear_h)
        
        wick_arr = np.array(wick_pts).reshape(-1, 2)
        self.wicks.setData(x=wick_arr[:, 0], y=wick_arr[:, 1])


class StreamSignaler(QObject):
    log_signal = pyqtSignal(str)
    metrics_signal = pyqtSignal(dict)


class QuantumTraderPro(QMainWindow):
    def __init__(self):
        super().__init__()
        self.setWindowTitle("T.R.A.C.K.E.R BOT - Algorithmic Execution Terminal")
        self.resize(1400, 850)

        self.signaler = StreamSignaler()
        self.signaler.log_signal.connect(self.update_log)
        self.signaler.metrics_signal.connect(self.update_metrics)
        self.engine = None
        self.selected_symbol = "EURUSD"
        self.is_dark_mode = True
        
        self.scan_tick = 0
        self.radar_pos = 0

        self.setup_ui()
        self.apply_theme()

    def setup_ui(self):
        main_widget = QWidget()
        self.root_layout = QHBoxLayout(main_widget)
        self.root_layout.setContentsMargins(0, 0, 0, 0)
        self.root_layout.setSpacing(0)

        # 1. LEFT SIDEBAR
        self.sidebar = QFrame()
        self.sidebar.setFixedWidth(220)
        sidebar_layout = QVBoxLayout(self.sidebar)
        sidebar_layout.setContentsMargins(12, 15, 12, 15)

        self.brand_lbl = QLabel("T.R.A.C.K.E.R BOT")
        self.brand_lbl.setFont(QFont("Segoe UI", 11, QFont.Weight.Bold))
        sidebar_layout.addWidget(self.brand_lbl)
        sidebar_layout.addSpacing(15)

        self.profile_card = QFrame()
        pc_layout = QVBoxLayout(self.profile_card)
        pc_layout.setSpacing(2)

        self.lbl_user_name = QLabel("Ezeaku Daniel")
        self.lbl_user_name.setFont(QFont("Segoe UI", 9, QFont.Weight.Bold))

        self.lbl_acc_num = QLabel("Acc: #202670665")
        self.lbl_acc_num.setFont(QFont("Segoe UI", 8))

        self.lbl_broker_tag = QLabel("● Deriv-Demo")
        self.lbl_broker_tag.setFont(QFont("Segoe UI", 8, QFont.Weight.Bold))

        pc_layout.addWidget(self.lbl_user_name)
        pc_layout.addWidget(self.lbl_acc_num)
        pc_layout.addWidget(self.lbl_broker_tag)
        sidebar_layout.addWidget(self.profile_card)
        sidebar_layout.addSpacing(15)

        self.btn_nav_terminal = QPushButton(" 💻 Terminal View")
        self.btn_nav_profile = QPushButton(" 👤 User Profile")

        self.nav_btns = [self.btn_nav_terminal, self.btn_nav_profile]
        for btn in self.nav_btns:
            btn.setFont(QFont("Segoe UI", 9, QFont.Weight.Bold))
            btn.setCursor(Qt.CursorShape.PointingHandCursor)
            sidebar_layout.addWidget(btn)

        sidebar_layout.addSpacing(15)

        # THEME TOGGLE BUTTON
        self.btn_theme_toggle = QPushButton("🌙 Dark Mode")
        self.btn_theme_toggle.setFont(QFont("Segoe UI", 9, QFont.Weight.Bold))
        self.btn_theme_toggle.setCursor(Qt.CursorShape.PointingHandCursor)
        self.btn_theme_toggle.clicked.connect(self.toggle_theme)
        sidebar_layout.addWidget(self.btn_theme_toggle)

        sidebar_layout.addStretch()

        self.diag_card = QFrame()
        dc_layout = QVBoxLayout(self.diag_card)
        dc_layout.setSpacing(4)

        self.lbl_ping = QLabel("MT5 Ping: 12ms")
        self.lbl_ping.setFont(QFont("Segoe UI", 8))
        self.lbl_trades_count = QLabel("Active Trades: 0/3")
        self.lbl_trades_count.setFont(QFont("Segoe UI", 8))

        dc_layout.addWidget(self.lbl_ping)
        dc_layout.addWidget(self.lbl_trades_count)
        sidebar_layout.addWidget(self.diag_card)

        self.root_layout.addWidget(self.sidebar)

        # 2. MAIN STACKED VIEW
        self.stacked_views = QStackedWidget()
        page_terminal = self.create_terminal_view()
        page_profile = self.create_profile_view()

        self.stacked_views.addWidget(page_terminal)
        self.stacked_views.addWidget(page_profile)
        self.root_layout.addWidget(self.stacked_views, stretch=1)

        self.btn_nav_terminal.clicked.connect(lambda: self.stacked_views.setCurrentIndex(0))
        self.btn_nav_profile.clicked.connect(lambda: self.stacked_views.setCurrentIndex(1))

        self.setCentralWidget(main_widget)

    def create_terminal_view(self):
        page = QWidget()
        main_layout = QVBoxLayout(page)
        main_layout.setContentsMargins(8, 8, 8, 8)
        main_layout.setSpacing(6)

        # HEADER BAR
        self.header_frame = QFrame()
        header_layout = QHBoxLayout(self.header_frame)
        header_layout.setContentsMargins(15, 6, 15, 6)

        self.lbl_bal = self.add_header_stat(header_layout, "BALANCE", "$0.00", "#00e676")
        self.lbl_eq = self.add_header_stat(header_layout, "EQUITY", "$0.00", "#29b6f6")
        self.lbl_pnl = self.add_header_stat(header_layout, "FLOATING P&L", "$0.00", "#00e676")

        header_layout.addStretch()

        self.btn_power = QPushButton("POWER BOT: OFF")
        self.btn_power.setFont(QFont("Segoe UI", 9, QFont.Weight.Bold))
        self.btn_power.setCursor(Qt.CursorShape.PointingHandCursor)
        self.btn_power.clicked.connect(self.toggle_engine)
        header_layout.addWidget(self.btn_power)

        main_layout.addWidget(self.header_frame)

        self.main_splitter = QSplitter(Qt.Orientation.Horizontal)

        # WATCHLIST & MODE SELECTION PANEL
        self.watchlist_frame = QFrame()
        wl_layout = QVBoxLayout(self.watchlist_frame)
        wl_layout.setContentsMargins(8, 8, 8, 8)
        
        self.mode_box = QGroupBox("EXECUTION MODE")
        self.mode_box.setFont(QFont("Segoe UI", 8, QFont.Weight.Bold))
        mode_layout = QVBoxLayout()
        mode_layout.setContentsMargins(8, 12, 8, 8)
        mode_layout.setSpacing(6)
        
        self.rad_auto = QRadioButton("Auto-Scan Best Pair")
        self.rad_manual = QRadioButton("Manual Select Pairs")
        self.rad_auto.setChecked(True)
        
        self.mode_group = QButtonGroup()
        self.mode_group.addButton(self.rad_auto)
        self.mode_group.addButton(self.rad_manual)
        self.rad_manual.toggled.connect(self.toggle_selection_mode)

        mode_layout.addWidget(self.rad_auto)
        mode_layout.addWidget(self.rad_manual)
        self.mode_box.setLayout(mode_layout)
        wl_layout.addWidget(self.mode_box)

        wl_title = QLabel("LIVE WATCHLIST & QUOTES")
        wl_title.setFont(QFont("Segoe UI", 9, QFont.Weight.Bold))
        wl_layout.addWidget(wl_title)

        self.pair_boxes = {}
        self.pair_frames = {}
        self.pair_price_lbls = {}
        self.pair_change_lbls = {}

        pairs_meta = [
            ("EURUSD", "1.1245", "+0.12%"),
            ("GBPUSD", "1.2980", "+0.08%"),
            ("USDJPY", "154.20", "-0.15%"),
            ("USDCHF", "0.8840", "-0.04%"),
            ("USDCAD", "1.3910", "+0.03%"),
            ("AUDUSD", "0.6580", "+0.21%"),
            ("NZDUSD", "0.5940", "-0.11%"),
            ("EURGBP", "0.8660", "+0.02%")
        ]
        
        for pair, mock_p, mock_c in pairs_meta:
            p_frame = QFrame()
            p_frame.setCursor(Qt.CursorShape.PointingHandCursor)
            p_layout = QHBoxLayout(p_frame)
            p_layout.setContentsMargins(8, 6, 8, 6)

            cb = QCheckBox(pair)
            cb.setFont(QFont("Segoe UI", 9, QFont.Weight.Bold))
            cb.setEnabled(False)
            if pair in ["EURUSD", "GBPUSD"]:
                cb.setChecked(True)
            self.pair_boxes[pair] = cb
            p_layout.addWidget(cb)

            p_layout.addStretch()

            v_info = QVBoxLayout()
            v_info.setSpacing(1)
            lbl_price = QLabel(mock_p)
            lbl_price.setFont(QFont("Consolas", 8, QFont.Weight.Bold))
            lbl_price.setAlignment(Qt.AlignmentFlag.AlignRight)

            lbl_change = QLabel(mock_c)
            lbl_change.setFont(QFont("Segoe UI", 7, QFont.Weight.Bold))
            lbl_change.setAlignment(Qt.AlignmentFlag.AlignRight)
            if "-" in mock_c:
                lbl_change.setStyleSheet("color: #ff1744;")
            else:
                lbl_change.setStyleSheet("color: #00e676;")

            v_info.addWidget(lbl_price)
            v_info.addWidget(lbl_change)
            p_layout.addLayout(v_info)

            p_frame.mousePressEvent = lambda event, p=pair: self.select_active_symbol(p)

            self.pair_frames[pair] = p_frame
            self.pair_price_lbls[pair] = lbl_price
            self.pair_change_lbls[pair] = lbl_change
            wl_layout.addWidget(p_frame)

        wl_layout.addStretch()
        self.main_splitter.addWidget(self.watchlist_frame)

        # CHART FRAME WITH LIVE TIMER BADGE
        self.chart_frame = QFrame()
        chart_layout = QVBoxLayout(self.chart_frame)

        chart_hdr_layout = QHBoxLayout()
        self.chart_title = QLabel("EURUSD - H1 Candlestick Chart & Technical Indicators")
        self.chart_title.setFont(QFont("Segoe UI", 10, QFont.Weight.Bold))
        chart_hdr_layout.addWidget(self.chart_title)
        
        self.lbl_candle_timer = QLabel("⏳ BAR CLOSE: --:--")
        self.lbl_candle_timer.setFont(QFont("Consolas", 9, QFont.Weight.Bold))
        chart_hdr_layout.addWidget(self.lbl_candle_timer)

        chart_layout.addLayout(chart_hdr_layout)

        self.plot_main = pg.PlotWidget()
        self.plot_main.showGrid(x=True, y=True, alpha=0.2)
        
        self.candle_container = ForexCandleContainer(self.plot_main)
        self.curve_dema = self.plot_main.plot(pen=pg.mkPen(color='#ff9100', width=2))
        chart_layout.addWidget(self.plot_main, stretch=3)

        self.plot_sub = pg.PlotWidget()
        self.plot_sub.showGrid(x=True, y=True, alpha=0.2)
        self.plot_sub.setYRange(0, 100)
        self.plot_sub.setXLink(self.plot_main)
        
        self.curve_rsi = self.plot_sub.plot(pen=pg.mkPen(color='#00e676', width=1.5))
        self.plot_sub.addLine(y=70, pen=pg.mkPen('#ff1744', width=0.8, style=Qt.PenStyle.DashLine))
        self.plot_sub.addLine(y=30, pen=pg.mkPen('#00e676', width=0.8, style=Qt.PenStyle.DashLine))
        chart_layout.addWidget(self.plot_sub, stretch=1)

        self.main_splitter.addWidget(self.chart_frame)

        # PROTECTION DOCK
        dock_scroll = QScrollArea()
        dock_scroll.setWidgetResizable(True)
        dock_scroll.setStyleSheet("QScrollArea { border: none; background-color: transparent; }")

        self.dock_frame = QFrame()
        dock_layout = QVBoxLayout(self.dock_frame)

        self.dock_title = QLabel("RISK & PROTECTION CAP")
        self.dock_title.setFont(QFont("Segoe UI", 9, QFont.Weight.Bold))
        dock_layout.addWidget(self.dock_title)

        risk_grid = QGridLayout()
        risk_grid.setSpacing(8)

        risk_grid.addWidget(QLabel("Lot Size:"), 0, 0)
        self.lot_input = QDoubleSpinBox()
        self.lot_input.setRange(0.01, 10.0)
        self.lot_input.setValue(0.01)
        risk_grid.addWidget(self.lot_input, 0, 1)

        risk_grid.addWidget(QLabel("Max Daily Loss:"), 1, 0)
        self.daily_risk = QDoubleSpinBox()
        self.daily_risk.setRange(0.5, 50.0)
        self.daily_risk.setValue(3.0)
        self.daily_risk.setSuffix("%")
        risk_grid.addWidget(self.daily_risk, 1, 1)

        risk_grid.addWidget(QLabel("Max Weekly Loss:"), 2, 0)
        self.weekly_risk = QDoubleSpinBox()
        self.weekly_risk.setRange(1.0, 50.0)
        self.weekly_risk.setValue(7.0)
        self.weekly_risk.setSuffix("%")
        risk_grid.addWidget(self.weekly_risk, 2, 1)

        risk_grid.addWidget(QLabel("Max Open Trades:"), 3, 0)
        self.max_trades = QSpinBox()
        self.max_trades.setRange(1, 10)
        self.max_trades.setValue(3)
        risk_grid.addWidget(self.max_trades, 3, 1)

        dock_layout.addLayout(risk_grid)
        dock_layout.addSpacing(10)

        dock_layout.addWidget(QLabel("Daily Drawdown Used:"))
        self.drawdown_bar = QProgressBar()
        self.drawdown_bar.setRange(0, 100)
        self.drawdown_bar.setValue(0)
        dock_layout.addWidget(self.drawdown_bar)
        dock_layout.addSpacing(10)

        self.btn_buy = QPushButton("BUY MARKET")
        self.btn_buy.setStyleSheet("background-color: #00c853; color: white; font-weight: bold; padding: 10px; border-radius: 4px;")
        dock_layout.addWidget(self.btn_buy)

        self.btn_sell = QPushButton("SELL MARKET")
        self.btn_sell.setStyleSheet("background-color: #d50000; color: white; font-weight: bold; padding: 10px; border-radius: 4px;")
        dock_layout.addWidget(self.btn_sell)

        dock_layout.addStretch()
        dock_scroll.setWidget(self.dock_frame)
        self.main_splitter.addWidget(dock_scroll)

        self.main_splitter.setSizes([260, 710, 280])
        main_layout.addWidget(self.main_splitter, stretch=4)

        # CONSOLE & RADAR
        console_container = QWidget()
        console_layout = QVBoxLayout(console_container)
        console_layout.setContentsMargins(0, 0, 0, 0)
        console_layout.setSpacing(2)

        console_header = QHBoxLayout()
        console_header.setContentsMargins(6, 2, 6, 2)
        
        self.lbl_bot_state = QLabel("STATE: ENGINE IDLE")
        self.lbl_bot_state.setFont(QFont("Segoe UI", 8, QFont.Weight.Bold))
        console_header.addWidget(self.lbl_bot_state)

        self.radar_bar = QProgressBar()
        self.radar_bar.setFixedHeight(12)
        self.radar_bar.setRange(0, 100)
        self.radar_bar.setTextVisible(False)
        console_header.addWidget(self.radar_bar, stretch=1)
        console_layout.addLayout(console_header)

        self.bottom_tabs = QTabWidget()
        self.log_display = QTextEdit()
        self.log_display.setReadOnly(True)
        self.log_display.setFont(QFont("Consolas", 9))
        self.bottom_tabs.addTab(self.log_display, "Execution Console")

        self.table_pos = QTableWidget(0, 6)
        self.table_pos.setHorizontalHeaderLabels(["Ticket", "Symbol", "Type", "Volume", "Open Price", "PnL ($)"])
        self.table_pos.horizontalHeader().setSectionResizeMode(QHeaderView.ResizeMode.Stretch)
        self.bottom_tabs.addTab(self.table_pos, "Active Positions (0)")

        console_layout.addWidget(self.bottom_tabs)
        main_layout.addWidget(console_container, stretch=2)
        return page

    def create_profile_view(self):
        page = QWidget()
        layout = QVBoxLayout(page)
        layout.setContentsMargins(25, 25, 25, 25)

        title = QLabel("TRADER PROFILE & MT5 CONNECTION")
        title.setFont(QFont("Segoe UI", 12, QFont.Weight.Bold))
        layout.addWidget(title)

        grid = QGridLayout()
        grid.setSpacing(15)

        self.p_name = self.add_profile_card(grid, "Trader Name", "Ezeaku Daniel", 0, 0)
        self.p_account = self.add_profile_card(grid, "Account Login", "202670665", 0, 1)
        self.p_server = self.add_profile_card(grid, "Broker Server", "Deriv-Demo", 1, 0)
        self.p_currency = self.add_profile_card(grid, "Currency / Leverage", "USD / 1:500", 1, 1)
        self.p_status = self.add_profile_card(grid, "API Connection", "Connected", 2, 0)
        self.p_strategy = self.add_profile_card(grid, "Active Strategy", "DEMA Session-Overlap", 2, 1)

        layout.addLayout(grid)
        layout.addStretch()
        return page

    def toggle_theme(self):
        self.is_dark_mode = not self.is_dark_mode
        self.apply_theme()

    def apply_theme(self):
        if self.is_dark_mode:
            self.btn_theme_toggle.setText("🌙 Dark Mode")
            bg_window = "#0d0e15"
            bg_sidebar = "#12131a"
            bg_card = "#181922"
            border_col = "#232533"
            text_main = "#ffffff"
            text_sub = "#a0a5b5"
            
            pg.setConfigOption('background', bg_window)
            pg.setConfigOption('foreground', text_sub)
            self.plot_main.setBackground(bg_window)
            self.plot_sub.setBackground(bg_window)

            app_style = f"""
                QMainWindow, QWidget {{ background-color: {bg_window}; color: {text_main}; }}
                QFrame {{ background-color: {bg_card}; border: 1px solid {border_col}; border-radius: 6px; }}
                QGroupBox {{ color: {text_sub}; font-weight: bold; border: 1px solid {border_col}; margin-top: 6px; padding: 4px; }}
                QGroupBox::title {{ subcontrol-origin: margin; left: 6px; }}
                QPushButton {{ background-color: #1f212e; color: {text_main}; border: 1px solid {border_col}; padding: 8px; border-radius: 4px; }}
                QPushButton:hover {{ background-color: #2b2e40; }}
                QTextEdit, QTableWidget {{ background-color: #090a0f; color: #00e676; border: 1px solid {border_col}; }}
                QHeaderView::section {{ background-color: {bg_card}; color: {text_sub}; border: 1px solid {border_col}; padding: 4px; }}
                QProgressBar {{ border: 1px solid {border_col}; border-radius: 4px; background: #0d0e15; text-align: center; color: white; }}
                QProgressBar::chunk {{ background-color: #00c853; }}
                QTabBar::tab {{ background: {bg_card}; color: {text_sub}; padding: 6px 16px; border-top-left-radius: 4px; border-top-right-radius: 4px; }}
                QTabBar::tab:selected {{ background: {border_col}; color: #00e676; font-weight: bold; }}
            """
        else:
            self.btn_theme_toggle.setText("☀️ Light Mode")
            bg_window = "#f1f5f9"
            bg_sidebar = "#ffffff"
            bg_card = "#ffffff"
            border_col = "#cbd5e1"
            text_main = "#0f172a"
            text_sub = "#475569"
            chart_bg = "#f8fafc"

            pg.setConfigOption('background', chart_bg)
            pg.setConfigOption('foreground', text_sub)
            self.plot_main.setBackground(chart_bg)
            self.plot_sub.setBackground(chart_bg)

            app_style = f"""
                QMainWindow, QWidget {{ background-color: {bg_window}; color: {text_main}; font-family: 'Segoe UI', sans-serif; }}
                QFrame {{ background-color: {bg_card}; border: 1px solid {border_col}; border-radius: 6px; }}
                QGroupBox {{ color: {text_main}; font-weight: bold; border: 1px solid {border_col}; margin-top: 6px; padding: 6px; background: {bg_card}; }}
                QGroupBox::title {{ subcontrol-origin: margin; left: 8px; color: {text_main}; }}
                
                QLabel {{ color: {text_main}; }}
                
                QDoubleSpinBox, QSpinBox {{
                    background-color: #f8fafc;
                    color: {text_main};
                    border: 1px solid {border_col};
                    padding: 4px;
                    border-radius: 4px;
                    font-weight: bold;
                }}
                QDoubleSpinBox:focus, QSpinBox:focus {{
                    border: 1px solid #2563eb;
                }}

                QPushButton {{
                    background-color: #ffffff;
                    color: {text_main};
                    border: 1px solid {border_col};
                    padding: 8px;
                    border-radius: 4px;
                    font-weight: 600;
                }}
                QPushButton:hover {{
                    background-color: #f8fafc;
                    border-color: #94a3b8;
                }}
                
                QTextEdit {{
                    background-color: #0f172a;
                    color: #38bdf8;
                    border: 1px solid {border_col};
                    font-family: Consolas;
                    font-size: 11px;
                }}
                QTableWidget {{
                    background-color: #ffffff;
                    color: {text_main};
                    border: 1px solid {border_col};
                    gridline-color: #e2e8f0;
                }}
                QHeaderView::section {{
                    background-color: #f8fafc;
                    color: {text_main};
                    border: 1px solid {border_col};
                    padding: 4px;
                    font-weight: bold;
                }}
                
                QProgressBar {{
                    border: 1px solid {border_col};
                    border-radius: 4px;
                    background: #e2e8f0;
                    text-align: center;
                    color: {text_main};
                    font-weight: bold;
                }}
                QProgressBar::chunk {{
                    background-color: #10b981;
                }}
                
                QTabBar::tab {{
                    background: #e2e8f0;
                    color: {text_sub};
                    padding: 6px 16px;
                    border-top-left-radius: 4px;
                    border-top-right-radius: 4px;
                    font-weight: 600;
                }}
                QTabBar::tab:selected {{
                    background: #ffffff;
                    color: #0f172a;
                    border-top: 2px solid #2563eb;
                    font-weight: bold;
                }}
            """

        self.setStyleSheet(app_style)
        self.sidebar.setStyleSheet(f"background-color: {bg_sidebar}; border-right: 1px solid {border_col};")
        self.brand_lbl.setStyleSheet("color: #00e676;" if self.is_dark_mode else "color: #0284c7; font-weight: bold;")
        self.lbl_broker_tag.setStyleSheet("color: #00e676;" if self.is_dark_mode else "color: #059669;")
        
        self.lbl_candle_timer.setStyleSheet(
            "color: #00e676; background: #181922; padding: 2px 8px; border-radius: 3px;"
            if self.is_dark_mode else
            "color: #0284c7; background: #e0f2fe; padding: 2px 8px; border-radius: 3px; font-weight: bold;"
        )

        for pair, frame in self.pair_frames.items():
            is_active = (pair == self.selected_symbol)
            if self.is_dark_mode:
                border = "#00e676" if is_active else border_col
                bg = "#1c1e2b" if is_active else "#181922"
            else:
                border = "#0284c7" if is_active else border_col
                bg = "#e0f2fe" if is_active else "#ffffff"
            frame.setStyleSheet(f"background-color: {bg}; border: 1px solid {border}; border-radius: 4px;")

    def toggle_selection_mode(self, manual_active):
        for cb in self.pair_boxes.values():
            cb.setEnabled(manual_active)

    def add_profile_card(self, grid, label, val, row, col):
        card = QFrame()
        l_layout = QVBoxLayout(card)
        
        lbl_t = QLabel(label)
        lbl_t.setStyleSheet("font-size: 10px; font-weight: bold;")
        lbl_v = QLabel(val)
        lbl_v.setStyleSheet("color: #00e676; font-size: 14px; font-weight: bold;" if self.is_dark_mode else "color: #0284c7; font-size: 14px; font-weight: bold;")
        
        l_layout.addWidget(lbl_t)
        l_layout.addWidget(lbl_v)
        grid.addWidget(card, row, col)
        return lbl_v

    def select_active_symbol(self, symbol):
        self.selected_symbol = symbol
        self.chart_title.setText(f"{symbol} - H1 Candlestick Chart & Technical Indicators")
        if self.engine:
            self.engine.set_active_symbol(symbol)
        self.apply_theme()

    def resizeEvent(self, event):
        w = event.size().width()
        if w < 950:
            self.main_splitter.setOrientation(Qt.Orientation.Vertical)
            self.plot_sub.setVisible(False)
        else:
            self.main_splitter.setOrientation(Qt.Orientation.Horizontal)
            self.plot_sub.setVisible(True)
        super().resizeEvent(event)

    def add_header_stat(self, layout, title, val, color):
        vbox = QVBoxLayout()
        vbox.setSpacing(1)
        lbl_t = QLabel(title)
        lbl_t.setStyleSheet("font-size: 8px; font-weight: bold;")
        lbl_v = QLabel(val)
        lbl_v.setStyleSheet(f"color: {color}; font-size: 15px; font-weight: bold;")
        vbox.addWidget(lbl_t)
        vbox.addWidget(lbl_v)
        layout.addLayout(vbox)
        layout.addSpacing(15)
        return lbl_v

    def route_log(self, text):
        self.signaler.log_signal.emit(text)

    def route_metrics(self, data):
        self.signaler.metrics_signal.emit(data)

    def update_log(self, text):
        self.log_display.append(text)

    def update_metrics(self, d):
        bal = d["balance"]
        eq = d["equity"]
        pnl = d["profit"]

        self.lbl_bal.setText(f"${bal:,.2f}")
        self.lbl_eq.setText(f"${eq:,.2f}")
        pnl_color = "#00e676" if pnl >= 0 else "#ff1744"
        self.lbl_pnl.setText(f"${pnl:+,.2f}")
        self.lbl_pnl.setStyleSheet(f"color: {pnl_color}; font-size: 15px; font-weight: bold;")

        self.p_account.setText(str(d["login"]))
        self.p_server.setText(d["server"])
        self.p_currency.setText(f"{d['currency']} / 1:{d['leverage']}")

        sec_remaining = d.get("seconds_left", 3600)
        mins = sec_remaining // 60
        secs = sec_remaining % 60
        self.lbl_candle_timer.setText(f"⏳ BAR CLOSE: {mins:02d}m {secs:02d}s")

        candles = d.get("candles", [])
        if candles:
            self.candle_container.set_data(candles)

            close_prices = [c[2] for c in candles]
            high_prices = [c[4] for c in candles]
            low_prices = [c[3] for c in candles]
            x_data = list(range(len(close_prices)))

            min_val, max_val = min(low_prices), max(high_prices)
            pad = (max_val - min_val) * 0.08 if max_val > min_val else 0.001
            
            self.plot_main.setYRange(min_val - pad, max_val + pad, padding=0)
            self.plot_main.setXRange(0, len(candles), padding=0)

            dema_vals = d.get("dema", [p * 0.9998 for p in close_prices])
            self.curve_dema.setData(x_data, dema_vals)
            
            rsi_vals = d.get("rsi", [50 + (i % 20) - 10 for i in x_data])
            self.curve_rsi.setData(x_data, rsi_vals)

        positions = d.get("positions", [])
        self.table_pos.setRowCount(len(positions))
        for row, pos in enumerate(positions):
            self.table_pos.setItem(row, 0, QTableWidgetItem(str(pos["ticket"])))
            self.table_pos.setItem(row, 1, QTableWidgetItem(pos["symbol"]))
            self.table_pos.setItem(row, 2, QTableWidgetItem(pos["type"]))
            self.table_pos.setItem(row, 3, QTableWidgetItem(str(pos["volume"])))
            self.table_pos.setItem(row, 4, QTableWidgetItem(f"{pos['price_open']:.5f}"))
            
            pnl_item = QTableWidgetItem(f"${pos['profit']:+.2f}")
            pnl_item.setForeground(QColor("#00e676" if pos["profit"] >= 0 else "#ff1744"))
            self.table_pos.setItem(row, 5, pnl_item)

        self.bottom_tabs.setTabText(1, f"Active Positions ({len(positions)})")
        self.lbl_trades_count.setText(f"Active Trades: {len(positions)}/{self.max_trades.value()}")

        if self.engine and self.engine.running:
            self.scan_tick += 1
            self.radar_pos = (self.radar_pos + 10) % 110
            self.radar_bar.setValue(self.radar_pos)

            active_sym = d.get("active_symbol", "EURUSD")
            mode_str = "AUTO-SCANNING" if self.rad_auto.isChecked() else "MONITORING"
            
            pulse_icon = "🟢" if self.scan_tick % 2 == 0 else "⚡"
            self.lbl_bot_state.setText(f"{pulse_icon} STATE: {mode_str} [{active_sym}] (TICK #{self.scan_tick})")
        else:
            self.lbl_bot_state.setText("STATE: ENGINE IDLE")
            self.radar_bar.setValue(0)

        dd_pct = d.get("daily_drawdown_pct", 0.0)
        max_dd = self.daily_risk.value()
        used_ratio = min(100, int((dd_pct / max_dd) * 100)) if max_dd > 0 else 0
        self.drawdown_bar.setValue(used_ratio)

    def toggle_engine(self):
        if self.engine is None:
            mode = "AUTO" if self.rad_auto.isChecked() else "MANUAL"
            selected_pairs = [pair for pair, cb in self.pair_boxes.items() if cb.isChecked()]
            
            if mode == "MANUAL" and not selected_pairs:
                self.update_log("ERROR: In Manual mode, please select at least one trading pair.")
                return

            self.engine = TradingEngine(
                symbols=selected_pairs,
                mode=mode,
                lot_size=self.lot_input.value(),
                daily_risk_pct=self.daily_risk.value(),
                weekly_risk_pct=self.weekly_risk.value(),
                max_trades=self.max_trades.value(),
                log_callback=self.route_log,
                metrics_callback=self.route_metrics
            )
            self.engine.start()

            self.btn_power.setText("POWER BOT: ONLINE")
            self.btn_power.setStyleSheet("""
                QPushButton { background-color: #00c853; color: white; padding: 6px 14px; border-radius: 4px; border: 1px solid #00c853; }
            """)
        else:
            self.engine.stop()
            self.engine = None
            self.btn_power.setText("POWER BOT: OFF")
            self.btn_power.setStyleSheet("""
                QPushButton { background-color: #262938; color: #ff1744; padding: 6px 14px; border-radius: 4px; border: 1px solid #ff1744; }
            """)


if __name__ == "__main__":
    app = QApplication(sys.argv)
    window = QuantumTraderPro()
    window.show()
    sys.exit(app.exec())