#!/bin/bash
# ============================================================================
# JARVIS SETUP SCRIPT
# Run this on your VPS: bash setup.sh
# ============================================================================

set -e

echo "============================================"
echo "  JARVIS SETUP"
echo "============================================"

JARVIS_DIR="/root/jarvis"

# Create directory structure
echo "Creating directories..."
mkdir -p $JARVIS_DIR/modules
mkdir -p $JARVIS_DIR/memory
mkdir -p $JARVIS_DIR/logs
mkdir -p $JARVIS_DIR/templates

# Create virtual environment
echo "Setting up Python venv..."
cd $JARVIS_DIR
python3 -m venv venv
source venv/bin/activate

# Install dependencies
echo "Installing dependencies..."
pip install flask pyyaml requests python-dotenv anthropic

# Copy .env from sharbel-bot (has all the keys we need)
if [ -f /root/sharbel-bot/.env ]; then
    echo "Copying .env from sharbel-bot..."
    cp /root/sharbel-bot/.env $JARVIS_DIR/.env
    echo ""
    echo "IMPORTANT: Add these lines to $JARVIS_DIR/.env:"
    echo "  ANTHROPIC_API_KEY=sk-ant-api03-your-key-here"
    echo "  GITHUB_TOKEN=ghp_your-token-here"
fi

# Setup git repo
echo "Setting up git repo..."
REPO_DIR="/root/jarvis-trading-system"
mkdir -p $REPO_DIR
cd $REPO_DIR

if [ ! -d ".git" ]; then
    git init
    git config user.name "Jarvis"
    git config user.email "jarvis@polymarket-bot"

    echo "# Jarvis Trading System" > README.md
    echo "" >> README.md
    echo "Automated trading bot management system." >> README.md
    echo "Changes tracked by Jarvis AI manager." >> README.md

    cat > .gitignore << 'EOF'
.env
*.env
__pycache__/
*.pyc
venv/
*.db
*.log
.DS_Store
node_modules/
EOF

    git add .
    git commit -m "jarvis: initial repository setup"

    echo ""
    echo "IMPORTANT: Connect to GitHub:"
    echo "  cd /root/jarvis-trading-system"
    echo "  git remote add origin https://YOUR_TOKEN@github.com/YOUR_USERNAME/jarvis-trading-system.git"
    echo "  git push -u origin main"
fi

# Install systemd service
echo "Installing systemd service..."
cp $JARVIS_DIR/jarvis.service /etc/systemd/system/jarvis.service
systemctl daemon-reload
systemctl enable jarvis

echo ""
echo "============================================"
echo "  SETUP COMPLETE"
echo "============================================"
echo ""
echo "Next steps:"
echo ""
echo "1. Edit $JARVIS_DIR/.env and add:"
echo "   ANTHROPIC_API_KEY=your-key-here"
echo "   GITHUB_TOKEN=your-token-here"
echo ""
echo "2. Connect GitHub repo:"
echo "   cd /root/jarvis-trading-system"
echo "   git remote add origin https://TOKEN@github.com/USER/jarvis-trading-system.git"
echo "   git push -u origin main"
echo ""
echo "3. Start Jarvis:"
echo "   systemctl start jarvis"
echo ""
echo "4. Check status:"
echo "   systemctl status jarvis"
echo "   journalctl -u jarvis -f"
echo ""
echo "5. Open dashboard:"
echo "   http://77.42.86.194:6000"
echo ""
echo "============================================"
