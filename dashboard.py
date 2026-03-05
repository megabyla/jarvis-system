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
            --cyan: #39d0d0;
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
        .chat-msg .src-strategies { color: var(--cyan); }

        /* --- STRATEGY PILLS --- */
        .pill {
            display: inline-block;
            padding: 3px 10px;
            border-radius: 10px;
            font-size: 0.75em;
            font-weight: 700;
            font-family: 'JetBrains Mono', monospace;
            letter-spacing: 0.5px;
        }
        .pill-ghost { background: rgba(188,140,255,0.15); color: var(--purple); border: 1px solid rgba(188,140,255,0.3); }
        .pill-surge { background: rgba(57,208,208,0.15); color: var(--cyan);   border: 1px solid rgba(57,208,208,0.3); }
        .pill-active  { background: rgba(63,185,80,0.15);  color: var(--green); }
        .pill-pending { background: rgba(210,153,34,0.15); color: var(--yellow); }
        .pill-idle    { background: rgba(125,133,144,0.12); color: var(--text-dim); }

        /* --- STRATEGY CARDS --- */
        .strat-card {
            background: var(--bg-card);
            border: 1px solid var(--border);
            border-radius: 8px;
            padding: 16px;
            margin-bottom: 16px;
        }
        .strat-card-header {
            display: flex;
            justify-content: space-between;
            align-items: center;
            margin-bottom: 14px;
        }
        .strat-card-title {
            font-weight: 700;
            font-size: 1em;
            display: flex;
            align-items: center;
            gap: 10px;
        }
        .strat-metrics {
            display: grid;
            grid-template-columns: repeat(auto-fit, minmax(120px, 1fr));
            gap: 10px;
            margin-bottom: 14px;
        }
        .strat-metric {
            background: var(--bg-panel);
            border-radius: 6px;
            padding: 10px 12px;
        }
        .strat-metric .lbl { font-size: 0.72em; color: var(--text-dim); text-transform: uppercase; letter-spacing: 0.8px; margin-bottom: 4px; }
        .strat-metric .val { font-family: 'JetBrains Mono', monospace; font-size: 1.1em; font-weight: 600; }
        .trade-row { display: flex; gap: 8px; align-items: center; padding: 5px 0; border-bottom: 1px solid var(--border); font-size: 0.8em; font-family: 'JetBrains Mono', monospace; }
        .trade-row:last-child { border-bottom: none; }
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
    <div class="tab" data-tab="futures">Futures</div>
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
    // Ghost + Surge strategy cards (same grid, appended before closing div)
    const q = state.strategies || {};
    const gh = q.ghost  || {};
    const su = q.surge  || {};

    function ghostStatePill(st) {
        const map = {
            'in_trade':       ['IN TRADE',  'var(--purple)', 'rgba(188,140,255,0.18)'],
            'signal_pending': ['ENTERING',  'var(--yellow)', 'rgba(210,153,34,0.15)'],
            'exit_pending':   ['EXITING',   'var(--orange)', 'rgba(219,109,40,0.15)'],
            'idle':           ['IDLE',      'var(--text-dim)', 'rgba(125,133,144,0.1)'],
        };
        const [label, color, bg] = map[st] || map['idle'];
        return `<span class="health-badge" style="background:${bg};color:${color}">${label}</span>`;
    }
    function surgeStatePill(st) {
        const map = {
            'comp_pending': ['WATCHING', 'var(--cyan)',     'rgba(57,208,208,0.15)'],
            'idle':         ['IDLE',     'var(--text-dim)', 'rgba(125,133,144,0.1)'],
        };
        const [label, color, bg] = map[st] || map['idle'];
        return `<span class="health-badge" style="background:${bg};color:${color}">${label}</span>`;
    }

    const ghostDetail = gh.state === 'in_trade'
        ? `Day ${gh.days_held}/7  ·  entry ${gh.entry_price?.toFixed(2) || '—'}`
        : gh.state === 'signal_pending' ? `Signal fired ${gh.signal_date || ''} · entering tomorrow`
        : gh.state === 'exit_pending'   ? `Exit signal fired · exiting tomorrow`
        : gh.trades ? `${gh.trades} trades · WR ${gh.win_rate || '—'}%` : 'Watching daily RSI(2)';

    const surgeDetail = su.state === 'comp_pending'
        ? `🟢 ${su.comp_high?.toFixed(2)}  ·  🔴 ${su.comp_low?.toFixed(2)}`
        : su.trades ? `${su.trades} trades · WR ${su.win_rate || '—'}%` : 'Watching daily compression';

    html += `
        <div class="health-card" style="border-left: 2px solid var(--purple)">
            <div>
                <div class="name" style="color:var(--purple)">👻 Ghost</div>
                <div class="detail">${ghostDetail}</div>
            </div>
            ${ghostStatePill(gh.state || 'idle')}
        </div>
        <div class="health-card" style="border-left: 2px solid var(--cyan)">
            <div>
                <div class="name" style="color:var(--cyan)">📡 Surge</div>
                <div class="detail">${surgeDetail}</div>
            </div>
            ${surgeStatePill(su.state || 'idle')}
        </div>
    </div>
    </div>`;

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


