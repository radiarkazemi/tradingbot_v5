"""
TraderBot v5 — Backtest with Real MT5 Data + Chart
Pulls 1M candles directly from your MT5.
Same strategy logic as the live bot.

Usage:
  python backtest.py
  python backtest.py --symbol XAUUSD_o --days 7 --balance 100
  python backtest.py --help
"""
import sys
import os
import argparse
import math
from datetime import datetime, timedelta, timezone
from dataclasses import dataclass

try:
    import MetaTrader5 as mt5
except ImportError:
    print("❌ pip install MetaTrader5")
    sys.exit(1)

try:
    import matplotlib
    matplotlib.use("TkAgg")   # shows a window
    import matplotlib.pyplot as plt
    import matplotlib.gridspec as gridspec
    import numpy as np
    HAS_MPL = True
except Exception:
    try:
        import matplotlib
        matplotlib.use("Qt5Agg")
        import matplotlib.pyplot as plt
        import matplotlib.gridspec as gridspec
        import numpy as np
        HAS_MPL = True
    except Exception:
        try:
            import matplotlib
            matplotlib.use("Agg")  # fallback: save only
            import matplotlib.pyplot as plt
            import matplotlib.gridspec as gridspec
            import numpy as np
            HAS_MPL = True
        except ImportError:
            HAS_MPL = False
            print("⚠ matplotlib not found — no chart. Run: pip install matplotlib")

import config as cfg

# ── Args ──────────────────────────────────────────────────────────
p = argparse.ArgumentParser()
p.add_argument("--symbol",    default=cfg.WATCH_SYMBOL)
p.add_argument("--days",      type=int,   default=7)
p.add_argument("--balance",   type=float, default=100.0)
p.add_argument("--lot",       type=float, default=cfg.LOT_SIZE)
p.add_argument("--count",     type=int,   default=cfg.GRID_COUNT)
p.add_argument("--step",      type=float, default=cfg.GRID_STEP_ATR)
p.add_argument("--sl",        type=float, default=cfg.SL_ATR_MULT)
p.add_argument("--trail",     type=float, default=cfg.TRAIL_ATR_MULT)
p.add_argument("--be",        type=float, default=cfg.BE_ATR_MULT)
p.add_argument("--target",    type=float, default=cfg.TARGET_PCT)
p.add_argument("--dailysl",   type=float, default=cfg.DAILY_SL_PCT)
p.add_argument("--pullback",  type=float, default=cfg.PULLBACK_PCT)
p.add_argument("--asian",     type=int,   default=cfg.ASIAN_END_HOUR)
p.add_argument("--end",       type=int,   default=cfg.TRADE_END_HOUR)
p.add_argument("--spread",    type=float, default=1.5,   help="Spread in pips")
p.add_argument("--commission", type=float, default=0.05,
               help="$ per side per 0.01 lot")
args = p.parse_args()

print(f"\n{'='*60}")
print(f"  TraderBot v5 — Backtest  |  {args.symbol}  |  {args.days} days")
print(f"{'='*60}")
print(
    f"  Balance: ${args.balance:.2f}  Lot: {args.lot}  Count: {args.count}/side")
print(f"  Step: ATR×{args.step}  SL: ATR×{args.sl}  Trail: ATR×{args.trail}")
print(
    f"  Target: {args.target}%  Daily SL: {args.dailysl}%  Pullback: {args.pullback}%")
print(f"{'='*60}\n")

# ── Connect & fetch ───────────────────────────────────────────────
if not mt5.initialize(login=cfg.MT5_LOGIN,
                      password=cfg.MT5_PASSWORD,
                      server=cfg.MT5_SERVER):
    print(f"❌ MT5 failed: {mt5.last_error()}")
    sys.exit(1)
print("✅ MT5 connected")

mt5.symbol_select(args.symbol, True)
info = mt5.symbol_info(args.symbol)
if info is None:
    print(f"❌ No info for {args.symbol}")
    mt5.shutdown()
    sys.exit(1)

