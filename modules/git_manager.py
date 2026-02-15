"""
Jarvis Git Manager
Auto-commits changes to GitHub with meaningful commit messages.
"""

import subprocess
import os
from datetime import datetime, timezone, timedelta


class GitManager:
    def __init__(self, config, logger):
        self.config = config
        self.logger = logger
        self.git_config = config.get("git", {})
        self.enabled = self.git_config.get("enabled", False)
        self.repo_path = self.git_config.get("repo_path", "")
        self.prefix = self.git_config.get("commit_prefix", "jarvis:")

    def _run_git(self, args, cwd=None):
        """Run a git command"""
        try:
            result = subprocess.run(
                ["git"] + args,
                capture_output=True,
                text=True,
                timeout=30,
                cwd=cwd or self.repo_path
            )
            return result.returncode == 0, result.stdout.strip(), result.stderr.strip()
        except Exception as e:
            return False, "", str(e)

    def init_repo(self):
        """Initialize git repo if it doesn't exist"""
        if not self.enabled:
            return False

        if not os.path.exists(self.repo_path):
            os.makedirs(self.repo_path, exist_ok=True)

        git_dir = os.path.join(self.repo_path, ".git")
        if not os.path.exists(git_dir):
            success, out, err = self._run_git(["init"])
            if success:
                self.logger.info("Git repo initialized")

                # Create .gitignore
                gitignore_path = os.path.join(self.repo_path, ".gitignore")
                with open(gitignore_path, "w") as f:
                    f.write("""# Secrets
.env
*.env
.env.*

# API keys
*api_key*
*secret*
*private_key*

# Python
__pycache__/
*.pyc
*.pyo
venv/
.venv/

# Databases (tracked separately)
*.db

# OS
.DS_Store
Thumbs.db

# Logs
*.log

# Node
node_modules/
""")

                self._run_git(["add", ".gitignore"])
                self._run_git(["commit", "-m", f"{self.prefix} initial setup with .gitignore"])

                return True
            else:
                self.logger.error(f"Git init failed: {err}")
                return False

        return True

    def commit_change(self, files, message, reason=""):
        """Commit specific files with a descriptive message"""
        if not self.enabled:
            return False

        full_message = f"{self.prefix} {message}"
        if reason:
            full_message += f"\n\nReason: {reason}"

        # Add timestamp
        est = datetime.now(timezone(timedelta(hours=-5)))
        full_message += f"\n\nTimestamp: {est.strftime('%Y-%m-%d %I:%M%p EST')}"

        try:
            # Stage files
            for f in files:
                self._run_git(["add", f])

            # Check if there are staged changes
            success, out, _ = self._run_git(["diff", "--cached", "--name-only"])
            if not out.strip():
                self.logger.info("No changes to commit")
                return False

            # Commit
            success, out, err = self._run_git(["commit", "-m", full_message])
            if success:
                self.logger.info(f"Committed: {message}")

                # Auto-push if configured
                if self.git_config.get("auto_push", False):
                    self.push()

                return True
            else:
                self.logger.error(f"Commit failed: {err}")
                return False

        except Exception as e:
            self.logger.error(f"Git commit error: {e}")
            return False

    def push(self):
        """Push to remote"""
        if not self.enabled:
            return False

        remote = self.git_config.get("remote", "origin")
        branch = self.git_config.get("branch", "main")

        success, out, err = self._run_git(["push", remote, branch])
        if success:
            self.logger.info(f"Pushed to {remote}/{branch}")
            return True
        else:
            self.logger.warning(f"Push failed: {err}")
            return False

    def get_recent_commits(self, limit=10):
        """Get recent commit log"""
        success, out, _ = self._run_git([
            "log", f"--oneline", f"-{limit}", "--format=%h %s (%ar)"
        ])

        if success and out:
            return out.strip().split("\n")
        return []

    def sync_bot_files(self, bot_name, bot_config):
        """Copy current bot files to repo for tracking"""
        if not self.enabled:
            return

        src_dir = bot_config["directory"]
        dst_dir = os.path.join(self.repo_path, bot_name)
        os.makedirs(dst_dir, exist_ok=True)

        # Copy Python files (not .env, not .db)
        import shutil
        for filename in os.listdir(src_dir):
            if filename.endswith(".py"):
                src = os.path.join(src_dir, filename)
                dst = os.path.join(dst_dir, filename)
                shutil.copy2(src, dst)

        self.logger.info(f"Synced {bot_name} files to repo")