function renderFutures(state) {
    const ft = state.futures || {};
    const stats = ft.stats || {};
    const levels = ft.levels || {};
    const eqStats = stats.eq_rejections || {};
    const biasStats = stats.bias_accuracy || {};
    const recent = stats.recent_signals || [];

    let html = '';

    // Bias card
    const biasColor = ft.bias === 'BULL' ? 'var(--green)' : ft.bias === 'BEAR' ? 'var(--red)' : 'var(--text-dim)';
    const biasIcon = ft.bias === 'BULL' ? '🟢' : ft.bias === 'BEAR' ? '🔴' : '⚪';

    html += '<div class="section-title">Pre-Market Bias</div><div class="stats-grid">';
    html += `
        <div class="stat-card">
            <div class="stat-label">Strat Sequence</div>
            <div class="stat-value" style="font-size: 1.3em;">${ft.sequence || 'N/A'}</div>
        </div>
        <div class="stat-card">
            <div class="stat-label">Bias</div>
            <div class="stat-value" style="color: ${biasColor}">${biasIcon} ${ft.bias || 'N/A'}</div>
        </div>
        <div class="stat-card">
            <div class="stat-label">Signal Today</div>
            <div class="stat-value" style="color: ${ft.signal_today ? 'var(--green)' : 'var(--text-dim)'}">${ft.signal_today ? '✅ YES' : '—'}</div>
        </div>`;
    html += '</div>';

    // Key levels
    if (levels.pdh) {
        html += '<div class="section-title">Key Levels</div><div class="stats-grid">';
        html += `
            <div class="stat-card">
                <div class="stat-label" style="color: var(--red)">PDH</div>
                <div class="stat-value" style="font-size: 1.3em;">${levels.pdh?.toFixed(2)}</div>
            </div>
            <div class="stat-card">
                <div class="stat-label" style="color: var(--yellow)">EQ (Midpoint)</div>
                <div class="stat-value" style="font-size: 1.3em;">${levels.pd_eq?.toFixed(2)}</div>
            </div>
            <div class="stat-card">
                <div class="stat-label" style="color: var(--green)">PDL</div>
                <div class="stat-value" style="font-size: 1.3em;">${levels.pdl?.toFixed(2)}</div>
            </div>
            <div class="stat-card">
                <div class="stat-label">PD Range</div>
                <div class="stat-value" style="font-size: 1.3em;">${levels.pd_range?.toFixed(1)} pts</div>
            </div>`;
        html += '</div>';
    }

    // EQ Rejection performance
    if (eqStats.total > 0) {
        const wr1r = eqStats.total > 0 ? (eqStats.wins_1r / eqStats.total * 100).toFixed(1) : '0';
        const wr2r = eqStats.total > 0 ? (eqStats.wins_2r / eqStats.total * 100).toFixed(1) : '0';
        const wr3r = eqStats.total > 0 ? (eqStats.wins_3r / eqStats.total * 100).toFixed(1) : '0';

        html += '<div class="section-title">EQ Rejection Performance</div><div class="stats-grid">';
        html += `
            <div class="stat-card">
                <div class="stat-label">Total Signals</div>
                <div class="stat-value">${eqStats.total}</div>
            </div>
            <div class="stat-card">
                <div class="stat-label">1R Win Rate</div>
                <div class="stat-value" style="color: ${wr1r >= 70 ? 'var(--green)' : 'var(--yellow)'}">${wr1r}%</div>
                <div class="stat-sub">${eqStats.wins_1r}/${eqStats.total}</div>
            </div>
            <div class="stat-card">
                <div class="stat-label">2R Win Rate</div>
                <div class="stat-value" style="color: ${wr2r >= 60 ? 'var(--green)' : 'var(--yellow)'}">${wr2r}%</div>
                <div class="stat-sub">${eqStats.wins_2r}/${eqStats.total}</div>
            </div>
            <div class="stat-card">
                <div class="stat-label">3R Win Rate</div>
                <div class="stat-value">${wr3r}%</div>
                <div class="stat-sub">${eqStats.wins_3r}/${eqStats.total}</div>
            </div>`;
        html += '</div>';
    }

    // Strat bias accuracy
    if (biasStats.total > 0) {
        html += '<div class="section-title">Strat Bias Accuracy</div><div class="stats-grid">';
        html += `
            <div class="stat-card">
                <div class="stat-label">Bias Accuracy</div>
                <div class="stat-value" style="color: ${biasStats.pct >= 70 ? 'var(--green)' : 'var(--yellow)'}">${biasStats.pct?.toFixed(1)}%</div>
                <div class="stat-sub">${biasStats.correct}/${biasStats.total} correct</div>
            </div>`;
        html += '</div>';
    }

    // Recent signals
    if (recent.length > 0) {
        html += '<div class="section-title" style="margin-top: 20px;">Recent Signals</div>';
        html += '<div class="git-log" style="max-height: 300px;">';
        for (const s of recent) {
            const icon = s.direction === 'LONG' ? '🟢' : '🔴';
            const outcomeIcon = s.outcome === 'win' ? '✅' : s.outcome === 'loss' ? '❌' : '⏳';
            html += `<div>${icon} ${s.date} | ${s.direction} @ ${s.entry?.toFixed(2)} | Stop: ${s.stop_dist?.toFixed(1)}pts | ${s.sequence} | ${outcomeIcon} ${s.outcome || 'pending'}</div>`;
        }
        html += '</div>';
    }

    // No data state
    if (!ft.sequence && !ft.enabled) {
        html += `<div style="text-align: center; padding: 60px 20px; color: var(--text-dim);">
            <div style="font-size: 2em; margin-bottom: 12px;">📊</div>
            <div>Futures module not active.</div>
            <div style="margin-top: 8px;">Type <span style="color: var(--accent);">futures</span> or <span style="color: var(--accent);">bias</span> to activate.</div>
        </div>`;
    } else if (!ft.sequence) {
        html += `<div style="text-align: center; padding: 60px 20px; color: var(--text-dim);">
            <div style="font-size: 2em; margin-bottom: 12px;">⏳</div>
            <div>Waiting for pre-market data...</div>
            <div style="margin-top: 8px;">Bias will populate at 9:00 AM ET.</div>
            <div style="margin-top: 4px;">Type <span style="color: var(--accent);">futures</span> to force refresh.</div>
        </div>`;
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
        } else if (currentTab === 'futures') {
            content.innerHTML = renderFutures(state);
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

    @app.route('/webhook/tv', methods=['POST'])
    def webhook_tradingview():
        """TradingView webhook endpoint"""
        try:
            data = request.get_json()
            if jarvis.trade_logger and jarvis.trade_logger.enabled:
                jarvis.trade_logger.handle_webhook(data)
                return jsonify({"ok": True})
            return jsonify({"error": "trade_logger not enabled"}), 400
        except Exception as e:
            jarvis.logger.error(f"Webhook error: {e}")
            return jsonify({"error": str(e)}), 500
    
    @app.route('/api/telegram_callback', methods=['POST'])
    def telegram_callback():
        """Handle Telegram button callbacks"""
        try:
            data = request.get_json()
            callback_data = data.get('callback_query', {}).get('data', '')
            
            if not jarvis.trade_logger:
                return jsonify({"ok": False})
            
            # Parse callback: confirm_123, skip_123, win_123, loss_123, manual_123
            parts = callback_data.split('_')
            if len(parts) != 2:
                return jsonify({"ok": False})
            
            action, id_str = parts
            item_id = int(id_str)
            
            if action == 'confirm':
                jarvis.trade_logger.confirm_trade(item_id)
            elif action == 'skip':
                jarvis.trade_logger.skip_trade(item_id)
            elif action == 'win':
                jarvis.trade_logger.close_trade('WIN')
            elif action == 'loss':
                jarvis.trade_logger.close_trade('LOSS')
            elif action == 'manual':
                jarvis.trade_logger.close_trade('MANUAL')
            
            return jsonify({"ok": True})
        except Exception as e:
            jarvis.logger.error(f"Telegram callback error: {e}")
            return jsonify({"ok": False})