# ── Pip & tick value from MT5 ─────────────────────────────────────
digits = info.digits
point = info.point
tick_size = info.trade_tick_size if info.trade_tick_size > 0 else point
tick_val = info.trade_tick_value  # $ per tick per 1 lot

# 1 pip in price units
pip = point if digits <= 2 else point * 10

# $ per pip per 1 LOT
# pip_val_per_lot = tick_val / tick_size * pip
if tick_size > 0 and tick_val > 0:
    pip_val_per_lot = (tick_val / tick_size) * pip
else:
    # Fallback for brokers with missing tick info
    # XAUUSD: 1 lot = 100oz, pip=$0.10 → pip_val = $10/pip/lot
    # BTCUSD: 1 lot = 1 BTC, pip=$0.01 → pip_val tiny
    pip_val_per_lot = 10.0 if "XAU" in args.symbol.upper() else pip * 100.0

spread_price = args.spread * pip
commission = args.commission

print(f"📐 Pip: {pip}  Digits: {digits}")
print(f"💵 Pip value: ${pip_val_per_lot:.4f}/pip/lot")
print(f"💵 Per trade:  ${pip_val_per_lot*args.lot:.6f}/pip at {args.lot} lot")

# ── Verify P&L accuracy with MT5 order_calc_profit ───────────────
# Test: what does MT5 say a 100-pip move earns at args.lot?
try:
    test_price = mt5.symbol_info_tick(args.symbol)
    if test_price:
        test_profit = mt5.order_calc_profit(
            mt5.ORDER_TYPE_BUY,
            args.symbol,
            args.lot,
            test_price.ask,
            test_price.ask + 100 * pip
        )
        our_calc = (100 * pip_val_per_lot * args.lot)
        if test_profit is not None:
            diff_pct = abs(our_calc - test_profit) / \
                max(abs(test_profit), 0.0001) * 100
            status = "✅" if diff_pct < 1.0 else "⚠"
            print(f"{status} P&L accuracy check: 100pip BUY at {args.lot}lot")
            print(
                f"   MT5 says: ${test_profit:.4f}  |  Our calc: ${our_calc:.4f}  |  Diff: {diff_pct:.2f}%")
            if diff_pct > 1.0:
                print(f"   ⚠ Adjusting pip_val to match MT5 exactly...")
                pip_val_per_lot = test_profit / (100 * args.lot)
                print(
                    f"   ✅ Adjusted pip value: ${pip_val_per_lot:.6f}/pip/lot")
except Exception as e:
    print(f"   (P&L verify skipped: {e})")
print()

# ── Fetch bars ────────────────────────────────────────────────────
now = datetime.now(tz=timezone.utc)
start_from = now - timedelta(days=args.days + 2)

# Fetch available history — LiteFinance demo typically has ~30 days of M1
print(f"⬇  Fetching M1 history for {args.symbol}...")
bars = mt5.copy_rates_from_pos(
    args.symbol, mt5.TIMEFRAME_M1, 0, args.days * 24 * 60)
mt5.shutdown()

if bars is None or len(bars) == 0:
    print(
        f"❌ No bars returned. Make sure MT5 is open and {args.symbol} chart is visible.")
    sys.exit(1)

# Find what's actually available
earliest = datetime.fromtimestamp(bars[0]['time'], tz=timezone.utc)
available_days = (now - earliest).days

# If requested more days than available, warn and use what we have
if available_days < args.days:
    print(
        f"⚠  Requested {args.days} days but only {available_days} days available")
    print(f"   LiteFinance demo keeps ~{available_days} days of M1 history")
    print(
        f"   Running on all available data: {earliest.date()} → {now.date()}")
    print()
    cutoff = earliest
else:
    cutoff = now - timedelta(days=args.days)
    print(
        f"✅ History available: {available_days} days  ({earliest.date()} → {now.date()})")
    print()

