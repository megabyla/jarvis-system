"""
Telegram Listener — Jarvis incoming command handler
====================================================
Polls the Telegram Bot API for incoming messages and routes
them to the appropriate Jarvis action, sending responses back.

Security: only responds to messages from the configured chat_id.

Supported commands:
  /bias  or  /premarket  — today's Strat sequence, bias, and key levels (refreshes data)
  /levels                — PDH / EQ / PDL for today (no bias lookup)
  /status                — bot health summary
  /weekly                — weekly Strat bias accuracy summary
  /stats                 — EQ Rejection trade stats
  /help                  — list all commands

Anything else is forwarded to Haiku (if budget allows).
"""

import time
import logging
import threading

import requests


POLL_INTERVAL  = 2      # seconds between getUpdates calls
REQUEST_TIMEOUT = 8     # seconds for each API call

HELP_TEXT = (
    "📋 *Jarvis Commands*\n"
    "━━━━━━━━━━━━━━━━━━━━\n"
    "/bias  or  /premarket — today's bias + levels\n"
    "/levels — PDH / EQ / PDL only\n"
    "/status — bot health\n"
    "/weekly — weekly bias accuracy\n"
    "/stats  — EQ Rejection trade stats\n"
    "━━━━━━━━━━━━━━━━━━━━\n"
    "*Quant strategies:*\n"
    "/ghost — Ghost (RSI2 bull-gate) current state\n"
    "/surge — Surge (compression breakout) current state\n"
    "━━━━━━━━━━━━━━━━━━━━\n"
    "*Manual trade logging:*\n"
    "/log LONG 6875.50 8.5 — log entry (direction, price, stop dist)\n"
    "/win   — close current trade as winner\n"
    "/loss  — close current trade as stopped out\n"
    "/be    — close current trade at breakeven\n"
    "━━━━━━━━━━━━━━━━━━━━\n"
    "/help  — this list\n"
    "Anything else → ask Haiku ✨"
)


