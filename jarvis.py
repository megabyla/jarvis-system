#!/usr/bin/env python3
"""
JARVIS - Trading Bot Manager
Persistent monitoring, AI-powered analysis, autonomous optimization.

Architecture:
  systemd -> jarvis.py (this file) -> monitors all bots

Components:
  - Watchdog: Process health, heartbeats, auto-restart
  - Analyst: Haiku brain for pattern recognition
  - Approvals: Tiered permission system
  - Budget: API usage tracking
  - Git: Change tracking with reasoning
  - Dashboard: Web UI on port 6000
"""

import sys
import os
import json
import time
import logging
import signal
import threading
import yaml
import sqlite3
from datetime import datetime, timezone, timedelta

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

from modules.watchdog import Watchdog
from modules.analyst import Analyst
from modules.budget_tracker import BudgetTracker
from modules.approvals import ApprovalSystem
from modules.git_manager import GitManager
from modules.executor import ActionExecutor
from modules.futures_monitor import FuturesMonitor

from dotenv import load_dotenv
load_dotenv()


def setup_logger():
    logger = logging.getLogger("jarvis")
    logger.setLevel(logging.INFO)

    ch = logging.StreamHandler()
    ch.setLevel(logging.INFO)

    log_dir = os.path.join(os.path.dirname(os.path.abspath(__file__)), "logs")
    os.makedirs(log_dir, exist_ok=True)
    fh = logging.FileHandler(os.path.join(log_dir, "jarvis.log"))
    fh.setLevel(logging.DEBUG)

    fmt = logging.Formatter("%(asctime)s [%(levelname)s] %(message)s", datefmt="%Y-%m-%d %H:%M:%S")
    ch.setFormatter(fmt)
    fh.setFormatter(fmt)
    logger.addHandler(ch)
    logger.addHandler(fh)

    return logger