bars = [b for b in bars if datetime.fromtimestamp(
    b['time'], tz=timezone.utc) >= cutoff]
actual_start = datetime.fromtimestamp(
    bars[0]['time'], tz=timezone.utc) if bars else now
print(f"📊 {len(bars):,} M1 bars  |  {actual_start.date()} → {now.date()}")
print()
mt5.shutdown()

if len(bars) < 50:
    print("❌ Not enough bars — try --days with a smaller number")
    sys.exit(1)

if len(bars) < 50:
    print("❌ Not enough bars.")
    sys.exit(1)

# ── Helpers ───────────────────────────────────────────────────────


def snap(price: float) -> float:
    if tick_size <= 0:
        return round(price, digits)
    return round(round(price / tick_size) * tick_size, digits)


def calc_atr(i: int, period: int = 14) -> float:
    start = max(1, i - period + 1)
    trs = [max(bars[j]['high']-bars[j]['low'],
               abs(bars[j]['high']-bars[j-1]['close']),
               abs(bars[j]['low']-bars[j-1]['close']))
           for j in range(start, i+1)]
    raw = sum(trs)/len(trs) if trs else pip*20
    return max(3.0*pip, raw)


def pnl(side, entry, exit_p, lot):
    """P&L in USD using real tick value from MT5."""
    diff = (exit_p - entry) if side == "BUY" else (entry - exit_p)
    gross = (diff / pip) * pip_val_per_lot * lot
    comm = commission * (lot / 0.01)
    return round(gross - comm, 6)


@dataclass
class Pos:
    id: int
    side: str
    entry: float
    sl: float
    trail_d: float
    lot: float
    be_done: bool = False
    peak: float = 0.0


@dataclass
class SR:
    num: int
    start_bal: float
    end_bal: float
    pnl: float
    peak_pnl: float
    reason: str
    n_pos: int
    locked: str
    atr_pip: float
    date: str


# ── Backtest loop ─────────────────────────────────────────────────
balance = args.balance
sessions = []
equity = []
pid = 1

asian_h = 0.0
asian_l = float('inf')
asian_ready = False
daily_start = balance
daily_hit = False
sess_fired = False
last_day = None

active = False
locked = False
locked_side = ""
bal_start = balance
peak = 0.0
anchor = 0.0
atr_v = 0.0
step_d = 0.0
sl_d = 0.0
trail_d = 0.0
be_d = 0.0
positions = []
p_buy = []
p_sell = []
sess_num = 0
n_win = 0
be_set = set()
sess_npos = 0
sess_peak = 0.0
buy_sl = 0.0
sell_sl = 0.0


def start_session(i, mid, use_asian):
    global active, locked, locked_side, bal_start, peak, anchor
    global atr_v, step_d, sl_d, trail_d, be_d, sess_num, n_win
    global be_set, sess_npos, sess_peak, buy_sl, sell_sl
    global p_buy, p_sell

    atr_v = calc_atr(i)
    step_d = atr_v * args.step
    sl_d = atr_v * args.sl
    trail_d = atr_v * args.trail
    be_d = atr_v * args.be

    if use_asian and asian_h > 0 and asian_l < float('inf'):
        anchor = snap((asian_h + asian_l) / 2.0)
    else:
        anchor = snap(mid)

    buy_sl = snap(anchor - sl_d)
    sell_sl = snap(anchor + sl_d)

    p_buy = [snap(anchor + (j+1)*step_d) for j in range(args.count)]
    p_sell = [snap(anchor - (j+1)*step_d) for j in range(args.count)]

    active = True
    locked = False
    locked_side = ""
    bal_start = balance
    peak = 0.0
    sess_peak = 0.0
    be_set = set()
    sess_npos = 0
    n_win = 0
    sess_num += 1


