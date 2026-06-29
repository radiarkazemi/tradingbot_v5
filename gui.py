"""
TraderBot v5 — GUI
Smart ATR Breakout Grid | Asian Range + London Breakout
"""
import sys
import os
from datetime import datetime
from typing import Optional

from PyQt5.QtCore import Qt, QTimer, pyqtSignal, QObject
from PyQt5.QtGui import QColor, QPainter, QPainterPath, QPen, QFont
from PyQt5.QtWidgets import (
    QApplication, QMainWindow, QWidget, QVBoxLayout, QHBoxLayout,
    QLabel, QPushButton, QGroupBox, QTextEdit, QFrame,
    QTabWidget, QTableWidget, QTableWidgetItem, QHeaderView,
    QDoubleSpinBox, QSpinBox, QComboBox, QSplitter, QSizePolicy,
    QProgressBar, QScrollArea, QLineEdit, QGridLayout,
)

import config as cfg
from core.grid_engine import GridEngine

os.makedirs("logs", exist_ok=True)

# ── Palette ───────────────────────────────────────────────────────
C = {
    "bg":       "#0D1117", "panel":  "#161B22", "card":  "#1C2333",
    "input":    "#141D2E", "border": "#2A3550", "bhi":   "#4A6090",
    "txt":      "#E8EDF5", "txt2":   "#8B9BB4", "txt3":  "#4A5568",
    "gold":     "#F5A623", "green":  "#00D97E", "gdk":   "#003D22",
    "red":      "#FF4560", "rdk":    "#3D0015", "orange": "#FF8C00",
    "cyan":     "#00BCD4", "blue":   "#2979FF", "purple": "#B388FF",
}

SS = f"""
QWidget     {{background:{C['bg']};color:{C['txt']};font-family:'Segoe UI';font-size:12px;}}
QMainWindow {{background:{C['bg']};}}
QLabel      {{background:transparent;}}
QGroupBox   {{background:{C['card']};border:1px solid {C['border']};border-radius:6px;
               margin-top:14px;padding:8px 6px 6px;
               font-size:10px;font-weight:bold;color:{C['txt2']};}}
QGroupBox::title {{subcontrol-origin:margin;left:10px;padding:0 4px;}}
QPushButton {{background:{C['card']};color:{C['txt']};border:1px solid {C['border']};
               border-radius:5px;padding:6px 14px;}}
QPushButton:hover   {{background:{C['border']};border-color:{C['bhi']};}}
QPushButton:disabled{{color:{C['txt3']};border-color:{C['card']};}}
QPushButton#btn_start{{background:{C['gdk']};color:{C['green']};
    border:1px solid {C['green']};font-weight:bold;font-size:13px;}}
QPushButton#btn_start:hover{{background:{C['green']};color:#000;}}
QPushButton#btn_stop {{background:{C['rdk']};color:{C['red']};
    border:1px solid {C['red']};font-weight:bold;font-size:13px;}}
QPushButton#btn_stop:hover {{background:{C['red']};color:#fff;}}
QDoubleSpinBox,QSpinBox,QComboBox,QLineEdit {{
    background:{C['input']};color:{C['txt']};
    border:1px solid {C['border']};border-radius:4px;
    padding:4px 7px;min-height:26px;}}
QDoubleSpinBox::up-button,QDoubleSpinBox::down-button,
QSpinBox::up-button,QSpinBox::down-button
    {{background:{C['border']};border:none;width:16px;}}
QComboBox::drop-down {{border:none;width:20px;}}
QComboBox QAbstractItemView {{background:{C['card']};color:{C['txt']};
    selection-background-color:{C['border']};}}
QTextEdit {{background:{C['bg']};color:{C['txt']};border:1px solid {C['border']};
            border-radius:4px;font-family:'Consolas';font-size:11px;}}
QTableWidget {{background:{C['bg']};color:{C['txt']};border:1px solid {C['border']};
                border-radius:4px;gridline-color:{C['border']};
                alternate-background-color:{C['panel']};}}
QTableWidget::item {{padding:4px 8px;}}
QTableWidget::item:selected {{background:{C['border']};}}
QHeaderView::section {{background:{C['card']};color:{C['txt2']};padding:5px 8px;
    border:none;border-right:1px solid {C['border']};
    border-bottom:1px solid {C['border']};font-size:10px;font-weight:bold;}}
QTabWidget::pane {{background:{C['panel']};border:1px solid {C['border']};border-radius:4px;}}
QTabBar::tab {{background:{C['card']};color:{C['txt2']};padding:6px 18px;
    border:1px solid {C['border']};border-bottom:none;
    border-radius:4px 4px 0 0;margin-right:2px;}}
QTabBar::tab:selected {{background:{C['panel']};color:{C['gold']};
    border-bottom:2px solid {C['gold']};}}
QScrollArea {{border:none;background:transparent;}}
QScrollBar:vertical {{background:{C['bg']};width:6px;}}
QScrollBar::handle:vertical {{background:{C['border']};border-radius:3px;min-height:20px;}}
QScrollBar::add-line:vertical,QScrollBar::sub-line:vertical {{height:0;}}
QProgressBar {{background:{C['input']};border:1px solid {C['border']};
                border-radius:4px;text-align:center;font-size:11px;}}
QProgressBar::chunk {{background:{C['green']};border-radius:3px;}}
"""


