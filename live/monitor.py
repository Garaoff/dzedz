"""
Monitoring dashboard — Interface web pour surveiller le bot en temps réel.

RÈGLE 9 : Affiche des chiffres bruts, pas de conclusions générales.
RÈGLE 6 : Pas d'échec silencieux.

Lance depuis scripts/start_dashboard.py.
Accède sur http://localhost:5000
"""

import logging
from flask import Flask, jsonify, render_template_string

logger = logging.getLogger(__name__)

app = Flask(__name__)

# Reference to the bot instance — set by start_bot.py
bot_instance = None


HTML_TEMPLATE = """
<!DOCTYPE html>
<html lang="fr">
<head>
    <meta charset="UTF-8">
    <meta name="viewport" content="width=device-width, initial-scale=1.0">
    <title>Bot SMC/ICT v2 — Monitoring</title>
    <style>
        * { font-family: 'Segoe UI', monospace; margin: 0; padding: 0; }
        body { background: #0a0a0a; color: #e0e0e0; padding: 20px; }
        .header { font-size: 24px; color: #00ff88; margin-bottom: 20px; border-bottom: 2px solid #00ff88; }
        .stats { display: grid; grid-template-columns: repeat(3, 1fr); gap: 15px; margin-bottom: 20px; }
        .stat-box { background: #1a1a2e; padding: 15px; border-radius: 8px; border: 1px solid #333; }
        .stat-box .label { color: #888; font-size: 12px; }
        .stat-box .value { color: #00ff88; font-size: 24px; font-weight: bold; }
        .stat-box .value.negative { color: #ff4444; }
        .stat-box .value.warning { color: #ff8800; }
        .trades { background: #1a1a2e; padding: 15px; border-radius: 8px; border: 1px solid #333; }
        .trades h3 { color: #00ff88; margin-bottom: 10px; }
        .symbols { background: #1a1a2e; padding: 15px; border-radius: 8px; border: 1px solid #333; margin-bottom: 20px; }
        .symbols h3 { color: #00ff88; margin-bottom: 10px; }
        .trade-row { display: grid; grid-template-columns: repeat(8, 1fr); padding: 8px; border-bottom: 1px solid #222; font-size: 13px; }
        .kill-switch { margin-top: 20px; padding: 15px; background: #2a0000; border-radius: 8px; border: 2px solid #ff0000; }
        .kill-switch.active { background: #4a0000; }
        .kill-switch .status { font-size: 18px; color: #ff0000; }
        .kill-switch .status.safe { color: #00ff88; }
        .refresh { margin-top: 10px; color: #888; font-size: 11px; }
        .btn { background: #333; color: #e0e0e0; padding: 8px 16px; border: 1px solid #555;
               border-radius: 4px; cursor: pointer; font-size: 14px; margin: 5px; }
        .btn:hover { background: #444; }
        .btn.danger { background: #4a0000; border-color: #ff0000; }
        .btn.danger:hover { background: #6a0000; }
    </style>
</head>
<body>
    <div class="header">🤖 Bot SMC/ICT v2 — Live Monitoring</div>
    
    <div class="stats">
        <div class="stat-box">
            <div class="label">CAPITAL</div>
            <div class="value" id="capital">—</div>
        </div>
        <div class="stat-box">
            <div class="label">PnL JOURNALIER</div>
            <div class="value" id="daily_pnl">—</div>
        </div>
        <div class="stat-box">
            <div class="label">LOSS % JOURNALIER</div>
            <div class="value" id="daily_loss_pct">—</div>
        </div>
        <div class="stat-box">
            <div class="label">SIGNAUX TOTAL</div>
            <div class="value" id="total_signals">—</div>
        </div>
        <div class="stat-box">
            <div class="label">ORDRES ENVOYÉS</div>
            <div class="value" id="orders_sent">—</div>
        </div>
        <div class="stat-box">
            <div class="label">ORDRES REJETÉS</div>
            <div class="value" id="orders_rejected">—</div>
        </div>
        <div class="stat-box">
            <div class="label">TRADES/JOUR</div>
            <div class="value" id="daily_trades">—</div>
        </div>
        <div class="stat-box">
            <div class="label">POSITIONS OUVERTES</div>
            <div class="value" id="open_positions">—</div>
        </div>
        <div class="stat-box">
            <div class="label">MODE</div>
            <div class="value" id="mode">—</div>
        </div>
    </div>
    
    <div class="symbols">
        <h3>Symboles : XAUUSD 🥇 | NAS100 📊 | BTCUSD ₿</h3>
        <div id="symbol_stats">
            <div class="trade-row">
                <span>Symbole</span>
                <span>Trades/j</span>
                <span>PnL/j</span>
                <span>Signaux</span>
                <span>Ordres</span>
                <span>Rejetés</span>
            </div>
        </div>
    </div>
    
    <div class="trades">
        <h3>Trades ouverts</h3>
        <div id="trades_list">
            <div class="trade-row">
                <span>Ticket</span>
                <span>Direction</span>
                <span>Entry</span>
                <span>SL</span>
                <span>TP</span>
                <span>PnL</span>
                <span>BE</span>
                <span>Conf</span>
            </div>
        </div>
    </div>
    
    <div class="kill-switch">
        <div class="label">KILL SWITCH</div>
        <div class="status" id="kill_status">—</div>
        <div id="kill_reason" style="font-size: 12px; color: #888;"></div>
        <button class="btn danger" onclick="manualStop()">🛑 STOP MANUEL</button>
    </div>
    
    <div class="refresh">Auto-refresh every 5s | Ctrl+C to stop</div>
    
    <script>
        function refresh() {
            fetch('/api/status')
                .then(r => r.json())
                .then(data => {
                    document.getElementById('capital').textContent = '$' + data.capital.toFixed(2);
                    
                    const pnlEl = document.getElementById('daily_pnl');
                    pnlEl.textContent = '$' + data.daily_pnl.toFixed(2);
                    pnlEl.className = 'value' + (data.daily_pnl < 0 ? ' negative' : '');
                    
                    const lossEl = document.getElementById('daily_loss_pct');
                    lossEl.textContent = data.daily_loss_pct.toFixed(2) + '%';
                    lossEl.className = 'value' + (data.daily_loss_pct < -1 ? ' warning' : '') + (data.daily_loss_pct < -3 ? ' negative' : '');
                    
                    document.getElementById('total_signals').textContent = data.total_signals;
                    document.getElementById('orders_sent').textContent = data.total_orders_sent;
                    document.getElementById('orders_rejected').textContent = data.total_orders_rejected;
                    document.getElementById('daily_trades').textContent = data.daily_trades;
                    document.getElementById('open_positions').textContent = data.open_positions;
                    document.getElementById('mode').textContent = data.mode.toUpperCase();
                    
                    const killEl = document.getElementById('kill_status');
                    killEl.textContent = data.kill_switch_active ? '🔴 ACTIVÉ' : '🟢 SAFE';
                    killEl.className = 'status' + (data.kill_switch_active ? '' : ' safe');
                    document.getElementById('kill_reason').textContent = data.kill_switch_reason || '';
                    
                    // Symbols stats
                    const symList = document.getElementById('symbol_stats');
                    if (data.symbol_stats) {
                        let symHtml = '<div class="trade-row"><span>Symbole</span><span>Trades/j</span><span>PnL/j</span><span>Signaux</span><span>Ordres</span><span>Rejetés</span></div>';
                        Object.entries(data.symbol_stats).forEach(([sym, stats]) => {
                            symHtml += `<div class="trade-row">
                                <span>${sym}</span>
                                <span>${stats.daily_trades}</span>
                                <span>${stats.daily_pnl.toFixed(2)}</span>
                                <span>${stats.total_signals}</span>
                                <span>${stats.total_orders_sent}</span>
                                <span>${stats.total_orders_rejected}</span>
                            </div>`;
                        });
                        symList.innerHTML = symHtml;
                    }
                    
                    // Trades
                    fetch('/api/trades')
                        .then(r => r.json())
                        .then(trades => {
                            const list = document.getElementById('trades_list');
                            list.innerHTML = '<div class="trade-row"><span>Ticket</span><span>Dir</span><span>Entry</span><span>SL</span><span>TP</span><span>PnL</span><span>BE</span><span>Conf</span></div>';
                            trades.trades.forEach(t => {
                                list.innerHTML += `<div class="trade-row">
                                    <span>${t.ticket}</span>
                                    <span>${t.direction}</span>
                                    <span>${t.entry.toFixed(5)}</span>
                                    <span>${t.sl.toFixed(5)}</span>
                                    <span>${t.tp.toFixed(5)}</span>
                                    <span>${t.pnl.toFixed(2)}</span>
                                    <span>${t.be_reached ? '✅' : '—'}</span>
                                    <span>${t.confluence}</span>
                                </div>`;
                            });
                        });
                })
                .catch(e => console.error('Fetch error:', e));
        }
        
        function manualStop() {
            fetch('/api/stop', {method: 'POST'})
                .then(r => r.json())
                .then(data => { refresh(); });
        }
        
        refresh();
        setInterval(refresh, 5000);  // STRUCTURAL: 5s refresh
    </script>
</body>
</html>
"""