def close_session(reason, bid, ask):
    global balance, active, locked, locked_side
    for pos in positions:
        ep = bid if pos.side == "BUY" else ask
        g = pnl(pos.side, pos.entry, ep, pos.lot)
        balance += g
        if g > 0:
            pass  # count wins separately
    sp = balance - bal_start
    sessions.append(SR(
        num=sess_num, start_bal=bal_start, end_bal=balance,
        pnl=sp, peak_pnl=sess_peak, reason=reason,
        n_pos=sess_npos, locked=locked_side,
        atr_pip=atr_v/pip if pip > 0 else 0,
        date=str(last_day or "")
    ))
    positions.clear()
    p_buy.clear()
    p_sell.clear()
    active = False
    locked = False
    locked_side = ""


for i, bar in enumerate(bars):
    bt = datetime.fromtimestamp(bar['time'], tz=timezone.utc)
    h = bt.hour
    day = bt.date()
    hi = bar['high']
    lo = bar['low']
    bid = bar['close'] - spread_price/2
    ask = bar['close'] + spread_price/2
    mid = bar['close']

    # Running equity
    fl = sum(pnl(p.side, p.entry, bid if p.side == "BUY" else ask, p.lot)
             for p in positions)
    equity.append(balance + max(0, fl))

    # New day
    if day != last_day:
        if active:
            close_session("day end", bid, ask)
        asian_h = 0.0
        asian_l = float('inf')
        asian_ready = False
        daily_start = balance
        daily_hit = False
        sess_fired = False
        last_day = day

    if daily_hit:
        continue

    # Daily SL check
    dl = (balance - daily_start)/daily_start*100 if daily_start > 0 else 0
    if dl <= -args.dailysl:
        daily_hit = True
        if active:
            close_session("daily SL", bid, ask)
        continue

    # Asian range
    if h < args.asian:
        if mid > asian_h:
            asian_h = mid
        if mid < asian_l:
            asian_l = mid
        asian_ready = asian_h > 0 and asian_l < float('inf')
        continue

    # Trade end
    if h >= args.end:
        if active:
            close_session("trade end", bid, ask)
        continue

    # Start session
    if not active and not sess_fired and i >= 14:
        start_session(i, mid, asian_ready)
        sess_fired = True
        continue

    if not active:
        continue

    # Trigger pending
    if not locked or locked_side == "BUY":
        for price in [p for p in p_buy if hi >= p]:
            p_buy.remove(price)
            pos = Pos(pid, "BUY", price+spread_price/2,
                      buy_sl, trail_d, args.lot, peak=price)
            positions.append(pos)
            pid += 1
            sess_npos += 1

    if not locked or locked_side == "SELL":
        for price in [p for p in p_sell if lo <= p]:
            p_sell.remove(price)
            pos = Pos(pid, "SELL", price-spread_price/2,
                      sell_sl, trail_d, args.lot, peak=price)
            positions.append(pos)
            pid += 1
            sess_npos += 1

    # SL hits
    alive = []
    for pos in positions:
        if pos.side == "BUY" and lo <= pos.sl:
            balance += pnl("BUY", pos.entry, pos.sl, pos.lot)
        elif pos.side == "SELL" and hi >= pos.sl:
            balance += pnl("SELL", pos.entry, pos.sl, pos.lot)
        else:
            alive.append(pos)
    positions[:] = alive

    # Side lock
    if not locked and positions:
        buys = [p for p in positions if p.side == "BUY"]
        sells = [p for p in positions if p.side == "SELL"]
        if buys and not sells:
            locked_side = "BUY"
            p_sell.clear()
            locked = True
        elif sells and not buys:
            locked_side = "SELL"
            p_buy.clear()
            locked = True
        elif buys and sells:
            if len(buys) >= len(sells):
                locked_side = "BUY"
                for p in sells:
                    balance += pnl("SELL", p.entry, ask, p.lot)
                positions[:] = buys
                p_sell.clear()
            else:
                locked_side = "SELL"
                for p in buys:
                    balance += pnl("BUY", p.entry, bid, p.lot)
                positions[:] = sells
                p_buy.clear()
            locked = True

    # Trailing + BE
    if positions:
        be_pips = be_d/pip if pip > 0 else 5
        any_be = any(
            (bid-p.entry)/pip >= be_pips if p.side == "BUY"
            else (p.entry-ask)/pip >= be_pips
            for p in positions
        )
        for pos in positions:
            ib = pos.side == "BUY"
            cur = bid if ib else ask
            if ib:
                if cur > pos.peak:
                    pos.peak = cur
                nsl = snap(pos.peak-pos.trail_d)
                if nsl > pos.sl:
                    pos.sl = nsl
                pp = (bid-pos.entry)/pip
            else:
                if cur < pos.peak:
                    pos.peak = cur
                nsl = snap(pos.peak+pos.trail_d)
                if pos.sl == 0 or nsl < pos.sl:
                    pos.sl = nsl
                pp = (pos.entry-ask)/pip
            sb = pp >= be_pips or (any_be and pp >= 0)
            if sb and pos.id not in be_set:
                bsl = snap(
                    pos.entry+tick_size) if ib else snap(pos.entry-tick_size)
                if ib and bsl > pos.sl:
                    pos.sl = bsl
                    be_set.add(pos.id)
                elif not ib and (pos.sl == 0 or bsl < pos.sl):
                    pos.sl = bsl
                    be_set.add(pos.id)

    # Exits
    if positions:
        fl = sum(pnl(p.side, p.entry, bid if p.side == "BUY" else ask, p.lot)
                 for p in positions)
        if fl > sess_peak:
            sess_peak = fl
        tgt = bal_start * args.target/100.0

        # Pullback
        if sess_peak >= tgt*0.4 and sess_peak > 0:
            drop = (sess_peak-fl)/sess_peak*100
            if drop >= args.pullback:
                close_session(f"pullback {drop:.0f}%", bid, ask)
                if not daily_hit:
                    start_session(i, mid, False)

        # Target
        elif fl >= tgt:
            close_session(f"target ${fl:.2f}", bid, ask)
            if not daily_hit:
                start_session(i, mid, False)