class Jarvis:
    def __init__(self):
        self.logger = setup_logger()
        self.logger.info("=" * 60)
        self.logger.info("JARVIS STARTING UP")
        self.logger.info("=" * 60)

        config_path = os.path.join(os.path.dirname(os.path.abspath(__file__)), "config.yaml")
        with open(config_path, "r") as f:
            self.config = yaml.safe_load(f)

        # Initialize modules
        self.budget = BudgetTracker(self.config, self.logger)
        self.watchdog = Watchdog(self.config, self.logger)
        self.analyst = Analyst(self.config, self.logger, self.budget)
        self.approvals = ApprovalSystem(self.config, self.logger)
        self.git = GitManager(self.config, self.logger)
        self.executor = ActionExecutor(self.config, self.logger, self.git)

        # Futures module
        if self.config.get('futures', {}).get('enabled', False):
            self.futures = FuturesMonitor(self.config, self.logger, self.analyst)
            self.logger.info('Futures monitor enabled')
        else:
            self.futures = None

        # State
        self.running = True
        self.last_analysis_time = 0
        self.last_stats_time = 0
        self.last_health_check = 0
        self.last_settlement_check = 0
        self.bot_health = {}
        self.bot_stats = {}
        self.chat_log = []
        self.last_stale_alert = {}  # bot_name -> timestamp (prevent spam)
        self.last_futures_check = 0

        # Initialize git repo
        self.git.init_repo()

        # Sync bot files on startup
        for bot_name, bot_config in self.config["bots"].items():
            if bot_config.get("enabled"):
                try:
                    self.git.sync_bot_files(bot_name, bot_config)
                except Exception as e:
                    self.logger.warning(f"Could not sync {bot_name}: {e}")
        try:
            self.git.commit_change(["sharbel/", "hybrid/"], "startup sync", "initial file sync")
        except:
            pass

        self.logger.info("All modules initialized")
        self.logger.info(f"Monitoring: {', '.join(n for n, c in self.config['bots'].items() if c.get('enabled'))}")

    def _log_chat(self, source, message, level="info"):
        entry = {
            "time": datetime.now(timezone(timedelta(hours=-5))).strftime("%I:%M:%S %p"),
            "source": source,
            "message": message,
            "level": level
        }
        self.chat_log.append(entry)
        if len(self.chat_log) > 200:
            self.chat_log = self.chat_log[-200:]

    def check_health(self):
        self.bot_health = self.watchdog.get_full_health_report(self.config["bots"])

        for bot_name, health in self.bot_health.items():
            if health.get("status") == "disabled":
                continue

            status = health.get("health", "UNKNOWN")

            if status == "DEAD":
                self._log_chat("watchdog", f"🚨 {bot_name} is DOWN!", "error")

                result = self.approvals.submit_action(
                    "restart_crashed_bot",
                    f"Restart {bot_name} - process not found",
                    f"Screen session not detected",
                    bot_name=bot_name
                )

                if result["status"] == "auto_approved":
                    bot_config = self.config["bots"][bot_name]
                    restart = self.watchdog.restart_bot(bot_name, bot_config)
                    if restart["success"]:
                        self._log_chat("jarvis", f"✅ Restarted {bot_name}", "success")
                    else:
                        self._log_chat("jarvis", f"❌ Restart failed: {restart['reason']}", "error")

            elif status == "STALE":
                stale_secs = health.get("database", {}).get("stale_seconds", 0)
                now = time.time()
                last_alert = self.last_stale_alert.get(bot_name, 0)
                if now - last_alert >= 300:  # Only alert every 5 minutes
                    self._log_chat("watchdog", f"⚠️ {bot_name} stale ({stale_secs}s since last trade)", "warning")
                    self.last_stale_alert[bot_name] = now

    def check_loss_streaks(self):
        max_losses = self.config["safety"]["max_consecutive_losses"]

        for bot_name, bot_config in self.config["bots"].items():
            if not bot_config.get("enabled"):
                continue

            streak = self.analyst._detect_loss_streak(bot_config["db_path"])

            if streak >= max_losses:
                self._log_chat("analyst", f"🚨 {bot_name}: {streak} consecutive losses!", "error")

                result = self.approvals.submit_action(
                    "pause_on_loss_streak",
                    f"Pause {bot_name} - {streak} consecutive losses",
                    f"Safety rail: {streak} losses >= {max_losses}",
                    bot_name=bot_name,
                    params={"reason": f"{streak}_consecutive_losses", "streak": streak}
                )

                if result["status"] == "auto_approved":
                    exec_result = self.executor.execute_action(result["action"])
                    if exec_result["success"]:
                        self._log_chat("jarvis", f"⏸️ Paused {bot_name} ({streak} loss streak)", "warning")

                        if self.config["haiku"].get("triggered_analysis"):
                            analysis = self.analyst.run_triggered_analysis(
                                f"{streak} consecutive losses", bot_name, bot_config
                            )
                            if analysis:
                                self._log_chat("haiku", analysis.get("diagnosis", ""), "info")

    def check_settlements(self):
        for bot_name, bot_config in self.config["bots"].items():
            if not bot_config.get("enabled"):
                continue
            try:
                conn = sqlite3.connect(bot_config["db_path"])
                c = conn.cursor()
                c.execute("""
                    SELECT COUNT(*) FROM trades
                    WHERE settled = 1 AND order_id IS NOT NULL
                    AND settle_time > datetime('now', '-60 minutes')
                """)
                unredeemed = c.fetchone()[0]
                conn.close()
                if unredeemed > 0:
                    self._log_chat("watchdog", f"💰 {bot_name}: {unredeemed} unredeemed", "info")
            except:
                pass

    def calculate_stats(self):
        for bot_name, bot_config in self.config["bots"].items():
            if not bot_config.get("enabled"):
                continue
            stats = self.analyst._get_rolling_stats(bot_config["db_path"], window=50)
            if stats:
                self.bot_stats[bot_name] = stats

    def run_scheduled_analysis(self):
        analysis = self.analyst.run_scheduled_analysis(self.config["bots"])
        if not analysis:
            self._log_chat("haiku", "Analysis skipped (budget or API issue)", "warning")
            return

        # Clean summary only
        summary = analysis.get("summary", "")
        if summary:
            # Strip any leftover JSON/markdown artifacts
            summary = summary.replace("```json", "").replace("```", "").strip()
            self._log_chat("haiku", f"📊 {summary[:300]}", "info")

        # Top 3 observations max
        observations = analysis.get("observations", [])
        for obs in observations[:3]:
            short = obs[:150] if len(obs) > 150 else obs
            self._log_chat("haiku", f"  → {short}", "info")
        if len(observations) > 3:
            self._log_chat("haiku", f"  ... +{len(observations) - 3} more observations", "info")

        # Recommendations go to approval queue (not chat spam)
        recs = analysis.get("recommendations", [])
        for rec in recs:
            self.approvals.submit_action(
                rec.get("action", "log_observation"),
                rec.get("description", ""),
                rec.get("reason", ""),
                params=rec
            )
        if recs:
            self._log_chat("haiku", f"📋 {len(recs)} recommendation(s) queued for approval", "info")

        # Risk alerts - keep these visible
        for alert in analysis.get("risk_alerts", []):
            short = alert[:200] if len(alert) > 200 else alert
            self._log_chat("haiku", f"⚠️ {short}", "error")

    def process_approved_actions(self):
        for action in self.approvals.get_pending_actions():
            if action["status"] == "approved":
                result = self.executor.execute_action(action)
                self._log_chat("jarvis", f"✅ Executed: {action['description']}", "success")

    def _run_futures_checks(self, now):
        """Run futures-related checks based on time of day."""
        from datetime import time as dt_time
        et_now = datetime.now(timezone(timedelta(hours=-5)))
        current_time = et_now.time()

        ft_config = self.config.get("futures", {})
        premarket = dt_time(9, 0)
        session_start = dt_time(9, 30)
        session_end = dt_time(11, 0)
        postsession = dt_time(11, 15)
        monitor_interval = ft_config.get("monitor_interval", 300)

        # Pre-market brief (9:00 AM ET)
        if current_time >= premarket and current_time < session_start:
            brief = self.futures.run_premarket(force=True)
            if brief:
                self._log_chat("futures", brief["message"], "info")

        # Live session monitoring (9:30-11:00, every 5 min)
        if current_time >= session_start and current_time <= session_end:
            if now - self.last_futures_check >= monitor_interval:
                signal = self.futures.check_eq_rejection()
                if signal:
                    self._log_chat("futures", signal["message"], "success")

                    # Submit to approval queue if configured
                    self.approvals.submit_action(
                        "eq_rejection_signal",
                        f"EQ Rejection {signal['direction']} @ {signal['entry']:.2f}",
                        signal["bias_confirms"],
                        params=signal
                    )
                self.last_futures_check = now

        # Post-session (11:15 AM ET)
        if current_time >= postsession and current_time < dt_time(11, 30):
            summary = self.futures.run_postsession()
            if summary:
                fired = "Signal fired" if summary["signal_fired"] else "No signal"
                self._log_chat("futures",
                    f"📋 Session complete: {summary['sequence']} | {summary['bias']} | {fired}",
                    "info")

    def get_dashboard_state(self):
        return {
            "health": self.bot_health,
            "stats": self.bot_stats,
            "budget": self.budget.get_dashboard_data(),
            "approvals": self.approvals.get_dashboard_data(),
            "chat_log": self.chat_log[-50:],
            "git_commits": self.git.get_recent_commits(10),
            "futures": self.futures.get_dashboard_data() if self.futures else None,
            "config": {
                "bots": {k: {
                    "name": v["name"],
                    "enabled": v.get("enabled", True),
                    "dashboard_port": v.get("dashboard_port")
                } for k, v in self.config["bots"].items()}
            }
        }

    def handle_user_command(self, command_text):
        self._log_chat("user", command_text, "info")
        cmd = command_text.strip().lower()

        if cmd in ("status", "health"):
            self.check_health()
            self._log_chat("jarvis", "Health check complete", "info")
        elif cmd.startswith("pause "):
            bot = cmd.split(" ", 1)[1].strip()
            if bot in self.config["bots"]:
                self.executor._pause_bot(bot, {"reason": "user_command"})
                self._log_chat("jarvis", f"⏸️ Paused {bot}", "success")
            else:
                self._log_chat("jarvis", f"Unknown bot: {bot}", "error")
        elif cmd.startswith("resume "):
            bot = cmd.split(" ", 1)[1].strip()
            if bot in self.config["bots"]:
                self.executor._resume_bot(bot, {})
                self._log_chat("jarvis", f"▶️ Resumed {bot}", "success")
            else:
                self._log_chat("jarvis", f"Unknown bot: {bot}", "error")
        elif cmd in ("analyze", "analysis"):
            self._log_chat("jarvis", "Running analysis...", "info")
            self.run_scheduled_analysis()
        elif cmd == "budget":
            data = self.budget.get_dashboard_data()
            d, m = data["daily"], data["monthly"]
            self._log_chat("jarvis",
                f"Today: ${d['cost']:.4f}/{d['limit']} ({d['calls']} calls) | Month: ${m['cost']:.4f}/{m['limit']}", "info")
        elif cmd in ("futures", "premarket", "bias"):
            if self.futures:
                brief = self.futures.run_premarket(force=True)
                if brief:
                    self._log_chat("futures", brief["message"], "info")
                else:
                    data = self.futures.get_dashboard_data()
                    seq = data.get("sequence", "unknown")
                    bias = data.get("bias", "unknown")
                    self._log_chat("futures", f"Current: {seq} → {bias}", "info")
            else:
                self._log_chat("jarvis", "Futures module not enabled", "warning")
        elif cmd == "futures stats":
            if self.futures:
                stats = self.futures.get_stats()
                self._log_chat("futures", json.dumps(stats, indent=2, default=str), "info")
        elif cmd == "weekly":
            if self.futures:
                summary = self.futures.get_weekly_summary()
                if summary:
                    self._log_chat("futures", summary, "info")
        else:
            if self.budget.can_make_call():
                self._log_chat("jarvis", "Asking Haiku...", "info")
                stats_summary = json.dumps(self.bot_stats, default=str)
                response = self.analyst._call_haiku(
                    "You are Jarvis, a trading bot manager. Answer concisely based on the data. Keep under 3 sentences.",
                    f"User asks: {command_text}\n\nBot stats: {stats_summary}"
                )
                if response:
                    self._log_chat("haiku", response, "info")
                else:
                    self._log_chat("jarvis", "Haiku unavailable", "warning")
            else:
                self._log_chat("jarvis", "Budget limit reached", "warning")

    def run(self):
        self.logger.info("Main loop starting")
        self._log_chat("jarvis", "🤖 Jarvis online. Monitoring all systems.", "success")

        from dashboard import create_dashboard_app
        dashboard_app = create_dashboard_app(self)
        dash_thread = threading.Thread(
            target=lambda: dashboard_app.run(
                host="0.0.0.0",
                port=self.config.get("jarvis_port", 6000),
                debug=False,
                use_reloader=False
            ),
            daemon=True
        )
        dash_thread.start()
        self.logger.info(f"Dashboard on port {self.config.get('jarvis_port', 6000)}")

        self.check_health()
        self.calculate_stats()

        while self.running:
            try:
                now = time.time()

                if now - self.last_health_check >= self.config["watchdog"]["heartbeat_interval"]:
                    self.check_health()
                    self.last_health_check = now

                if now - self.last_settlement_check >= self.config["watchdog"]["settlement_check_interval"]:
                    self.check_settlements()
                    self.check_loss_streaks()
                    self.last_settlement_check = now

                if now - self.last_stats_time >= self.config["watchdog"]["stats_interval"]:
                    self.calculate_stats()
                    self.last_stats_time = now

                if now - self.last_analysis_time >= self.config["haiku"]["analysis_interval"]:
                    self.run_scheduled_analysis()
                    self.last_analysis_time = now

                # Futures monitoring
                if self.futures and self.futures.enabled:
                    self._run_futures_checks(now)

                self.process_approved_actions()
                time.sleep(5)

            except KeyboardInterrupt:
                self.logger.info("Shutting down...")
                self.running = False
            except Exception as e:
                self.logger.error(f"Main loop error: {e}")
                import traceback
                traceback.print_exc()
                time.sleep(10)

        self.logger.info("Jarvis shut down")


if __name__ == "__main__":
    def signal_handler(sig, frame):
        print("\nReceived shutdown signal")
        sys.exit(0)

    signal.signal(signal.SIGINT, signal_handler)
    signal.signal(signal.SIGTERM, signal_handler)

    jarvis = Jarvis()
    jarvis.run()

