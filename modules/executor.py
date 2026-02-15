"""
Jarvis Action Executor
Applies approved actions to bot configurations and code.
"""

import subprocess
import re
import sqlite3
from datetime import datetime, timezone, timedelta


class ActionExecutor:
    def __init__(self, config, logger, git_manager):
        self.config = config
        self.logger = logger
        self.git = git_manager

    def execute_action(self, action):
        """Route an action to the correct handler"""
        action_type = action["type"]
        bot_name = action.get("bot")
        params = action.get("params", {})

        handlers = {
            "restart_crashed_bot": self._restart_bot,
            "redeem_settlements": self._force_redeem,
            "pause_on_loss_streak": self._pause_bot,
            "resume_after_cooldown": self._resume_bot,
            "change_movement_filter": self._change_movement_filter,
            "change_stake_size": self._change_stake_size,
            "change_entry_timing": self._change_entry_timing,
            "enable_disable_rsi": self._toggle_rsi,
            "change_conviction_range": self._change_conviction,
            "log_observation": self._log_observation,
        }

        handler = handlers.get(action_type)
        if handler:
            try:
                result = handler(bot_name, params)
                self.logger.info(f"Executed {action_type}: {result}")
                return {"success": True, "result": result}
            except Exception as e:
                self.logger.error(f"Execute failed {action_type}: {e}")
                return {"success": False, "error": str(e)}
        else:
            self.logger.warning(f"No handler for action: {action_type}")
            return {"success": False, "error": "no_handler"}

    def _restart_bot(self, bot_name, params):
        """Restart a bot (delegated to watchdog)"""
        return {"action": "restart", "bot": bot_name, "delegate": "watchdog"}

    def _force_redeem(self, bot_name, params):
        """Force redemption of settled positions"""
        bot_config = self.config["bots"].get(bot_name, {})
        directory = bot_config.get("directory", "")

        try:
            result = subprocess.run(
                ["python3", "redeem_winnings.py"],
                capture_output=True, text=True, timeout=60,
                cwd=directory
            )
            return {"stdout": result.stdout[:500], "returncode": result.returncode}
        except Exception as e:
            return {"error": str(e)}

    def _pause_bot(self, bot_name, params):
        """Pause a bot by creating a kill switch file"""
        bot_config = self.config["bots"].get(bot_name, {})
        directory = bot_config.get("directory", "")
        kill_file = f"{directory}/KILL_SWITCH"

        with open(kill_file, "w") as f:
            reason = params.get("reason", "loss_streak")
            f.write(f"Paused by Jarvis: {reason}\n")
            f.write(f"Time: {datetime.now(timezone(timedelta(hours=-5))).isoformat()}\n")

        return {"paused": True, "kill_file": kill_file}

    def _resume_bot(self, bot_name, params):
        """Resume a bot by removing kill switch"""
        import os
        bot_config = self.config["bots"].get(bot_name, {})
        directory = bot_config.get("directory", "")
        kill_file = f"{directory}/KILL_SWITCH"

        if os.path.exists(kill_file):
            os.remove(kill_file)
            return {"resumed": True}
        return {"resumed": True, "note": "kill_switch_not_found"}

    def _change_movement_filter(self, bot_name, params):
        """Change the minimum price movement filter"""
        new_value = params.get("value")
        if new_value is None:
            return {"error": "no_value_provided"}

        bot_config = self.config["bots"].get(bot_name, {})
        directory = bot_config.get("directory", "")
        main_file = f"{directory}/{bot_config.get('main_file', '')}"

        # Read file
        with open(main_file, "r") as f:
            content = f.read()

        # Find and replace movement filter
        old_pattern = r"self\.min_price_movement\s*=\s*[\d.]+"
        new_line = f"self.min_price_movement = {new_value}"

        if re.search(old_pattern, content):
            content = re.sub(old_pattern, new_line, content)
            with open(main_file, "w") as f:
                f.write(content)

            # Git commit
            self.git.sync_bot_files(bot_name, bot_config)
            self.git.commit_change(
                [f"{bot_name}/{bot_config.get('main_file', '')}"],
                f"movement filter {new_value}%",
                params.get("reason", "")
            )

            return {"changed": True, "new_value": new_value}
        else:
            return {"error": "pattern_not_found"}

    def _change_stake_size(self, bot_name, params):
        """Change stake size"""
        new_value = params.get("value")
        if new_value is None:
            return {"error": "no_value_provided"}

        bot_config = self.config["bots"].get(bot_name, {})
        directory = bot_config.get("directory", "")
        main_file = f"{directory}/{bot_config.get('main_file', '')}"

        with open(main_file, "r") as f:
            content = f.read()

        old_pattern = r"self\.stake_size\s*=\s*[\d.]+"
        new_line = f"self.stake_size = {new_value}"

        if re.search(old_pattern, content):
            content = re.sub(old_pattern, new_line, content)
            with open(main_file, "w") as f:
                f.write(content)

            self.git.sync_bot_files(bot_name, bot_config)
            self.git.commit_change(
                [f"{bot_name}/{bot_config.get('main_file', '')}"],
                f"stake size → ${new_value}",
                params.get("reason", "")
            )

            return {"changed": True, "new_value": new_value}
        else:
            return {"error": "pattern_not_found"}

    def _change_entry_timing(self, bot_name, params):
        """Change entry timing (seconds before close)"""
        new_seconds = params.get("value")
        if new_seconds is None:
            return {"error": "no_value_provided"}

        bot_config = self.config["bots"].get(bot_name, {})
        directory = bot_config.get("directory", "")
        main_file = f"{directory}/{bot_config.get('main_file', '')}"

        with open(main_file, "r") as f:
            content = f.read()

        old_pattern = r"window_end\s*-\s*\d+"
        new_line = f"window_end - {new_seconds}"

        if re.search(old_pattern, content):
            content = re.sub(old_pattern, new_line, content)
            with open(main_file, "w") as f:
                f.write(content)

            self.git.sync_bot_files(bot_name, bot_config)
            self.git.commit_change(
                [f"{bot_name}/{bot_config.get('main_file', '')}"],
                f"entry timing → {new_seconds}s before close",
                params.get("reason", "")
            )

            return {"changed": True, "new_value": new_seconds}
        else:
            return {"error": "pattern_not_found"}

    def _toggle_rsi(self, bot_name, params):
        """Enable or disable RSI filter"""
        enable = params.get("enable", False)

        bot_config = self.config["bots"].get(bot_name, {})
        directory = bot_config.get("directory", "")
        main_file = f"{directory}/{bot_config.get('main_file', '')}"

        with open(main_file, "r") as f:
            content = f.read()

        if enable:
            # Uncomment the RSI block
            content = content.replace(
                "#                        # Block weak RSI signals",
                "                        # Block weak RSI signals"
            ).replace(
                "#                        if rsi_result['signal'] == 'weak':",
                "                        if rsi_result['signal'] == 'weak':"
            ).replace(
                "#                            print(f\"    ⏭️  SKIP - Weak RSI signal (avoiding bad entry)\")",
                "                            print(f\"    ⏭️  SKIP - Weak RSI signal (avoiding bad entry)\")"
            ).replace(
                "#                            sys.stdout.flush()",
                "                            sys.stdout.flush()"
            ).replace(
                "#                            continue",
                "                            continue"
            )
        else:
            # Comment out the RSI block
            content = content.replace(
                "                        # Block weak RSI signals",
                "#                        # Block weak RSI signals"
            ).replace(
                "                        if rsi_result['signal'] == 'weak':",
                "#                        if rsi_result['signal'] == 'weak':"
            )

        with open(main_file, "w") as f:
            f.write(content)

        state = "enabled" if enable else "disabled"
        self.git.sync_bot_files(bot_name, bot_config)
        self.git.commit_change(
            [f"{bot_name}/{bot_config.get('main_file', '')}"],
            f"RSI filter {state}",
            params.get("reason", "")
        )

        return {"changed": True, "rsi_enabled": enable}

    def _change_conviction(self, bot_name, params):
        """Change conviction range (min/max poly conviction)"""
        new_min = params.get("min")
        new_max = params.get("max")

        bot_config = self.config["bots"].get(bot_name, {})
        directory = bot_config.get("directory", "")
        main_file = f"{directory}/{bot_config.get('main_file', '')}"

        with open(main_file, "r") as f:
            content = f.read()

        changed = False

        if new_min is not None:
            pattern = r"self\.min_poly_conviction\s*=\s*[\d.]+"
            content = re.sub(pattern, f"self.min_poly_conviction = {new_min}", content)
            changed = True

        if new_max is not None:
            pattern = r"self\.max_poly_conviction\s*=\s*[\d.]+"
            content = re.sub(pattern, f"self.max_poly_conviction = {new_max}", content)
            changed = True

        if changed:
            with open(main_file, "w") as f:
                f.write(content)

            self.git.sync_bot_files(bot_name, bot_config)
            self.git.commit_change(
                [f"{bot_name}/{bot_config.get('main_file', '')}"],
                f"conviction range → {new_min or '?'}-{new_max or '?'}",
                params.get("reason", "")
            )

        return {"changed": changed, "min": new_min, "max": new_max}

    def _log_observation(self, bot_name, params):
        """Just log an observation - no code changes"""
        return {"logged": True, "observation": params.get("message", "")}
