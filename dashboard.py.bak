"""
Jarvis Dashboard - Command Center Hub
Port 6000 - Modular tabs for each bot + global controls
"""

from flask import Flask, render_template_string, jsonify, request


def create_dashboard_app(jarvis_instance):
    app = Flask(__name__)
    jarvis = jarvis_instance

    DASHBOARD_HTML = '''
<!DOCTYPE html>
<html lang="en">
<head>
    <meta charset="UTF-8">
    <title>JARVIS Command Center</title>
    <style>
        @import url('https://fonts.googleapis.com/css2?family=JetBrains+Mono:wght@300;400;500;600;700&family=Space+Grotesk:wght@400;500;600;700&display=swap');

        :root {
            --bg-deep: #06080d;
            --bg-panel: #0d1117;
            --bg-card: #151b25;
            --bg-hover: #1c2333;
            --border: #21262d;
            --text: #e6edf3;
            --text-dim: #7d8590;
            --accent: #58a6ff;
            --green: #3fb950;
            --red: #f85149;
            --yellow: #d29922;
            --orange: #db6d28;
            --purple: #bc8cff;
        }

        * { margin: 0; padding: 0; box-sizing: border-box; }

        body {
            font-family: 'Space Grotesk', sans-serif;
            background: var(--bg-deep);
            color: var(--text);
            min-height: 100vh;
        }

        /* --- HEADER --- */
        .header {
            background: var(--bg-panel);
            border-bottom: 1px solid var(--border);
            padding: 16px 24px;
            display: flex;
            justify-content: space-between;
            align-items: center;
        }
        .header h1 {
            font-size: 1.4em;
            font-weight: 600;
            letter-spacing: 2px;
        }
        .header h1 span { color: var(--accent); }
        .header-status {
            display: flex;
            gap: 16px;
            align-items: center;
            font-family: 'JetBrains Mono', monospace;
            font-size: 0.85em;
        }
        .pulse {
            width: 8px; height: 8px;
            background: var(--green);
            border-radius: 50%;
            animation: pulse 2s infinite;
        }
        @keyframes pulse {
            0%, 100% { opacity: 1; }
            50% { opacity: 0.3; }
        }

        /* --- TABS --- */
        .tabs {
            display: flex;
            background: var(--bg-panel);
            border-bottom: 1px solid var(--border);
            padding: 0 24px;
        }
        .tab {
            padding: 12px 20px;
            cursor: pointer;
            font-size: 0.9em;
            font-weight: 500;
            color: var(--text-dim);
            border-bottom: 2px solid transparent;
            transition: all 0.2s;
        }
        .tab:hover { color: var(--text); }
        .tab.active { color: var(--accent); border-bottom-color: var(--accent); }

        /* --- MAIN LAYOUT --- */
        .main {
            display: grid;
            grid-template-columns: 1fr 380px;
            gap: 0;
            height: calc(100vh - 100px);
        }
        .content {
            padding: 20px;
            overflow-y: auto;
        }
        .content::-webkit-scrollbar { width: 6px; }
        .content::-webkit-scrollbar-track { background: var(--bg-deep); }
        .content::-webkit-scrollbar-thumb { background: var(--border); border-radius: 3px; }
        .content::-webkit-scrollbar-thumb:hover { background: var(--text-dim); }
        .sidebar {
            background: var(--bg-panel);
            border-left: 1px solid var(--border);
            display: flex;
            flex-direction: column;
            height: calc(100vh - 100px);
            overflow: hidden;
        }

        /* --- STAT CARDS --- */
        .stats-grid {
            display: grid;
            grid-template-columns: repeat(auto-fit, minmax(180px, 1fr));
            gap: 12px;
            margin-bottom: 20px;
        }
        .stat-card {
            background: var(--bg-card);
            border: 1px solid var(--border);
            border-radius: 8px;
            padding: 16px;
        }
        .stat-label {
            font-size: 0.75em;
            color: var(--text-dim);
            text-transform: uppercase;
            letter-spacing: 1px;
            margin-bottom: 6px;
        }
        .stat-value {
            font-family: 'JetBrains Mono', monospace;
            font-size: 1.6em;
            font-weight: 600;
        }
        .stat-sub {
            font-size: 0.8em;
            color: var(--text-dim);
            margin-top: 4px;
        }

        /* --- HEALTH INDICATORS --- */
        .health-grid {
            display: grid;
            grid-template-columns: repeat(auto-fit, minmax(280px, 1fr));
            gap: 12px;
            margin-bottom: 20px;
        }
        .health-card {
            background: var(--bg-card);
            border: 1px solid var(--border);
            border-radius: 8px;
            padding: 16px;
            display: flex;
            justify-content: space-between;
            align-items: center;
        }
        .health-card .name { font-weight: 600; }
        .health-card .detail { font-size: 0.8em; color: var(--text-dim); margin-top: 4px; }
        .health-badge {
            padding: 4px 12px;
            border-radius: 12px;
            font-size: 0.8em;
            font-weight: 600;
            font-family: 'JetBrains Mono', monospace;
        }
        .health-HEALTHY { background: rgba(63,185,80,0.15); color: var(--green); }
        .health-DEAD { background: rgba(248,81,73,0.15); color: var(--red); }
        .health-STALE { background: rgba(210,153,34,0.15); color: var(--yellow); }

        /* --- BUDGET BAR --- */
        .budget-section { margin-bottom: 20px; }
        .budget-bar-container {
            background: var(--bg-card);
            border: 1px solid var(--border);
            border-radius: 8px;
            padding: 16px;
        }
        .budget-row {
            display: flex;
            justify-content: space-between;
            align-items: center;
            margin-bottom: 8px;
            font-size: 0.85em;
        }
        .budget-bar {
            width: 100%;
            height: 8px;
            background: var(--bg-deep);
            border-radius: 4px;
            overflow: hidden;
            margin: 6px 0;
        }
        .budget-fill {
            height: 100%;
            border-radius: 4px;
            transition: width 0.5s;
        }
        .fill-green { background: var(--green); }
        .fill-yellow { background: var(--yellow); }
        .fill-red { background: var(--red); }

        /* --- APPROVAL QUEUE --- */
        .approval-card {
            background: var(--bg-card);
            border: 1px solid var(--yellow);
            border-radius: 8px;
            padding: 14px;
            margin-bottom: 10px;
        }
        .approval-card .desc { font-weight: 500; margin-bottom: 6px; }
        .approval-card .reason { font-size: 0.8em; color: var(--text-dim); margin-bottom: 10px; }
        .approval-actions { display: flex; gap: 8px; }
        .btn {
            padding: 6px 16px;
            border: none;
            border-radius: 6px;
            font-size: 0.85em;
            font-weight: 600;
            cursor: pointer;
            font-family: 'Space Grotesk', sans-serif;
        }
        .btn-approve { background: var(--green); color: #000; }
        .btn-reject { background: var(--red); color: #fff; }
        .btn-approve:hover { opacity: 0.85; }
        .btn-reject:hover { opacity: 0.85; }

        /* --- CHAT / LOG --- */
        .chat-section {
            flex: 1;
            display: flex;
            flex-direction: column;
            overflow: hidden;
            min-height: 0;
        }
        .chat-header {
            padding: 12px 16px;
            border-bottom: 1px solid var(--border);
            font-weight: 600;
            font-size: 0.9em;
            flex-shrink: 0;
        }
        .chat-messages {
            flex: 1;
            overflow-y: auto;
            padding: 12px 16px;
            font-family: 'JetBrains Mono', monospace;
            font-size: 0.78em;
            line-height: 1.6;
            min-height: 0;
        }
        .chat-messages::-webkit-scrollbar { width: 6px; }
        .chat-messages::-webkit-scrollbar-track { background: var(--bg-deep); }
        .chat-messages::-webkit-scrollbar-thumb { background: var(--border); border-radius: 3px; }
        .chat-messages::-webkit-scrollbar-thumb:hover { background: var(--text-dim); }
        .chat-msg {
            margin-bottom: 6px;
            padding: 4px 0;
            word-wrap: break-word;
            overflow-wrap: break-word;
        }
        .chat-msg .time { color: var(--text-dim); }
        .chat-msg .src-jarvis { color: var(--accent); }
        .chat-msg .src-watchdog { color: var(--yellow); }
        .chat-msg .src-haiku { color: var(--purple); }
        .chat-msg .src-user { color: var(--green); }
        .chat-msg.level-error .msg { color: var(--red); }
        .chat-msg.level-warning .msg { color: var(--yellow); }
        .chat-msg.level-success .msg { color: var(--green); }

        .chat-input-area {
            padding: 12px 16px;
            border-top: 1px solid var(--border);
            display: flex;
            gap: 8px;
            flex-shrink: 0;
        }
        .chat-input {
            flex: 1;
            background: var(--bg-deep);
            border: 1px solid var(--border);
            border-radius: 6px;
            padding: 8px 12px;
            color: var(--text);
            font-family: 'JetBrains Mono', monospace;
            font-size: 0.85em;
        }
        .chat-input:focus { outline: none; border-color: var(--accent); }
        .chat-send {
            background: var(--accent);
            color: #000;
            border: none;
            border-radius: 6px;
            padding: 8px 16px;
            font-weight: 600;
            cursor: pointer;
        }

        /* --- GIT LOG --- */
        .git-log {
            background: var(--bg-card);
            border: 1px solid var(--border);
            border-radius: 8px;
            padding: 14px;
            font-family: 'JetBrains Mono', monospace;
            font-size: 0.78em;
            max-height: 200px;
            overflow-y: auto;
        }
        .git-log div {
            padding: 3px 0;
            color: var(--text-dim);
        }
        .git-log div span { color: var(--accent); }

        .section-title {
            font-size: 0.85em;
            font-weight: 600;
            text-transform: uppercase;
            letter-spacing: 1px;
            color: var(--text-dim);
            margin-bottom: 10px;
        }
    </style>
</head>
<body>

<div class="header">
    <h1><span>J.A.R.V.I.S</span> Command Center</h1>
    <div class="header-status">
        <div class="pulse"></div>
        <span id="uptime">ONLINE</span>
        <span style="color: var(--text-dim)">|</span>
        <span id="header-budget">$0.00 today</span>
    </div>
</div>

<div class="tabs">
    <div class="tab active" data-tab="polymarket">Polymarket</div>
    <div class="tab" data-tab="global">Global</div>
</div>

<div class="main">
    <div class="content" id="content-area">
        <!-- Populated by JS -->
    </div>
    <div class="sidebar">
        <div class="chat-section">
            <div class="chat-header">Activity Log</div>
            <div class="chat-messages" id="chat-messages"></div>
            <div class="chat-input-area">
                <input class="chat-input" id="chat-input" placeholder="Command Jarvis..." />
                <button class="chat-send" id="chat-send">Send</button>
            </div>
        </div>
    </div>
</div>

<script>
let currentTab = 'polymarket';

// Tab switching
document.querySelectorAll('.tab').forEach(tab => {
    tab.addEventListener('click', () => {
        document.querySelectorAll('.tab').forEach(t => t.classList.remove('active'));
        tab.classList.add('active');
        currentTab = tab.dataset.tab;
        refresh();
    });
});

// Chat input
document.getElementById('chat-send').addEventListener('click', sendCommand);
document.getElementById('chat-input').addEventListener('keypress', (e) => {
    if (e.key === 'Enter') sendCommand();
});

function sendCommand() {
    const input = document.getElementById('chat-input');
    const cmd = input.value.trim();
    if (!cmd) return;
    input.value = '';

    fetch('/api/command', {
        method: 'POST',
        headers: {'Content-Type': 'application/json'},
        body: JSON.stringify({command: cmd})
    }).then(() => setTimeout(refresh, 500));
}

function approveAction(actionId) {
    fetch('/api/approve', {
        method: 'POST',
        headers: {'Content-Type': 'application/json'},
        body: JSON.stringify({action_id: actionId})
    }).then(() => refresh());
}

function rejectAction(actionId) {
    fetch('/api/reject', {
        method: 'POST',
        headers: {'Content-Type': 'application/json'},
        body: JSON.stringify({action_id: actionId})
    }).then(() => refresh());
}

function getBudgetColor(pct) {
    if (pct < 50) return 'fill-green';
    if (pct < 80) return 'fill-yellow';
    return 'fill-red';
}

function renderPolymarket(state) {
    const health = state.health || {};
    const stats = state.stats || {};
    const budget = state.budget || {};
    const approvals = state.approvals || {};
    const commits = state.git_commits || [];

    // Stats for Sharbel
    const sh = stats.sharbel || {};
    const hy = stats.hybrid || {};

    let html = '';

    // Health cards
    html += '<div class="section-title">Bot Health</div><div class="health-grid">';
    for (const [name, h] of Object.entries(health)) {
        if (h.status === 'disabled') continue;
        const status = h.health || 'UNKNOWN';
        const db = h.database || {};
        const lastTrade = db.last_trade ? new Date(db.last_trade).toLocaleString('en-US', {timeZone: 'America/New_York'}) : 'N/A';
        html += `
            <div class="health-card">
                <div>
                    <div class="name">${name}</div>
                    <div class="detail">Last trade: ${lastTrade}</div>
                </div>
                <div class="health-badge health-${status}">${status}</div>
            </div>`;
    }
    html += '</div>';

    // Stats
    html += '<div class="section-title">Performance (Last 50 Trades)</div><div class="stats-grid">';
    if (sh.total) {
        html += `
            <div class="stat-card">
                <div class="stat-label">Sharbel Win Rate</div>
                <div class="stat-value" style="color: ${sh.win_rate >= 85 ? 'var(--green)' : sh.win_rate >= 75 ? 'var(--yellow)' : 'var(--red)'}">${sh.win_rate?.toFixed(1) || 0}%</div>
                <div class="stat-sub">${sh.wins}W / ${sh.losses}L</div>
            </div>
            <div class="stat-card">
                <div class="stat-label">Sharbel P&L</div>
                <div class="stat-value" style="color: ${sh.total_pnl >= 0 ? 'var(--green)' : 'var(--red)'}">$${sh.total_pnl?.toFixed(2) || '0.00'}</div>
                <div class="stat-sub">${sh.total} trades</div>
            </div>`;
    }
    if (hy.total) {
        html += `
            <div class="stat-card">
                <div class="stat-label">Hybrid Win Rate</div>
                <div class="stat-value" style="color: ${hy.win_rate >= 85 ? 'var(--green)' : 'var(--yellow)'}">${hy.win_rate?.toFixed(1) || 0}%</div>
                <div class="stat-sub">${hy.wins}W / ${hy.losses}L (paper)</div>
            </div>
            <div class="stat-card">
                <div class="stat-label">Hybrid P&L</div>
                <div class="stat-value" style="color: var(--green)">$${hy.total_pnl?.toFixed(2) || '0.00'}</div>
                <div class="stat-sub">${hy.total} trades (paper)</div>
            </div>`;
    }
    html += '</div>';

    // Budget
    const daily = budget.daily || {};
    const monthly = budget.monthly || {};
    html += `
        <div class="section-title">API Budget</div>
        <div class="budget-bar-container">
            <div class="budget-row">
                <span>Daily: $${daily.cost?.toFixed(4) || '0.00'} / $${daily.limit || 2}</span>
                <span>${daily.calls || 0} / ${daily.max_calls || 12} calls</span>
            </div>
            <div class="budget-bar"><div class="budget-fill ${getBudgetColor(daily.percent || 0)}" style="width: ${daily.percent || 0}%"></div></div>
            <div class="budget-row" style="margin-top: 12px;">
                <span>Monthly: $${monthly.cost?.toFixed(4) || '0.00'} / $${monthly.limit || 30}</span>
                <span>${monthly.calls || 0} calls</span>
            </div>
            <div class="budget-bar"><div class="budget-fill ${getBudgetColor(monthly.percent || 0)}" style="width: ${monthly.percent || 0}%"></div></div>
        </div>`;

    // Approval Queue
    const pending = approvals.pending || [];
    if (pending.length > 0) {
        html += '<div class="section-title" style="margin-top: 20px;">Pending Approvals</div>';
        for (const action of pending) {
            html += `
                <div class="approval-card">
                    <div class="desc">${action.description}</div>
                    <div class="reason">${action.reason}</div>
                    <div class="approval-actions">
                        <button class="btn btn-approve" onclick="approveAction('${action.id}')">Approve</button>
                        <button class="btn btn-reject" onclick="rejectAction('${action.id}')">Reject</button>
                    </div>
                </div>`;
        }
    }

    // Git log
    if (commits.length > 0) {
        html += '<div class="section-title" style="margin-top: 20px;">Git History</div><div class="git-log">';
        for (const c of commits) {
            const parts = c.split(' ');
            const hash = parts[0];
            const rest = parts.slice(1).join(' ');
            html += `<div><span>${hash}</span> ${rest}</div>`;
        }
        html += '</div>';
    }

    return html;
}

function renderGlobal(state) {
    const budget = state.budget || {};
    const approvals = state.approvals || {};
    const history = approvals.recent_history || [];

    let html = '<div class="section-title">All Activity History</div>';
    html += '<div class="git-log" style="max-height: 400px;">';
    for (const a of history.reverse()) {
        const icon = a.status === 'auto_approved' ? '⚡' : a.status === 'approved' ? '✅' : a.status === 'rejected' ? '❌' : a.status === 'blocked' ? '🚫' : '⏳';
        html += `<div>${icon} [${a.submitted_at?.slice(11,19) || ''}] ${a.description} <span>(${a.status})</span></div>`;
    }
    html += '</div>';

    return html;
}

function renderChat(chatLog) {
    const container = document.getElementById('chat-messages');
    let html = '';
    for (const msg of chatLog) {
        html += `<div class="chat-msg level-${msg.level}">
            <span class="time">${msg.time}</span>
            <span class="src-${msg.source}">[${msg.source}]</span>
            <span class="msg">${msg.message}</span>
        </div>`;
    }
    container.innerHTML = html;
    container.scrollTop = container.scrollHeight;
}

function refresh() {
    fetch('/api/state').then(r => r.json()).then(state => {
        const content = document.getElementById('content-area');

        if (currentTab === 'polymarket') {
            content.innerHTML = renderPolymarket(state);
        } else {
            content.innerHTML = renderGlobal(state);
        }

        renderChat(state.chat_log || []);

        // Update header budget
        const daily = state.budget?.daily || {};
        document.getElementById('header-budget').textContent = `$${daily.cost?.toFixed(4) || '0.00'} today`;
    });
}

// Initial load + auto-refresh
refresh();
setInterval(refresh, 5000);
</script>
</body>
</html>
'''

    @app.route('/')
    def index():
        return render_template_string(DASHBOARD_HTML)

    @app.route('/api/state')
    def api_state():
        return jsonify(jarvis.get_dashboard_state())

    @app.route('/api/command', methods=['POST'])
    def api_command():
        data = request.get_json()
        cmd = data.get("command", "")
        if cmd:
            jarvis.handle_user_command(cmd)
        return jsonify({"ok": True})

    @app.route('/api/approve', methods=['POST'])
    def api_approve():
        data = request.get_json()
        action_id = data.get("action_id")
        if action_id:
            action = jarvis.approvals.approve_action(action_id)
            if action:
                jarvis.executor.execute_action(action)
                jarvis._log_chat("user", f"Approved: {action['description']}", "success")
        return jsonify({"ok": True})

    @app.route('/api/reject', methods=['POST'])
    def api_reject():
        data = request.get_json()
        action_id = data.get("action_id")
        if action_id:
            action = jarvis.approvals.reject_action(action_id)
            if action:
                jarvis._log_chat("user", f"Rejected: {action['description']}", "info")
        return jsonify({"ok": True})

    return app