class Sig(QObject):
    log_line = pyqtSignal(str, str)
    status = pyqtSignal(str)
    stats = pyqtSignal(dict)
    done = pyqtSignal(str)


def _hline():
    f = QFrame()
    f.setFrameShape(QFrame.HLine)
    f.setStyleSheet(f"color:{C['border']};")
    return f


def _card(title: str, accent: str, big=False):
    card = QFrame()
    card.setStyleSheet(
        f"QFrame{{background:{C['input']};border:1px solid {C['border']};"
        f"border-top:2px solid {accent};border-radius:5px;}}"
    )
    lay = QVBoxLayout(card)
    lay.setContentsMargins(10, 6, 10, 8)
    lay.setSpacing(2)
    tl = QLabel(title.upper())
    tl.setStyleSheet(
        f"color:{C['txt3']};font-size:9px;font-weight:bold;letter-spacing:1px;border:none;")
    lay.addWidget(tl)
    vl = QLabel("—")
    vl.setStyleSheet(
        f"color:{C['txt']};font-family:Consolas;font-size:{'16' if big else '13'}px;font-weight:bold;border:none;")
    lay.addWidget(vl)
    return card, vl


class Sparkline(QWidget):
    def __init__(self):
        super().__init__()
        self._data = []
        self.setMinimumHeight(50)
        self.setSizePolicy(QSizePolicy.Expanding, QSizePolicy.Fixed)

    def push(self, v):
        self._data.append(v)
        if len(self._data) > 200:
            self._data = self._data[-200:]
        self.update()

    def paintEvent(self, _):
        if len(self._data) < 2:
            return
        p = QPainter(self)
        p.setRenderHint(QPainter.Antialiasing)
        w, h = self.width(), self.height()
        mn, mx = min(self._data), max(self._data)
        rng = mx - mn or 1.0

        def pt(i, v):
            return int(i/(len(self._data)-1)*w), int(h-(v-mn)/rng*(h-4)-2)
        up = self._data[-1] >= self._data[0]
        col = QColor(C['green'] if up else C['red'])
        fc = QColor(col)
        fc.setAlpha(28)
        path = QPainterPath()
        path.moveTo(*pt(0, self._data[0]))
        for i, v in enumerate(self._data[1:], 1):
            path.lineTo(*pt(i, v))
        fill = QPainterPath(path)
        fill.lineTo(w, h)
        fill.lineTo(0, h)
        fill.closeSubpath()
        p.fillPath(fill, fc)
        p.setPen(QPen(col, 1.5))
        p.drawPath(path)


# ══════════════════════════════════════════════════════════════════