@app.route("/")
def index():
    """Page principale du dashboard."""
    return render_template_string(HTML_TEMPLATE)


@app.route("/api/status")
def api_status():
    """API : statut du bot — chiffres bruts (Règle 9)."""
    if bot_instance is None:
        return jsonify({
            "capital": 0, "daily_pnl": 0, "daily_loss_pct": 0,
            "total_signals": 0, "total_orders_sent": 0, "total_orders_rejected": 0,
            "daily_trades": 0, "open_positions": 0, "mode": "unknown",
            "kill_switch_active": False, "kill_switch_reason": "bot not started",
            "running": False,
        })
    
    status = bot_instance.get_status()
    kill_status = bot_instance.kill_switch.get_status()
    
    return jsonify({
        "capital": status.get("capital", 0),
        "daily_pnl": status.get("daily_pnl", 0),
        "daily_loss_pct": status.get("daily_loss_pct", 0),
        "total_signals": status.get("total_signals", 0),
        "total_orders_sent": status.get("total_orders_sent", 0),
        "total_orders_rejected": status.get("total_orders_rejected", 0),
        "daily_trades": status.get("daily_trades", 0),
        "open_positions": status.get("open_positions", 0),
        "mode": status.get("mode", "unknown"),
        "running": status.get("running", False),
        "kill_switch_active": kill_status.get("is_active", False),
        "kill_switch_reason": kill_status.get("reason", ""),
        "symbol_stats": status.get("symbol_stats", {}),
    })


@app.route("/api/trades")
def api_trades():
    """API : trades ouverts — chiffres bruts."""
    if bot_instance is None:
        return jsonify({"trades": []})
    
    return jsonify(bot_instance.trade_manager.get_stats())


@app.route("/api/stop", methods=["POST"])
def api_stop():
    """API : arrêt manuel du bot."""
    if bot_instance is None:
        return jsonify({"success": False, "reason": "bot not running"})
    
    bot_instance.kill_switch.manual_stop("dashboard_manual_stop")
    bot_instance.running = False
    
    return jsonify({"success": True, "message": "Bot stopped by dashboard"})


def start_dashboard(bot=None, port=5000):
    """Lance le dashboard."""
    global bot_instance
    bot_instance = bot
    
    logger.info(f"DASHBOARD_START | port={port} | url=http://localhost:{port}")
    
    app.run(host="0.0.0.0", port=port, debug=False, use_reloader=False)
