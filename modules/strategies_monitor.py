"""
StrategiesMonitor — Ghost (RSI2 + 200-SMA) + Surge (Compression Breakout) on ES=F Daily
Fires once daily at 4:15 PM ET after market close.

Ghost state machine:
  idle          -> RSI(2)<10 + close>SMA200 -> signal_pending
  signal_pending -> next day                -> in_trade  (entry = T+1 open)
  in_trade      -> RSI(2)>65 or day 7       -> exit_pending
  exit_pending  -> next day                -> idle  (exit = open, final P&L logged)

Surge state machine:
  idle          -> bar range < 50% avg      -> comp_pending
  comp_pending  -> next day close           -> idle  (trade logged: long/short/no_break)
"""

import os
import sqlite3
from datetime import datetime, timezone, timedelta, date as _date
from zoneinfo import ZoneInfo

ET = ZoneInfo("America/New_York")


def _next_market_open(from_date_str: str) -> str:
    """Return 'Monday' or 'tomorrow' depending on whether from_date is Fri/Sat."""
    try:
        d = _date.fromisoformat(from_date_str)
    except Exception:
        d = datetime.now(ET).date()
    # weekday(): 0=Mon … 4=Fri, 5=Sat, 6=Sun
    if d.weekday() == 4:   # Friday → next is Monday
        return "Monday"
    elif d.weekday() == 5:  # Saturday → next is Monday
        return "Monday"
    elif d.weekday() == 6:  # Sunday → next is Monday
        return "Monday"
    else:
        return "tomorrow"

GHOST_RSI_ENTRY  = 10.0
GHOST_RSI_EXIT   = 65.0
GHOST_SMA_PERIOD = 200
GHOST_MAX_DAYS   = 7
SURGE_COMP_THR   = 0.50
SURGE_ATR_PERIOD = 20
COST_RT          = 0.60   # round-trip slippage + commission (pts)
MES_MULT         = 5.0
ES_MULT          = 50.0

GS_IDLE           = "idle"
GS_SIGNAL_PENDING = "signal_pending"
GS_IN_TRADE       = "in_trade"
GS_EXIT_PENDING   = "exit_pending"
SS_IDLE           = "idle"
SS_COMP_PENDING   = "comp_pending"