# Close remaining
if active and positions:
    close_session("data end", bid, ask)

# ── Results ───────────────────────────────────────────────────────
total_pnl = balance - args.balance
total_pct = total_pnl / args.balance * 100
ns = len(sessions)
nw = sum(1 for s in sessions if s.pnl > 0)
nl = ns - nw
wr = nw/ns*100 if ns else 0

# Drawdown
peak_e = args.balance
max_dd = 0.0
for eq in equity:
    if eq > peak_e:
        peak_e = eq
    dd = (peak_e-eq)/peak_e*100 if peak_e > 0 else 0
    if dd > max_dd:
        max_dd = dd

print(f"{'='*60}")
print(f"  RESULTS  |  {args.symbol}  |  Last {args.days} days")
print(f"{'='*60}")
print(f"  Start Balance : ${args.balance:.2f}")
print(f"  Final Balance : ${balance:.2f}")
print(f"  Total P&L     : ${total_pnl:+.2f}  ({total_pct:+.1f}%)")
print(f"  Lot Size      : {args.lot}  →  ${pip_val_per_lot*args.lot:.5f}/pip")
print(f"  Sessions      : {ns}  |  {nw}W / {nl}L  ({wr:.0f}% win rate)")
print(f"  Max Drawdown  : {max_dd:.1f}%")
avg_w = sum(s.pnl for s in sessions if s.pnl > 0)/max(nw, 1)
avg_l = sum(s.pnl for s in sessions if s.pnl <= 0)/max(nl, 1)
print(f"  Avg Win       : ${avg_w:.4f}")
print(f"  Avg Loss      : ${avg_l:.4f}")
print(f"  Pip value     : ${pip_val_per_lot:.4f}/pip/lot  (verified vs MT5)")
print(f"{'='*60}")
print()
print(f"  {'#':>4}  {'Date':>11}  {'Start':>8}  {'End':>8}  "
      f"{'P&L':>9}  {'ATR':>6}  {'Side':>5}  Reason")
