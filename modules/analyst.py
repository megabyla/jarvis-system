"""
Jarvis Analyst Module
Calls Claude Haiku for intelligent analysis of trading data.
Reads memory, analyzes patterns, recommends changes.
"""

import os
import json
import sqlite3
import time
from datetime import datetime, timezone, timedelta


class Analyst:
    def __init__(self, config, logger, budget_tracker):
        self.config = config
        self.logger = logger
        self.budget = budget_tracker
        self.api_key = os.getenv("ANTHROPIC_API_KEY", "")
        self.model = config["haiku"]["model"]
        self.max_tokens = config["haiku"]["max_tokens"]
        self.temperature = config["haiku"]["temperature"]
        self.memory_path = os.path.join(
            os.path.dirname(os.path.dirname(os.path.abspath(__file__))),
            "memory", "jarvis_memory.md"
        )

    def _call_haiku(self, system_prompt, user_prompt):
        """Make API call to Claude Haiku"""
        if not self.api_key:
            self.logger.error("No ANTHROPIC_API_KEY set")
            return None

        # Check budget before calling
        if not self.budget.can_make_call():
            self.logger.warning("Budget limit reached - skipping API call")
            return None

        try:
            import requests

            resp = requests.post(
                "https://api.anthropic.com/v1/messages",
                headers={
                    "x-api-key": self.api_key,
                    "anthropic-version": "2023-06-01",
                    "content-type": "application/json"
                },
                json={
                    "model": self.model,
                    "max_tokens": self.max_tokens,
                    "temperature": self.temperature,
                    "system": system_prompt,
                    "messages": [
                        {"role": "user", "content": user_prompt}
                    ]
                },
                timeout=30
            )

            if resp.status_code != 200:
                self.logger.error(f"Haiku API error {resp.status_code}: {resp.text[:200]}")
                return None

            data = resp.json()

            # Track usage
            usage = data.get("usage", {})
            input_tokens = usage.get("input_tokens", 0)
            output_tokens = usage.get("output_tokens", 0)
            self.budget.log_call(input_tokens, output_tokens)

            # Extract text response
            content = data.get("content", [])
            text = ""
            for block in content:
                if block.get("type") == "text":
                    text += block.get("text", "")

            return text

        except Exception as e:
            self.logger.error(f"Haiku API call failed: {e}")
            return None

    def _read_memory(self):
        """Read current memory file"""
        try:
            with open(self.memory_path, "r") as f:
                return f.read()
        except:
            return "(no memory file found)"

    def _update_memory(self, new_entry):
        """Append a new entry to memory under Past Decisions"""
        try:
            memory = self._read_memory()
            timestamp = datetime.now(timezone(timedelta(hours=-5))).strftime("%-m/%-d %-I:%M%p")

            # Find the Past Decisions section and append
            if "## Past Decisions" in memory:
                memory = memory.replace(
                    "## Past Decisions",
                    f"## Past Decisions\n- {timestamp}: {new_entry}",
                    1
                )
            else:
                memory += f"\n## Past Decisions\n- {timestamp}: {new_entry}\n"

            with open(self.memory_path, "w") as f:
                f.write(memory)

            self.logger.info(f"Memory updated: {new_entry[:80]}...")

        except Exception as e:
            self.logger.error(f"Memory update failed: {e}")

    def _get_recent_trades(self, db_path, limit=50):
        """Pull recent trades from a bot's database"""
        try:
            conn = sqlite3.connect(db_path)
            c = conn.cursor()

            c.execute("""
                SELECT id, timestamp, asset, side, entry_price, binance_movement,
                       stake, settled, won, pnl
                FROM trades
                ORDER BY id DESC
                LIMIT ?
            """, (limit,))

            trades = []
            for row in c.fetchall():
                trades.append({
                    "id": row[0],
                    "time": row[1],
                    "asset": row[2],
                    "side": row[3],
                    "entry": row[4],
                    "movement": row[5],
                    "stake": row[6],
                    "settled": row[7],
                    "won": row[8],
                    "pnl": row[9]
                })

            conn.close()
            return trades

        except Exception as e:
            self.logger.error(f"Trade fetch error: {e}")
            return []

    def _get_rolling_stats(self, db_path, window=50):
        """Calculate rolling stats for a bot"""
        try:
            conn = sqlite3.connect(db_path)
            c = conn.cursor()

            c.execute("""
                SELECT COUNT(*) as total,
                       SUM(CASE WHEN won = 1 THEN 1 ELSE 0 END) as wins,
                       SUM(pnl) as total_pnl,
                       AVG(entry_price) as avg_entry,
                       AVG(ABS(binance_movement)) as avg_movement
                FROM (
                    SELECT * FROM trades
                    WHERE settled = 1
                    ORDER BY id DESC
                    LIMIT ?
                )
            """, (window,))

            row = c.fetchone()
            conn.close()

            if not row or not row[0]:
                return None

            total, wins, pnl, avg_entry, avg_movement = row
            return {
                "total": total,
                "wins": wins,
                "losses": total - wins,
                "win_rate": (wins / total * 100) if total > 0 else 0,
                "total_pnl": pnl or 0,
                "avg_entry": avg_entry or 0,
                "avg_movement": avg_movement or 0
            }

        except Exception as e:
            self.logger.error(f"Stats error: {e}")
            return None

    def _detect_loss_streak(self, db_path):
        """Detect consecutive losses"""
        try:
            conn = sqlite3.connect(db_path)
            c = conn.cursor()

            c.execute("""
                SELECT won FROM trades
                WHERE settled = 1
                ORDER BY id DESC
                LIMIT 10
            """)

            results = [row[0] for row in c.fetchall()]
            conn.close()

            streak = 0
            for won in results:
                if won == 0:
                    streak += 1
                else:
                    break

            return streak

        except:
            return 0

    def run_scheduled_analysis(self, bots_config):
        """Run full scheduled analysis across all bots"""
        memory = self._read_memory()

        # Gather data from all bots
        bot_data = {}
        for bot_name, bot_config in bots_config.items():
            if not bot_config.get("enabled"):
                continue

            db_path = bot_config["db_path"]
            trades = self._get_recent_trades(db_path, limit=50)
            stats = self._get_rolling_stats(db_path, window=50)
            loss_streak = self._detect_loss_streak(db_path)

            bot_data[bot_name] = {
                "recent_trades": trades[:20],  # Send last 20 to save tokens
                "stats": stats,
                "loss_streak": loss_streak
            }

        system_prompt = """You are Jarvis, an AI trading bot manager. You monitor Polymarket trading bots and provide actionable analysis.

Your job:
1. Analyze recent trade data and identify patterns
2. Compare current performance to historical baselines
3. Recommend specific parameter changes when warranted
4. Update the memory log with new learnings

RULES:
- Be specific with numbers. "Win rate dropped" is useless. "Win rate dropped from 89% to 78% over last 20 trades" is actionable.
- Only recommend changes backed by data (10+ trade sample minimum)
- Distinguish between normal variance and real signal
- If everything looks fine, say so. Don't invent problems.

RESPONSE FORMAT (JSON):
{
    "summary": "1-2 sentence overall assessment",
    "observations": ["specific observation 1", "specific observation 2"],
    "recommendations": [
        {
            "action": "change_movement_filter",
            "description": "Raise movement filter from 0.2% to 0.25%",
            "reason": "12 of 15 losses in last 50 trades had movement between 0.2-0.25%",
            "priority": "medium",
            "requires_approval": true
        }
    ],
    "memory_updates": ["New pattern: ...", "Confirmed: ..."],
    "risk_alerts": ["any urgent issues"]
}"""

        user_prompt = f"""## CURRENT MEMORY
{memory}

## BOT DATA
{json.dumps(bot_data, indent=2, default=str)}

## TIMESTAMP
{datetime.now(timezone(timedelta(hours=-5))).isoformat()}

Analyze the current state of all bots. What patterns do you see? Any recommendations?"""

        response = self._call_haiku(system_prompt, user_prompt)

        if not response:
            return None

        # Parse JSON response
        try:
            # Strip markdown code fences if present
            clean = response.strip()
            
            # Find JSON object in the response (Haiku sometimes adds text around it)
            json_start = clean.find('{')
            json_end = clean.rfind('}')
            
            if json_start >= 0 and json_end > json_start:
                json_str = clean[json_start:json_end + 1]
                analysis = json.loads(json_str)
            else:
                # No JSON found, treat entire response as summary
                analysis = {"summary": clean[:500], "observations": [], "recommendations": [], "memory_updates": [], "risk_alerts": []}

            # Update memory with new learnings
            for update in analysis.get("memory_updates", []):
                self._update_memory(update)

            self.logger.info(f"Analysis complete: {analysis.get('summary', 'No summary')[:100]}")
            return analysis

        except json.JSONDecodeError:
            self.logger.warning(f"Could not parse Haiku JSON response, storing raw")
            return {"summary": response, "observations": [], "recommendations": [], "raw": True}

    def run_triggered_analysis(self, trigger_reason, bot_name, bot_config):
        """Run analysis triggered by an anomaly (loss streak, crash, etc)"""
        memory = self._read_memory()
        db_path = bot_config["db_path"]
        trades = self._get_recent_trades(db_path, limit=30)
        stats = self._get_rolling_stats(db_path, window=30)

        system_prompt = """You are Jarvis, responding to an anomaly in a trading bot. Be concise and actionable.

RESPONSE FORMAT (JSON):
{
    "diagnosis": "what happened and why",
    "severity": "low|medium|high|critical",
    "immediate_action": {"action": "...", "requires_approval": true/false},
    "explanation": "1-2 sentences for the user"
}"""

        user_prompt = f"""TRIGGER: {trigger_reason}
BOT: {bot_name}
STATS: {json.dumps(stats, default=str)}
RECENT TRADES: {json.dumps(trades[:15], default=str)}
MEMORY: {memory[:1000]}"""

        response = self._call_haiku(system_prompt, user_prompt)

        if not response:
            return None

        try:
            clean = response.strip().strip("`").strip()
            if clean.startswith("json"):
                clean = clean[4:].strip()
            return json.loads(clean)
        except:
            return {"diagnosis": response, "severity": "unknown", "raw": True}

