"""
Lab Tracker — ° perfume target list manager
=============================================
Handles /lab commands from Telegram. Uses Haiku to parse natural language
into structured entries, then updates the Obsidian vault markdown table.

Statuses:
  target    — reverse engineering, active formulation goal
  reference — studying for inspiration, not cloning
  watching  — on the radar, undecided
  killed    — ruled out

Usage examples:
  /lab Rettre Seongsu — reverse engineering this
  /lab Maison Margiela Beach Walk — love the dry down, want to study it
  /lab Le Labo Santal 33 — maybe someday
  /lab Creed Aventus — too mainstream, not interested
  /lab update Santal 33 — actually killing this one
"""

import json
import re
import subprocess
from datetime import datetime


TARGETS_FILE = "/root/obsidian-vault/°-lab/05-targets/Perfume Targets.md"
VAULT_PATH   = "/root/obsidian-vault"

SYSTEM_PROMPT = """You are a parser for a perfume lab tracking system. Extract structured data from a natural language message about a perfume.

Return ONLY valid JSON with these fields:
  brand           — brand name (string)
  name            — perfume name (string)
  status          — one of: target, reference, watching, killed
  degree_estimate — temperature estimate as string like "~64°" if mentioned, otherwise null
  note            — the user's comment cleaned up as a short phrase (max 12 words)
  is_update       — true if the user is updating an existing entry, false if adding new

Status inference rules:
  target    — "reverse engineer", "clone", "recreate", "reformulate", "making this", "already own"
  reference — "study", "learn from", "inspiration", "understand", "research"
  watching  — "maybe", "someday", "not sure", "keep an eye", "interesting"
  killed    — "not interested", "ruling out", "too mainstream", "not for me", "kill", "remove"
  update    — user says "update", "change", "move to", "now a", "actually"

Return only the JSON object, no other text."""


class LabTracker:
    def __init__(self, analyst, logger):
        self.analyst = analyst
        self.logger  = logger

    def handle(self, text):
        """Parse message, update vault file, return confirmation string."""
        try:
            parsed = self._parse(text)
            if not parsed:
                return "Couldn't parse that. Try: /lab Brand Name — your note about it"

            brand  = parsed.get("brand", "").strip()
            name   = parsed.get("name", "").strip()
            status = parsed.get("status", "watching").strip()
            degree = parsed.get("degree_estimate") or "—"
            note   = parsed.get("note", "").strip()
            is_upd = parsed.get("is_update", False)
            date   = datetime.now().strftime("%Y-%m-%d")

            if not brand or not name:
                return "Couldn't extract brand/name. Try: /lab Maison Margiela Beach Walk — love the dry down"

            updated = self._update_file(brand, name, status, degree, note, date, is_upd)
            self._git_push(brand, name, status)

            action = "Updated" if updated else "Added"
            status_icon = {"target": "🎯", "reference": "📖", "watching": "👀", "killed": "❌"}.get(status, "•")
            return (
                f"{status_icon} {action}: {brand} — {name}\n"
                f"Status: {status}\n"
                f"Note: {note}\n"
                f"Vault updated."
            )

        except Exception as e:
            self.logger.error(f"LabTracker error: {e}")
            return f"Error updating lab: {e}"

    def _parse(self, text):
        """Use Haiku to parse natural language into structured fields."""
        # Strip the /lab prefix
        body = re.sub(r'^/lab\s*', '', text, flags=re.IGNORECASE).strip()
        if not body:
            return None

        response = self.analyst._call_haiku(SYSTEM_PROMPT, body)
        if not response:
            return None

        try:
            # Strip markdown code fences if present
            clean = re.sub(r'```(?:json)?\s*|\s*```', '', response).strip()
            return json.loads(clean)
        except json.JSONDecodeError:
            self.logger.error(f"LabTracker: failed to parse Haiku JSON: {response!r}")
            return None

    def _update_file(self, brand, name, status, degree, note, date, is_update):
        """
        Update the markdown table. If entry exists (matching brand+name), replace the row.
        If new, append. Returns True if updated existing, False if added new.
        """
        with open(TARGETS_FILE, "r") as f:
            content = f.read()

        lines = content.split("\n")
        new_row = f"| {brand} | {name} | {status} | {degree} | {note} | {date} |"

        # Check if entry already exists (case-insensitive brand+name match)
        updated = False
        new_lines = []
        for line in lines:
            if line.startswith("|") and not line.startswith("| Brand") and not line.startswith("|----"):
                cols = [c.strip() for c in line.split("|") if c.strip()]
                if (len(cols) >= 2 and
                    cols[0].lower() == brand.lower() and
                    cols[1].lower() == name.lower()):
                    new_lines.append(new_row)
                    updated = True
                    continue
            new_lines.append(line)

        if not updated:
            # Append before trailing blank lines
            insert_at = len(new_lines)
            while insert_at > 0 and new_lines[insert_at - 1].strip() == "":
                insert_at -= 1
            new_lines.insert(insert_at, new_row)

        with open(TARGETS_FILE, "w") as f:
            f.write("\n".join(new_lines))

        return updated

    def _git_push(self, brand, name, status):
        """Commit and push the vault."""
        try:
            subprocess.run(["git", "-C", VAULT_PATH, "add", "-A"], check=True, capture_output=True)
            msg = f"lab: {status} — {brand} {name}"
            subprocess.run(["git", "-C", VAULT_PATH, "commit", "-m", msg], check=True, capture_output=True)
            subprocess.run(["git", "-C", VAULT_PATH, "push"], check=True, capture_output=True)
        except subprocess.CalledProcessError as e:
            self.logger.warning(f"LabTracker git push failed: {e}")