print(f"  {'-'*78}")
for s in sessions:
    sd = "↑BUY" if s.locked == "BUY" else "↓SELL" if s.locked == "SELL" else "  —"
    print(f"  {s.num:>4}  {s.date:>11}  ${s.start_bal:>7.2f}  "
          f"${s.end_bal:>7.2f}  ${s.pnl:>+8.3f}  "
          f"{s.atr_pip:>5.0f}p  {sd:>5}  {s.reason}")
print(f"{'='*60}\n")

# ── Chart ─────────────────────────────────────────────────────────
if not HAS_MPL:
    print("Install matplotlib for chart: pip install matplotlib numpy")
    sys.exit(0)

BG = "#0D1117"
CARD = "#161B22"
BORDER = "#2A3550"
GR = "#00D97E"
RD = "#FF4560"
GL = "#F5A623"
CY = "#00BCD4"
T2 = "#8B9BB4"
PU = "#B388FF"

plt.style.use("dark_background")
fig = plt.figure(figsize=(18, 11), facecolor=BG)
fig.suptitle(
    f"TraderBot v5  ·  {args.symbol}  ·  Last {args.days} Days  ·  "
    f"Lot={args.lot}  ·  ${args.balance:.0f} → ${balance:.2f}  ({total_pct:+.1f}%)",
    color=GL, fontsize=13, fontweight="bold", y=0.98
)

gs = gridspec.GridSpec(3, 4, figure=fig, hspace=0.45, wspace=0.35,
                       top=0.93, bottom=0.07)

# ── Stat cards (4) ────────────────────────────────────────────────
cards = [
    ("Final Balance",  f"${balance:.2f}",
     GR if total_pnl >= 0 else RD),
    ("Total P&L",
     f"${total_pnl:+.2f}\n({total_pct:+.1f}%)", GR if total_pnl >= 0 else RD),
    ("Win Rate",       f"{wr:.0f}%\n{nw}W / {nl}L",               CY),
    ("Max Drawdown\nLot: "+str(args.lot),
     f"{max_dd:.1f}%\n${pip_val_per_lot*args.lot:.5f}/pip", PU),
]
for col, (title, val, color) in enumerate(cards):
    ax = fig.add_subplot(gs[0, col])
    ax.set_facecolor(CARD)
    ax.set_xticks([])
    ax.set_yticks([])
    for sp in ax.spines.values():
        sp.set_edgecolor(BORDER)
    ax.text(0.5, 0.76, title.upper(), transform=ax.transAxes,
            ha="center", va="center", color=T2, fontsize=8, fontweight="bold",
            multialignment="center")
    ax.text(0.5, 0.28, val, transform=ax.transAxes,
            ha="center", va="center", color=color,
            fontsize=11, fontweight="bold", fontfamily="monospace",
            multialignment="center")

# ── Equity curve (full width) ─────────────────────────────────────
ax_eq = fig.add_subplot(gs[1, :])
ax_eq.set_facecolor(CARD)
for sp in ax_eq.spines.values():
    sp.set_edgecolor(BORDER)
ax_eq.set_title("Equity Curve  (session boundaries = vertical lines)",
                color=T2, fontsize=10, pad=6)

x = np.arange(len(equity))
eq = np.array(equity)
peak_arr = np.maximum.accumulate(eq)

ax_eq.fill_between(x, args.balance, eq, where=eq >=
                   args.balance, alpha=0.15, color=GR)
ax_eq.fill_between(x, args.balance, eq, where=eq <
                   args.balance, alpha=0.15, color=RD)