class StrategiesMonitor:
    def __init__(self, config, logger):
        self.config = config
        self.logger = logger

        cfg = config.get("strategies", {})
        self.enabled  = cfg.get("enabled", True)
        self.db_path  = cfg.get("db_path", "/root/jarvis/strategies.db")

        tg = config.get("telegram", {})
        self.tg_enabled  = tg.get("enabled", False)
        self.tg_token    = tg.get("bot_token", "")
        self.tg_chat_id  = tg.get("chat_id", "")

        # Ghost in-memory state
        self.ghost_state       = GS_IDLE
        self.ghost_signal_date = None
        self.ghost_entry_date  = None
        self.ghost_entry_price = None
        self.ghost_days_held   = 0

        # Surge in-memory state
        self.surge_state      = SS_IDLE
        self.surge_comp_date  = None
        self.surge_comp_high  = None
        self.surge_comp_low   = None
        self.surge_atr_ratio  = None

        self.last_check_date = None

        self._init_db()
        self._load_state()
        self.logger.info(
            f"StrategiesMonitor ready | Ghost={self.ghost_state} | Surge={self.surge_state}"
        )

    # ── DATABASE ──────────────────────────────────────────────────────

    def _init_db(self):
        try:
            conn = sqlite3.connect(self.db_path)
            c = conn.cursor()
            c.execute("""
                CREATE TABLE IF NOT EXISTS strategy_state (
                    key TEXT PRIMARY KEY, value TEXT
                )
            """)
            c.execute("""
                CREATE TABLE IF NOT EXISTS ghost_trades (
                    id               INTEGER PRIMARY KEY AUTOINCREMENT,
                    signal_date      TEXT,
                    entry_date       TEXT,
                    exit_date        TEXT,
                    entry_price      REAL,
                    exit_price       REAL,
                    rsi_at_signal    REAL,
                    sma_at_signal    REAL,
                    close_at_signal  REAL,
                    days_held        INTEGER,
                    exit_reason      TEXT,
                    net_pts          REAL,
                    pnl_usd_mes      REAL,
                    pnl_usd_es       REAL,
                    win              INTEGER
                )
            """)
            c.execute("""
                CREATE TABLE IF NOT EXISTS surge_signals (
                    id           INTEGER PRIMARY KEY AUTOINCREMENT,
                    comp_date    TEXT,
                    comp_high    REAL,
                    comp_low     REAL,
                    atr_ratio    REAL,
                    trade_date   TEXT,
                    direction    TEXT,
                    entry_price  REAL,
                    exit_price   REAL,
                    net_pts      REAL,
                    pnl_usd_es   REAL,
                    pnl_usd_mes  REAL,
                    win          INTEGER,
                    outcome      TEXT
                )
            """)
            conn.commit()
            conn.close()
        except Exception as e:
            self.logger.error(f"StrategiesMonitor DB init: {e}")

    def _set(self, key, value):
        try:
            conn = sqlite3.connect(self.db_path)
            conn.execute(
                "INSERT OR REPLACE INTO strategy_state (key, value) VALUES (?, ?)",
                (key, str(value) if value is not None else "")
            )
            conn.commit()
            conn.close()
        except Exception as e:
            self.logger.error(f"state set [{key}]: {e}")

    def _get(self, key, default=None):
        try:
            conn = sqlite3.connect(self.db_path)
            row = conn.execute(
                "SELECT value FROM strategy_state WHERE key=?", (key,)
            ).fetchone()
            conn.close()
            return row[0] if (row and row[0]) else default
        except:
            return default

    def _load_state(self):
        self.ghost_state       = self._get("ghost_state", GS_IDLE)
        self.ghost_signal_date = self._get("ghost_signal_date")
        self.ghost_entry_date  = self._get("ghost_entry_date")
        v = self._get("ghost_entry_price")
        self.ghost_entry_price = float(v) if v else None
        v = self._get("ghost_days_held", "0")
        self.ghost_days_held   = int(v) if v else 0

        self.surge_state      = self._get("surge_state", SS_IDLE)
        self.surge_comp_date  = self._get("surge_comp_date")
        v = self._get("surge_comp_high")
        self.surge_comp_high  = float(v) if v else None
        v = self._get("surge_comp_low")
        self.surge_comp_low   = float(v) if v else None
        v = self._get("surge_atr_ratio")
        self.surge_atr_ratio  = float(v) if v else None

        self.last_check_date = self._get("last_check_date")

    def _save_ghost(self):
        self._set("ghost_state",       self.ghost_state)
        self._set("ghost_signal_date", self.ghost_signal_date or "")
        self._set("ghost_entry_date",  self.ghost_entry_date or "")
        self._set("ghost_entry_price", self.ghost_entry_price or "")
        self._set("ghost_days_held",   self.ghost_days_held)

    def _save_surge(self):
        self._set("surge_state",     self.surge_state)
        self._set("surge_comp_date", self.surge_comp_date or "")
        self._set("surge_comp_high", self.surge_comp_high or "")
        self._set("surge_comp_low",  self.surge_comp_low or "")
        self._set("surge_atr_ratio", self.surge_atr_ratio or "")

    # ── DATA ──────────────────────────────────────────────────────────

    def _get_es_daily(self):
        try:
            import yfinance as yf
            import pandas as pd
            df = yf.download("ES=F", period="2y", interval="1d",
                             auto_adjust=False, progress=False)
            if df.empty:
                return None
            if isinstance(df.columns, pd.MultiIndex):
                df.columns = df.columns.get_level_values(0)
            df = df[['Open', 'High', 'Low', 'Close']].dropna(subset=['Close'])
            self.logger.info(f"ES=F: {len(df)} bars | last={df.index[-1].date()}")
            return df
        except Exception as e:
            self.logger.error(f"ES=F fetch: {e}")
            return None

    # ── SIGNAL COMPUTATION ────────────────────────────────────────────

    def _rsi2(self, close):
        d    = close.diff()
        gain = d.clip(lower=0).ewm(alpha=0.5, min_periods=2, adjust=False).mean()
        loss = (-d.clip(upper=0)).ewm(alpha=0.5, min_periods=2, adjust=False).mean()
        rs   = gain / loss.clip(lower=1e-10)   # clip prevents float underflow → NaN
        return 100 - (100 / (1 + rs))

    def _ghost_indicators(self, df):
        if df is None or len(df) < GHOST_SMA_PERIOD + 5:
            return None
        close  = df['Close']
        rsi2   = self._rsi2(close)
        sma200 = close.rolling(GHOST_SMA_PERIOD).mean()
        return {
            'date':      str(df.index[-1].date()),
            'open':      float(df['Open'].iloc[-1]),
            'close':     float(close.iloc[-1]),
            'rsi2':      round(float(rsi2.iloc[-1]), 2),
            'sma200':    round(float(sma200.iloc[-1]), 2),
            'above_sma': float(close.iloc[-1]) > float(sma200.iloc[-1]),
        }

    def _surge_indicators(self, df):
        if df is None or len(df) < SURGE_ATR_PERIOD + 2:
            return None
        rng   = (df['High'] - df['Low']).clip(lower=0.25)
        avg   = rng.rolling(SURGE_ATR_PERIOD).mean()
        ratio = rng / avg
        last  = df.iloc[-1]
        r     = float(ratio.iloc[-1])
        return {
            'date':      str(df.index[-1].date()),
            'open':      float(last['Open']),
            'high':      float(last['High']),
            'low':       float(last['Low']),
            'close':     float(last['Close']),
            'atr_ratio': round(r, 4),
            'is_comp':   r < SURGE_COMP_THR,
        }

    # ── MAIN ENTRY POINT ──────────────────────────────────────────────

    def run_daily_check(self, force=False):
        now      = datetime.now(ET)
        # Only run on weekdays — market is closed Sat/Sun, counts would inflate days_held
        if now.weekday() >= 5 and not force:
            return []
        today    = now.strftime("%Y-%m-%d")
        if self.last_check_date == today and not force:
            return []

        self.logger.info("StrategiesMonitor: daily check")
        df = self._get_es_daily()
        if df is None:
            return []

        msgs = []
        msgs.extend(self._process_ghost(df))
        msgs.extend(self._process_surge(df))

        self.last_check_date = today
        self._set("last_check_date", today)
        return msgs

    # ── GHOST ─────────────────────────────────────────────────────────

    def _process_ghost(self, df):
        g = self._ghost_indicators(df)
        if not g:
            return []

        today    = g['date']
        rsi2     = g['rsi2']
        close    = g['close']
        sma200   = g['sma200']
        bar_open = g['open']
        msgs     = []

        # exit_pending: today is the exit bar — record at today's open
        if self.ghost_state == GS_EXIT_PENDING:
            # Check if a NEW entry signal also fires today (same-day rollover).
            # If yes: don't close — stay long, keep original entry price, reset days_held to 1.
            # Financially identical to closing and re-entering at the same open price.
            import math as _math
            new_signal_today = not _math.isnan(rsi2) and rsi2 < GHOST_RSI_ENTRY
            self.logger.info(f"GHOST exit_pending: rsi2={rsi2:.4f}, rollover={new_signal_today}")
            if new_signal_today:
                ep           = self.ghost_entry_price or bar_open
                running      = close - ep - COST_RT
                r_mes        = round(running * MES_MULT, 2)
                old_days     = self.ghost_days_held
                self.ghost_days_held  = 1
                self.ghost_entry_date = today   # reset entry date so in_trade counter works
                self.ghost_state      = GS_IN_TRADE
                self._save_ghost()
                msg = (
                    f"👻 GHOST — Day-Max + New Signal: Staying Long\n"
                    f"━━━━━━━━━━━━━━━━━━━━\n"
                    f"Would have exited (day {old_days} max) but RSI(2)={rsi2:.2f} fired a new entry.\n"
                    f"Holding position — counter reset to Day 1.\n"
                    f"Original entry: {ep:.2f}  (unchanged)\n"
                    f"Running P&L:    {running:+.2f} pts  (${r_mes:+.2f} MES)\n"
                    f"━━━━━━━━━━━━━━━━━━━━\n"
                    f"Exit watch: RSI(2) > {GHOST_RSI_EXIT} or day {GHOST_MAX_DAYS}"
                )
                self._alert(msg)
                msgs.append(msg)
                self.logger.info(f"GHOST rollover: day-max + new signal, staying long from {ep:.2f}, days reset to 1")
                return msgs

            # Normal exit — no new signal today
            exit_px = bar_open
            ep      = self.ghost_entry_price or exit_px
            net     = exit_px - ep - COST_RT
            pnl_mes = round(net * MES_MULT, 2)
            pnl_es  = round(net * ES_MULT, 2)
            win     = net > 0

            try:
                conn = sqlite3.connect(self.db_path)
                conn.execute("""
                    UPDATE ghost_trades
                    SET exit_date=?, exit_price=?, days_held=?,
                        net_pts=?, pnl_usd_mes=?, pnl_usd_es=?, win=?
                    WHERE signal_date=? AND exit_date IS NULL
                """, (today, exit_px, self.ghost_days_held,
                      round(net, 2), pnl_mes, pnl_es, 1 if win else 0,
                      self.ghost_signal_date))
                conn.commit()
                conn.close()
            except Exception as e:
                self.logger.error(f"Ghost exit DB: {e}")

            icon = "✅ WIN" if win else "❌ LOSS"
            msg = (
                f"👻 GHOST — Trade Closed\n"
                f"━━━━━━━━━━━━━━━━━━━━\n"
                f"{icon} | LONG\n"
                f"Entry:  {ep:.2f}\n"
                f"Exit:   {exit_px:.2f}  (today's open)\n"
                f"Net:    {net:+.2f} pts\n"
                f"P&L:    ${pnl_mes:+.2f} MES  |  ${pnl_es:+.2f} ES\n"
                f"Days held: {self.ghost_days_held}\n"
                f"━━━━━━━━━━━━━━━━━━━━\n"
                f"Ghost idle. Watching for next RSI(2) dip."
            )
            self._alert(msg)
            msgs.append(msg)
            self.logger.info(f"GHOST closed: {net:+.2f}pts {'WIN' if win else 'LOSS'}")

            self.ghost_state       = GS_IDLE
            self.ghost_signal_date = None
            self.ghost_entry_date  = None
            self.ghost_entry_price = None
            self.ghost_days_held   = 0
            self._save_ghost()
            return msgs

        # signal_pending: today is T+1 — record entry at today's open
        if (self.ghost_state == GS_SIGNAL_PENDING
                and self.ghost_signal_date
                and self.ghost_signal_date != today):

            self.ghost_entry_price = bar_open
            self.ghost_entry_date  = today
            self.ghost_days_held   = 1
            self.ghost_state       = GS_IN_TRADE

            try:
                conn = sqlite3.connect(self.db_path)
                conn.execute("""
                    UPDATE ghost_trades SET entry_date=?, entry_price=?
                    WHERE signal_date=? AND entry_date IS NULL
                """, (today, bar_open, self.ghost_signal_date))
                conn.commit()
                conn.close()
            except Exception as e:
                self.logger.error(f"Ghost entry record DB: {e}")

            running = close - bar_open
            if rsi2 > GHOST_RSI_EXIT or self.ghost_days_held >= GHOST_MAX_DAYS:
                reason = f"RSI(2)={rsi2:.1f}" if rsi2 > GHOST_RSI_EXIT else "day max"
                self.ghost_state = GS_EXIT_PENDING
                self._save_ghost()
                msg = (
                    f"👻 GHOST — Entered + Exit Trigger\n"
                    f"━━━━━━━━━━━━━━━━━━━━\n"
                    f"Entered LONG at open: {bar_open:.2f}\n"
                    f"Exit trigger already: {reason}\n"
                    f"Running today: {running:+.2f} pts\n"
                    f"Exiting at {_next_market_open(today)}'s open."
                )
                self._alert(msg)
                msgs.append(msg)
                return msgs

            self._save_ghost()
            msg = (
                f"👻 GHOST — Trade Entered\n"
                f"━━━━━━━━━━━━━━━━━━━━\n"
                f"LONG 1 MES — entered at open: {bar_open:.2f}\n"
                f"Day 1 of {GHOST_MAX_DAYS} max\n"
                f"━━━━━━━━━━━━━━━━━━━━\n"
                f"RSI(2) now:  {rsi2:.2f}\n"
                f"Close:       {close:.2f}\n"
                f"Running:     {running:+.2f} pts  (${running * MES_MULT:+.2f} MES)\n"
                f"Exit watch:  RSI(2) > {GHOST_RSI_EXIT} or day {GHOST_MAX_DAYS}"
            )
            self._alert(msg)
            msgs.append(msg)

        # in_trade: daily update + exit check
        if (self.ghost_state == GS_IN_TRADE
                and self.ghost_entry_date
                and self.ghost_entry_date != today):

            self.ghost_days_held += 1
            self._save_ghost()

            ep      = self.ghost_entry_price
            running = close - ep - COST_RT
            r_mes   = round(running * MES_MULT, 2)
            icon    = "📈" if running > 0 else "📉"

            should_exit = rsi2 > GHOST_RSI_EXIT or self.ghost_days_held >= GHOST_MAX_DAYS
            if should_exit:
                reason = f"RSI(2) = {rsi2:.1f}" if rsi2 > GHOST_RSI_EXIT else f"Day {GHOST_MAX_DAYS} max reached"
                self.ghost_state = GS_EXIT_PENDING
                self._save_ghost()

            days_left = GHOST_MAX_DAYS - self.ghost_days_held
            status_line = (
                f"⚠️ EXIT TRIGGERED — {reason}\nExiting at {_next_market_open(today)}'s open."
                if should_exit else
                f"Holding — {days_left} day(s) left. No exit trigger."
            )
            msg = (
                f"👻 GHOST — Daily Update\n"
                f"━━━━━━━━━━━━━━━━━━━━\n"
                f"{icon} Day {self.ghost_days_held}/{GHOST_MAX_DAYS}\n"
                f"RSI(2):   {rsi2:.2f}  (exit > {GHOST_RSI_EXIT})\n"
                f"Entry:    {ep:.2f}\n"
                f"Close:    {close:.2f}\n"
                f"Running:  {running:+.2f} pts  (${r_mes:+.2f} MES)\n"
                f"━━━━━━━━━━━━━━━━━━━━\n"
                f"{status_line}"
            )
            self._alert(msg)
            msgs.append(msg)

        # idle: check for new entry signal
        if self.ghost_state == GS_IDLE:
            if rsi2 < GHOST_RSI_ENTRY and g['above_sma']:
                self.ghost_state       = GS_SIGNAL_PENDING
                self.ghost_signal_date = today
                self.ghost_days_held   = 0
                self.ghost_entry_price = None
                self.ghost_entry_date  = None
                self._save_ghost()

                try:
                    conn = sqlite3.connect(self.db_path)
                    conn.execute("""
                        INSERT INTO ghost_trades
                        (signal_date, rsi_at_signal, sma_at_signal, close_at_signal)
                        VALUES (?, ?, ?, ?)
                    """, (today, rsi2, sma200, close))
                    conn.commit()
                    conn.close()
                except Exception as e:
                    self.logger.error(f"Ghost signal DB: {e}")

                msg = (
                    f"👻 GHOST — Entry Signal\n"
                    f"━━━━━━━━━━━━━━━━━━━━\n"
                    f"RSI(2):  {rsi2:.2f}  (< {GHOST_RSI_ENTRY} ✅)\n"
                    f"Close:   {close:.2f}\n"
                    f"SMA200:  {sma200:.2f}  (above ✅)\n"
                    f"━━━━━━━━━━━━━━━━━━━━\n"
                    f"Entering LONG 1 MES at {_next_market_open(today)}'s open.\n"
                    f"Exit: RSI(2) > {GHOST_RSI_EXIT} or {GHOST_MAX_DAYS} days."
                )
                self._alert(msg)
                msgs.append(msg)
                self.logger.info(f"GHOST entry signal: RSI2={rsi2:.2f}")

        return msgs

    # ── SURGE ─────────────────────────────────────────────────────────

    def _process_surge(self, df):
        s = self._surge_indicators(df)
        if not s:
            return []

        today = s['date']
        msgs  = []

        # comp_pending: today is T+1 — resolve the trade
        if (self.surge_state == SS_COMP_PENDING
                and self.surge_comp_date
                and self.surge_comp_date != today):

            ph = self.surge_comp_high
            pl = self.surge_comp_low
            t1_open  = s['open']
            t1_high  = s['high']
            t1_low   = s['low']
            t1_close = s['close']
            h_brk    = t1_high > ph
            l_brk    = t1_low  < pl

            if h_brk or l_brk:
                mid = (ph + pl) / 2.0
                if h_brk and not l_brk:
                    direction = "long"
                    entry = max(t1_open, ph)
                elif l_brk and not h_brk:
                    direction = "short"
                    entry = min(t1_open, pl)
                elif t1_close >= mid:
                    direction = "long"
                    entry = max(t1_open, ph)
                else:
                    direction = "short"
                    entry = min(t1_open, pl)

                net     = ((t1_close - entry) if direction == "long" else (entry - t1_close)) - COST_RT
                pnl_es  = round(net * ES_MULT, 2)
                pnl_mes = round(net * MES_MULT, 2)
                win     = net > 0
                d_icon  = "🟢" if direction == "long" else "🔴"
                r_icon  = "✅ WIN" if win else "❌ LOSS"
                gap     = " (gap through)" if (
                    (direction == "long" and t1_open > ph)
                    or (direction == "short" and t1_open < pl)
                ) else ""

                try:
                    conn = sqlite3.connect(self.db_path)
                    conn.execute("""
                        INSERT INTO surge_signals
                        (comp_date, comp_high, comp_low, atr_ratio, trade_date,
                         direction, entry_price, exit_price, net_pts, pnl_usd_es,
                         pnl_usd_mes, win, outcome)
                        VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                    """, (self.surge_comp_date, ph, pl, self.surge_atr_ratio,
                          today, direction, round(entry, 2), round(t1_close, 2),
                          round(net, 2), pnl_es, pnl_mes, 1 if win else 0,
                          "win" if win else "loss"))
                    conn.commit()
                    conn.close()
                except Exception as e:
                    self.logger.error(f"Surge trade DB: {e}")

                msg = (
                    f"📡 SURGE — Trade Closed\n"
                    f"━━━━━━━━━━━━━━━━━━━━\n"
                    f"{r_icon} | {d_icon} {direction.upper()}{gap}\n"
                    f"Entry:  {entry:.2f}\n"
                    f"Exit:   {t1_close:.2f}  (close)\n"
                    f"Net:    {net:+.2f} pts\n"
                    f"P&L:    ${pnl_mes:+.2f} MES  |  ${pnl_es:+.2f} ES\n"
                    f"━━━━━━━━━━━━━━━━━━━━\n"
                    f"Comp bar: {self.surge_comp_date}  ATR: {self.surge_atr_ratio:.3f}"
                )
                self._alert(msg)
                msgs.append(msg)
                self.logger.info(f"SURGE closed: {direction} {net:+.2f}pts {'WIN' if win else 'LOSS'}")

            else:
                try:
                    conn = sqlite3.connect(self.db_path)
                    conn.execute("""
                        INSERT INTO surge_signals
                        (comp_date, comp_high, comp_low, atr_ratio, trade_date, outcome)
                        VALUES (?, ?, ?, ?, ?, ?)
                    """, (self.surge_comp_date, ph, pl, self.surge_atr_ratio, today, "no_break"))
                    conn.commit()
                    conn.close()
                except Exception as e:
                    self.logger.error(f"Surge no_break DB: {e}")

                msg = (
                    f"📡 SURGE — No Breakout\n"
                    f"━━━━━━━━━━━━━━━━━━━━\n"
                    f"Compression from {self.surge_comp_date} — no boundary crossed today.\n"
                    f"Levels were: H {ph:.2f}  /  L {pl:.2f}\n"
                    f"No trade taken. Surge idle."
                )
                self._alert(msg)
                msgs.append(msg)
                self.logger.info(f"SURGE no_break on {today}")

            self.surge_state     = SS_IDLE
            self.surge_comp_date = None
            self.surge_comp_high = None
            self.surge_comp_low  = None
            self.surge_atr_ratio = None
            self._save_surge()

        # check if today is a compression bar
        if s['is_comp']:
            self.surge_state     = SS_COMP_PENDING
            self.surge_comp_date = today
            self.surge_comp_high = s['high']
            self.surge_comp_low  = s['low']
            self.surge_atr_ratio = s['atr_ratio']
            self._save_surge()

            range_pts = s['high'] - s['low']
            msg = (
                f"📡 SURGE — Compression Detected\n"
                f"━━━━━━━━━━━━━━━━━━━━\n"
                f"Range today:  {range_pts:.1f} pts  ({s['atr_ratio']:.1%} of 20d avg)\n"
                f"ATR ratio:    {s['atr_ratio']:.3f}  (threshold < {SURGE_COMP_THR})\n"
                f"━━━━━━━━━━━━━━━━━━━━\n"
                f"Watch levels tomorrow:\n"
                f"🟢 Long  above: {s['high']:.2f}\n"
                f"🔴 Short below: {s['low']:.2f}\n"
                f"━━━━━━━━━━━━━━━━━━━━\n"
                f"Entering on first boundary break. Exit at tomorrow's close."
            )
            self._alert(msg)
            msgs.append(msg)
            self.logger.info(
                f"SURGE compression: H={s['high']}, L={s['low']}, ratio={s['atr_ratio']:.3f}"
            )

        return msgs

    # ── TELEGRAM ──────────────────────────────────────────────────────

    def _alert(self, message):
        if not self.tg_enabled or not self.tg_token:
            return False
        try:
            import requests
            resp = requests.post(
                f"https://api.telegram.org/bot{self.tg_token}/sendMessage",
                json={"chat_id": self.tg_chat_id, "text": message},
                timeout=10
            )
            return resp.status_code == 200
        except Exception as e:
            self.logger.error(f"Telegram send: {e}")
            return False

    # ── DASHBOARD DATA ────────────────────────────────────────────────

    def get_dashboard_data(self):
        try:
            conn = sqlite3.connect(self.db_path)
            c = conn.cursor()

            c.execute("""
                SELECT COUNT(*), SUM(win), ROUND(SUM(pnl_usd_mes),2)
                FROM ghost_trades WHERE exit_date IS NOT NULL
            """)
            gr = c.fetchone()

            c.execute("""
                SELECT signal_date, entry_price, exit_price, net_pts, pnl_usd_mes, win, exit_reason, days_held
                FROM ghost_trades WHERE exit_date IS NOT NULL
                ORDER BY id DESC LIMIT 5
            """)
            ghost_recent = [
                {"date": r[0], "entry": r[1], "exit": r[2], "net_pts": r[3],
                 "pnl_mes": r[4], "win": bool(r[5]), "reason": r[6], "days": r[7]}
                for r in c.fetchall()
            ]

            c.execute("""
                SELECT COUNT(*), SUM(win), ROUND(SUM(pnl_usd_mes),2)
                FROM surge_signals WHERE outcome IN ('win','loss')
            """)
            sr = c.fetchone()

            c.execute("""
                SELECT comp_date, direction, entry_price, exit_price, net_pts, pnl_usd_mes, win
                FROM surge_signals WHERE outcome IN ('win','loss')
                ORDER BY id DESC LIMIT 5
            """)
            surge_recent = [
                {"date": r[0], "dir": r[1], "entry": r[2], "exit": r[3],
                 "net_pts": r[4], "pnl_mes": r[5], "win": bool(r[6])}
                for r in c.fetchall()
            ]

            conn.close()

            g_total = gr[0] or 0
            g_wins  = int(gr[1] or 0)
            s_total = sr[0] or 0
            s_wins  = int(sr[1] or 0)

            return {
                "ghost": {
                    "state":       self.ghost_state,
                    "signal_date": self.ghost_signal_date,
                    "entry_date":  self.ghost_entry_date,
                    "entry_price": self.ghost_entry_price,
                    "days_held":   self.ghost_days_held,
                    "trades":      g_total,
                    "wins":        g_wins,
                    "win_rate":    round(g_wins / g_total * 100, 1) if g_total else None,
                    "total_pnl":   gr[2],
                    "recent":      ghost_recent,
                },
                "surge": {
                    "state":      self.surge_state,
                    "comp_date":  self.surge_comp_date,
                    "comp_high":  self.surge_comp_high,
                    "comp_low":   self.surge_comp_low,
                    "atr_ratio":  self.surge_atr_ratio,
                    "trades":     s_total,
                    "wins":       s_wins,
                    "win_rate":   round(s_wins / s_total * 100, 1) if s_total else None,
                    "total_pnl":  sr[2],
                    "recent":     surge_recent,
                },
            }
        except Exception as e:
            self.logger.error(f"Strategies dashboard data: {e}")
            return {"ghost": {}, "surge": {}}
