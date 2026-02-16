#!/usr/bin/env python3
"""
JARVIS FUTURES INTEGRATION PATCH
=================================
Run this script from ~/jarvis/ to:
1. Copy futures_monitor.py into modules/
2. Add futures config to config.yaml
3. Patch jarvis.py to integrate the futures module
4. Stage everything for git commit

Usage: python3 integrate_futures.py
"""

import os
import sys
import shutil
import yaml

JARVIS_DIR = "/root/jarvis"
MODULES_DIR = os.path.join(JARVIS_DIR, "modules")
CONFIG_PATH = os.path.join(JARVIS_DIR, "config.yaml")
JARVIS_PY = os.path.join(JARVIS_DIR, "jarvis.py")
SOURCE_MODULE = "/root/3dpo3/futures_monitor.py"


def add_config():
    """Add futures section to config.yaml"""
    print("[1/3] Updating config.yaml...")

    with open(CONFIG_PATH, "r") as f:
        config = yaml.safe_load(f)

    if "futures" in config:
        print("  Futures config already exists, skipping.")
        return

    config["futures"] = {
        "enabled": True,
        "instrument": "ES",
        "data_dir": "/root/3dpo3/futures_data",
        "db_path": "/root/3dpo3/futures_trades.db",
        "eq_buffer": 2.0,
        "min_stop": 2.0,
        "max_stop": 15.0,
        "stop_buffer": 0.5,
        "premarket_time": "09:00",
        "session_start": "09:30",
        "session_end": "11:00",
        "postsession_time": "11:15",
        "monitor_interval": 300,  # 5 minutes (matches 5m candles)
    }

    with open(CONFIG_PATH, "w") as f:
        yaml.dump(config, f, default_flow_style=False, sort_keys=False)

    print("  ✅ Added futures config section")


def copy_module():
    """Copy futures_monitor.py to modules/"""
    print("[2/3] Copying futures module...")

    dest = os.path.join(MODULES_DIR, "futures_monitor.py")

    if os.path.exists(SOURCE_MODULE):
        shutil.copy2(SOURCE_MODULE, dest)
        print(f"  ✅ Copied {SOURCE_MODULE} → {dest}")
    else:
        print(f"  ⚠️ Source not found at {SOURCE_MODULE}")
        print(f"  Please manually copy futures_monitor.py to {dest}")


