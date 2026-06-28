"""
TraderBot v5 — Smart ATR Breakout Grid Engine
Fixed version: proper SL distances, session cost tracking, no silent losses
"""
import threading
import time
import logging
from datetime import datetime, timezone
from typing import Callable, Optional

import MetaTrader5 as mt5

log = logging.getLogger("grid_engine")


def _snap(price: float, tick_size: float, digits: int) -> float:
    if tick_size <= 0:
        return round(price, digits)
    return round(round(price / tick_size) * tick_size, digits)


def _pip_size(symbol: str) -> float:
    info = mt5.symbol_info(symbol)
    if info is None:
        sym = symbol.upper()
        if "JPY" in sym:  return 0.01
        if "XAU" in sym:  return 0.10
        if "BTC" in sym:  return 1.0
        if "ETH" in sym:  return 1.0
        return 0.0001
    if info.digits <= 2: return info.point
    if info.digits in (3, 5): return info.point * 10
    return info.point * 10


def _norm_lot(lot: float, info) -> float:
    lot = max(info.volume_min, min(info.volume_max, lot))
    return round(round(lot / info.volume_step) * info.volume_step, 8)


def _filling(symbol: str) -> int:
    info = mt5.symbol_info(symbol)
    if info is None: return mt5.ORDER_FILLING_IOC
    m = info.filling_mode
    if m & 1: return mt5.ORDER_FILLING_FOK
    if m & 2: return mt5.ORDER_FILLING_IOC
    return mt5.ORDER_FILLING_RETURN


def _calc_atr(symbol: str, period: int, pip: float) -> float:
    """
    Raw ATR in price units with only a floor minimum (3 pips).
    No upper cap — let the real ATR drive grid sizing.
    The step multiplier in the caller controls final size.
    """
    bars = mt5.copy_rates_from_pos(symbol, mt5.TIMEFRAME_M1, 0, period + 2)
    if bars is None or len(bars) < 2:
        return 20.0 * pip
    trs = []
    for i in range(1, len(bars)):
        tr = max(
            bars[i]['high'] - bars[i]['low'],
            abs(bars[i]['high'] - bars[i-1]['close']),
            abs(bars[i]['low']  - bars[i-1]['close']),
        )
        trs.append(tr)
    atr = sum(trs[-period:]) / max(len(trs[-period:]), 1)
    return max(3.0 * pip, atr)


def _modify_sl(ticket: int, new_sl: float, symbol: str) -> bool:
    pos = mt5.positions_get(ticket=ticket)
    if not pos: return False
    res = mt5.order_send({
        "action":   mt5.TRADE_ACTION_SLTP,
        "symbol":   symbol,
        "position": ticket,
        "sl":       new_sl,
        "tp":       pos[0].tp,
    })
    return res is not None and res.retcode == mt5.TRADE_RETCODE_DONE


