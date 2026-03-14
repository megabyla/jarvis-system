"""
Korean Tracker — reads 서연's word_bank.db and returns stats for JARVIS reporting.
Fires in the morning brief if 언니 hasn't practiced yet.
"""

import sqlite3
from datetime import date, datetime, timedelta, timezone
from pathlib import Path

SEOYEON_DB = Path("/root/seoyeon/word_bank.db")


def get_stats() -> dict | None:
    """Return Korean learning stats. Returns None if DB doesn't exist."""
    if not SEOYEON_DB.exists():
        return None
    try:
        conn = sqlite3.connect(SEOYEON_DB)
        c = conn.cursor()

        today = date.today()

        # Streak
        c.execute("SELECT DISTINCT date FROM sessions ORDER BY date DESC")
        dates = [date.fromisoformat(r[0]) for r in c.fetchall()]
        streak = 0
        for i, d in enumerate(dates):
            if (today - d).days == i:
                streak += 1
            else:
                break

        # Practiced today? Check sessions first, then fall back to messages table
        c.execute("SELECT duration_minutes, words_introduced FROM sessions WHERE date = ? ORDER BY start_time DESC LIMIT 1",
                  (today.isoformat(),))
        today_row = c.fetchone()

        # Also check messages table — use a 24h rolling window so evening sessions
        # (stored as UTC timestamps) aren't missed by next morning's ET-based check.
        talked_today = False
        try:
            cutoff = (datetime.now(timezone.utc) - timedelta(hours=24)).strftime("%Y-%m-%dT%H:%M:%S")
            c.execute("SELECT COUNT(*) FROM messages WHERE role='user' AND timestamp >= ?",
                      (cutoff,))
            talked_today = c.fetchone()[0] > 0
        except Exception:
            pass

        # Days since last activity (session OR message)
        c.execute("SELECT date FROM sessions ORDER BY date DESC LIMIT 1")
        last_row = c.fetchone()
        days_absent = (today - date.fromisoformat(last_row[0])).days if last_row else None

        # If talked in the last 24h via messages but no formal session, treat as active
        if talked_today:
            days_absent = 0

        # This week
        week_ago = (today - timedelta(days=7)).isoformat()
        c.execute("SELECT COUNT(*) FROM words WHERE date_added >= ?", (week_ago,))
        words_this_week = c.fetchone()[0]

        # Totals
        c.execute("SELECT COUNT(*) FROM words WHERE mastered = 1")
        mastered = c.fetchone()[0]
        c.execute("SELECT COUNT(*) FROM words")
        total_words = c.fetchone()[0]

        conn.close()
        return {
            "streak_days":     streak,
            "practiced_today": today_row is not None or talked_today,
            "today_minutes":   round(today_row[0], 1) if today_row else 0,
            "today_words":     today_row[1] if today_row else 0,
            "words_this_week": words_this_week,
            "total_words":     total_words,
            "mastered":        mastered,
            "days_absent":     days_absent,
        }
    except Exception:
        return None


def morning_brief_line() -> str | None:
    """
    Returns a one-line Korean status for JARVIS morning brief.
    Returns None if everything is fine (언니 practiced recently).
    Only pings if언니 hasn't practiced in 1+ days.
    """
    stats = get_stats()
    if not stats:
        return None

    days = stats.get("days_absent", 0) or 0

    if days == 0:
        return None  # Practiced today — no need to ping

    streak_emoji = "🔥" if stats["streak_days"] >= 3 else "📚"
    if days == 1:
        return f"{streak_emoji} 서연 hasn't heard from you in 1 day | streak: {stats['streak_days']}d | {stats['total_words']} words total"
    elif days == 2:
        return f"📚 서연 hasn't heard from you in 2 days 👀 | streak: {stats['streak_days']}d"
    else:
        return f"⚠️ 서연 hasn't heard from you in {days} days | streak lost"


def weekly_summary() -> str:
    """Returns a multi-line weekly Korean summary for JARVIS Sunday report."""
    stats = get_stats()
    if not stats:
        return "서연: no data yet"

    streak_bar = "🔥" * min(stats["streak_days"], 7)
    lines = [
        "━━━ 서연 Korean Report ━━━",
        f"Streak:       {stats['streak_days']} days {streak_bar}",
        f"Words (week): {stats['words_this_week']} new",
        f"Total words:  {stats['total_words']} | Mastered: {stats['mastered']}",
    ]
    if not stats["practiced_today"]:
        lines.append("⚠️  Not practiced today")
    return "\n".join(lines)