def patch_jarvis():
    """Patch jarvis.py to integrate futures module."""
    print("[3/3] Patching jarvis.py...")

    with open(JARVIS_PY, "r") as f:
        content = f.read()

    # Check if already patched
    if "futures_monitor" in content:
        print("  Already patched, skipping.")
        return

    # 1. Add import
    old_import = "from modules.executor import ActionExecutor"
    new_import = (
        "from modules.executor import ActionExecutor\n"
        "from modules.futures_monitor import FuturesMonitor"
    )
    content = content.replace(old_import, new_import)

    # 2. Add initialization in __init__
    old_init = "        # State\n        self.running = True"
    new_init = (
        "        # Futures module\n"
        "        if self.config.get('futures', {}).get('enabled', False):\n"
        "            self.futures = FuturesMonitor(self.config, self.logger, self.analyst)\n"
        "            self.logger.info('Futures monitor enabled')\n"
        "        else:\n"
        "            self.futures = None\n"
        "\n"
        "        # State\n"
        "        self.running = True"
    )
    content = content.replace(old_init, new_init)

    # 3. Add last_futures_check to state
    old_state = "        self.last_stale_alert = {}  # bot_name -> timestamp (prevent spam)"
    new_state = (
        "        self.last_stale_alert = {}  # bot_name -> timestamp (prevent spam)\n"
        "        self.last_futures_check = 0"
    )
    content = content.replace(old_state, new_state)

    # 4. Add futures loop logic in run() main loop
    old_loop_check = "                self.process_approved_actions()"
    new_loop_check = (
        "                # Futures monitoring\n"
        "                if self.futures and self.futures.enabled:\n"
        "                    self._run_futures_checks(now)\n"
        "\n"
        "                self.process_approved_actions()"
    )
    content = content.replace(old_loop_check, new_loop_check)

    # 5. Add the futures check method before get_dashboard_state
    old_dashboard = "    def get_dashboard_state(self):"
    new_method = '''    def _run_futures_checks(self, now):
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
            brief = self.futures.run_premarket()
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

    def get_dashboard_state(self):'''

    content = content.replace(old_dashboard, new_method)

    # 6. Add futures data to dashboard state
    old_return = '            "config": {'
    new_return = (
        '            "futures": self.futures.get_dashboard_data() if self.futures else None,\n'
        '            "config": {'
    )
    content = content.replace(old_return, new_return, 1)

    # 7. Add futures commands to handle_user_command
    old_else = '        else:\n            if self.budget.can_make_call():'
    new_else = (
        '        elif cmd in ("futures", "premarket", "bias"):\n'
        '            if self.futures:\n'
        '                brief = self.futures.run_premarket()\n'
        '                if brief:\n'
        '                    self._log_chat("futures", brief["message"], "info")\n'
        '                else:\n'
        '                    data = self.futures.get_dashboard_data()\n'
        '                    seq = data.get("sequence", "unknown")\n'
        '                    bias = data.get("bias", "unknown")\n'
        '                    self._log_chat("futures", f"Current: {seq} → {bias}", "info")\n'
        '            else:\n'
        '                self._log_chat("jarvis", "Futures module not enabled", "warning")\n'
        '        elif cmd == "futures stats":\n'
        '            if self.futures:\n'
        '                stats = self.futures.get_stats()\n'
        '                self._log_chat("futures", json.dumps(stats, indent=2, default=str), "info")\n'
        '        elif cmd == "weekly":\n'
        '            if self.futures:\n'
        '                summary = self.futures.get_weekly_summary()\n'
        '                if summary:\n'
        '                    self._log_chat("futures", summary, "info")\n'
        '        else:\n'
        '            if self.budget.can_make_call():'
    )
    content = content.replace(old_else, new_else)

    # Write patched file
    with open(JARVIS_PY, "w") as f:
        f.write(content)

    print("  ✅ Patched jarvis.py with futures integration")


def add_permissions():
    """Add futures-related permissions to config."""
    with open(CONFIG_PATH, "r") as f:
        config = yaml.safe_load(f)

    perms = config.get("permissions", {})

    # Add eq_rejection_signal to auto_approve (or require_approval)
    auto = perms.get("auto_approve", [])
    if "eq_rejection_signal" not in auto:
        auto.append("log_eq_rejection")
        perms["auto_approve"] = auto

    require = perms.get("require_approval", [])
    if "eq_rejection_signal" not in require:
        require.append("eq_rejection_signal")
        perms["require_approval"] = require

    config["permissions"] = perms

    with open(CONFIG_PATH, "w") as f:
        yaml.dump(config, f, default_flow_style=False, sort_keys=False)

    print("  ✅ Added futures permissions")


def main():
    print("=" * 50)
    print("JARVIS FUTURES INTEGRATION")
    print("=" * 50)

    add_config()
    copy_module()
    patch_jarvis()
    add_permissions()

    print("\n" + "=" * 50)
    print("DONE!")
    print("=" * 50)
    print(f"""
Next steps:
  1. Copy futures_monitor.py to ~/jarvis/modules/ if not auto-copied
  2. Review the changes:
     cd ~/jarvis
     git diff
  3. Commit and push:
     git add -A
     git commit -m "jarvis: add futures monitor module (Strat + EQ Rejection)"
     git push
  4. Restart Jarvis:
     sudo systemctl restart jarvis
  5. Test:
     - Open dashboard on port {6001}
     - Type 'futures' or 'bias' in the command box
""")


if __name__ == "__main__":
    main()