class GUI(QMainWindow):

    def __init__(self):
        super().__init__()
        self.setWindowTitle("TraderBot v5 — Smart ATR Breakout Grid")
        self.setMinimumSize(1060, 720)
        self.setStyleSheet(SS)
        self._engine: Optional[GridEngine] = None
        self._sig = Sig()
        self._sig.log_line.connect(self._on_log)
        self._sig.status.connect(self._on_status)
        self._sig.stats.connect(self._on_stats)
        self._sig.done.connect(self._on_done)
        self._build_ui()
        QTimer().singleShot(500, self._refresh_price)
        t = QTimer(self)
        t.timeout.connect(self._refresh_price)
        t.start(1000)
        t2 = QTimer(self)
        t2.timeout.connect(self._refresh_tables)
        t2.start(500)

    def _build_ui(self):
        cw = QWidget()
        self.setCentralWidget(cw)
        root = QHBoxLayout(cw)
        root.setContentsMargins(8, 8, 8, 8)
        root.setSpacing(8)
        sp = QSplitter(Qt.Horizontal)
        sp.addWidget(self._left())
        sp.addWidget(self._right())
        sp.setSizes([320, 740])
        sp.setChildrenCollapsible(False)
        root.addWidget(sp)
        sb = self.statusBar()
        sb.setStyleSheet(
            f"background:{C['panel']};color:{C['txt2']};border-top:1px solid {C['border']};font-size:11px;")
        self.lbl_sb = QLabel("Ready")
        self.lbl_sb.setStyleSheet(f"color:{C['txt2']};")
        sb.addWidget(self.lbl_sb, 1)

    # ── LEFT ──────────────────────────────────────────────────────
    def _left(self):
        outer = QWidget()
        outer.setFixedWidth(320)
        ol = QVBoxLayout(outer)
        ol.setContentsMargins(0, 0, 0, 0)
        scroll = QScrollArea()
        scroll.setWidgetResizable(True)
        scroll.setHorizontalScrollBarPolicy(Qt.ScrollBarAlwaysOff)
        inner = QWidget()
        lay = QVBoxLayout(inner)
        lay.setContentsMargins(4, 6, 8, 6)
        lay.setSpacing(8)

        t = QLabel("TraderBot v5")
        t.setStyleSheet(
            f"color:{C['gold']};font-size:18px;font-weight:bold;padding:2px 0;")
        s = QLabel("Smart ATR Breakout Grid")
        s.setStyleSheet(
            f"color:{C['txt2']};font-size:10px;padding-bottom:4px;")
        lay.addWidget(t)
        lay.addWidget(s)
        lay.addWidget(_hline())

        # Connection
        conn = QGroupBox("MT5 Connection")
        cg = QVBoxLayout(conn)
        cg.setSpacing(5)

        def _field(lbl, w):
            r = QHBoxLayout()
            lb = QLabel(lbl)
            lb.setFixedWidth(68)
            lb.setStyleSheet(f"color:{C['txt2']};font-size:11px;")
            r.addWidget(lb)
            r.addWidget(w)
            cg.addLayout(r)
        self.inp_login = QLineEdit(str(cfg.MT5_LOGIN))
        self.inp_pass = QLineEdit(cfg.MT5_PASSWORD)
        self.inp_pass.setEchoMode(QLineEdit.Password)
        self.inp_srv = QLineEdit(cfg.MT5_SERVER)
        _field("Login", self.inp_login)
        _field("Password", self.inp_pass)
        _field("Server", self.inp_srv)
        lay.addWidget(conn)

        # Symbol presets — stored for use after spinboxes are created
        self._PRESETS = {
            # Gold — optimized from backtests
            "XAUUSD_o": dict(count=8, step=0.40, lot=0.01, sl=2.25, trail=0.30, be=0.20, target=2.0, dsl=5.0, pb=30.0),
            "XAUUSD":   dict(count=8, step=0.40, lot=0.01, sl=2.25, trail=0.30, be=0.20, target=2.0, dsl=5.0, pb=30.0),
            # BTC — wide steps needed ($50+ per order, not $0.60)
            "BTCUSD":   dict(count=5, step=0.25, lot=0.01, sl=2.00, trail=0.40, be=0.15, target=1.5, dsl=3.0, pb=35.0),
            "BTCUSDm":  dict(count=5, step=0.25, lot=0.01, sl=2.00, trail=0.40, be=0.15, target=1.5, dsl=3.0, pb=35.0),
            "ETHUSD":   dict(count=5, step=0.25, lot=0.01, sl=2.00, trail=0.40, be=0.15, target=1.5, dsl=3.0, pb=35.0),
            # Forex
            "EURUSD":   dict(count=8, step=0.35, lot=0.01, sl=2.00, trail=0.35, be=0.20, target=2.0, dsl=5.0, pb=30.0),
            "GBPUSD":   dict(count=8, step=0.35, lot=0.01, sl=2.00, trail=0.35, be=0.20, target=2.0, dsl=5.0, pb=30.0),
            "USDJPY":   dict(count=8, step=0.35, lot=0.01, sl=2.00, trail=0.35, be=0.20, target=2.0, dsl=5.0, pb=30.0),
            "GBPJPY":   dict(count=8, step=0.40, lot=0.01, sl=2.25, trail=0.35, be=0.20, target=2.0, dsl=5.0, pb=30.0),
            "NASDAQ":   dict(count=6, step=0.35, lot=0.01, sl=2.00, trail=0.40, be=0.20, target=1.5, dsl=4.0, pb=35.0),
        }

        # Symbol
        sg = QGroupBox("Symbol & Live Price  (auto-loads presets)")
        sl = QVBoxLayout(sg)
        sl.setSpacing(5)
        cr = QHBoxLayout()
        self.sym_combo = QComboBox()
        syms = list(self._PRESETS.keys())
        self.sym_combo.addItems(syms)
        idx = syms.index(cfg.WATCH_SYMBOL) if cfg.WATCH_SYMBOL in syms else 0
        self.sym_combo.setCurrentIndex(idx)
        # NOTE: signal connected AFTER spinboxes are created below
        self.lbl_price = QLabel("—")
        self.lbl_price.setStyleSheet(
            f"color:{C['cyan']};font-family:Consolas;font-size:15px;font-weight:bold;")
        self.lbl_price.setAlignment(Qt.AlignRight | Qt.AlignVCenter)
        cr.addWidget(self.sym_combo, 1)
        cr.addWidget(self.lbl_price)
        sl.addLayout(cr)
        cust = QHBoxLayout()
        lc = QLabel("Custom:")
        lc.setStyleSheet(f"color:{C['txt2']};font-size:11px;")
        lc.setFixedWidth(52)
        self.inp_custom = QLineEdit()
        self.inp_custom.setPlaceholderText("e.g. XAUUSD_o…")
        self.inp_custom.returnPressed.connect(self._on_custom_sym)
        bu = QPushButton("Use")
        bu.setFixedWidth(44)
        bu.clicked.connect(self._on_custom_sym)
        cust.addWidget(lc)
        cust.addWidget(self.inp_custom, 1)
        cust.addWidget(bu)
        sl.addLayout(cust)
        lay.addWidget(sg)

        # Grid settings
        gg = QGroupBox("Grid Settings  (Optimized)")
        gl = QGridLayout(gg)
        gl.setSpacing(6)
        gl.setColumnStretch(1, 1)

        def lbl(t):
            l = QLabel(t)
            l.setStyleSheet(f"color:{C['txt2']};font-size:11px;")
            return l

        self.sp_count = QSpinBox()
        self.sp_count.setRange(1, 50)
        self.sp_count.setValue(cfg.GRID_COUNT)
        self.sp_count.setSuffix(" each side")

        self.sp_step = QDoubleSpinBox()
        self.sp_step.setRange(0.05, 2.0)
        self.sp_step.setSingleStep(0.05)
        self.sp_step.setDecimals(2)
        self.sp_step.setValue(cfg.GRID_STEP_ATR)
        self.sp_step.setPrefix("ATR × ")

        self.sp_lot = QDoubleSpinBox()
        self.sp_lot.setRange(0.01, 100.0)
        self.sp_lot.setSingleStep(0.01)
        self.sp_lot.setDecimals(2)
        self.sp_lot.setValue(cfg.LOT_SIZE)
        self.sp_lot.setPrefix("lot  ")

        gl.addWidget(lbl("Count"),   0, 0)
        gl.addWidget(self.sp_count, 0, 1)
        gl.addWidget(lbl("Step"),    1, 0)
        gl.addWidget(self.sp_step,  1, 1)
        gl.addWidget(lbl("Lot"),     2, 0)
        gl.addWidget(self.sp_lot,   2, 1)
        lay.addWidget(gg)

        # Stop management
        stg = QGroupBox("Stop Management  (Optimized)")
        stl = QGridLayout(stg)
        stl.setSpacing(6)
        stl.setColumnStretch(1, 1)

        self.sp_sl = QDoubleSpinBox()
        self.sp_sl.setRange(0.5, 5.0)
        self.sp_sl.setSingleStep(0.25)
        self.sp_sl.setDecimals(2)
        self.sp_sl.setValue(cfg.SL_ATR_MULT)
        self.sp_sl.setPrefix("ATR × ")

        self.sp_trail = QDoubleSpinBox()
        self.sp_trail.setRange(0.1, 2.0)
        self.sp_trail.setSingleStep(0.1)
        self.sp_trail.setDecimals(2)
        self.sp_trail.setValue(cfg.TRAIL_ATR_MULT)
        self.sp_trail.setPrefix("ATR × ")

        self.sp_be = QDoubleSpinBox()
        self.sp_be.setRange(0.05, 1.0)
        self.sp_be.setSingleStep(0.05)
        self.sp_be.setDecimals(2)
        self.sp_be.setValue(cfg.BE_ATR_MULT)
        self.sp_be.setPrefix("ATR × ")

        stl.addWidget(lbl("Hard SL"),    0, 0)
        stl.addWidget(self.sp_sl,    0, 1)
        stl.addWidget(lbl("Trail Stop"), 1, 0)
        stl.addWidget(self.sp_trail, 1, 1)
        stl.addWidget(lbl("Breakeven"),  2, 0)
        stl.addWidget(self.sp_be,    2, 1)
        lay.addWidget(stg)

        # Session settings
        sess = QGroupBox("Session Settings")
        sel = QGridLayout(sess)
        sel.setSpacing(6)
        sel.setColumnStretch(1, 1)

        self.sp_target = QDoubleSpinBox()
        self.sp_target.setRange(0.1, 20.0)
        self.sp_target.setSingleStep(0.5)
        self.sp_target.setDecimals(1)
        self.sp_target.setValue(cfg.TARGET_PCT)
        self.sp_target.setSuffix(" % profit")

        self.sp_dsl = QDoubleSpinBox()
        self.sp_dsl.setRange(1.0, 20.0)
        self.sp_dsl.setSingleStep(1.0)
        self.sp_dsl.setDecimals(1)
        self.sp_dsl.setValue(cfg.DAILY_SL_PCT)
        self.sp_dsl.setSuffix(" % daily SL")

        self.sp_pb = QDoubleSpinBox()
        self.sp_pb.setRange(10.0, 80.0)
        self.sp_pb.setSingleStep(5.0)
        self.sp_pb.setDecimals(1)
        self.sp_pb.setValue(cfg.PULLBACK_PCT)
        self.sp_pb.setSuffix(" % pullback")

        self.sp_asian = QSpinBox()
        self.sp_asian.setRange(0, 12)
        self.sp_asian.setValue(cfg.ASIAN_END_HOUR)
        self.sp_asian.setSpecialValueText("0 = Trade immediately (no wait)")
        self.sp_asian.setSuffix(" UTC (0=now)")
        self.sp_asian.setToolTip(
            "0 = start immediately\n7 = wait for London open\nAny hour = wait until that hour")

        self.sp_tend = QSpinBox()
        self.sp_tend.setRange(12, 24)
        self.sp_tend.setValue(cfg.TRADE_END_HOUR)
        self.sp_tend.setSuffix(" UTC end")

        sel.addWidget(lbl("Target"),      0, 0)
        sel.addWidget(self.sp_target, 0, 1)
        sel.addWidget(lbl("Daily SL"),    1, 0)
        sel.addWidget(self.sp_dsl,    1, 1)
        sel.addWidget(lbl("Pullback"),    2, 0)
        sel.addWidget(self.sp_pb,     2, 1)
        sel.addWidget(lbl("Start Hour"),  3, 0)
        sel.addWidget(self.sp_asian,  3, 1)
        sel.addWidget(lbl("End Hour"),    4, 0)
        sel.addWidget(self.sp_tend,   4, 1)
        lay.addWidget(sess)

        # Buttons
        self.btn_start = QPushButton("▶  Start Bot")
        self.btn_start.setObjectName("btn_start")
        self.btn_start.setMinimumHeight(42)
        self.btn_start.clicked.connect(self._on_start)
        self.btn_stop = QPushButton("⏹  Stop && Close All")
        self.btn_stop.setObjectName("btn_stop")
        self.btn_stop.setMinimumHeight(42)
        self.btn_stop.setEnabled(False)
        self.btn_stop.clicked.connect(self._on_stop)

        # Connect preset signal NOW (all spinboxes exist at this point)
        self.sym_combo.currentTextChanged.connect(self._apply_preset)
        # Apply initial preset for default symbol
        self._apply_preset(self.sym_combo.currentText())
        lay.addWidget(self.btn_start)
        lay.addWidget(self.btn_stop)

        self.lbl_status = QLabel("● Idle")
        self.lbl_status.setAlignment(Qt.AlignCenter)
        self.lbl_status.setStyleSheet(
            f"color:{C['txt3']};font-size:11px;background:{C['panel']};"
            f"border:1px solid {C['border']};border-radius:4px;padding:5px;")
        lay.addWidget(self.lbl_status)
        lay.addStretch()
        scroll.setWidget(inner)
        ol.addWidget(scroll)
        return outer

    # ── RIGHT ─────────────────────────────────────────────────────
    def _right(self):
        tabs = QTabWidget()
        tabs.addTab(self._tab_dashboard(), "📊  Dashboard")
        tabs.addTab(self._tab_positions(), "📋  Positions")
        tabs.addTab(self._tab_log(),       "🖥  Log")
        return tabs

    def _tab_dashboard(self):
        w = QWidget()
        lay = QVBoxLayout(w)
        lay.setContentsMargins(10, 10, 10, 10)
        lay.setSpacing(10)

        # Row 1 — financial
        r1 = QHBoxLayout()
        r1.setSpacing(8)
        c1, self.c_float = _card("Floating P&L",   C['green'], big=True)
        c2, self.c_peak = _card("Session Peak",    C['gold'])
        c3, self.c_bal = _card("Balance",         C['cyan'])
        c4, self.c_eq = _card("Equity",          C['blue'])
        for c in (c1, c2, c3, c4):
            c.setSizePolicy(QSizePolicy.Expanding, QSizePolicy.Fixed)
            r1.addWidget(c)
        lay.addLayout(r1)

        # Row 2 — session
        r2 = QHBoxLayout()
        r2.setSpacing(8)
        c5, self.c_sess = _card("Sessions",        C['purple'])
        c6, self.c_buy = _card("Open Buys",       C['green'])
        c7, self.c_sell = _card("Open Sells",      C['red'])
        c8, self.c_timer = _card("Session Time",    C['orange'])
        for c in (c5, c6, c7, c8):
            c.setSizePolicy(QSizePolicy.Expanding, QSizePolicy.Fixed)
            r2.addWidget(c)
        lay.addLayout(r2)

        # Progress bar
        pf = QFrame()
        pf.setStyleSheet(
            f"QFrame{{background:{C['card']};border:1px solid {C['border']};border-radius:5px;}}")
        pfl = QVBoxLayout(pf)
        pfl.setContentsMargins(10, 8, 10, 10)
        pfl.setSpacing(4)
        ph = QHBoxLayout()
        pl = QLabel("Profit Progress")
        pl.setStyleSheet(f"color:{C['txt2']};font-size:10px;font-weight:bold;")
        self.lbl_pct = QLabel("0.0%")
        self.lbl_pct.setStyleSheet(
            f"color:{C['green']};font-family:Consolas;font-size:11px;font-weight:bold;")
        ph.addWidget(pl)
        ph.addStretch()
        ph.addWidget(self.lbl_pct)
        pfl.addLayout(ph)
        self.progress = QProgressBar()
        self.progress.setRange(0, 100)
        self.progress.setValue(0)
        self.progress.setTextVisible(False)
        self.progress.setFixedHeight(12)
        pfl.addWidget(self.progress)
        lay.addWidget(pf)

        # Info bar
        ib = QFrame()
        ib.setStyleSheet(
            f"QFrame{{background:{C['card']};border:1px solid {C['border']};border-radius:5px;}}")
        ibl = QHBoxLayout(ib)
        ibl.setContentsMargins(12, 8, 12, 8)
        ibl.setSpacing(16)
        self.lbl_anchor = QLabel("Anchor: —")
        self.lbl_locked = QLabel("Side: —")
        self.lbl_asian = QLabel("Asian: —")
        self.lbl_daily = QLabel("Daily P&L: —")
        for lb in (self.lbl_anchor, self.lbl_locked, self.lbl_asian, self.lbl_daily):
            lb.setStyleSheet(
                f"color:{C['txt2']};font-family:Consolas;font-size:11px;")
            ibl.addWidget(lb)
        ibl.addStretch()
        lay.addWidget(ib)

        # ATR info bar
        ab = QFrame()
        ab.setStyleSheet(
            f"QFrame{{background:{C['card']};border:1px solid {C['border']};border-radius:5px;}}")
        abl = QHBoxLayout(ab)
        abl.setContentsMargins(12, 8, 12, 8)
        abl.setSpacing(16)
        self.lbl_atr = QLabel("ATR: —")
        self.lbl_step = QLabel("Step: —")
        self.lbl_pending = QLabel("Pending: —")
        self.lbl_target = QLabel("Target: —")
        for lb in (self.lbl_atr, self.lbl_step, self.lbl_pending, self.lbl_target):
            lb.setStyleSheet(
                f"color:{C['txt2']};font-family:Consolas;font-size:11px;")
            abl.addWidget(lb)
        abl.addStretch()
        lay.addWidget(ab)

        # Sparkline
        sf = QFrame()
        sf.setStyleSheet(
            f"QFrame{{background:{C['card']};border:1px solid {C['border']};border-radius:5px;}}")
        sfl = QVBoxLayout(sf)
        sfl.setContentsMargins(10, 8, 10, 8)
        sfl.setSpacing(4)
        sl = QLabel("Equity Trend")
        sl.setStyleSheet(f"color:{C['txt2']};font-size:10px;font-weight:bold;")
        sfl.addWidget(sl)
        self.sparkline = Sparkline()
        sfl.addWidget(self.sparkline)
        lay.addWidget(sf)
        lay.addStretch()
        return w

    def _tab_positions(self):
        w = QWidget()
        lay = QVBoxLayout(w)
        lay.setContentsMargins(10, 10, 10, 10)
        lay.setSpacing(8)

        lp = QLabel("OPEN POSITIONS")
        lp.setStyleSheet(
            f"color:{C['txt3']};font-size:9px;font-weight:bold;letter-spacing:2px;")
        lay.addWidget(lp)
        self.pos_table = QTableWidget()
        self.pos_table.setColumnCount(7)
        self.pos_table.setHorizontalHeaderLabels(
            ["Ticket", "Type", "Lot", "Open", "Current", "P&L", "Comment"])
        hh = self.pos_table.horizontalHeader()
        hh.setSectionResizeMode(QHeaderView.Stretch)
        hh.setSectionResizeMode(0, QHeaderView.ResizeToContents)
        self.pos_table.setAlternatingRowColors(True)
        self.pos_table.setEditTriggers(QTableWidget.NoEditTriggers)
        self.pos_table.setSelectionBehavior(QTableWidget.SelectRows)
        self.pos_table.verticalHeader().setVisible(False)
        lay.addWidget(self.pos_table)

        lay.addWidget(_hline())

        lo = QLabel("PENDING ORDERS")
        lo.setStyleSheet(
            f"color:{C['txt3']};font-size:9px;font-weight:bold;letter-spacing:2px;")
        lay.addWidget(lo)
        self.ord_table = QTableWidget()
        self.ord_table.setColumnCount(5)
        self.ord_table.setHorizontalHeaderLabels(
            ["Ticket", "Type", "Lot", "Price", "Comment"])
        hh2 = self.ord_table.horizontalHeader()
        hh2.setSectionResizeMode(QHeaderView.Stretch)
        hh2.setSectionResizeMode(0, QHeaderView.ResizeToContents)
        self.ord_table.setAlternatingRowColors(True)
        self.ord_table.setEditTriggers(QTableWidget.NoEditTriggers)
        self.ord_table.setSelectionBehavior(QTableWidget.SelectRows)
        self.ord_table.verticalHeader().setVisible(False)
        lay.addWidget(self.ord_table)

        # Footer
        foot = QFrame()
        foot.setStyleSheet(
            f"QFrame{{background:{C['card']};border:1px solid {C['border']};border-radius:5px;}}")
        fl = QHBoxLayout(foot)
        fl.setContentsMargins(12, 8, 12, 8)
        fl.setSpacing(20)
        self.lbl_sbuy = QLabel("Buys: —")
        self.lbl_ssell = QLabel("Sells: —")
        self.lbl_spnl = QLabel("Net P&L: —")
        for lb in (self.lbl_sbuy, self.lbl_ssell, self.lbl_spnl):
            lb.setStyleSheet(
                f"color:{C['txt2']};font-family:Consolas;font-size:11px;")
            fl.addWidget(lb)
        fl.addStretch()
        lay.addWidget(foot)
        return w

    def _tab_log(self):
        w = QWidget()
        lay = QVBoxLayout(w)
        lay.setContentsMargins(8, 8, 8, 8)
        lay.setSpacing(6)
        tb = QHBoxLayout()
        hdr = QLabel("SESSION LOG")
        hdr.setStyleSheet(
            f"color:{C['txt3']};font-size:9px;font-weight:bold;letter-spacing:2px;")
        bc = QPushButton("Clear")
        bc.setFixedWidth(70)
        bc.clicked.connect(lambda: self.log_view.clear())
        tb.addWidget(hdr)
        tb.addStretch()
        tb.addWidget(bc)
        lay.addLayout(tb)
        lay.addWidget(_hline())
        self.log_view = QTextEdit()
        self.log_view.setReadOnly(True)
        self.log_view.setLineWrapMode(QTextEdit.NoWrap)
        lay.addWidget(self.log_view)
        return w

    # ── Helpers ───────────────────────────────────────────────────
    def _sym(self):
        c = self.inp_custom.text().strip().upper()
        return c if c else self.sym_combo.currentText().strip()

    def _apply_preset(self, sym: str):
        p = self._PRESETS.get(sym, self._PRESETS.get("EURUSD"))
        if not p:
            return
        self.sp_count.setValue(p['count'])
        self.sp_step.setValue(p['step'])
        self.sp_lot.setValue(p['lot'])
        self.sp_sl.setValue(p['sl'])
        self.sp_trail.setValue(p['trail'])
        self.sp_be.setValue(p['be'])
        self.sp_target.setValue(p['target'])
        self.sp_dsl.setValue(p['dsl'])
        self.sp_pb.setValue(p['pb'])
        self.inp_custom.clear()
        self.lbl_price.setText("—")

    def _on_custom_sym(self):
        sym = self.inp_custom.text().strip().upper()
        if sym:
            self.inp_custom.setText(sym)
            self.lbl_price.setText("—")

    def _set_inputs(self, en):
        for w in (self.sym_combo, self.inp_login, self.inp_pass, self.inp_srv,
                  self.sp_count, self.sp_step, self.sp_lot, self.sp_sl,
                  self.sp_trail, self.sp_be, self.sp_target, self.sp_dsl,
                  self.sp_pb, self.sp_asian, self.sp_tend):
            w.setEnabled(en)

    # ── Start / Stop ──────────────────────────────────────────────
    def _on_start(self):
        if self._engine and self._engine.is_alive():
            return
        sym = self._sym()
        if not sym:
            return

        self._engine = GridEngine(
            symbol=sym,
            login=int(self.inp_login.text()),
            password=self.inp_pass.text(),
            server=self.inp_srv.text(),
            magic=cfg.MAGIC_NUMBER,
            lot_size=self.sp_lot.value(),
            grid_count=int(self.sp_count.value()),
            step_atr_mult=self.sp_step.value(),
            atr_period=cfg.ATR_PERIOD,
            sl_atr_mult=self.sp_sl.value(),
            trail_atr_mult=self.sp_trail.value(),
            be_atr_mult=self.sp_be.value(),
            min_step_pips=cfg.MIN_STEP_PIPS,
            min_sl_pips=cfg.MIN_SL_PIPS,
            asian_end_hour=self.sp_asian.value(),
            trade_end_hour=self.sp_tend.value(),
            target_pct=self.sp_target.value(),
            daily_sl_pct=self.sp_dsl.value(),
            pullback_pct=self.sp_pb.value(),
            max_spread_pips=cfg.MAX_SPREAD_PIPS,
            scan_interval=cfg.SCAN_INTERVAL_SEC,
            log_fn=lambda m, l="INFO": self._sig.log_line.emit(m, l),
            status_fn=lambda m:          self._sig.status.emit(m),
            stats_fn=lambda d:          self._sig.stats.emit(d),
            done_fn=lambda r:          self._sig.done.emit(r),
        )
        self._engine.start()
        self.btn_start.setEnabled(False)
        self.btn_stop.setEnabled(True)
        self._set_inputs(False)

    def _on_stop(self):
        if self._engine:
            self._engine.stop()
        self.btn_stop.setEnabled(False)

    # ── Signal handlers ───────────────────────────────────────────
    def _on_log(self, msg, level="INFO"):
        cols = {"ERROR": C['red'], "WARN": C['orange'], "NEW": C['green']}
        col = cols.get(level, C['txt'])
        self.log_view.append(f'<span style="color:{col};">{msg}</span>')
        self.log_view.verticalScrollBar().setValue(
            self.log_view.verticalScrollBar().maximum())
        self.lbl_sb.setText(msg[:120])

    def _on_status(self, msg):
        self.lbl_status.setText(f"● {msg}")
        col = (C['green'] if any(k in msg.lower() for k in ("active", "placed", "grid", "target")) else
               C['orange'] if any(k in msg.lower() for k in ("closing", "starting", "waiting")) else
               C['txt3'])
        self.lbl_status.setStyleSheet(
            f"color:{col};font-size:11px;background:{C['panel']};"
            f"border:1px solid {C['border']};border-radius:4px;padding:5px;")

    def _on_stats(self, d):
        floating = d.get("floating", 0.0)
        peak = d.get("peak",     0.0)
        bal = d.get("balance",  0.0)
        eq = d.get("equity",   0.0)
        bal_day = d.get("bal_day",  0.0)
        pct = d.get("progress_pct", 0.0)
        elapsed = d.get("elapsed_sec",  0.0)
        target = d.get("target",       0.0)
        anchor = d.get("anchor",       0.0)
        locked = d.get("locked_side",  "")
        asian_h = d.get("asian_h",      0.0)
        asian_l = d.get("asian_l",      0.0)
        asian_r = d.get("asian_range",  0.0)
        atr_pip = d.get("atr_pip",      0.0)
        step_pip = d.get("step_pip",     0.0)
        pending = d.get("pending",      0)
        n_sess = d.get("total_sess",   0)
        n_win = d.get("win_sess",     0)
        active = d.get("active",       False)

        fl_col = C['green'] if floating >= 0 else C['red']
        eq_col = C['green'] if eq >= bal else C['red']
        dp_val = bal - bal_day
        dp_col = C['green'] if dp_val >= 0 else C['red']

        self.c_float.setText(f'<font color="{fl_col}">${floating:+.2f}</font>')
        self.c_peak.setText(f"${peak:.2f}")
        self.c_bal.setText(f"${bal:.2f}")
        self.c_eq.setText(f'<font color="{eq_col}">${eq:.2f}</font>')
        self.c_buy.setText(str(d.get("open_buy", 0)))
        self.c_sell.setText(str(d.get("open_sell", 0)))

        sess_str = f"{n_sess} sessions  {n_win}W/{n_sess-n_win}L"
        self.c_sess.setText(sess_str)

        mins = int(elapsed//60)
        secs = int(elapsed % 60)
        self.c_timer.setText(f"{mins:02d}:{secs:02d}" if active else "—")

        self.progress.setValue(int(min(100, max(0, pct))))
        self.lbl_pct.setText(f"{pct:.1f}%")
        self.lbl_pct.setStyleSheet(
            f"color:{C['green'] if pct>75 else C['orange'] if pct>40 else C['txt2']};"
            f"font-family:Consolas;font-size:11px;font-weight:bold;")

        # Info bars
        if anchor > 0:
            self.lbl_anchor.setText(f"Anchor: {anchor:.2f}")
        lk_col = C['green'] if locked == "BUY" else C['red'] if locked == "SELL" else C['txt3']
        self.lbl_locked.setStyleSheet(
            f"color:{lk_col};font-family:Consolas;font-size:11px;")
        self.lbl_locked.setText(f"Locked: {locked if locked else '—'}")
        if asian_h > 0:
            self.lbl_asian.setText(
                f"Asian: {asian_l:.2f}–{asian_h:.2f}  ({asian_r:.0f}pip)")
        self.lbl_daily.setStyleSheet(
            f"color:{dp_col};font-family:Consolas;font-size:11px;")
        self.lbl_daily.setText(f"Daily: ${dp_val:+.2f}")

        if atr_pip > 0:
            self.lbl_atr.setText(f"ATR: {atr_pip:.1f}pip")
            self.lbl_step.setText(f"Step: {step_pip:.1f}pip")
        self.lbl_pending.setText(f"Pending: {pending}")
        if target > 0:
            self.lbl_target.setText(f"Target: ${target:.2f}")

        if eq > 0:
            self.sparkline.push(eq)

    def _on_done(self, reason):
        self._on_log("=" * 50, "INFO")
        self._on_log(f"  Bot stopped: {reason}", "NEW")
        self._on_log("=" * 50, "INFO")
        self.btn_start.setEnabled(True)
        self.btn_stop.setEnabled(False)
        self._set_inputs(True)
        self._on_status(f"Stopped — {reason}")
        for lb in (self.c_float, self.c_buy, self.c_sell, self.c_peak):
            lb.setText("—")
        self.progress.setValue(0)
        self.lbl_pct.setText("0.0%")

    # ── Table refresh ─────────────────────────────────────────────
    def _refresh_tables(self):
        if not self._engine or not self._engine.is_alive():
            return
        try:
            import MetaTrader5 as mt5
            if mt5.account_info() is None:
                return  # MT5 not connected
            sym = self._sym()
            positions = mt5.positions_get(symbol=sym) or []
            our = [p for p in positions if p.magic == cfg.MAGIC_NUMBER]
            self.pos_table.setRowCount(len(our))
            bp = sp = bpnl = spnl = 0.0
            bc = sc = 0
            for r, p in enumerate(our):
                ts = "BUY" if p.type == mt5.ORDER_TYPE_BUY else "SELL"
                tc = C['green'] if p.type == mt5.ORDER_TYPE_BUY else C['red']
                pnl = p.profit + p.swap
                pc = C['green'] if pnl >= 0 else C['red']
                if p.type == mt5.ORDER_TYPE_BUY:
                    bp += pnl
                    bc += 1
                else:
                    sp += pnl
                    sc += 1
                for c, (v, col) in enumerate([
                    (str(p.ticket),            C['txt2']),
                    (ts,                       tc),
                    (f"{p.volume:.2f}",        C['txt']),
                    (f"{p.price_open:.2f}",    C['txt']),
                    (f"{p.price_current:.2f}", C['cyan']),
                    (f"${pnl:+.2f}",           pc),
                    (p.comment,                C['txt3']),
                ]):
                    it = QTableWidgetItem(v)
                    it.setForeground(QColor(col))
                    self.pos_table.setItem(r, c, it)

            net = bp+sp
            nc = C['green'] if net >= 0 else C['red']
            self.lbl_sbuy.setText(f"Buys: {bc}  (${bp:+.2f})")
            self.lbl_ssell.setText(f"Sells: {sc}  (${sp:+.2f})")
            self.lbl_spnl.setStyleSheet(
                f"color:{nc};font-family:Consolas;font-size:11px;")
            self.lbl_spnl.setText(f"Net P&L: ${net:+.2f}")

            orders = mt5.orders_get(symbol=sym) or []
            our_o = [o for o in orders if o.magic == cfg.MAGIC_NUMBER]
            self.ord_table.setRowCount(len(our_o))
            TM = {
                mt5.ORDER_TYPE_BUY_STOP:   ("BUY STOP",  C['green']),
                mt5.ORDER_TYPE_SELL_STOP:  ("SELL STOP", C['red']),
                mt5.ORDER_TYPE_BUY_LIMIT:  ("BUY LIMIT", C['cyan']),
                mt5.ORDER_TYPE_SELL_LIMIT: ("SELL LIMIT", C['orange']),
            }
            for r, o in enumerate(our_o):
                ts2, tc2 = TM.get(o.type, (str(o.type), C['txt']))
                for c, (v, col) in enumerate([
                    (str(o.ticket),             C['txt2']),
                    (ts2,                       tc2),
                    (f"{o.volume_current:.2f}", C['txt']),
                    (f"{o.price_open:.2f}",     C['cyan']),
                    (o.comment,                 C['txt3']),
                ]):
                    it = QTableWidgetItem(v)
                    it.setForeground(QColor(col))
                    self.ord_table.setItem(r, c, it)
        except Exception:
            pass

    def _refresh_price(self):
        try:
            import MetaTrader5 as mt5
            tick = mt5.symbol_info_tick(self._sym())
            if tick:
                self.lbl_price.setText(f"{tick.bid:.2f}")
        except Exception:
            pass


def main():
    app = QApplication(sys.argv)
    app.setStyle("Fusion")
    win = GUI()
    win.show()
    sys.exit(app.exec_())


if __name__ == "__main__":
    main()
