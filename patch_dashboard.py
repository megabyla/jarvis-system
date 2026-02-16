#!/usr/bin/env python3
"""
Patch dashboard.py to add Futures tab.
Run from ~/jarvis/
Back up first: cp dashboard.py dashboard.py.bak
"""

import os

DASHBOARD_PATH = "/root/jarvis/dashboard.py"

with open(DASHBOARD_PATH, "r") as f:
    content = f.read()

if "renderFutures" in content:
    print("Already patched!")
    exit(0)

# 1. Add Futures tab button
content = content.replace(
    '<div class="tab" data-tab="global">Global</div>',
    '<div class="tab" data-tab="futures">Futures</div>\n    <div class="tab" data-tab="global">Global</div>'
)

# 2. Add renderFutures function before renderGlobal
futures_render = '''
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

'''

content = content.replace(
    'function renderGlobal(state) {',
    futures_render + 'function renderGlobal(state) {'
)

# 3. Add futures to the refresh/tab rendering logic
content = content.replace(
    """if (currentTab === 'polymarket') {
            content.innerHTML = renderPolymarket(state);
        } else {
            content.innerHTML = renderGlobal(state);
        }""",
    """if (currentTab === 'polymarket') {
            content.innerHTML = renderPolymarket(state);
        } else if (currentTab === 'futures') {
            content.innerHTML = renderFutures(state);
        } else {
            content.innerHTML = renderGlobal(state);
        }"""
)

with open(DASHBOARD_PATH, "w") as f:
    f.write(content)

print("✅ Dashboard patched — Futures tab added!")
print("Restart Jarvis to see changes: sudo systemctl restart jarvis")