ax_eq.fill_between(x, eq, peak_arr, alpha=0.07, color=RD, label="Drawdown")
ax_eq.plot(x, eq, color=GR if balance >= args.balance else RD, lw=1.5)
ax_eq.axhline(args.balance, color=T2, lw=0.8, ls="--", alpha=0.5,
              label=f"Start ${args.balance:.0f}")

# Mark session starts
bar_idx = 0
for s in sessions:
    ax_eq.axvline(bar_idx, color=BORDER, lw=0.5, alpha=0.5)
    bar_idx += max(1, s.n_pos * 3)  # approximate

ax_eq.annotate(f"${balance:.2f}",
               xy=(len(equity)-1, equity[-1]),
               xytext=(-60, 8), textcoords="offset points",
               color=GR if balance >= args.balance else RD,
               fontsize=10, fontweight="bold")
ax_eq.set_ylabel("Balance ($)", color=T2, fontsize=9)
ax_eq.tick_params(colors=T2, labelsize=8)
ax_eq.grid(color=BORDER, lw=0.3, alpha=0.5)
ax_eq.legend(fontsize=8, facecolor=CARD, edgecolor=BORDER, labelcolor=T2)

# ── Session P&L bars ──────────────────────────────────────────────
ax_bar = fig.add_subplot(gs[2, :3])
ax_bar.set_facecolor(CARD)
for sp in ax_bar.spines.values():
    sp.set_edgecolor(BORDER)
ax_bar.set_title("P&L per Session", color=T2, fontsize=10, pad=6)
pnls = [s.pnl for s in sessions]
cols = [GR if p > 0 else RD for p in pnls]
snums = list(range(1, len(pnls)+1))
ax_bar.bar(snums, pnls, color=cols, alpha=0.85, width=0.65)
ax_bar.axhline(0, color=T2, lw=0.8)
for n, p in zip(snums, pnls):
    if abs(p) > max(abs(x) for x in pnls)*0.05:
        ax_bar.text(n, p+(0.005 if p >= 0 else -0.005)*max(abs(x) for x in pnls),
                    f"${p:+.1f}", ha="center", va="bottom" if p >= 0 else "top",
                    color=T2, fontsize=6)
ax_bar.set_xlabel("Session #", color=T2, fontsize=8)
ax_bar.set_ylabel("P&L ($)", color=T2, fontsize=8)
ax_bar.tick_params(colors=T2, labelsize=7)
ax_bar.grid(axis="y", color=BORDER, lw=0.3, alpha=0.5)

# ── Drawdown curve ────────────────────────────────────────────────
ax_dd = fig.add_subplot(gs[2, 3])
ax_dd.set_facecolor(CARD)
for sp in ax_dd.spines.values():
    sp.set_edgecolor(BORDER)
ax_dd.set_title(f"Drawdown  (max {max_dd:.1f}%)", color=T2, fontsize=10, pad=6)
dd_arr = (peak_arr - eq) / np.where(peak_arr > 0, peak_arr, 1) * 100
ax_dd.fill_between(x, 0, -dd_arr, alpha=0.4, color=RD)
ax_dd.plot(x, -dd_arr, color=RD, lw=1.0)
ax_dd.axhline(0, color=T2, lw=0.5)
ax_dd.set_ylabel("Drawdown %", color=T2, fontsize=8)
ax_dd.tick_params(colors=T2, labelsize=7)
ax_dd.grid(color=BORDER, lw=0.3, alpha=0.5)

out = f"backtest_{args.symbol}_{args.days}d.png"
plt.savefig(out, dpi=150, bbox_inches="tight", facecolor=BG)
print(f"📈 Chart saved → {out}")

# Try to show in window — works on desktop, skip silently if headless
try:
    plt.show()
except Exception:
    # If no display, auto-open the saved file
    import subprocess
    import platform
    try:
        if platform.system() == "Windows":
            os.startfile(out)
        elif platform.system() == "Darwin":
            subprocess.run(["open", out])
        else:
            subprocess.run(["xdg-open", out])
    except Exception:
        pass
