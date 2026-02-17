"""
Jarvis Futures Module
Monitors ES futures for Strat sequences, EQ Rejection setups,
and provides pre-market bias during NY session (9:30-11:00 AM ET).

Integrates with existing Jarvis architecture:
  - Pre-market brief at 9:00 AM ET
  - Live monitoring 9:30-11:00 AM ET (checks every 5m candle)
  - Post-session logging at 11:15 AM ET
  - Weekly summary stats
"""

import os
import json
import time
import sqlite3
import logging
from datetime import datetime, timezone, timedelta
from pathlib import Path

ET = timezone(timedelta(hours=-5))


class FuturesMonitor:
    def __init__(self, config, logger, analyst=None):
        self.config = config
        self.logger = logger
        self.analyst = analyst  # Optional: for Haiku analysis

        # Futures-specific config
        ft_config = config.get("futures", {})
        self.enabled = ft_config.get("enabled", True)
        self.instrument = ft_config.get("instrument", "ES")
        self.data_dir = ft_config.get("data_dir", "/root/3dpo3/futures_data")
        self.db_path = ft_config.get("db_path", "/root/3dpo3/futures_trades.db")
        self.eq_buffer = ft_config.get("eq_buffer", 2.0)
        self.min_stop = ft_config.get("min_stop", 2.0)
        self.max_stop = ft_config.get("max_stop", 15.0)
        self.stop_buffer = ft_config.get("stop_buffer", 0.5)

        # Telegram config (reuse from main config)
        self.telegram_enabled = config.get("telegram", {}).get("enabled", False)
        self.telegram_token = config.get("telegram", {}).get("bot_token", "")
        self.telegram_chat_id = config.get("telegram", {}).get("chat_id", "")

        # State
        self.today_bias = None
        self.today_sequence = None
        self.today_levels = None
        self.session_active = False
        self.signal_fired_today = False
        self.last_premarket_date = None
        self.last_postsession_date = None

        # Initialize database
        self._init_db()

        self.logger.info(f"FuturesMonitor initialized: {self.instrument}")

    # ================================================================
    # DATABASE
    # ================================================================

    def _init_db(self):
        """Create futures tracking database."""
        try:
            conn = sqlite3.connect(self.db_path)
            c = conn.cursor()

            c.execute("""
                CREATE TABLE IF NOT EXISTS strat_log (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    date TEXT UNIQUE,
                    strat_label TEXT,
                    sequence TEXT,
                    bias TEXT,
                    bias_pct INTEGER,
                    pdh REAL,
                    pdl REAL,
                    pd_eq REAL,
                    pd_range REAL,
                    session_open REAL,
                    session_close REAL,
                    session_direction TEXT,
                    session_range REAL,
                    actual_direction TEXT,
                    bias_correct INTEGER
                )
            """)

            c.execute("""
                CREATE TABLE IF NOT EXISTS eq_rejections (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    date TEXT,
                    direction TEXT,
                    entry_price REAL,
                    stop_price REAL,
                    stop_distance REAL,
                    eq_level REAL,
                    sweep_wick REAL,
                    entry_time TEXT,
                    strat_sequence TEXT,
                    strat_bias TEXT,
                    four_h_trend TEXT,
                    target_1r REAL,
                    target_2r REAL,
                    target_3r REAL,
                    hit_1r INTEGER,
                    hit_2r INTEGER,
                    hit_3r INTEGER,
                    stopped_out INTEGER,
                    outcome TEXT,
                    notes TEXT
                )
            """)

            c.execute("""
                CREATE TABLE IF NOT EXISTS session_log (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    date TEXT UNIQUE,
                    premarket_sent INTEGER DEFAULT 0,
                    setups_detected INTEGER DEFAULT 0,
                    signals_fired INTEGER DEFAULT 0,
                    postsession_logged INTEGER DEFAULT 0,
                    notes TEXT
                )
            """)

            conn.commit()
            conn.close()
            self.logger.info("Futures database initialized")
        except Exception as e:
            self.logger.error(f"Futures DB init failed: {e}")

    # ================================================================
    # DATA LOADING (from yfinance CSV files)
    # ================================================================

    def _load_daily_data(self):
        """Load daily candle data from CSV."""
        try:
            import pandas as pd
            filepath = os.path.join(self.data_dir, f"{self.instrument}_daily.csv")
            if not os.path.exists(filepath):
                self.logger.error(f"Daily data not found: {filepath}")
                return None
            df = pd.read_csv(filepath, index_col='Datetime')
            df.index = pd.to_datetime(df.index.astype(str).str.replace(
                r'[-+]\d{2}:\d{2}$', '', regex=True))
            return df
        except Exception as e:
            self.logger.error(f"Failed to load daily data: {e}")
            return None

    def _load_5m_data(self):
        """Load 5-minute candle data from CSV."""
        try:
            import pandas as pd
            filepath = os.path.join(self.data_dir, f"{self.instrument}_5m.csv")
            if not os.path.exists(filepath):
                return None
            df = pd.read_csv(filepath, index_col='Datetime')
            df.index = pd.to_datetime(df.index.astype(str).str.replace(
                r'[-+]\d{2}:\d{2}$', '', regex=True))
            return df
        except Exception as e:
            self.logger.error(f"Failed to load 5m data: {e}")
            return None

    # ================================================================
    # STRAT CLASSIFICATION
    # ================================================================

    def _classify_strat(self, curr_high, curr_low, prev_high, prev_low):
        """Classify a candle using The Strat methodology."""
        broke_high = curr_high > prev_high
        broke_low = curr_low < prev_low

        if broke_high and broke_low:
            return "3"
        elif broke_high:
            return "2U"
        elif broke_low:
            return "2D"
        else:
            return "1"

    def _get_strat_sequence(self, daily_df):
        """Get the current 3-candle Strat sequence and bias."""
        if daily_df is None or len(daily_df) < 4:
            return None, None, 0

        # Classify last 3 candles
        s1 = self._classify_strat(
            daily_df.iloc[-3]['High'], daily_df.iloc[-3]['Low'],
            daily_df.iloc[-4]['High'], daily_df.iloc[-4]['Low']
        )
        s2 = self._classify_strat(
            daily_df.iloc[-2]['High'], daily_df.iloc[-2]['Low'],
            daily_df.iloc[-3]['High'], daily_df.iloc[-3]['Low']
        )
        s3 = self._classify_strat(
            daily_df.iloc[-1]['High'], daily_df.iloc[-1]['Low'],
            daily_df.iloc[-2]['High'], daily_df.iloc[-2]['Low']
        )

        sequence = f"{s1}-{s2}-{s3}"
        bias, pct = self._lookup_bias(sequence)

        return sequence, bias, pct

    def _lookup_bias(self, sequence):
        """Lookup directional bias from backtested patterns."""
        bias_table = {
            # 100% patterns
            "1-2U-2U":  ("BULL", 100),
            "2D-1-2D":  ("BEAR", 100),
            "2D-3-2D":  ("BEAR", 100),
            "1-2U-1":   ("BEAR", 100),
            "1-2D-2U":  ("BULL", 100),
            "2D-3-2U":  ("BULL", 100),
            "3-2D-2U":  ("BULL", 100),
            # 90%+
            "2U-2U-2D": ("BEAR", 93),
            # 80%+
            "2U-2D-2U": ("BULL", 86),
            "2U-1-2D":  ("BEAR", 83),
            "2D-1-2U":  ("BULL", 83),
            "1-3-2U":   ("BULL", 80),
            "3-2U-2D":  ("BEAR", 80),
            "2D-2D-1":  ("BULL", 80),
            # 75%+
            "2U-2U-2U": ("BULL", 77),
            "2D-2D-2D": ("BEAR", 75),
            "2D-2D-2U": ("BULL", 73),
        }
        return bias_table.get(sequence, ("NEUTRAL", 0))

    def _get_key_levels(self, daily_df):
        """Calculate PDH, PDL, EQ from the previous day."""
        if daily_df is None or len(daily_df) < 2:
            return None

        prev = daily_df.iloc[-2]
        pdh = prev['High']
        pdl = prev['Low']
        pd_eq = (pdh + pdl) / 2.0
        pd_range = pdh - pdl

        return {
            'pdh': pdh,
            'pdl': pdl,
            'pd_eq': pd_eq,
            'pd_range': pd_range,
            'premium': pdl + (pd_range * 0.75),
            'discount': pdl + (pd_range * 0.25),
        }

    # ================================================================
    # PRE-MARKET BRIEF (run at 9:00 AM ET)
    # ================================================================

    def run_premarket(self, force=False):
        """Generate and send pre-market brief."""
        now = datetime.now(ET)
        today_str = now.strftime("%Y-%m-%d")

        if self.last_premarket_date == today_str and not force:
            return None  # Already sent today

        daily_df = self._load_daily_data()
        if daily_df is None:
            return None

        sequence, bias, pct = self._get_strat_sequence(daily_df)
        levels = self._get_key_levels(daily_df)

        if not sequence or not levels:
            self.logger.warning("Could not calculate Strat sequence or levels")
            return None

        self.today_sequence = sequence
        self.today_bias = bias
        self.today_levels = levels
        self.signal_fired_today = False

        # Log to database
        try:
            conn = sqlite3.connect(self.db_path)
            c = conn.cursor()
            c.execute("""
                INSERT OR REPLACE INTO strat_log
                (date, sequence, bias, bias_pct, pdh, pdl, pd_eq, pd_range)
                VALUES (?, ?, ?, ?, ?, ?, ?, ?)
            """, (today_str, sequence, bias, pct,
                  levels['pdh'], levels['pdl'], levels['pd_eq'], levels['pd_range']))

            c.execute("""
                INSERT OR REPLACE INTO session_log (date, premarket_sent)
                VALUES (?, 1)
            """, (today_str,))

            conn.commit()
            conn.close()
        except Exception as e:
            self.logger.error(f"DB log failed: {e}")

        self.last_premarket_date = today_str

        # Build brief
        bias_icon = "🟢" if bias == "BULL" else "🔴" if bias == "BEAR" else "⚪"
        direction = "LONG" if bias == "BULL" else "SHORT" if bias == "BEAR" else "EITHER"

        brief = {
            "title": f"PRE-MARKET BRIEF — {self.instrument}",
            "sequence": sequence,
            "bias": bias,
            "bias_pct": pct,
            "levels": levels,
            "message": (
                f"📊 PRE-MARKET BRIEF — {self.instrument}\n"
                f"━━━━━━━━━━━━━━━━━━━━\n"
                f"Sequence: {sequence}\n"
                f"{bias_icon} Bias: {bias} {pct}%\n"
                f"━━━━━━━━━━━━━━━━━━━━\n"
                f"PDH: {levels['pdh']:.2f}\n"
                f"EQ:  {levels['pd_eq']:.2f}\n"
                f"PDL: {levels['pdl']:.2f}\n"
                f"Range: {levels['pd_range']:.1f} pts\n"
                f"━━━━━━━━━━━━━━━━━━━━\n"
                f"{'✅ Look ' + direction + ' only' if bias != 'NEUTRAL' else '⚪ No strong bias — be selective'}"
            )
        }

        self.logger.info(f"Pre-market: {sequence} → {bias} {pct}%")

        # Send Telegram if enabled
        if self.telegram_enabled:
            self._send_telegram(brief["message"])

        return brief

    # ================================================================
    # LIVE SESSION MONITOR (9:30-11:00 AM, every 5m candle)
    # ================================================================

    def check_eq_rejection(self):
        """
        Check latest 5m candles for EQ Rejection setup.
        Call this every 5 minutes during session.
        Returns signal dict if triggered, None otherwise.
        """
        if not self.today_levels or self.signal_fired_today:
            return None

        now = datetime.now(ET)

        # Only check during NY session
        if now.hour < 9 or (now.hour == 9 and now.minute < 30):
            return None
        if now.hour >= 11:
            return None

        pd_eq = self.today_levels['pd_eq']
        eq_upper = pd_eq + self.eq_buffer
        eq_lower = pd_eq - self.eq_buffer

        df_5m = self._load_5m_data()
        if df_5m is None or len(df_5m) < 5:
            return None

        today_str = now.strftime("%Y-%m-%d")
        from datetime import time as dt_time

        # Get today's session candles
        mask = (
            (df_5m.index.date == now.date()) &
            (df_5m.index.time >= dt_time(9, 30)) &
            (df_5m.index.time <= dt_time(11, 0))
        )
        session = df_5m[mask]

        if len(session) < 3:
            return None

        # Check last 2 confirmed candles
        sweep_candle = session.iloc[-2]
        confirm_candle = session.iloc[-1]

        signal = None

        # --- EQ REJECTION LONG ---
        if (sweep_candle['Low'] < eq_lower and
            sweep_candle['Close'] > pd_eq and
            confirm_candle['Close'] > confirm_candle['Open'] and
            confirm_candle['Close'] > pd_eq):

            entry = confirm_candle['Close']
            stop = sweep_candle['Low'] - self.stop_buffer
            stop_dist = entry - stop

            if self.min_stop <= stop_dist <= self.max_stop:
                signal = self._build_signal(
                    "LONG", entry, stop, stop_dist, pd_eq,
                    sweep_candle['Low'], str(confirm_candle.name.time()),
                    today_str
                )

        # --- EQ REJECTION SHORT ---
        if signal is None:
            if (sweep_candle['High'] > eq_upper and
                sweep_candle['Close'] < pd_eq and
                confirm_candle['Close'] < confirm_candle['Open'] and
                confirm_candle['Close'] < pd_eq):

                entry = confirm_candle['Close']
                stop = sweep_candle['High'] + self.stop_buffer
                stop_dist = stop - entry

                if self.min_stop <= stop_dist <= self.max_stop:
                    signal = self._build_signal(
                        "SHORT", entry, stop, stop_dist, pd_eq,
                        sweep_candle['High'], str(confirm_candle.name.time()),
                        today_str
                    )

        if signal:
            self.signal_fired_today = True
            self._log_signal(signal)

            # Send Telegram alert
            if self.telegram_enabled:
                self._send_telegram(signal["message"])

            self.logger.info(f"EQ Rejection {signal['direction']} triggered @ {signal['entry']:.2f}")

        return signal

    def _build_signal(self, direction, entry, stop, stop_dist, eq,
                      sweep_price, entry_time, date_str):
        """Build a signal dict with all trade info."""
        if direction == "LONG":
            t1r = entry + stop_dist
            t15r = entry + (stop_dist * 1.5)
            t2r = entry + (stop_dist * 2.0)
            t3r = entry + (stop_dist * 3.0)
            icon = "🟢"
        else:
            t1r = entry - stop_dist
            t15r = entry - (stop_dist * 1.5)
            t2r = entry - (stop_dist * 2.0)
            t3r = entry - (stop_dist * 3.0)
            icon = "🔴"

        bias_confirm = ""
        if self.today_bias:
            if (direction == "LONG" and self.today_bias == "BULL") or \
               (direction == "SHORT" and self.today_bias == "BEAR"):
                bias_confirm = "✅ Strat bias CONFIRMS"
            elif self.today_bias == "NEUTRAL":
                bias_confirm = "⚪ No Strat bias"
            else:
                bias_confirm = "⚠️ Strat bias CONFLICTS"

        message = (
            f"{icon} EQ REJECTION {direction} — {self.instrument}\n"
            f"━━━━━━━━━━━━━━━━━━━━\n"
            f"Entry: {entry:.2f}\n"
            f"Stop:  {stop:.2f} ({stop_dist:.1f} pts)\n"
            f"━━━━━━━━━━━━━━━━━━━━\n"
            f"1R:  {t1r:.2f}\n"
            f"1.5R: {t15r:.2f}\n"
            f"2R:  {t2r:.2f}\n"
            f"3R:  {t3r:.2f}\n"
            f"━━━━━━━━━━━━━━━━━━━━\n"
            f"EQ Level: {eq:.2f}\n"
            f"Strat: {self.today_sequence}\n"
            f"{bias_confirm}\n"
            f"Time: {entry_time}"
        )

        return {
            "date": date_str,
            "direction": direction,
            "entry": entry,
            "stop": stop,
            "stop_distance": stop_dist,
            "eq_level": eq,
            "sweep_price": sweep_price,
            "entry_time": entry_time,
            "t1r": t1r, "t15r": t15r, "t2r": t2r, "t3r": t3r,
            "strat_sequence": self.today_sequence,
            "strat_bias": self.today_bias,
            "bias_confirms": bias_confirm,
            "message": message,
        }

    def _log_signal(self, signal):
        """Log EQ Rejection signal to database."""
        try:
            conn = sqlite3.connect(self.db_path)
            c = conn.cursor()
            c.execute("""
                INSERT INTO eq_rejections
                (date, direction, entry_price, stop_price, stop_distance,
                 eq_level, sweep_wick, entry_time, strat_sequence, strat_bias,
                 target_1r, target_2r, target_3r)
                VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
            """, (
                signal['date'], signal['direction'], signal['entry'],
                signal['stop'], signal['stop_distance'], signal['eq_level'],
                signal['sweep_price'], signal['entry_time'],
                signal['strat_sequence'], signal['strat_bias'],
                signal['t1r'], signal['t2r'], signal['t3r']
            ))

            # Update session log
            c.execute("""
                UPDATE session_log SET signals_fired = signals_fired + 1
                WHERE date = ?
            """, (signal['date'],))

            conn.commit()
            conn.close()
        except Exception as e:
            self.logger.error(f"Signal log failed: {e}")

    # ================================================================
    # POST-SESSION (run at 11:15 AM ET)
    # ================================================================

    def run_postsession(self):
        """Log session results after NY session ends."""
        now = datetime.now(ET)
        today_str = now.strftime("%Y-%m-%d")

        if self.last_postsession_date == today_str:
            return None

        if not self.today_levels:
            return None

        self.last_postsession_date = today_str

        # TODO: Once live trading is integrated, check if targets were hit
        # For now, log that session is complete

        summary = {
            "date": today_str,
            "sequence": self.today_sequence,
            "bias": self.today_bias,
            "signal_fired": self.signal_fired_today,
        }

        try:
            conn = sqlite3.connect(self.db_path)
            c = conn.cursor()
            c.execute("""
                UPDATE session_log SET postsession_logged = 1
                WHERE date = ?
            """, (today_str,))
            conn.commit()
            conn.close()
        except Exception as e:
            self.logger.error(f"Post-session log failed: {e}")

        self.logger.info(f"Post-session: {today_str} | {self.today_sequence} | Signal: {self.signal_fired_today}")
        return summary

    # ================================================================
    # STATS & REPORTING
    # ================================================================

    def get_stats(self):
        """Get running stats for dashboard."""
        try:
            conn = sqlite3.connect(self.db_path)
            c = conn.cursor()

            # Strat bias accuracy
            c.execute("""
                SELECT COUNT(*) as total,
                       SUM(CASE WHEN bias_correct = 1 THEN 1 ELSE 0 END) as correct
                FROM strat_log
                WHERE bias != 'NEUTRAL' AND bias_correct IS NOT NULL
            """)
            row = c.fetchone()
            bias_total = row[0] or 0
            bias_correct = row[1] or 0
            bias_accuracy = (bias_correct / bias_total * 100) if bias_total > 0 else 0

            # EQ Rejection stats
            c.execute("""
                SELECT COUNT(*) as total,
                       SUM(CASE WHEN hit_1r = 1 THEN 1 ELSE 0 END) as wins_1r,
                       SUM(CASE WHEN hit_2r = 1 THEN 1 ELSE 0 END) as wins_2r,
                       SUM(CASE WHEN hit_3r = 1 THEN 1 ELSE 0 END) as wins_3r,
                       SUM(CASE WHEN stopped_out = 1 THEN 1 ELSE 0 END) as stopped
                FROM eq_rejections
                WHERE outcome IS NOT NULL
            """)
            eq_row = c.fetchone()

            # Recent signals
            c.execute("""
                SELECT date, direction, entry_price, stop_distance,
                       strat_sequence, outcome
                FROM eq_rejections
                ORDER BY id DESC LIMIT 10
            """)
            recent = [
                {
                    "date": r[0], "direction": r[1], "entry": r[2],
                    "stop_dist": r[3], "sequence": r[4], "outcome": r[5]
                }
                for r in c.fetchall()
            ]

            # Total sessions logged
            c.execute("SELECT COUNT(*) FROM session_log")
            total_sessions = c.fetchone()[0] or 0

            conn.close()

            return {
                "instrument": self.instrument,
                "current_sequence": self.today_sequence,
                "current_bias": self.today_bias,
                "current_levels": self.today_levels,
                "bias_accuracy": {
                    "total": bias_total,
                    "correct": bias_correct,
                    "pct": bias_accuracy
                },
                "eq_rejections": {
                    "total": eq_row[0] or 0,
                    "wins_1r": eq_row[1] or 0,
                    "wins_2r": eq_row[2] or 0,
                    "wins_3r": eq_row[3] or 0,
                    "stopped": eq_row[4] or 0,
                },
                "recent_signals": recent,
                "total_sessions": total_sessions,
                "signal_today": self.signal_fired_today,
            }

        except Exception as e:
            self.logger.error(f"Stats error: {e}")
            return {"error": str(e)}

    def get_weekly_summary(self):
        """Generate weekly summary for Telegram/dashboard."""
        try:
            conn = sqlite3.connect(self.db_path)
            c = conn.cursor()

            c.execute("""
                SELECT date, sequence, bias, bias_pct, bias_correct
                FROM strat_log
                WHERE date >= date('now', '-7 days')
                ORDER BY date
            """)
            week = c.fetchall()
            conn.close()

            if not week:
                return None

            total = len(week)
            biased = [w for w in week if w[2] != 'NEUTRAL']
            correct = [w for w in biased if w[4] == 1]

            summary = (
                f"📊 WEEKLY STRAT SUMMARY — {self.instrument}\n"
                f"━━━━━━━━━━━━━━━━━━━━\n"
                f"Sessions: {total}\n"
                f"Biased days: {len(biased)}/{total}\n"
                f"Bias accuracy: {len(correct)}/{len(biased)} "
                f"({len(correct)/len(biased)*100:.0f}%)\n" if biased else ""
                f"━━━━━━━━━━━━━━━━━━━━\n"
            )

            for day in week:
                icon = "✅" if day[4] == 1 else "❌" if day[4] == 0 else "⚪"
                summary += f"  {day[0]}: {day[1]} → {day[2]} {day[3]}% {icon}\n"

            return summary

        except Exception as e:
            self.logger.error(f"Weekly summary error: {e}")
            return None

    # ================================================================
    # TELEGRAM
    # ================================================================

    def _send_telegram(self, message):
        """Send a Telegram message."""
        if not self.telegram_enabled or not self.telegram_token:
            return False

        try:
            import requests
            url = f"https://api.telegram.org/bot{self.telegram_token}/sendMessage"
            resp = requests.post(url, json={
                "chat_id": self.telegram_chat_id,
                "text": message,
                "parse_mode": "HTML"
            }, timeout=10)
            return resp.status_code == 200
        except Exception as e:
            self.logger.error(f"Telegram send failed: {e}")
            return False

    # ================================================================
    # DASHBOARD DATA
    # ================================================================

    def get_dashboard_data(self):
        """Return data for the Jarvis web dashboard."""
        # Extract bias confidence from sequence lookup
        bias_conf = 0
        if self.today_sequence:
            _, conf = self._lookup_bias(self.today_sequence)
            bias_conf = conf
        
        return {
            "enabled": self.enabled,
            "instrument": self.instrument,
            "strat_sequence": self.today_sequence,  # Match frontend
            "sequence": self.today_sequence,  # Keep for compatibility
            "bias": self.today_bias,
            "bias_confidence": bias_conf,
            "pdh": self.today_levels.get('pdh') if self.today_levels else None,
            "pdl": self.today_levels.get('pdl') if self.today_levels else None,
            "eq": self.today_levels.get('pd_eq') if self.today_levels else None,
            "levels": self.today_levels,
            "signal_today": self.signal_fired_today,
            "signals_today": 1 if self.signal_fired_today else 0,
            "stats": self.get_stats(),
            "last_update": "Pre-market" if self.today_sequence else "N/A"
        }