class TelegramListener:
    def __init__(self, jarvis, config, logger):
        self.jarvis   = jarvis
        self.logger   = logger
        self.token    = config.get("telegram", {}).get("bot_token", "")
        self.chat_id  = str(config.get("telegram", {}).get("chat_id", ""))
        self._offset  = 0
        self._running = False
        self._thread  = None

        if not self.token:
            self.logger.warning("TelegramListener: no bot_token — listener disabled")

    # ─── PUBLIC ───────────────────────────────────────────────────────────────

    def start(self):
        if not self.token:
            return
        self._running = True
        self._thread  = threading.Thread(target=self._run_loop, daemon=True, name="TelegramListener")
        self._thread.start()
        self.logger.info("TelegramListener started — polling for commands")

    def stop(self):
        self._running = False

    # ─── POLLING ──────────────────────────────────────────────────────────────

    def _run_loop(self):
        while self._running:
            try:
                updates = self._get_updates()
                for update in updates:
                    self._process_update(update)
            except Exception as e:
                self.logger.error(f"TelegramListener error: {e}")
            time.sleep(POLL_INTERVAL)

    def _get_updates(self):
        url = f"https://api.telegram.org/bot{self.token}/getUpdates"
        try:
            resp = requests.get(url, params={"offset": self._offset, "timeout": 5},
                                timeout=REQUEST_TIMEOUT)
            if resp.status_code != 200:
                return []
            data = resp.json()
            updates = data.get("result", [])
            if updates:
                self._offset = updates[-1]["update_id"] + 1
            return updates
        except Exception as e:
            self.logger.debug(f"getUpdates failed: {e}")
            return []

    def _process_update(self, update):
        # Only handle regular text messages (not channel posts, edits, etc.)
        msg = update.get("message")
        if not msg:
            return

        incoming_chat = str(msg.get("chat", {}).get("id", ""))
        text = msg.get("text", "").strip()

        if not text:
            return

        # Security: only respond to the configured chat
        if incoming_chat != self.chat_id:
            self.logger.warning(f"TelegramListener: ignored message from unauthorized chat {incoming_chat}")
            return

        self.logger.info(f"Telegram command received: {text!r}")
        self._route(text)

    # ─── COMMAND ROUTER ───────────────────────────────────────────────────────

    def _route(self, text):
        cmd = text.lower().lstrip("/").strip()

        if cmd in ("bias", "premarket", "futures"):
            self._cmd_bias()
        elif cmd == "levels":
            self._cmd_levels()
        elif cmd in ("status", "health"):
            self._cmd_status()
        elif cmd == "weekly":
            self._cmd_weekly()
        elif cmd in ("stats", "futures stats"):
            self._cmd_stats()
        elif cmd == "ghost":
            self._cmd_ghost()
        elif cmd == "surge":
            self._cmd_surge()
        elif cmd.startswith("log") or cmd.startswith("trade"):
            self._cmd_log_trade(cmd)
        elif cmd == "win":
            self._cmd_close_trade("WIN")
        elif cmd == "loss":
            self._cmd_close_trade("LOSS")
        elif cmd == "be":
            self._cmd_close_trade("MANUAL")
        elif cmd == "help":
            self.send(HELP_TEXT, markdown=True)
        else:
            self._cmd_haiku(text)

    # ─── COMMAND HANDLERS ─────────────────────────────────────────────────────

    def _cmd_bias(self):
        if not self.jarvis.futures:
            self.send("⚠️ Futures module not enabled.")
            return

        # run_premarket refreshes data and sends the brief to Telegram itself.
        brief = self.jarvis.futures.run_premarket(force=True)
        if brief:
            # Already sent by futures._send_telegram() — nothing more to do.
            return

        # Telegram send already happened OR no fresh data; fall back to cached state.
        data = self.jarvis.futures.get_dashboard_data()
        seq  = data.get("strat_sequence") or data.get("sequence", "N/A")
        bias = data.get("bias", "N/A")
        conf = data.get("bias_confidence", 0)
        pdh  = data.get("pdh")
        pdl  = data.get("pdl")
        eq   = data.get("eq")

        bias_icon = "🟢" if bias == "BULL" else "🔴" if bias == "BEAR" else "⚪"
        msg = (
            f"📊 CURRENT STATE — ES\n"
            f"━━━━━━━━━━━━━━━━━━━━\n"
            f"Sequence: {seq}\n"
            f"{bias_icon} Bias: {bias} {conf}%\n"
        )
        if pdh and pdl and eq:
            msg += (
                f"━━━━━━━━━━━━━━━━━━━━\n"
                f"PDH: {pdh:.2f}\n"
                f"EQ:  {eq:.2f}\n"
                f"PDL: {pdl:.2f}\n"
            )
        self.send(msg)

    def _cmd_levels(self):
        if not self.jarvis.futures:
            self.send("⚠️ Futures module not enabled.")
            return

        data   = self.jarvis.futures.get_dashboard_data()
        levels = data.get("levels")
        if not levels:
            self.send("⚠️ No levels available yet — run /bias first.")
            return

        pdh = levels.get("pdh")
        pdl = levels.get("pdl")
        eq  = levels.get("pd_eq")
        rng = levels.get("pd_range")
        prem = levels.get("premium")
        disc = levels.get("discount")

        msg = (
            f"📐 KEY LEVELS — ES\n"
            f"━━━━━━━━━━━━━━━━━━━━\n"
            f"PDH:       {pdh:.2f}\n"
            f"Premium:   {prem:.2f}  (75%)\n"
            f"EQ:        {eq:.2f}  (50%)\n"
            f"Discount:  {disc:.2f}  (25%)\n"
            f"PDL:       {pdl:.2f}\n"
            f"Range:     {rng:.1f} pts\n"
        )
        self.send(msg)

    def _cmd_status(self):
        try:
            state = self.jarvis.get_dashboard_state()
            bots  = state.get("bots", {})
            lines = ["🤖 BOT STATUS\n━━━━━━━━━━━━━━━━━━━━"]
            for name, info in bots.items():
                running = info.get("running", False)
                icon    = "✅" if running else "❌"
                paused  = " (paused)" if info.get("paused") else ""
                lines.append(f"{icon} {name}{paused}")

            # Futures state
            if self.jarvis.futures:
                fdata = self.jarvis.futures.get_dashboard_data()
                seq   = fdata.get("strat_sequence", "N/A")
                bias  = fdata.get("bias", "N/A")
                lines.append(f"━━━━━━━━━━━━━━━━━━━━")
                lines.append(f"ES: {seq} → {bias}")

            # Ghost + Surge state
            if getattr(self.jarvis, 'strategies', None):
                sd = self.jarvis.strategies.get_dashboard_data()
                g_state = sd.get("ghost", {}).get("state", "idle")
                s_state = sd.get("surge", {}).get("state", "idle")
                g_icon = "🟣" if g_state == "in_trade" else "⬜"
                s_icon = "🟦" if s_state == "comp_pending" else "⬜"
                lines.append(f"━━━━━━━━━━━━━━━━━━━━")
                lines.append(f"{g_icon} Ghost: {g_state}")
                lines.append(f"{s_icon} Surge: {s_state}")

            self.send("\n".join(lines))
        except Exception as e:
            self.send(f"⚠️ Status error: {e}")

    def _cmd_weekly(self):
        if not self.jarvis.futures:
            self.send("⚠️ Futures module not enabled.")
            return
        summary = self.jarvis.futures.get_weekly_summary()
        if summary:
            self.send(summary)
        else:
            self.send("📊 No weekly data yet.")

    def _cmd_stats(self):
        if not self.jarvis.futures:
            self.send("⚠️ Futures module not enabled.")
            return
        try:
            s  = self.jarvis.futures.get_stats()
            eq = s.get("eq_rejections", {})
            ba = s.get("bias_accuracy", {})

            total   = eq.get("total", 0)
            wins_1r = eq.get("wins_1r", 0)
            wins_2r = eq.get("wins_2r", 0)
            stopped = eq.get("stopped", 0)
            wr_1r   = (wins_1r / total * 100) if total > 0 else 0

            msg = (
                f"📈 EQ REJECTION STATS\n"
                f"━━━━━━━━━━━━━━━━━━━━\n"
                f"Total signals:  {total}\n"
                f"Hit 1R:         {wins_1r} ({wr_1r:.0f}%)\n"
                f"Hit 2R:         {wins_2r}\n"
                f"Stopped out:    {stopped}\n"
                f"━━━━━━━━━━━━━━━━━━━━\n"
                f"Bias accuracy:  {ba.get('correct', 0)}/{ba.get('total', 0)} "
                f"({ba.get('pct', 0):.0f}%)\n"
                f"Sessions logged: {s.get('total_sessions', 0)}\n"
            )
            self.send(msg)
        except Exception as e:
            self.send(f"⚠️ Stats error: {e}")

    def _cmd_ghost(self):
        if not getattr(self.jarvis, 'strategies', None):
            self.send("Ghost module not enabled.")
            return
        try:
            d = self.jarvis.strategies.get_dashboard_data()
            g = d.get("ghost", {})
            state = g.get("state", "idle")

            if state == "in_trade":
                ep = g.get("entry_price") or 0
                days = g.get("days_held", 0)
                # get current close estimate from DB state (no live fetch needed)
                running_note = f"Entry: {ep:.2f}  |  Day {days}/7"
                msg = (
                    f"GHOST — In Trade\n"
                    f"━━━━━━━━━━━━━━━━━━━━\n"
                    f"LONG 1 MES active\n"
                    f"{running_note}\n"
                    f"Signal: {g.get('signal_date', 'N/A')}\n"
                    f"Entered: {g.get('entry_date', 'N/A')}\n"
                    f"Exit watch: RSI(2) > 65 or day 7"
                )
            elif state == "signal_pending":
                msg = (
                    f"GHOST — Signal Pending\n"
                    f"━━━━━━━━━━━━━━━━━━━━\n"
                    f"Signal fired: {g.get('signal_date', 'N/A')}\n"
                    f"Entering LONG at tomorrow's open."
                )
            elif state == "exit_pending":
                ep = g.get("entry_price") or 0
                msg = (
                    f"GHOST — Exit Pending\n"
                    f"━━━━━━━━━━━━━━━━━━━━\n"
                    f"Exit trigger fired. Exiting at tomorrow's open.\n"
                    f"Entry was: {ep:.2f}  |  Day {g.get('days_held', 0)}/7"
                )
            else:
                trades = g.get("trades", 0)
                wr = g.get("win_rate")
                pnl = g.get("total_pnl") or 0
                wr_str = f"{wr:.1f}%" if wr is not None else "N/A"
                msg = (
                    f"GHOST — Idle\n"
                    f"━━━━━━━━━━━━━━━━━━━━\n"
                    f"Watching for RSI(2) < 10 above SMA200.\n"
                    f"All-time: {trades} trades  |  WR {wr_str}  |  ${pnl:+.2f} MES"
                )
            self.send(msg)
        except Exception as e:
            self.send(f"Ghost error: {e}")

    def _cmd_surge(self):
        if not getattr(self.jarvis, 'strategies', None):
            self.send("Surge module not enabled.")
            return
        try:
            d = self.jarvis.strategies.get_dashboard_data()
            s = d.get("surge", {})
            state = s.get("state", "idle")

            if state == "comp_pending":
                ch = s.get("comp_high") or 0
                cl = s.get("comp_low") or 0
                ratio = s.get("atr_ratio") or 0
                msg = (
                    f"SURGE — Watching\n"
                    f"━━━━━━━━━━━━━━━━━━━━\n"
                    f"Compression bar: {s.get('comp_date', 'N/A')}\n"
                    f"ATR ratio: {ratio:.3f}  (< 0.50 threshold)\n"
                    f"━━━━━━━━━━━━━━━━━━━━\n"
                    f"Long above:  {ch:.2f}\n"
                    f"Short below: {cl:.2f}\n"
                    f"Resolves at today's close (4:15 PM ET check)."
                )
            else:
                trades = s.get("trades", 0)
                wr = s.get("win_rate")
                pnl = s.get("total_pnl") or 0
                wr_str = f"{wr:.1f}%" if wr is not None else "N/A"
                msg = (
                    f"SURGE — Idle\n"
                    f"━━━━━━━━━━━━━━━━━━━━\n"
                    f"No compression bar active.\n"
                    f"Watching for daily range < 50% of 20d avg.\n"
                    f"All-time: {trades} trades  |  WR {wr_str}  |  ${pnl:+.2f} MES"
                )
            self.send(msg)
        except Exception as e:
            self.send(f"Surge error: {e}")

    def _cmd_log_trade(self, cmd):
        if not self.jarvis.trade_logger:
            self.send("⚠️ Trade logger not enabled.")
            return
        # Expected: /log LONG 6875.50 8.5  OR  /trade LONG 6875.50 8.5
        parts = cmd.split()
        # parts[0] = "log" or "trade", then direction, entry, stop_dist
        if len(parts) < 4:
            self.send(
                "⚠️ Format: /log LONG 6875.50 8.5\n"
                "(direction, entry price, stop distance in points)"
            )
            return
        try:
            direction  = parts[1].upper()
            entry      = float(parts[2])
            stop_dist  = float(parts[3])
            if direction not in ("LONG", "SHORT"):
                self.send("⚠️ Direction must be LONG or SHORT.")
                return
            self.jarvis.trade_logger.manual_entry(direction, entry, stop_dist)
            # manual_entry() sends its own Telegram confirmation with buttons
        except ValueError:
            self.send("⚠️ Couldn't parse numbers. Format: /log LONG 6875.50 8.5")
        except Exception as e:
            self.send(f"⚠️ Log error: {e}")

    def _cmd_close_trade(self, outcome):
        if not self.jarvis.trade_logger:
            self.send("⚠️ Trade logger not enabled.")
            return
        if not self.jarvis.trade_logger.current_trade:
            self.send("⚠️ No open trade to close.")
            return
        self.jarvis.trade_logger.close_trade(outcome)
        # close_trade() sends its own Telegram confirmation

    def _cmd_haiku(self, text):
        if not self.jarvis.budget.can_make_call():
            self.send("⚠️ Haiku budget limit reached for today.")
            return
        try:
            self.send("⏳ Asking Haiku...")
            stats_summary = str(self.jarvis.bot_stats)
            response = self.jarvis.analyst._call_haiku(
                "You are Jarvis, a trading bot manager assistant. "
                "Answer concisely in plain text (no markdown). Keep under 3 sentences.",
                f"User asks: {text}\n\nBot stats: {stats_summary}"
            )
            if response:
                self.send(f"🤖 {response}")
            else:
                self.send("⚠️ Haiku unavailable right now.")
        except Exception as e:
            self.send(f"⚠️ Haiku error: {e}")

    # ─── SEND ─────────────────────────────────────────────────────────────────

    def send(self, text, markdown=False):
        if not self.token or not self.chat_id:
            return False
        try:
            url     = f"https://api.telegram.org/bot{self.token}/sendMessage"
            payload = {"chat_id": self.chat_id, "text": text}
            if markdown:
                payload["parse_mode"] = "Markdown"
            resp = requests.post(url, json=payload, timeout=REQUEST_TIMEOUT)
            return resp.status_code == 200
        except Exception as e:
            self.logger.error(f"TelegramListener send failed: {e}")
            return False
