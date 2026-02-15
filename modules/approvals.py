"""
Jarvis Approval System
Manages pending actions with tiered permissions.
Auto-approves safe actions, queues risky ones for user approval.
"""

import json
import os
import time
from datetime import datetime, timezone, timedelta


class ApprovalSystem:
    def __init__(self, config, logger):
        self.config = config
        self.logger = logger
        self.permissions = config["permissions"]
        self.queue_path = os.path.join(
            os.path.dirname(os.path.dirname(os.path.abspath(__file__))),
            "memory", "approval_queue.json"
        )
        self.history_path = os.path.join(
            os.path.dirname(os.path.dirname(os.path.abspath(__file__))),
            "memory", "action_history.json"
        )
        self.queue = self._load_queue()
        self.history = self._load_history()

    def _load_queue(self):
        try:
            if os.path.exists(self.queue_path):
                with open(self.queue_path, "r") as f:
                    return json.load(f)
        except:
            pass
        return []

    def _save_queue(self):
        try:
            with open(self.queue_path, "w") as f:
                json.dump(self.queue, f, indent=2, default=str)
        except Exception as e:
            self.logger.error(f"Failed to save queue: {e}")

    def _load_history(self):
        try:
            if os.path.exists(self.history_path):
                with open(self.history_path, "r") as f:
                    return json.load(f)
        except:
            pass
        return []

    def _save_history(self):
        try:
            # Keep last 200 actions
            self.history = self.history[-200:]
            with open(self.history_path, "w") as f:
                json.dump(self.history, f, indent=2, default=str)
        except Exception as e:
            self.logger.error(f"Failed to save history: {e}")

    def get_permission_tier(self, action_type):
        """Determine which permission tier an action falls into"""
        if action_type in self.permissions["auto_approve"]:
            return "auto"
        elif action_type in self.permissions["require_approval"]:
            return "approval"
        elif action_type in self.permissions["never_touch"]:
            return "forbidden"
        else:
            return "approval"  # Default to requiring approval for unknown actions

    def submit_action(self, action_type, description, reason, bot_name=None, params=None):
        """Submit an action for approval or auto-execution"""
        tier = self.get_permission_tier(action_type)
        now = datetime.now(timezone(timedelta(hours=-5))).isoformat()

        action = {
            "id": f"action_{int(time.time() * 1000)}",
            "type": action_type,
            "description": description,
            "reason": reason,
            "bot": bot_name,
            "params": params or {},
            "tier": tier,
            "status": "pending",
            "submitted_at": now,
            "resolved_at": None,
            "resolved_by": None
        }

        if tier == "forbidden":
            action["status"] = "blocked"
            action["resolved_at"] = now
            action["resolved_by"] = "system"
            self.history.append(action)
            self._save_history()
            self.logger.warning(f"BLOCKED forbidden action: {action_type}")
            return {"status": "blocked", "action": action}

        elif tier == "auto":
            action["status"] = "auto_approved"
            action["resolved_at"] = now
            action["resolved_by"] = "jarvis"
            self.history.append(action)
            self._save_history()
            self.logger.info(f"Auto-approved: {description}")
            return {"status": "auto_approved", "action": action}

        else:
            # Requires user approval
            self.queue.append(action)
            self._save_queue()
            self.logger.info(f"Queued for approval: {description}")
            return {"status": "pending", "action": action}

    def approve_action(self, action_id):
        """User approves a pending action"""
        for i, action in enumerate(self.queue):
            if action["id"] == action_id:
                action["status"] = "approved"
                action["resolved_at"] = datetime.now(timezone(timedelta(hours=-5))).isoformat()
                action["resolved_by"] = "user"
                self.history.append(action)
                self.queue.pop(i)
                self._save_queue()
                self._save_history()
                self.logger.info(f"User approved: {action['description']}")
                return action
        return None

    def reject_action(self, action_id):
        """User rejects a pending action"""
        for i, action in enumerate(self.queue):
            if action["id"] == action_id:
                action["status"] = "rejected"
                action["resolved_at"] = datetime.now(timezone(timedelta(hours=-5))).isoformat()
                action["resolved_by"] = "user"
                self.history.append(action)
                self.queue.pop(i)
                self._save_queue()
                self._save_history()
                self.logger.info(f"User rejected: {action['description']}")
                return action
        return None

    def get_pending_actions(self):
        """Get all pending actions"""
        return [a for a in self.queue if a["status"] == "pending"]

    def get_recent_history(self, limit=30):
        """Get recent action history"""
        return self.history[-limit:]

    def get_dashboard_data(self):
        """Get data for dashboard display"""
        return {
            "pending": self.get_pending_actions(),
            "recent_history": self.get_recent_history(20),
            "pending_count": len(self.get_pending_actions())
        }
