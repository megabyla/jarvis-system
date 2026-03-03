"""
Trade Logger Module
Logs manual ES futures trades via Telegram
Tracks entries, exits, calculates stats
NO AI tokens - pure webhook + Telegram buttons
"""

import os
import sqlite3
import time
import requests
from datetime import datetime, timezone, timedelta
from threading import Thread

ET = timezone(timedelta(hours=-5))


class TradeLogger:
    def __init__(self, config, logger):
        self.config = config
        self.logger = logger
        
        # Config
        tl_config = config.get('trade_logger', {})
        self.enabled = tl_config.get('enabled', True)
        self.db_path = tl_config.get('db_path', '/root/3dpo3/trader_log.db')
        
        # Telegram
        tg_config = config.get('telegram', {})
        self.telegram_token = tg_config.get('bot_token', '')
        self.telegram_chat_id = tg_config.get('chat_id', '')
        self.telegram_enabled = bool(self.telegram_token and self.telegram_chat_id)
        
        # State
        self.current_trade = None  # Active trade being monitored
        self.pending_signal = None  # Signal waiting for confirmation
        
        # Initialize DB
        self._init_db()
        
        self.logger.info("TradeLogger initialized")
    
    def _init_db(self):
        """Create trade log database"""
        conn = sqlite3.connect(self.db_path)
        c = conn.cursor()
        
        c.execute("""
            CREATE TABLE IF NOT EXISTS trades (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                date TEXT,
                direction TEXT,
                entry_price REAL,
                stop_price REAL,
                stop_distance REAL,
                target_1r REAL,
                entry_time TEXT,
                exit_time TEXT,
                outcome TEXT,
                exit_type TEXT,
                pnl_points REAL,
                pnl_dollars REAL,
                strat_sequence TEXT,
                strat_bias TEXT,
                eq_level REAL,
                notes TEXT,
                source TEXT,
                logged_at TEXT
            )
        """)
        
        c.execute("""
            CREATE TABLE IF NOT EXISTS signals (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                date TEXT,
                direction TEXT,
                entry_price REAL,
                stop_price REAL,
                target_1r REAL,
                strat_sequence TEXT,
                strat_bias TEXT,
                eq_level REAL,
                signal_time TEXT,
                confirmed INTEGER DEFAULT 0,
                skipped INTEGER DEFAULT 0,
                trade_id INTEGER,
                FOREIGN KEY (trade_id) REFERENCES trades(id)
            )
        """)
        
        conn.commit()
        conn.close()
        self.logger.info(f"Trade log DB ready: {self.db_path}")
    
    def _send_telegram(self, text, buttons=None):
        """Send Telegram message with inline buttons"""
        if not self.telegram_enabled:
            self.logger.warning("Telegram not configured")
            return False
        
        url = f"https://api.telegram.org/bot{self.telegram_token}/sendMessage"
        payload = {
            'chat_id': self.telegram_chat_id,
            'text': text,
            'parse_mode': 'HTML'
        }
        
        if buttons:
            # Inline keyboard
            keyboard = {'inline_keyboard': [buttons]}
            payload['reply_markup'] = keyboard
        
        try:
            resp = requests.post(url, json=payload, timeout=5)
            return resp.status_code == 200
        except Exception as e:
            self.logger.error(f"Telegram send failed: {e}")
            return False
    
    def handle_webhook(self, data):
        """
        Handle incoming TradingView webhook
        Expected format: {"dir":"LONG","entry":6875.50,"stop":6866.75,"target":6884.25}
        """
        try:
            direction = data.get('dir', '').upper()
            entry = float(data.get('entry', 0))
            stop = float(data.get('stop', 0))
            target = float(data.get('target', 0))
            
            if not all([direction, entry, stop, target]):
                self.logger.error(f"Invalid webhook data: {data}")
                return False
            
            # Calculate stop distance
            if direction == 'LONG':
                stop_dist = entry - stop
            else:
                stop_dist = stop - entry
            
            # Store signal
            signal = {
                'direction': direction,
                'entry': entry,
                'stop': stop,
                'stop_distance': stop_dist,
                'target_1r': target,
                'signal_time': datetime.now(ET).isoformat(),
                'sequence': data.get('sequence', 'unknown'),
                'bias': data.get('bias', 'unknown'),
                'eq': data.get('eq', 0)
            }
            
            # Log to DB
            conn = sqlite3.connect(self.db_path)
            c = conn.cursor()
            c.execute("""
                INSERT INTO signals 
                (date, direction, entry_price, stop_price, target_1r, 
                 strat_sequence, strat_bias, eq_level, signal_time)
                VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)
            """, (
                datetime.now(ET).date().isoformat(),
                signal['direction'],
                signal['entry'],
                signal['stop'],
                signal['target_1r'],
                signal['sequence'],
                signal['bias'],
                signal['eq'],
                signal['signal_time']
            ))
            signal_id = c.lastrowid
            conn.commit()
            conn.close()
            
            # Send Telegram confirmation
            icon = "🟢" if direction == "LONG" else "🔴"
            text = f"""
{icon} <b>EQ REJECTION {direction}</b>
━━━━━━━━━━━━━━━━━━
💰 Entry: <b>{entry:.2f}</b>
🛑 Stop: {stop:.2f} ({stop_dist:.1f} pts)
🎯 Target 1R: {target:.2f}

Did you take this trade?
"""
            
            buttons = [
                {'text': '✅ YES - TAKE TRADE', 'callback_data': f'confirm_{signal_id}'},
                {'text': '❌ SKIP', 'callback_data': f'skip_{signal_id}'}
            ]
            
            self.pending_signal = signal
            self.pending_signal['id'] = signal_id
            
            self._send_telegram(text, buttons)
            self.logger.info(f"Signal sent: {direction} @ {entry:.2f}")
            return True
            
        except Exception as e:
            self.logger.error(f"Webhook handler error: {e}")
            return False
    
    def confirm_trade(self, signal_id):
        """User confirmed they took the trade"""
        try:
            conn = sqlite3.connect(self.db_path)
            c = conn.cursor()
            
            # Get signal
            c.execute("SELECT * FROM signals WHERE id = ?", (signal_id,))
            row = c.fetchone()
            if not row:
                return False
            
            # Create trade entry
            c.execute("""
                INSERT INTO trades
                (date, direction, entry_price, stop_price, stop_distance, 
                 target_1r, entry_time, outcome, source, logged_at,
                 strat_sequence, strat_bias, eq_level)
                VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
            """, (
                row[1],  # date
                row[2],  # direction
                row[3],  # entry_price
                row[4],  # stop_price
                row[3] - row[4] if row[2] == 'LONG' else row[4] - row[3],  # stop_distance
                row[5],  # target_1r
                row[9],  # signal_time as entry_time
                'OPEN',  # outcome
                'webhook',  # source
                datetime.now(ET).isoformat(),  # logged_at
                row[6],  # strat_sequence
                row[7],  # strat_bias
                row[8]   # eq_level
            ))
            
            trade_id = c.lastrowid
            
            # Update signal
            c.execute("""
                UPDATE signals SET confirmed = 1, trade_id = ?
                WHERE id = ?
            """, (trade_id, signal_id))
            
            conn.commit()
            conn.close()
            
            # Store as current trade for monitoring
            self.current_trade = {
                'id': trade_id,
                'direction': row[2],
                'entry': row[3],
                'stop': row[4],
                'target': row[5]
            }
            
            self._send_telegram(
                f"✅ <b>Trade logged!</b>\n\n"
                f"Monitoring {row[2]} @ {row[3]:.2f}\n"
                f"I'll check for exit every minute."
            )
            
            self.logger.info(f"Trade confirmed: {row[2]} @ {row[3]:.2f}")
            return True
            
        except Exception as e:
            self.logger.error(f"Confirm trade error: {e}")
            return False
    
    def skip_trade(self, signal_id):
        """User skipped this trade"""
        try:
            conn = sqlite3.connect(self.db_path)
            c = conn.cursor()
            c.execute("UPDATE signals SET skipped = 1 WHERE id = ?", (signal_id,))
            conn.commit()
            conn.close()
            
            self._send_telegram("⏭️ Trade skipped")
            self.logger.info(f"Signal {signal_id} skipped")
            return True
        except Exception as e:
            self.logger.error(f"Skip trade error: {e}")
            return False
    
    def close_trade(self, outcome, exit_type='manual'):
        """Close current trade with outcome"""
        if not self.current_trade:
            return False
        
        try:
            trade_id = self.current_trade['id']
            direction = self.current_trade['direction']
            entry = self.current_trade['entry']
            stop = self.current_trade['stop']
            target = self.current_trade['target']
            
            # Calculate P&L
            if outcome == 'WIN':
                pnl_points = target - entry if direction == 'LONG' else entry - target
                exit_price = target
            elif outcome == 'LOSS':
                pnl_points = -(entry - stop) if direction == 'LONG' else -(stop - entry)
                exit_price = stop
            else:  # Manual exit - ask for price
                # For now, assume breakeven
                pnl_points = 0
                exit_price = entry
            
            pnl_dollars = pnl_points * 50  # ES = $50/point
            
            # Update trade
            conn = sqlite3.connect(self.db_path)
            c = conn.cursor()
            c.execute("""
                UPDATE trades
                SET outcome = ?, exit_type = ?, exit_time = ?,
                    pnl_points = ?, pnl_dollars = ?
                WHERE id = ?
            """, (
                outcome,
                exit_type,
                datetime.now(ET).isoformat(),
                pnl_points,
                pnl_dollars,
                trade_id
            ))
            conn.commit()
            conn.close()
            
            # Send confirmation
            icon = "✅" if outcome == 'WIN' else "❌" if outcome == 'LOSS' else "📊"
            self._send_telegram(
                f"{icon} <b>Trade closed: {outcome}</b>\n\n"
                f"{direction} @ {entry:.2f} → {exit_price:.2f}\n"
                f"P&L: {pnl_points:+.1f} pts (${pnl_dollars:+.0f})"
            )
            
            self.current_trade = None
            self.logger.info(f"Trade closed: {outcome} {pnl_points:+.1f}pts")
            return True
            
        except Exception as e:
            self.logger.error(f"Close trade error: {e}")
            return False
    
    def manual_entry(self, direction, entry, stop_distance):
        """
        Manually log a trade via Telegram command
        /trade LONG 6875.50 8.5
        """
        try:
            direction = direction.upper()
            entry = float(entry)
            stop_dist = float(stop_distance)
            
            # Calculate stop and target
            if direction == 'LONG':
                stop = entry - stop_dist
                target = entry + stop_dist  # 1R
            else:
                stop = entry + stop_dist
                target = entry - stop_dist
            
            # Create trade
            conn = sqlite3.connect(self.db_path)
            c = conn.cursor()
            c.execute("""
                INSERT INTO trades
                (date, direction, entry_price, stop_price, stop_distance,
                 target_1r, entry_time, outcome, source, logged_at)
                VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
            """, (
                datetime.now(ET).date().isoformat(),
                direction,
                entry,
                stop,
                stop_dist,
                target,
                datetime.now(ET).isoformat(),
                'OPEN',
                'manual',
                datetime.now(ET).isoformat()
            ))
            trade_id = c.lastrowid
            conn.commit()
            conn.close()
            
            # Store as current trade
            self.current_trade = {
                'id': trade_id,
                'direction': direction,
                'entry': entry,
                'stop': stop,
                'target': target
            }
            
            # Send confirmation with outcome buttons
            icon = "🟢" if direction == "LONG" else "🔴"
            text = f"""
{icon} <b>Trade logged: {direction}</b>
━━━━━━━━━━━━━━━━━━
💰 Entry: <b>{entry:.2f}</b>
🛑 Stop: {stop:.2f} ({stop_dist:.1f} pts)
🎯 Target: {target:.2f}

How did it close?
"""
            
            buttons = [
                {'text': '🎯 HIT TARGET', 'callback_data': f'win_{trade_id}'},
                {'text': '🛑 STOPPED OUT', 'callback_data': f'loss_{trade_id}'},
                {'text': '📊 MANUAL EXIT', 'callback_data': f'manual_{trade_id}'}
            ]
            
            self._send_telegram(text, buttons)
            self.logger.info(f"Manual trade: {direction} @ {entry:.2f}")
            return True
            
        except Exception as e:
            self.logger.error(f"Manual entry error: {e}")
            return False
    
    def get_stats(self, period='today'):
        """Calculate trading stats"""
        try:
            conn = sqlite3.connect(self.db_path)
            c = conn.cursor()
            
            if period == 'today':
                date_filter = datetime.now(ET).date().isoformat()
                c.execute("""
                    SELECT COUNT(*), SUM(CASE WHEN outcome = 'WIN' THEN 1 ELSE 0 END),
                           SUM(pnl_dollars), AVG(stop_distance)
                    FROM trades
                    WHERE date = ? AND outcome IN ('WIN', 'LOSS')
                """, (date_filter,))
            elif period == 'week':
                # Last 7 days
                c.execute("""
                    SELECT COUNT(*), SUM(CASE WHEN outcome = 'WIN' THEN 1 ELSE 0 END),
                           SUM(pnl_dollars), AVG(stop_distance)
                    FROM trades
                    WHERE date >= date('now', '-7 days') AND outcome IN ('WIN', 'LOSS')
                """)
            else:  # all time
                c.execute("""
                    SELECT COUNT(*), SUM(CASE WHEN outcome = 'WIN' THEN 1 ELSE 0 END),
                           SUM(pnl_dollars), AVG(stop_distance)
                    FROM trades
                    WHERE outcome IN ('WIN', 'LOSS')
                """)
            
            row = c.fetchone()
            conn.close()
            
            total = row[0] or 0
            wins = row[1] or 0
            pnl = row[2] or 0
            avg_stop = row[3] or 0
            
            win_rate = (wins / total * 100) if total > 0 else 0
            
            return {
                'total': total,
                'wins': wins,
                'losses': total - wins,
                'win_rate': win_rate,
                'pnl': pnl,
                'avg_stop': avg_stop
            }
            
        except Exception as e:
            self.logger.error(f"Get stats error: {e}")
            return {}
    
    def get_dashboard_data(self):
        """Data for JARVIS dashboard"""
        today_stats = self.get_stats('today')
        week_stats = self.get_stats('week')
        
        return {
            'today': today_stats,
            'week': week_stats,
            'current_trade': self.current_trade,
            'enabled': self.enabled
        }
