"""
Jarvis Budget Tracker
Tracks API usage, enforces spending limits, provides dashboard data.
"""

import json
import os
from datetime import datetime, timezone, timedelta


class BudgetTracker:
    def __init__(self, config, logger):
        self.config = config
        self.logger = logger
        self.budget_config = config["budget"]
        self.log_path = os.path.join(
            os.path.dirname(os.path.dirname(os.path.abspath(__file__))),
            "memory", "api_usage.json"
        )
        self.usage = self._load_usage()

    def _load_usage(self):
        """Load usage data from disk"""
        try:
            if os.path.exists(self.log_path):
                with open(self.log_path, "r") as f:
                    return json.load(f)
        except:
            pass

        return {
            "calls": [],
            "daily_totals": {},
            "monthly_totals": {}
        }

    def _save_usage(self):
        """Save usage data to disk"""
        try:
            with open(self.log_path, "w") as f:
                json.dump(self.usage, f, indent=2, default=str)
        except Exception as e:
            self.logger.error(f"Failed to save usage: {e}")

    def _estimate_cost(self, input_tokens, output_tokens):
        """Estimate cost of an API call"""
        input_cost = (input_tokens / 1000) * self.budget_config["cost_per_1k_input"]
        output_cost = (output_tokens / 1000) * self.budget_config["cost_per_1k_output"]
        return round(input_cost + output_cost, 6)

    def log_call(self, input_tokens, output_tokens):
        """Log an API call with token counts"""
        now = datetime.now(timezone.utc)
        cost = self._estimate_cost(input_tokens, output_tokens)

        call_record = {
            "timestamp": now.isoformat(),
            "input_tokens": input_tokens,
            "output_tokens": output_tokens,
            "cost": cost
        }

        self.usage["calls"].append(call_record)

        # Update daily total
        day_key = now.strftime("%Y-%m-%d")
        if day_key not in self.usage["daily_totals"]:
            self.usage["daily_totals"][day_key] = {"calls": 0, "cost": 0, "tokens": 0}

        self.usage["daily_totals"][day_key]["calls"] += 1
        self.usage["daily_totals"][day_key]["cost"] += cost
        self.usage["daily_totals"][day_key]["tokens"] += input_tokens + output_tokens

        # Update monthly total
        month_key = now.strftime("%Y-%m")
        if month_key not in self.usage["monthly_totals"]:
            self.usage["monthly_totals"][month_key] = {"calls": 0, "cost": 0, "tokens": 0}

        self.usage["monthly_totals"][month_key]["calls"] += 1
        self.usage["monthly_totals"][month_key]["cost"] += cost
        self.usage["monthly_totals"][month_key]["tokens"] += input_tokens + output_tokens

        self._save_usage()

        self.logger.info(f"API call: {input_tokens}in/{output_tokens}out = ${cost:.4f}")

    def can_make_call(self):
        """Check if we're within budget limits"""
        now = datetime.now(timezone.utc)
        day_key = now.strftime("%Y-%m-%d")
        month_key = now.strftime("%Y-%m")

        # Check daily call limit
        daily = self.usage["daily_totals"].get(day_key, {"calls": 0, "cost": 0})
        if daily["calls"] >= self.budget_config["max_calls_per_day"]:
            return False

        # Check daily cost limit
        if daily["cost"] >= self.budget_config["daily_limit"]:
            return False

        # Check monthly cost limit
        monthly = self.usage["monthly_totals"].get(month_key, {"cost": 0})
        if monthly["cost"] >= self.budget_config["monthly_limit"]:
            return False

        return True

    def get_dashboard_data(self):
        """Get data for the dashboard budget display"""
        now = datetime.now(timezone.utc)
        day_key = now.strftime("%Y-%m-%d")
        month_key = now.strftime("%Y-%m")

        daily = self.usage["daily_totals"].get(day_key, {"calls": 0, "cost": 0, "tokens": 0})
        monthly = self.usage["monthly_totals"].get(month_key, {"calls": 0, "cost": 0, "tokens": 0})

        daily_limit = self.budget_config["daily_limit"]
        monthly_limit = self.budget_config["monthly_limit"]
        max_calls = self.budget_config["max_calls_per_day"]

        return {
            "daily": {
                "cost": round(daily["cost"], 4),
                "limit": daily_limit,
                "percent": min(100, round(daily["cost"] / daily_limit * 100, 1)) if daily_limit > 0 else 0,
                "calls": daily["calls"],
                "max_calls": max_calls,
                "tokens": daily["tokens"]
            },
            "monthly": {
                "cost": round(monthly["cost"], 4),
                "limit": monthly_limit,
                "percent": min(100, round(monthly["cost"] / monthly_limit * 100, 1)) if monthly_limit > 0 else 0,
                "calls": monthly["calls"],
                "tokens": monthly["tokens"]
            },
            "can_call": self.can_make_call(),
            "recent_calls": self.usage["calls"][-10:]  # Last 10 calls
        }
