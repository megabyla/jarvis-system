"""
Jarvis Watchdog Module
Monitors bot processes, checks heartbeats, auto-restarts crashed bots.
"""

import subprocess
import time
import sqlite3
from datetime import datetime, timezone, timedelta


class Watchdog:
    def __init__(self, config, logger):
        self.config = config
        self.logger = logger
        self.restart_history = {}  # bot_name -> [(timestamp, success)]

    def check_screen_session(self, screen_name):
        """Check if a screen session is running"""
        try:
            result = subprocess.run(
                ["screen", "-ls"],
                capture_output=True, text=True, timeout=5
            )
            return screen_name in result.stdout
        except Exception as e:
            self.logger.error(f"Screen check error: {e}")
            return False

    def check_process_alive(self, bot_name, bot_config):
        """Check if a bot's process is alive via screen session"""
        screen_name = bot_config["screen_name"]
        is_alive = self.check_screen_session(screen_name)

        return {
            "bot": bot_name,
            "alive": is_alive,
            "screen_name": screen_name,
            "checked_at": datetime.now(timezone.utc).isoformat()
        }

    def check_db_freshness(self, bot_name, bot_config):
        """Check if the bot's database has been updated recently"""
        db_path = bot_config["db_path"]
        stale_threshold = self.config["watchdog"]["stale_threshold"]

        try:
            conn = sqlite3.connect(db_path)
            c = conn.cursor()
            c.execute("SELECT MAX(timestamp) FROM trades")
            result = c.fetchone()
            conn.close()

            if not result or not result[0]:
                return {"fresh": False, "last_trade": None, "stale_seconds": None}

            last_trade_str = result[0]
            # Handle both ISO formats
            try:
                # Handle ISO format timestamps (with or without timezone)
                if 'Z' in last_trade_str:
                    last_trade = datetime.fromisoformat(last_trade_str.replace('Z', '+00:00'))
                elif '+' in last_trade_str or last_trade_str.endswith('00:00'):
                    last_trade = datetime.fromisoformat(last_trade_str)
                else:
                    # No timezone info - assume UTC
                    last_trade = datetime.fromisoformat(last_trade_str).replace(tzinfo=timezone.utc)
            except Exception as e:
                # Fallback - try without timezone then add UTC
                try:
                    last_trade = datetime.fromisoformat(last_trade_str.split('+')[0].split('Z')[0])
                    last_trade = last_trade.replace(tzinfo=timezone.utc)
                except:
                    return {"fresh": False, "last_trade": None, "stale_seconds": None}

            if last_trade.tzinfo is None:
                last_trade = last_trade.replace(tzinfo=timezone.utc)

            now = datetime.now(timezone.utc)
            stale_seconds = (now - last_trade).total_seconds()

            return {
                "fresh": stale_seconds < stale_threshold,
                "last_trade": last_trade.isoformat(),
                "stale_seconds": int(stale_seconds)
            }

        except Exception as e:
            self.logger.error(f"DB freshness check error for {bot_name}: {e}")
            return {"fresh": False, "last_trade": None, "stale_seconds": None}

    def restart_bot(self, bot_name, bot_config):
        """Restart a crashed bot via screen session"""
        # Check if auto_restart is enabled for this bot
        if not bot_config.get("auto_restart", True):
            self.logger.info(f"{bot_name} crashed but auto_restart disabled (managed manually)")
            return {
                "success": False,
                "reason": "auto_restart_disabled",
                "message": "Bot is managed manually"
            }

        max_attempts = self.config["watchdog"]["max_restart_attempts"]
        cooldown = self.config["watchdog"]["restart_cooldown"]

        # Check restart history
        now = time.time()
        history = self.restart_history.get(bot_name, [])

        # Clean old entries beyond cooldown
        history = [(ts, s) for ts, s in history if now - ts < cooldown * max_attempts]
        recent = [ts for ts, s in history if now - ts < cooldown]

        if len(recent) >= max_attempts:
            self.logger.warning(f"Max restart attempts reached for {bot_name}")
            return {
                "success": False,
                "reason": "max_attempts_exceeded",
                "attempts": len(recent)
            }

        # Attempt restart
        try:
            directory = bot_config["directory"]
            main_file = bot_config["main_file"]
            screen_name = bot_config["screen_name"]
            venv_path = bot_config.get("venv_path", "")

            # Kill existing screen if any
            subprocess.run(
                ["screen", "-S", screen_name, "-X", "quit"],
                capture_output=True, timeout=5
            )
            time.sleep(1)

            # Start new screen session
            if venv_path:
                cmd = f"cd {directory} && source {venv_path}/bin/activate && python3 {main_file}"
            else:
                cmd = f"cd {directory} && python3 {main_file}"

            subprocess.run(
                ["screen", "-dmS", screen_name, "bash", "-c", cmd],
                capture_output=True, timeout=10
            )

            time.sleep(3)

            # Verify it started
            is_alive = self.check_screen_session(screen_name)

            history.append((now, is_alive))
            self.restart_history[bot_name] = history

            if is_alive:
                self.logger.info(f"✅ Successfully restarted {bot_name}")
            else:
                self.logger.error(f"❌ Failed to restart {bot_name}")

            return {
                "success": is_alive,
                "reason": "restarted" if is_alive else "start_failed",
                "attempts": len(recent) + 1
            }

        except Exception as e:
            self.logger.error(f"Restart error for {bot_name}: {e}")
            history.append((now, False))
            self.restart_history[bot_name] = history
            return {"success": False, "reason": str(e), "attempts": len(recent) + 1}

    def check_dashboard_alive(self, bot_config):
        """Check if a bot's dashboard is responding"""
        port = bot_config.get("dashboard_port")
        if not port:
            return {"alive": False, "reason": "no_port_configured"}

        try:
            import requests
            resp = requests.get(f"http://localhost:{port}/", timeout=3)
            return {"alive": resp.status_code == 200, "status_code": resp.status_code}
        except:
            return {"alive": False, "reason": "connection_failed"}

    def get_full_health_report(self, bots_config):
        """Generate health report for all bots"""
        report = {}

        for bot_name, bot_config in bots_config.items():
            if not bot_config.get("enabled", True):
                report[bot_name] = {"status": "disabled"}
                continue

            process = self.check_process_alive(bot_name, bot_config)
            db = self.check_db_freshness(bot_name, bot_config)
            dashboard = self.check_dashboard_alive(bot_config)

            # Overall health
            if not process["alive"]:
                health = "DEAD"
            elif not db["fresh"]:
                health = "STALE"
            else:
                health = "HEALTHY"

            report[bot_name] = {
                "health": health,
                "process": process,
                "database": db,
                "dashboard": dashboard,
                "checked_at": datetime.now(timezone.utc).isoformat()
            }

        return report