class GridEngine(threading.Thread):

    def __init__(
        self,
        symbol: str,
        login: int, password: str, server: str,
        magic: int,
        lot_size: float,
        grid_count: int,
        step_atr_mult: float,
        atr_period: int,
        sl_atr_mult: float,
        trail_atr_mult: float,
        be_atr_mult: float,
        min_step_pips: int,
        min_sl_pips: int,
        asian_end_hour: int,
        trade_end_hour: int,
        target_pct: float,
        daily_sl_pct: float,
        pullback_pct: float,
        max_spread_pips: float,
        scan_interval: float,
        log_fn: Callable,
        status_fn: Callable,
        stats_fn: Callable,
        done_fn: Callable,
    ):
        super().__init__(daemon=True)
        self.symbol          = symbol
        self.login           = login
        self.password        = password
        self.server          = server
        self.magic           = magic
        self.lot_size        = lot_size
        self.grid_count      = grid_count
        self.step_atr_mult   = step_atr_mult
        self.atr_period      = atr_period
        self.sl_atr_mult     = sl_atr_mult
        self.trail_atr_mult  = trail_atr_mult
        self.be_atr_mult     = be_atr_mult
        self.min_step_pips   = min_step_pips
        self.min_sl_pips     = min_sl_pips
        self.asian_end_hour  = asian_end_hour
        self.trade_end_hour  = trade_end_hour
        self.target_pct      = target_pct
        self.daily_sl_pct    = daily_sl_pct
        self.pullback_pct    = pullback_pct
        self.max_spread_pips = max_spread_pips
        self.scan_interval   = scan_interval

        self._log    = log_fn
        self._status = status_fn
        self._stats  = stats_fn
        self._done   = done_fn

        self._stop_flag  = threading.Event()

        # Symbol info
        self._pip        = 0.0
        self._digits     = 2
        self._tick_size  = 0.01

        # Day state
        self._last_day           = None
        self._bal_day            = 0.0
        self._daily_sl_hit       = False
        self._session_fired_today= False
        self._asian_h            = 0.0
        self._asian_l            = float('inf')
        self._asian_ready        = False

        # Session state
        self._active       = False
        self._locked       = False
        self._locked_side  = ""
        self._bal_start    = 0.0
        self._peak         = 0.0
        self._anchor       = 0.0
        self._atr_val      = 0.0
        self._step         = 0.0
        self._sl_dist      = 0.0
        self._trail        = 0.0
        self._be_dist      = 0.0
        self._session_n    = 0
        self._total_sess   = 0
        self._win_sess     = 0
        self._total_profit = 0.0
        self._sess_start   = None
        self._be_done      = set()

    def stop(self):
        self._stop_flag.set()

    # ── Main loop ─────────────────────────────────────────────────

    def run(self):
        self._log("=" * 54, "INFO")
        self._log("  TraderBot v5 — Smart ATR Breakout Grid", "INFO")
        self._log("=" * 54, "INFO")

        if not mt5.initialize(login=self.login,
                              password=self.password,
                              server=self.server):
            self._log(f"❌ MT5 init failed: {mt5.last_error()}", "ERROR")
            self._done("MT5 failed"); return

        self._log("✅ MT5 connected", "INFO")

        if not mt5.symbol_select(self.symbol, True):
            self._log(f"❌ Cannot select {self.symbol}", "ERROR")
            mt5.shutdown(); self._done("Symbol error"); return

        info = mt5.symbol_info(self.symbol)
        self._pip       = _pip_size(self.symbol)
        self._digits    = info.digits
        self._tick_size = info.trade_tick_size if info.trade_tick_size > 0 else info.point

        acct = mt5.account_info()
        self._bal_day = acct.balance
        self._log(f"💰 Balance: ${self._bal_day:.2f}", "INFO")
        self._log(f"📐 Symbol: {self.symbol}  Pip: {self._pip}  Digits: {self._digits}", "INFO")
        self._status("Connected — waiting for session window...")

        while not self._stop_flag.is_set():
            try:
                self._tick()
            except Exception as e:
                self._log(f"⚠ Tick error: {e}", "WARN")
            time.sleep(self.scan_interval)

        # ── Graceful shutdown ─────────────────────────────────────
        self._log("⏹ Stopped by user — closing all positions...", "WARN")
        self._status("Stopping — closing positions...")
        try:
            # Close active session
            if self._active:
                self._close_all("user stop")
            # Also catch any orphan positions
            else:
                positions = mt5.positions_get(symbol=self.symbol) or []
                our = [p for p in positions if p.magic == self.magic]
                if our:
                    self._log(f"⚠ Closing {len(our)} orphan positions", "WARN")
                    self._close_all("user stop cleanup")
        except Exception as e:
            self._log(f"⚠ Shutdown error: {e}", "WARN")
        finally:
            mt5.shutdown()
            self._done("user stop")

    # ── Tick ──────────────────────────────────────────────────────

    def _tick(self):
        tick = mt5.symbol_info_tick(self.symbol)
        if tick is None:
            self._status("Waiting for tick...")
            return

        bid = tick.bid
        ask = tick.ask
        now_utc  = datetime.now(tz=timezone.utc)
        h        = now_utc.hour
        day      = now_utc.date()
        tick_age = now_utc.timestamp() - tick.time

        # Market closed check
        if tick_age > 120:
            self._status(f"Market closed (last tick {int(tick_age/60)}min ago)")
            self._emit_stats(); return

        # ── New day reset ─────────────────────────────────────────
        if day != self._last_day:
            if self._active: self._close_all("day end")
            self._asian_h             = 0.0
            self._asian_l             = float('inf')
            self._asian_ready         = False
            self._session_fired_today = False
            self._daily_sl_hit        = False
            acct = mt5.account_info()
            self._bal_day = acct.balance if acct else self._bal_day
            self._last_day = day
            self._log(f"📅 New day {day} | Balance: ${self._bal_day:.2f}", "INFO")

        # ── Daily SL gate ─────────────────────────────────────────
        if self._daily_sl_hit:
            self._status("⛔ Daily SL reached — waiting for tomorrow")
            self._emit_stats(); return

        acct = mt5.account_info()
        bal  = acct.balance if acct else self._bal_day
        if self._bal_day > 0:
            daily_loss_pct = (bal - self._bal_day) / self._bal_day * 100
            if daily_loss_pct <= -self.daily_sl_pct:
                self._daily_sl_hit = True
                self._log(f"⛔ Daily SL hit ({daily_loss_pct:.1f}%) — no more sessions today", "WARN")
                if self._active: self._close_all("daily SL")
                self._status("⛔ Daily SL reached — waiting for tomorrow")
                self._emit_stats(); return

        # ── Build Asian range ─────────────────────────────────────
        if h < self.asian_end_hour:
            if bid > self._asian_h: self._asian_h = bid
            if bid < self._asian_l: self._asian_l = bid
            self._asian_ready = self._asian_h > 0 and self._asian_l < float('inf')
            rng = f"{self._asian_l:.2f}–{self._asian_h:.2f}" if self._asian_ready else "building..."
            self._status(f"Asian range: {rng}")
            self._emit_stats(); return

        # ── Start session if not active ───────────────────────────
        if not self._active and not self._session_fired_today:
            spread_pips = (ask - bid) / self._pip
            if spread_pips <= self.max_spread_pips:
                use_asian = self._asian_ready
                if not use_asian:
                    self._log("⚠ No Asian range — using current price as anchor", "WARN")
                self._start_session(bid, ask, use_asian)
                self._session_fired_today = True
            else:
                self._status(f"Spread {spread_pips:.1f}pip too wide — waiting...")
            self._emit_stats(); return

        if not self._active:
            self._emit_stats(); return

        # ── End of trading day ────────────────────────────────────
        if h >= self.trade_end_hour:
            self._log(f"🕙 Trade end ({self.trade_end_hour}:00 UTC)", "INFO")
            self._close_all("trade end")
            self._emit_stats(); return

        # ── Active session management ─────────────────────────────
        if not self._locked:
            self._check_side_lock(bid, ask)
        self._update_stops(bid, ask)
        self._check_exits(bid, ask)
        self._emit_stats()

    # ── Start session ─────────────────────────────────────────────

    def _start_session(self, bid: float, ask: float, use_asian: bool):
        atr = _calc_atr(self.symbol, self.atr_period, self._pip)
        if atr <= 0:
            atr = 20.0 * self._pip

        self._atr_val = atr
        self._step    = max(atr * self.step_atr_mult,  self.min_step_pips * self._pip)
        self._sl_dist = max(atr * self.sl_atr_mult,    self.min_sl_pips   * self._pip)
        self._trail   = max(atr * self.trail_atr_mult, 8.0 * self._pip)
        self._be_dist = max(atr * self.be_atr_mult,    3.0 * self._pip)

        if use_asian and self._asian_h > 0 and self._asian_l < float('inf'):
            self._anchor = _snap((self._asian_h + self._asian_l) / 2.0,
                                 self._tick_size, self._digits)
        else:
            self._anchor = _snap((bid + ask) / 2.0, self._tick_size, self._digits)

        acct = mt5.account_info()
        self._bal_start  = acct.balance if acct else self._bal_start
        self._active     = True
        self._locked     = False
        self._locked_side= ""
        self._peak       = 0.0
        self._be_done    = set()
        self._session_n += 1
        self._total_sess+= 1
        self._sess_start = datetime.now()

        info    = mt5.symbol_info(self.symbol)
        lot     = _norm_lot(self.lot_size, info)
        fill    = _filling(self.symbol)
        buy_sl  = _snap(self._anchor - self._sl_dist, self._tick_size, self._digits)
        sell_sl = _snap(self._anchor + self._sl_dist, self._tick_size, self._digits)
        target  = self._bal_start * self.target_pct / 100.0

        self._log("=" * 54, "INFO")
        self._log(f"▶ SESSION #{self._session_n} | Balance: ${self._bal_start:.2f} | Target: ${target:.2f}", "NEW")
        if use_asian:
            self._log(f"📌 Asian H={self._asian_h:.{self._digits}f}  L={self._asian_l:.{self._digits}f}  "
                      f"Anchor={self._anchor:.{self._digits}f}  "
                      f"Range={(self._asian_h-self._asian_l)/self._pip:.0f}pip", "INFO")
        else:
            self._log(f"📌 Anchor={self._anchor:.{self._digits}f} (current mid)", "INFO")
        self._log(
            f"📐 ATR={atr/self._pip:.1f}pip  Step={self._step/self._pip:.1f}pip  "
            f"SL={self._sl_dist/self._pip:.1f}pip  Trail={self._trail/self._pip:.1f}pip  "
            f"lot={lot}", "INFO"
        )

        pb = ps = 0

        for i in range(self.grid_count):
            price = _snap(self._anchor + (i+1)*self._step, self._tick_size, self._digits)
            otype = mt5.ORDER_TYPE_BUY_STOP if price > ask else mt5.ORDER_TYPE_BUY_LIMIT
            res = mt5.order_send({
                "action": mt5.TRADE_ACTION_PENDING, "symbol": self.symbol,
                "volume": lot, "type": otype, "price": price,
                "sl": buy_sl, "tp": 0.0, "deviation": 50, "magic": self.magic,
                "comment": f"TB5_B{i+1}", "type_time": mt5.ORDER_TIME_GTC,
                "type_filling": fill,
            })
            if res and res.retcode == mt5.TRADE_RETCODE_DONE:
                pb += 1
                tag = "BUY STOP" if otype == mt5.ORDER_TYPE_BUY_STOP else "BUY LIMIT"
                self._log(f"   🟢 {tag} #{i+1} @ {price:.{self._digits}f}  SL={buy_sl:.{self._digits}f}", "NEW")
            else:
                rc = res.retcode if res else "N/A"
                self._log(f"   ❌ BUY #{i+1} FAILED @ {price:.{self._digits}f}  retcode={rc}", "ERROR")

        for i in range(self.grid_count):
            price = _snap(self._anchor - (i+1)*self._step, self._tick_size, self._digits)
            otype = mt5.ORDER_TYPE_SELL_STOP if price < bid else mt5.ORDER_TYPE_SELL_LIMIT
            res = mt5.order_send({
                "action": mt5.TRADE_ACTION_PENDING, "symbol": self.symbol,
                "volume": lot, "type": otype, "price": price,
                "sl": sell_sl, "tp": 0.0, "deviation": 50, "magic": self.magic,
                "comment": f"TB5_S{i+1}", "type_time": mt5.ORDER_TIME_GTC,
                "type_filling": fill,
            })
            if res and res.retcode == mt5.TRADE_RETCODE_DONE:
                ps += 1
                tag = "SELL STOP" if otype == mt5.ORDER_TYPE_SELL_STOP else "SELL LIMIT"
                self._log(f"   🔴 {tag} #{i+1} @ {price:.{self._digits}f}  SL={sell_sl:.{self._digits}f}", "NEW")
            else:
                rc = res.retcode if res else "N/A"
                self._log(f"   ❌ SELL #{i+1} FAILED @ {price:.{self._digits}f}  retcode={rc}", "ERROR")

        total = pb + ps
        self._log(f"✅ Grid placed: {pb}B + {ps}S = {total} orders", "INFO")
        if total == 0:
            self._log("❌ No orders placed — aborting", "ERROR")
            self._active = False
        else:
            self._status(f"Grid active — {pb}B + {ps}S pending | Target ${target:.2f}")

    # ── Side lock ─────────────────────────────────────────────────

    def _check_side_lock(self, bid: float, ask: float):
        positions = mt5.positions_get(symbol=self.symbol) or []
        our   = [p for p in positions if p.magic == self.magic]
        buys  = [p for p in our if p.type == mt5.ORDER_TYPE_BUY]
        sells = [p for p in our if p.type == mt5.ORDER_TYPE_SELL]
        if not buys and not sells: return

        cancel = ""
        if buys and not sells:
            self._locked_side = "BUY";  cancel = "SELL"
        elif sells and not buys:
            self._locked_side = "SELL"; cancel = "BUY"
        elif buys and sells:
            if len(buys) >= len(sells):
                self._locked_side = "BUY"; cancel = "SELL"
                self._close_side("SELL", bid, ask)
            else:
                self._locked_side = "SELL"; cancel = "BUY"
                self._close_side("BUY", bid, ask)
            self._log(f"⚡ Both sides ({len(buys)}B/{len(sells)}S) — locking {self._locked_side}", "WARN")

        self._log(f"🔒 Locked: {self._locked_side} | Cancelling {cancel} pending", "NEW")
        self._cancel_side(cancel)
        self._locked = True

    # ── Update trailing / BE ──────────────────────────────────────

    def _update_stops(self, bid: float, ask: float):
        positions = mt5.positions_get(symbol=self.symbol) or []
        our = [p for p in positions if p.magic == self.magic]
        if not our: return

        be_pips = self.be_atr_mult * (self._atr_val / self._pip) if self._pip > 0 else 5
        any_be  = any(
            (bid - p.price_open) / self._pip >= be_pips if p.type == mt5.ORDER_TYPE_BUY
            else (p.price_open - ask) / self._pip >= be_pips
            for p in our
        )

        for p in our:
            is_buy  = (p.type == mt5.ORDER_TYPE_BUY)
            cur_sl  = p.sl
            new_sl  = cur_sl
            cur_p   = bid if is_buy else ask

            if is_buy:
                tsl = _snap(cur_p - self._trail, self._tick_size, self._digits)
                if tsl > new_sl: new_sl = tsl
                pp = (bid - p.price_open) / self._pip
                if (pp >= be_pips or (any_be and pp >= 0)) and p.ticket not in self._be_done:
                    be_sl = _snap(p.price_open + self._tick_size, self._tick_size, self._digits)
                    if be_sl > new_sl: new_sl = be_sl
            else:
                tsl = _snap(cur_p + self._trail, self._tick_size, self._digits)
                if cur_sl == 0 or tsl < new_sl: new_sl = tsl
                pp = (p.price_open - ask) / self._pip
                if (pp >= be_pips or (any_be and pp >= 0)) and p.ticket not in self._be_done:
                    be_sl = _snap(p.price_open - self._tick_size, self._tick_size, self._digits)
                    if cur_sl == 0 or be_sl < new_sl: new_sl = be_sl

            if abs(new_sl - cur_sl) > self._tick_size * 2:
                if _modify_sl(p.ticket, new_sl, self.symbol):
                    be_triggered = (is_buy and new_sl >= p.price_open) or \
                                   (not is_buy and new_sl <= p.price_open)
                    if be_triggered and p.ticket not in self._be_done:
                        self._be_done.add(p.ticket)
                        self._log(f"   ✅ BE: #{p.ticket} {'BUY' if is_buy else 'SELL'} → {new_sl:.{self._digits}f}", "NEW")

    # ── Exit checks ───────────────────────────────────────────────

    def _check_exits(self, bid: float, ask: float):
        positions = mt5.positions_get(symbol=self.symbol) or []
        our = [p for p in positions if p.magic == self.magic]
        orders = mt5.orders_get(symbol=self.symbol) or []
        our_ord = [o for o in orders if o.magic == self.magic]

        # Nothing left — restart (unless stopped/daily SL)
        if not our and not our_ord:
            if self._stop_flag.is_set() or self._daily_sl_hit:
                self._reset_session(); return
            now_utc = datetime.now(tz=timezone.utc)
            h = now_utc.hour
            if self.asian_end_hour <= h < self.trade_end_hour:
                self._log("ℹ All SL/BE closed — new session", "INFO")
                self._reset_session()
                self._start_session(bid, ask, False)
            else:
                self._reset_session()
            return

        if not our: return

        floating = sum(p.profit + p.swap for p in our)
        target   = self._bal_start * self.target_pct / 100.0
        if floating > self._peak: self._peak = floating

        # Pullback guard
        if self._peak >= target * 0.4 and self._peak > 0:
            drop = (self._peak - floating) / self._peak * 100
            if drop >= self.pullback_pct:
                self._log(f"📉 Pullback guard: {drop:.1f}% drop — closing", "WARN")
                self._close_all(f"pullback {drop:.0f}%"); return

        # Target
        if floating >= target:
            self._log(f"🎯 Target hit! ${floating:.2f} ≥ ${target:.2f}", "NEW")
            self._close_all(f"target ${floating:.2f}")

    # ── Close all ─────────────────────────────────────────────────

    def _close_all(self, reason: str):
        fill = _filling(self.symbol)
        cancelled = closed = 0

        # Cancel pending
        for o in (mt5.orders_get(symbol=self.symbol) or []):
            if o.magic != self.magic: continue
            if mt5.order_send({"action": mt5.TRADE_ACTION_REMOVE, "order": o.ticket}):
                cancelled += 1
        if cancelled:
            self._log(f"   🗑 Cancelled {cancelled} pending orders", "INFO")

        # Close positions with retry
        for attempt in range(5):
            positions = mt5.positions_get(symbol=self.symbol) or []
            our = [p for p in positions if p.magic == self.magic]
            if not our: break
            failed = 0
            for p in our:
                tick = mt5.symbol_info_tick(self.symbol)
                if not tick: failed += 1; continue
                close_type = mt5.ORDER_TYPE_SELL if p.type == mt5.ORDER_TYPE_BUY else mt5.ORDER_TYPE_BUY
                price = tick.bid if p.type == mt5.ORDER_TYPE_BUY else tick.ask
                pnl   = p.profit + p.swap
                res = mt5.order_send({
                    "action": mt5.TRADE_ACTION_DEAL, "symbol": self.symbol,
                    "volume": p.volume, "type": close_type, "position": p.ticket,
                    "price": price, "deviation": 100, "magic": self.magic,
                    "comment": "TB5_CLOSE", "type_filling": fill,
                })
                if res and res.retcode == mt5.TRADE_RETCODE_DONE:
                    closed += 1
                    self._log(f"   {'🟢' if pnl>=0 else '🔴'} Closed #{p.ticket}  P&L: ${pnl:+.2f}", "INFO")
                else:
                    failed += 1
                    self._log(f"   ⚠ Close #{p.ticket} failed: {res.retcode if res else 'N/A'}", "WARN")
            if failed == 0: break
            time.sleep(0.3)

        # Session summary
        acct = mt5.account_info()
        bal  = acct.balance if acct else self._bal_start
        sess_pnl = bal - self._bal_start
        if sess_pnl > 0: self._win_sess += 1
        self._total_profit += sess_pnl
        self._log(
            f"🏁 Session #{self._session_n} done [{reason}]  "
            f"P&L: ${sess_pnl:+.2f}  Balance: ${bal:.2f}", "NEW"
        )
        self._reset_session()
        self._emit_stats()

        # Auto-restart (only if safe)
        if self._stop_flag.is_set() or self._daily_sl_hit:
            return
        tick = mt5.symbol_info_tick(self.symbol)
        if tick:
            now_utc  = datetime.now(tz=timezone.utc)
            h        = now_utc.hour
            tick_age = now_utc.timestamp() - tick.time
            if tick_age < 120 and self.asian_end_hour <= h < self.trade_end_hour:
                self._log("🔄 Starting new session...", "INFO")
                self._session_fired_today = True
                self._start_session(tick.bid, tick.ask, False)

    # ── Helpers ───────────────────────────────────────────────────

    def _cancel_side(self, side: str):
        buy_t  = {mt5.ORDER_TYPE_BUY_STOP, mt5.ORDER_TYPE_BUY_LIMIT}
        sell_t = {mt5.ORDER_TYPE_SELL_STOP, mt5.ORDER_TYPE_SELL_LIMIT}
        target = buy_t if side == "BUY" else sell_t
        n = 0
        for o in (mt5.orders_get(symbol=self.symbol) or []):
            if o.magic == self.magic and o.type in target:
                if mt5.order_send({"action": mt5.TRADE_ACTION_REMOVE, "order": o.ticket}):
                    n += 1
        if n: self._log(f"   🗑 Cancelled {n} {side} pending orders", "INFO")

    def _close_side(self, side: str, bid: float, ask: float):
        fill = _filling(self.symbol)
        for p in (mt5.positions_get(symbol=self.symbol) or []):
            if p.magic != self.magic: continue
            is_buy = p.type == mt5.ORDER_TYPE_BUY
            if (side == "BUY" and is_buy) or (side == "SELL" and not is_buy):
                price = bid if is_buy else ask
                mt5.order_send({
                    "action": mt5.TRADE_ACTION_DEAL, "symbol": self.symbol,
                    "volume": p.volume,
                    "type": mt5.ORDER_TYPE_SELL if is_buy else mt5.ORDER_TYPE_BUY,
                    "position": p.ticket, "price": price,
                    "deviation": 100, "magic": self.magic,
                    "comment": "TB5_LOCK", "type_filling": fill,
                })

    def _reset_session(self):
        self._active      = False
        self._locked      = False
        self._locked_side = ""
        self._peak        = 0.0
        self._be_done     = set()
        self._sess_start  = None

    def _emit_stats(self):
        positions = mt5.positions_get(symbol=self.symbol) or []
        orders    = mt5.orders_get(symbol=self.symbol)    or []
        acct      = mt5.account_info()

        our_pos  = [p for p in positions if p.magic == self.magic]
        our_ord  = [o for o in orders    if o.magic == self.magic]
        buy_pos  = [p for p in our_pos   if p.type == mt5.ORDER_TYPE_BUY]
        sell_pos = [p for p in our_pos   if p.type == mt5.ORDER_TYPE_SELL]
        floating = sum(p.profit + p.swap for p in our_pos)
        target   = self._bal_start * self.target_pct / 100.0
        elapsed  = (datetime.now() - self._sess_start).total_seconds() if self._sess_start else 0.0
        pct      = (floating / target * 100) if target > 0 else 0.0
        asian_r  = (self._asian_h - self._asian_l) / self._pip \
                   if self._asian_h > 0 and self._asian_l < float('inf') else 0.0

        self._stats({
            "active":       self._active,
            "session_n":    self._session_n,
            "total_sess":   self._total_sess,
            "win_sess":     self._win_sess,
            "locked_side":  self._locked_side,
            "open_buy":     len(buy_pos),
            "open_sell":    len(sell_pos),
            "pending":      len(our_ord),
            "floating":     floating,
            "peak":         self._peak,
            "target":       target,
            "progress_pct": min(100.0, pct),
            "balance":      acct.balance if acct else 0.0,
            "equity":       acct.equity  if acct else 0.0,
            "bal_day":      self._bal_day,
            "elapsed_sec":  elapsed,
            "anchor":       self._anchor,
            "atr_pip":      self._atr_val / self._pip if self._pip > 0 else 0,
            "step_pip":     self._step    / self._pip if self._pip > 0 else 0,
            "asian_h":      self._asian_h,
            "asian_l":      self._asian_l if self._asian_l < float('inf') else 0.0,
            "asian_range":  asian_r,
            "asian_ready":  self._asian_ready,
            "total_profit": self._total_profit,
            "daily_sl_hit": self._daily_sl_hit,
        })