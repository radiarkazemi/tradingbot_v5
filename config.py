"""
TraderBot v5 — Configuration
Smart ATR Breakout Grid | Asian Range + London Breakout
"""

# ── MT5 CREDENTIALS ──────────────────────────────────────────────
MT5_LOGIN = 91246510
MT5_PASSWORD = "@Radiar9841@"
MT5_SERVER = "LiteFinance-MT5-Demo"

# ── SYMBOL ───────────────────────────────────────────────────────
WATCH_SYMBOL = "XAUUSD_o"

# ── MAGIC NUMBER ─────────────────────────────────────────────────
MAGIC_NUMBER = 554433

# ── SCAN INTERVAL ────────────────────────────────────────────────
SCAN_INTERVAL_SEC = 0.1   # 100ms

# ── GRID SETTINGS (Optimized from backtests) ─────────────────────
GRID_COUNT = 8      # orders per side
GRID_STEP_ATR = 0.40   # step = ATR × this
ATR_PERIOD = 14     # bars for ATR

# ── STOP MANAGEMENT ──────────────────────────────────────────────
SL_ATR_MULT = 2.25   # hard SL = ATR × this
TRAIL_ATR_MULT = 0.30   # trailing stop = ATR × this
BE_ATR_MULT = 0.20   # breakeven after ATR × this profit
MIN_STEP_PIPS = 3      # minimum step in pips (overridden by ATR symbol cap)
# minimum SL distance in pips (overridden by ATR symbol cap)
MIN_SL_PIPS = 15

# ── SESSION SETTINGS ─────────────────────────────────────────────
ASIAN_END_HOUR = 7      # London open (UTC) — Asian range ends
TRADE_END_HOUR = 21     # stop new sessions after this UTC hour
TARGET_PCT = 2.0    # close basket at X% profit
DAILY_SL_PCT = 5.0    # stop if daily loss >= X%
PULLBACK_PCT = 30.0   # close if profit drops X% from peak
MAX_SPREAD_PIPS = 25.0    # wait if spread > this, but start after 5min regardless

# ── LOT ──────────────────────────────────────────────────────────
LOT_SIZE = 0.01
