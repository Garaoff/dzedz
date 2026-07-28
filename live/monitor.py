"""
Dashboard APEX — Interface professionnelle pour surveiller le bot en temps réel.

RÈGLE 9 : Affiche des chiffres bruts, pas de conclusions générales.
RÈGLE 6 : Pas d'échec silencieux.

Lance depuis scripts/start_dashboard.py.
Accède sur http://localhost:5000

Affiche :
- Moteur de Scenarios (8 scenarios avec probabilités)
- Killzone ICT active + timer
- PO3 phase (Accumulation/Manipulation/Distribution)
- MSS status
- 13 concepts ICT avec indicateurs
- Trades ouverts avec détails
- Kill Switch
"""

import logging
from flask import Flask, jsonify, render_template_string

from core.displacement import measure_displacement

logger = logging.getLogger(__name__)

app = Flask(__name__)

bot_instance = None


HTML_TEMPLATE = """
<!DOCTYPE html>
<html lang="fr">
<head>
<meta charset="UTF-8">
<meta name="viewport" content="width=device-width, initial-scale=1.0">
<title>SMC/ICT v2 — APEX Dashboard</title>
<style>
:root{--bg0:#05060f;--bg1:#0d1117;--bg2:#161b22;--bg3:#1c2333;--border:#30363d;--green:#00ff88;--red:#ff4757;--orange:#ffa502;--blue:#3b82f6;--cyan:#06b6d4;--purple:#a855f7;--gold:#fbbf24;--silver:#94a3b8;--text:#e6edf3;--text2:#8b949e;--text3:#484f58;}
*{margin:0;padding:0;box-sizing:border-box;font-family:'JetBrains Mono','Fira Code','Cascadia Code',monospace;}
body{background:var(--bg0);color:var(--text);overflow-x:hidden;}
.glow{animation:glow 2s ease-in-out infinite alternate;}
@keyframes glow{from{text-shadow:0 0 5px var(--green);}to{text-shadow:0 0 20px var(--green),0 0 40px var(--green);}}
.pulse{animation:pulse 1.5s ease-in-out infinite;}
@keyframes pulse{0%,100%{opacity:1;}50%{opacity:0.5;}}
.fade-in{animation:fadeIn 0.5s ease-in;}
@keyframes fadeIn{from{opacity:0;}to{opacity:1;}}

/* GRID */
.dashboard{display:grid;grid-template-columns:1fr 1fr 1fr;gap:12px;padding:12px;max-width:1800px;margin:0 auto;}
.full-row{grid-column:1/-1;}

/* HEADER */
.header{display:flex;align-items:center;justify-content:space-between;padding:12px 20px;background:var(--bg1);border-bottom:2px solid var(--green);margin-bottom:0;}
.header-left{display:flex;align-items:center;gap:12px;}
.header h1{font-size:20px;color:var(--green);font-weight:700;letter-spacing:2px;}
.header .version{color:var(--text3);font-size:11px;}
.header .live-badge{background:var(--red);color:#fff;padding:2px 8px;border-radius:3px;font-size:10px;font-weight:700;animation:pulse;}
.header .clock{color:var(--text2);font-size:13px;}

/* CARD */
.card{background:var(--bg1);border:1px solid var(--border);border-radius:8px;padding:14px;position:relative;}
.card::before{content:'';position:absolute;top:0;left:0;right:0;height:1px;background:linear-gradient(90deg,transparent,var(--green),transparent);opacity:0.3;}
.card-title{font-size:12px;color:var(--text2);letter-spacing:1px;margin-bottom:10px;display:flex;align-items:center;gap:6px;}
.card-title .icon{font-size:14px;}

/* STAT BOX */
.stat-grid{display:grid;grid-template-columns:repeat(3,1fr);gap:8px;}
.stat{background:var(--bg2);padding:10px;border-radius:6px;border:1px solid var(--border);}
.stat .label{font-size:10px;color:var(--text3);letter-spacing:0.5px;margin-bottom:4px;}
.stat .value{font-size:22px;font-weight:700;color:var(--green);}
.stat .value.red{color:var(--red);}
.stat .value.orange{color:var(--orange);}
.stat .value.blue{color:var(--blue);}
.stat .value.purple{color:var(--purple);}
.stat .value.cyan{color:var(--cyan);}
.stat .sub{font-size:9px;color:var(--text3);margin-top:2px;}

/* SCENARIO PANEL */
.scenario-list{display:flex;flex-direction:column;gap:6px;}
.scenario-row{display:flex;align-items:center;gap:8px;padding:6px 10px;background:var(--bg2);border-radius:6px;border:1px solid var(--border);font-size:12px;transition:all 0.3s;}
.scenario-row.primary{border-color:var(--green);background:rgba(0,255,136,0.05);}
.scenario-row.trap{border-color:var(--orange);background:rgba(255,165,2,0.05);}
.scenario-row .name{flex:1;font-weight:600;}
.scenario-row .direction{padding:1px 6px;border-radius:3px;font-size:10px;font-weight:700;}
.scenario-row .direction.long{background:rgba(0,255,136,0.15);color:var(--green);}
.scenario-row .direction.short{background:rgba(255,71,87,0.15);color:var(--red);}
.scenario-row .direction.neutral{background:rgba(139,148,158,0.15);color:var(--text2);}
.prob-bar{width:80px;height:16px;background:var(--bg3);border-radius:3px;overflow:hidden;position:relative;}
.prob-fill{height:100%;border-radius:3px;transition:width 0.5s;}
.prob-fill.green{background:var(--green);}
.prob-fill.orange{background:var(--orange);}
.prob-fill.red{background:var(--red);}
.prob-fill.blue{background:var(--blue);}
.prob-fill.cyan{background:var(--cyan);}
.prob-fill.silver{background:var(--silver);}
.prob-text{font-size:10px;font-weight:600;min-width:40px;text-align:right;}
.scenario-row .action{font-size:9px;color:var(--text3);padding:1px 4px;border-radius:2px;background:var(--bg3);}

/* ICT CONCEPTS */
.ict-grid{display:grid;grid-template-columns:repeat(4,1fr);gap:6px;}
.ict-item{display:flex;align-items:center;gap:6px;padding:8px;background:var(--bg2);border-radius:6px;border:1px solid var(--border);font-size:11px;transition:all 0.3s;}
.ict-item.active{border-color:var(--green);background:rgba(0,255,136,0.03);}
.ict-item.inactive{opacity:0.4;}
.ict-dot{width:8px;height:8px;border-radius:50%;background:var(--text3);}
.ict-dot.on{background:var(--green);box-shadow:0 0 6px var(--green);}
.ict-dot.warn{background:var(--orange);box-shadow:0 0 6px var(--orange);}
.ict-name{flex:1;font-weight:500;}
.ict-val{font-size:9px;color:var(--text3);}

/* KILLZONE */
.kz-bar{display:flex;gap:4px;margin-top:6px;}
.kz-slot{height:24px;border-radius:4px;position:relative;overflow:hidden;font-size:10px;display:flex;align-items:center;justify-content:center;color:#fff;font-weight:700;}
.kz-slot.active{box-shadow:0 0 8px var(--green);}
.kz-slot .fill{position:absolute;top:0;left:0;right:0;bottom:0;background:var(--bg3);}
.kz-slot .active-fill{position:absolute;top:0;left:0;height:100%;background:var(--green);transition:width 1s;}
.kz-slot .label{z-index:2;}

/* PO3 */
.po3-bar{display:flex;gap:2px;margin-top:8px;height:28px;border-radius:6px;overflow:hidden;background:var(--bg3);}
.po3-phase{flex:1;display:flex;align-items:center;justify-content:center;font-size:11px;font-weight:600;transition:all 0.5s;}
.po3-phase.active{filter:brightness(1.5);box-shadow:inset 0 0 10px rgba(255,255,255,0.2);}
.po3-acc{background:rgba(59,130,246,0.3);color:var(--blue);}
.po3-man{background:rgba(255,165,2,0.3);color:var(--orange);}
.po3-dist{background:rgba(0,255,136,0.3);color:var(--green);}

/* TRADE TABLE */
.trade-table{width:100%;border-collapse:collapse;font-size:12px;}
.trade-table th{color:var(--text3);font-size:10px;text-align:left;padding:6px 8px;border-bottom:1px solid var(--border);}
.trade-table td{padding:6px 8px;border-bottom:1px solid var(--border);}
.trade-table tr:hover{background:var(--bg2);}
.trade-table .long{color:var(--green);}
.trade-table .short{color:var(--red);}
.trade-table .pnl-pos{color:var(--green);}
.trade-table .pnl-neg{color:var(--red);}

/* KILL SWITCH */
.kill-section{display:flex;align-items:center;gap:12px;padding:12px;border-radius:8px;border:2px solid var(--red);background:rgba(255,71,87,0.05);}
.kill-section.safe{border-color:var(--green);background:rgba(0,255,136,0.05);}
.kill-status{font-size:16px;font-weight:700;}
.kill-status.active{color:var(--red);}
.kill-status.safe{color:var(--green);}
.kill-reason{font-size:10px;color:var(--text3);flex:1;}
.kill-btn{background:var(--red);color:#fff;padding:6px 14px;border:none;border-radius:4px;font-size:12px;font-weight:700;cursor:pointer;transition:all 0.2s;}
.kill-btn:hover{background:#ff6b81;transform:scale(1.05);}

/* SYMBOL TABLE */
.sym-table{width:100%;border-collapse:collapse;font-size:12px;}
.sym-table th{color:var(--text3);font-size:10px;text-align:left;padding:6px;border-bottom:1px solid var(--border);}
.sym-table td{padding:6px;border-bottom:1px solid var(--border);}

/* FOOTER */
.footer{display:flex;justify-content:space-between;padding:8px 20px;color:var(--text3);font-size:10px;}
</style>
</head>
<body>

<!-- HEADER -->
<div class="header">
    <div class="header-left">
        <h1 class="glow">⚡ SMC/ICT v2</h1>
        <span class="version">APEX ENGINE • 13 CONCEPTS • SCENARIO AI</span>
        <span class="live-badge">LIVE</span>
    </div>
    <div>
        <span class="clock" id="clock">—</span>
    </div>
</div>

<div class="dashboard">

<!-- ROW 1: STATS -->
<div class="card full-row">
    <div class="card-title"><span class="icon">📊</span> PERFORMANCE</div>
    <div class="stat-grid">
        <div class="stat"><div class="label">CAPITAL</div><div class="value" id="capital">—</div><div class="sub" id="capital_currency"></div></div>
        <div class="stat"><div class="label">PnL JOURNALIER</div><div class="value" id="daily_pnl">—</div><div class="sub">net realized</div></div>
        <div class="stat"><div class="label">LOSS % / JOUR</div><div class="value" id="daily_loss_pct">—</div><div class="sub">max: 3%</div></div>
        <div class="stat"><div class="label">SIGNAUX TOTAL</div><div class="value blue" id="total_signals">—</div></div>
        <div class="stat"><div class="label">ORDRES ENVOYÉS</div><div class="value cyan" id="orders_sent">—</div></div>
        <div class="stat"><div class="label">ORDRES REJETÉS</div><div class="value orange" id="orders_rejected">—</div></div>
        <div class="stat"><div class="label">TRADES / JOUR</div><div class="value" id="daily_trades">—</div></div>
        <div class="stat"><div class="label">POSITIONS OUVERTES</div><div class="value purple" id="open_positions">—</div></div>
        <div class="stat"><div class="label">SCENARIO PRIMAIRE</div><div class="value" id="scenario_primary" style="font-size:16px;">—</div></div>
    </div>
</div>

<!-- ROW 2: SCENARIOS + ICT CONCEPTS -->
<div class="card" style="grid-column:span 2;">
    <div class="card-title"><span class="icon">🧠</span> MOTEUR DE SCENARIOS — Anticipation de toutes les éventualités</div>
    <div class="scenario-list" id="scenario_list">
        <div class="scenario-row"><span style="color:var(--text3)">Loading...</span></div>
    </div>
</div>

<div class="card">
    <div class="card-title"><span class="icon">📡</span> 13 CONCEPTS ICT ACTIFS</div>
    <div class="ict-grid" id="ict_grid">
        <div class="ict-item"><div class="ict-dot"></div><span class="ict-name">Loading...</span></div>
    </div>
</div>

<!-- ROW 3: KILLZONE + PO3 + MSS -->
<div class="card">
    <div class="card-title"><span class="icon">⏰</span> KILLZONE ICT</div>
    <div id="kz_info" style="font-size:13px;margin-bottom:4px;">—</div>
    <div class="kz-bar" id="kz_bar"></div>
    <div id="kz_timer" style="font-size:10px;color:var(--text3);margin-top:6px;">—</div>
</div>

<div class="card">
    <div class="card-title"><span class="icon">⚡</span> POWER OF 3 (PO3)</div>
    <div id="po3_info" style="font-size:13px;margin-bottom:2px;">—</div>
    <div class="po3-bar" id="po3_bar">
        <div class="po3-phase po3-acc">ACC</div>
        <div class="po3-phase po3-man">MANIP</div>
        <div class="po3-phase po3-dist">DIST</div>
    </div>
    <div id="po3_detail" style="font-size:10px;color:var(--text3);margin-top:6px;">—</div>
</div>

<div class="card">
    <div class="card-title"><span class="icon">🔥</span> MSS + SIGNAL</div>
    <div id="mss_info" style="font-size:13px;">—</div>
    <div id="signal_info" style="font-size:11px;margin-top:8px;color:var(--text2);">—</div>
    <div id="grade_info" style="font-size:12px;margin-top:4px;">—</div>
</div>

<!-- ROW 4: SYMBOLS + TRADES -->
<div class="card" style="grid-column:span 2;">
    <div class="card-title"><span class="icon">🥇</span> SYMBOLES : XAUUSD • NAS100 • BTCUSD</div>
    <table class="sym-table">
        <thead><tr><th>Symbole</th><th>Trades/j</th><th>PnL/j</th><th>Signaux</th><th>Ordres</th><th>Rejetés</th><th>Tendance</th><th>Zone</th></tr></thead>
        <tbody id="sym_table"><tr><td>—</td></tr></tbody>
    </table>
</div>

<div class="card">
    <div class="card-title"><span class="icon">📈</span> TRADES OUVERTS</div>
    <table class="trade-table">
        <thead><tr><th>Dir</th><th>Entry</th><th>SL</th><th>TP</th><th>PnL</th><th>BE</th><th>Conf</th></tr></thead>
        <tbody id="trade_table"><tr><td>—</td></tr></tbody>
    </table>
</div>

<!-- ROW 5: KILL SWITCH + PDHL -->
<div class="card full-row">
    <div style="display:grid;grid-template-columns:1fr 1fr;gap:12px;">
        <div>
            <div class="card-title"><span class="icon">🛑</span> KILL SWITCH</div>
            <div class="kill-section safe" id="kill_section">
                <div class="kill-status safe" id="kill_status">🟢 SAFE</div>
                <div class="kill-reason" id="kill_reason">—</div>
                <button class="kill-btn" onclick="manualStop()">STOP MANUEL</button>
            </div>
        </div>
        <div>
            <div class="card-title"><span class="icon">🏛️</span> PDHL (Previous Day/Week H/L)</div>
            <div id="pdhl_info" style="font-size:12px;color:var(--text2);">—</div>
        </div>
    </div>
</div>

</div>

<!-- FOOTER -->
<div class="footer">
    <span>Auto-refresh 3s • Règle 9 : chiffres bruts uniquement</span>
    <span id="footer_status">—</span>
</div>

<script>
const REFRESH_MS = 3000;
let lastData = null;

function fmt(n,d=2){return typeof n==='number'?n.toFixed(d):'—';}
function fmt$(n){return typeof n==='number'?'$'+n.toFixed(2):'—';}
function pct(n){return typeof n==='number'?n.toFixed(1)+'%':'—';}

function updateClock(){
    const now=new Date();
    const utc=now.toUTCString().slice(17,25);
    const est_h=(now.getUTCHours()-5)%24;
    document.getElementById('clock').textContent='UTC '+utc+' • EST '+String(est_h).padStart(2,'0')+':'+String(now.getUTCMinutes()).padStart(2,'0');
}
setInterval(updateClock,1000);updateClock();

function refresh(){
    fetch('/api/status').then(r=>r.json()).then(data=>{
        lastData=data;
        updateStats(data);
        updateScenarios(data);
        updateICT(data);
        updateKillzone(data);
        updatePO3(data);
        updateMSS(data);
        updateSymbols(data);
        updateKillSwitch(data);
        updatePDHL(data);
        fetch('/api/trades').then(r=>r.json()).then(t=>updateTrades(t));
    }).catch(e=>console.error('Fetch error:',e));
}

function updateStats(d){
    document.getElementById('capital').textContent=fmt$(d.capital);
    document.getElementById('capital').className='value'+(d.capital>0?'':' red');
    
    const pnlEl=document.getElementById('daily_pnl');
    pnlEl.textContent=fmt$(d.daily_pnl);
    pnlEl.className='value'+(d.daily_pnl>=0?'':' red');
    
    const lossEl=document.getElementById('daily_loss_pct');
    lossEl.textContent=pct(d.daily_loss_pct);
    lossEl.className='value'+(d.daily_loss_pct<-1?' orange':'')+(d.daily_loss_pct<-3?' red':'');
    
    document.getElementById('total_signals').textContent=d.total_signals;
    document.getElementById('orders_sent').textContent=d.total_orders_sent;
    document.getElementById('orders_rejected').textContent=d.total_orders_rejected;
    document.getElementById('daily_trades').textContent=d.daily_trades;
    document.getElementById('open_positions').textContent=d.open_positions;
    
    const sp=d.scenario_primary||'none';
    const spEl=document.getElementById('scenario_primary');
    spEl.textContent=sp.replace(/_/g,' ').toUpperCase();
    spEl.className='value'+(sp.includes('reversal')||sp.includes('distribution_bull')?'':' orange');
    
    document.getElementById('footer_status').textContent='Mode: '+d.mode.toUpperCase()+' • Running: '+d.running;
}

function updateScenarios(d){
    const list=d.scenarios||[];
    if(!list.length){
        document.getElementById('scenario_list').innerHTML='<div class="scenario-row" style="color:var(--text3)">Pipeline non initialisé</div>';
        return;
    }
    let html='';
    const sorted=[...list].sort((a,b)=>b.probability_pct-a.probability_pct);
    sorted.forEach(s=>{
        const isPrimary=s.scenario_type===d.primary_scenario;
        const isTrap=s.scenario_type===d.trap_scenario;
        const cls=isPrimary?'primary':'';
        const trapCls=isTrap?'trap':'';
        const probColor=s.probability_pct>=30?'green':s.probability_pct>=15?'orange':'silver';
        const dirCls=s.direction||'neutral';
        
        html+=`<div class="scenario-row ${cls} ${trapCls}">
            <span class="name">${isPrimary?'🥇 ':''}${isTrap?'⚠️ ':''}${s.scenario_type.replace(/_/g,' ')}</span>
            <span class="direction ${dirCls}">${s.direction}</span>
            <div class="prob-bar"><div class="prob-fill ${probColor}" style="width:${Math.min(s.probability_pct,100)}%"></div></div>
            <span class="prob-text" style="color:var(--${probColor})">${s.probability_pct.toFixed(1)}%</span>
            <span class="action">${s.action}</span>
        </div>`;
    });
    document.getElementById('scenario_list').innerHTML=html;
}

function updateICT(d){
    const concepts=[
        {name:'Structure',active:d.active_swings>0,val:d.active_swings+' swings'},
        {name:'FVG',active:d.active_fvgs>0,val:d.active_fvgs+' actifs'},
        {name:'OB',active:d.active_obs>0,val:d.active_obs+' actifs'},
        {name:'Sweep',active:d.last_sweep_dir!=='none',val:d.last_sweep_dir},
        {name:'Displacement',active:d.displacement_significant,val:d.displacement_atr},
        {name:'Zone',active:true,val:d.zone},
        {name:'HTF Bias',active:d.htf_bias!=='neutral',val:d.htf_bias},
        {name:'Killzone',active:d.killzone_active,val:d.killzone_name},
        {name:'PDHL',active:d.active_pdhl>0,val:d.active_pdhl+' lvls'},
        {name:'MSS',active:d.mss_present,val:d.mss_type},
        {name:'Breaker',active:d.active_breakers>0,val:d.active_breakers+' actifs'},
        {name:'Silver Bullet',active:d.silver_bullet_active,val:d.sb_quality},
        {name:'PO3',active:d.po3_phase!=='none',val:d.po3_phase},
    ];
    let html='';
    concepts.forEach(c=>{
        const cls=c.active?'active':'inactive';
        const dotCls=c.active?'on':c.val==='none'||c.val===0?'':'warn';
        html+=`<div class="ict-item ${cls}"><div class="ict-dot ${dotCls}"></div><span class="ict-name">${c.name}</span><span class="ict-val">${c.val}</span></div>`;
    });
    document.getElementById('ict_grid').innerHTML=html;
}

function updateKillzone(d){
    const kzName=d.killzone_name||'none';
    const kzActive=d.killzone_active||false;
    const kzMin=d.killzone_minutes_remaining||0;
    
    document.getElementById('kz_info').innerHTML=kzActive?
        `<span style="color:var(--green);font-weight:700">⏰ ${kzName.toUpperCase()} ACTIVE</span>`:
        `<span style="color:var(--text3)">HORS KILLZONE</span>`;
    
    // Build 24h timeline
    const hours=['0','1','2','3','4','5','6','7','8','9','10','11','12','13','14','15','16','17','18','19','20','21','22','23'];
    let html='';
    hours.forEach(h=>{
        const est_h=parseInt(h);
        const isLondon=est_h>=2&&est_h<5;
        const isNYOpen=est_h>=8&&est_h<11;
        const isNYPM=est_h>=13&&est_h<16;
        const isActive=(isLondon&&kzName==='london_open')||(isNYOpen&&kzName==='ny_open')||(isNYPM&&kzName==='ny_pm');
        const bg=isLondon?'rgba(0,255,136,0.1)':isNYOpen?'rgba(59,130,246,0.1)':isNYPM?'rgba(168,85,247,0.1)':'var(--bg3)';
        html+=`<div class="kz-slot ${isActive?'active':''}" style="flex:1;background:${bg};${isActive?'border:1px solid var(--green);':''}">
            ${isActive?'<div class="active-fill" style="width:'+Math.min(100,((kzMin||0)/180*100))+'%"></div>':''}
            <span class="label" style="${isLondon||isNYOpen||isNYPM?'font-weight:700;':'color:var(--text3);'}">${h}</span>
        </div>`;
    });
    document.getElementById('kz_bar').innerHTML=html;
    
    document.getElementById('kz_timer').textContent=kzActive?
        `${kzMin} min restantes • Killzone = momentum institutionnel`:
        'Pas de killzone active • Trades hors killzone = win rate plus bas';
}

function updatePO3(d){
    const phase=d.po3_phase||'unknown';
    const conf=d.po3_confidence||0;
    const hasSweep=d.po3_has_sweep||false;
    const hasDisp=d.po3_has_displacement||false;
    
    document.getElementById('po3_info').innerHTML=phase==='distribution'?
        `<span style="color:var(--green);font-weight:700">⚡ DISTRIBUTION — MOMENT D'ENTRER</span>`:
        phase==='manipulation'?
        `<span style="color:var(--orange);font-weight:700">⚠️ MANIPULATION — SWEEP EN COURS</span>`:
        phase==='accumulation'?
        `<span style="color:var(--blue)">📊 ACCUMULATION — RANGE TIGHT</span>`:
        `<span style="color:var(--text3)">—</span>`;
    
    // Highlight active phase
    const phases=document.querySelectorAll('.po3-phase');
    phases.forEach(p=>{
        p.classList.remove('active');
        if(p.textContent.includes('ACC')&&phase==='accumulation')p.classList.add('active');
        if(p.textContent.includes('MANIP')&&phase==='manipulation')p.classList.add('active');
        if(p.textContent.includes('DIST')&&phase==='distribution')p.classList.add('active');
    });
    
    document.getElementById('po3_detail').textContent=
        `Phase: ${phase} • Confiance: ${pct(conf)} • Sweep: ${hasSweep?'✅':'❌'} • Displacement: ${hasDisp?'✅':'❌'}`;
}

function updateMSS(d){
    const mssType=d.mss_type||'none';
    const mssPresent=d.mss_present||false;
    const disp=d.displacement_atr||0;
    
    document.getElementById('mss_info').innerHTML=mssPresent?
        `<span style="color:var(--green);font-weight:700">🔥 MSS ${mssType.replace('mss_','').toUpperCase()} DÉTECTÉ</span>
         <br><span style="color:var(--text2);font-size:11px">Displacement: ${disp.toFixed(2)} ATR • FVG créé ✅</span>`:
        mssType!=='none'?
        `<span style="color:var(--orange)">MSS sans FVG — signal incomplet</span>`:
        `<span style="color:var(--text3)">Pas de MSS</span>`;
    
    document.getElementById('signal_info').textContent=
        `Tendance: ${d.current_trend||'neutral'} • HTF: ${d.htf_bias||'neutral'} • Zone: ${d.zone||'equilibrium'}`;
    
    const grade=d.setup_grade||'none';
    const gradeMap={gold:'🥇 GOLD',silver:'🥈 SILVER',bronze:'🥉 BRONZE',basic:'⚪ BASIC'};
    document.getElementById('grade_info').innerHTML=
        grade!=='none'?`<span style="color:var(--${grade==='gold'?'gold':grade==='silver'?'cyan':'silver'});font-weight:700">${gradeMap[grade]||grade}</span>`:'';
}

function updateSymbols(d){
    const stats=d.symbol_stats||{};
    let html='';
    Object.entries(stats).forEach(([sym,s])=>{
        html+=`<tr>
            <td style="font-weight:700">${sym}</td>
            <td>${s.daily_trades}</td>
            <td class="${s.daily_pnl>=0?'pnl-pos':'pnl-neg'}">${fmt$(s.daily_pnl)}</td>
            <td>${s.total_signals}</td>
            <td>${s.total_orders_sent}</td>
            <td>${s.total_orders_rejected}</td>
            <td>—</td>
            <td>—</td>
        </tr>`;
    });
    if(!html)html='<tr><td colspan="8" style="color:var(--text3)">Pas de données</td></tr>';
    document.getElementById('sym_table').innerHTML=html;
}

function updateTrades(t){
    const trades=t.trades||[];
    let html='';
    trades.forEach(tr=>{
        html+=`<tr>
            <td class="${tr.direction}">${tr.direction.toUpperCase()}</td>
            <td>${fmt(tr.entry,5)}</td>
            <td>${fmt(tr.sl,5)}</td>
            <td>${fmt(tr.tp,5)}</td>
            <td class="${tr.pnl>=0?'pnl-pos':'pnl-neg'}">${fmt$(tr.pnl)}</td>
            <td>${tr.be_reached?'✅':'—'}</td>
            <td>${tr.confluence}</td>
        </tr>`;
    });
    if(!html)html='<tr><td colspan="7" style="color:var(--text3)">Pas de trades ouverts</td></tr>';
    document.getElementById('trade_table').innerHTML=html;
}

function updateKillSwitch(d){
    const active=d.kill_switch_active||false;
    const reason=d.kill_switch_reason||'';
    
    const section=document.getElementById('kill_section');
    section.className='kill-section '+active?'':'safe';
    
    const status=document.getElementById('kill_status');
    status.textContent=active?'🔴 ACTIVÉ':'🟢 SAFE';
    status.className='kill-status '+active?'active':'safe';
    
    document.getElementById('kill_reason').textContent=reason||'Aucun trigger';
}

function updatePDHL(d){
    const pdhl=d.pdhl_info||'';
    document.getElementById('pdhl_info').textContent=pdhl||'PDHL non calculé — en attente de données journalières';
}

function manualStop(){
    fetch('/api/stop',{method:'POST'}).then(r=>r.json()).then(d=>refresh());
}

refresh();
setInterval(refresh,REFRESH_MS);
</script>
</body>
</html>
"""


@app.route("/")
def index():
    return render_template_string(HTML_TEMPLATE)


@app.route("/api/status")
def api_status():
    """API : statut complet — chiffres bruts (Règle 9)."""
    if bot_instance is None:
        return jsonify({
            "capital": 0, "daily_pnl": 0, "daily_loss_pct": 0,
            "total_signals": 0, "total_orders_sent": 0, "total_orders_rejected": 0,
            "daily_trades": 0, "open_positions": 0, "mode": "unknown",
            "kill_switch_active": False, "kill_switch_reason": "bot not started",
            "running": False,
            "scenarios": [], "primary_scenario": "none",
            "trap_scenario": "none",
            "killzone_name": "none", "killzone_active": False,
            "killzone_minutes_remaining": 0,
            "po3_phase": "unknown", "po3_confidence": 0,
            "po3_has_sweep": False, "po3_has_displacement": False,
            "mss_type": "none", "mss_present": False,
            "displacement_atr": 0, "displacement_significant": False,
            "current_trend": "neutral", "htf_bias": "neutral", "zone": "equilibrium",
            "setup_grade": "none",
            "active_swings": 0, "active_fvgs": 0, "active_obs": 0,
            "active_pdhl": 0, "active_breakers": 0,
            "last_sweep_dir": "none",
            "silver_bullet_active": False, "sb_quality": "none",
            "symbol_stats": {},
            "pdhl_info": "PDHL non calculé",
        })

    status = bot_instance.get_status()
    kill = bot_instance.kill_switch.get_status()
    pipeline = bot_instance.pipelines

    # === Pipeline stats (premier symbole disponible) ===
    pipe_stats = {}
    for sym, pipe in pipeline.items():
        if pipe is not None:
            pipe_stats = pipe.get_stats()
            break

    # === Scenario analysis ===
    scenario_data = []
    primary_scenario = "none"
    trap_scenario = "none"
    sa = None
    for sym, pipe in pipeline.items():
        if pipe is not None and pipe.last_scenario_analysis is not None:
            sa = pipe.last_scenario_analysis
            break

    if sa is not None:
        for s in sa.scenarios:
            scenario_data.append({
                "scenario_type": s.scenario_type.value,
                "direction": s.direction,
                "probability_pct": s.probability_pct,
                "action": s.action,
                "risk_level": s.risk_level.value,
                "reasoning": s.reasoning[:3],
            })
        if sa.primary_scenario:
            primary_scenario = sa.primary_scenario.scenario_type.value
        if sa.trap_scenario:
            trap_scenario = sa.trap_scenario.scenario_type.value

    # === Killzone ===
    kz_name = pipe_stats.get("killzone", "none")
    kz_active = kz_name != "none"

    # === PO3 ===
    po3_phase = pipe_stats.get("po3_phase", "unknown")
    po3_conf = 0
    po3_sweep = False
    po3_disp = False
    for sym, pipe in pipeline.items():
        if pipe is not None and pipe.current_po3_phase is not None:
            po3_conf = pipe.current_po3_phase.confidence
            po3_sweep = pipe.current_po3_phase.has_sweep
            po3_disp = pipe.current_po3_phase.has_displacement
            break

    # === MSS ===
    mss_type = pipe_stats.get("last_mss_type", "none")
    mss_present = mss_type != "none" and "mss" in mss_type

    # === Displacement ===
    disp_atr = 0
    disp_sig = False
    for sym, pipe in pipeline.items():
        if pipe is not None:
            disp_result = measure_displacement(pipe.df, len(pipe.df) - 1)
            disp_atr = disp_result["displacement_atr"]
            disp_sig = disp_result["is_significant"]
            break

    # === Zone ===
    zone = pipe_stats.get("zone", "equilibrium") if "zone" in pipe_stats else "equilibrium"

    # === PDHL ===
    pdhl_active = pipe_stats.get("active_pdhl_levels", 0)
    pdhl_info = ""
    for sym, pipe in pipeline.items():
        if pipe is not None and pipe.pdhl_levels:
            unswept = [l for l in pipe.pdhl_levels if not l.swept]
            pdhl_info = " | ".join([f"{l.type}={l.price:.5f}" for l in unswept[:6]])
            break

    # === Sweep ===
    sweep_dir = "none"
    for sym, pipe in pipeline.items():
        if pipe is not None and pipe.last_sweep is not None:
            sweep_dir = pipe.last_sweep.direction
            break

    # === Silver Bullet ===
    sb_active = False
    sb_quality = "none"
    for sym, pipe in pipeline.items():
        if pipe is not None and pipe.last_silver_bullet is not None:
            sb_active = pipe.last_silver_bullet.is_complete
            sb_quality = pipe.last_silver_bullet.setup_quality
            break

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
        "kill_switch_active": kill.get("is_active", False),
        "kill_switch_reason": kill.get("reason", ""),
        "symbol_stats": status.get("symbol_stats", {}),
        # Scenarios
        "scenarios": scenario_data,
        "primary_scenario": primary_scenario,
        "trap_scenario": trap_scenario,
        # Killzone
        "killzone_name": kz_name,
        "killzone_active": kz_active,
        "killzone_minutes_remaining": 0,
        # PO3
        "po3_phase": po3_phase,
        "po3_confidence": po3_conf,
        "po3_has_sweep": po3_sweep,
        "po3_has_displacement": po3_disp,
        # MSS
        "mss_type": mss_type,
        "mss_present": mss_present,
        # ICT concepts
        "displacement_atr": disp_atr,
        "displacement_significant": disp_sig,
        "current_trend": pipe_stats.get("current_trend", "neutral"),
        "htf_bias": pipe_stats.get("htf_bias", "neutral"),
        "zone": zone,
        "setup_grade": "none",
        "active_swings": pipe_stats.get("active_swings", 0),
        "active_fvgs": pipe_stats.get("active_fvgs", 0),
        "active_obs": pipe_stats.get("active_obs", 0),
        "active_pdhl": pdhl_active,
        "active_breakers": pipe_stats.get("active_breaker_blocks", 0),
        "last_sweep_dir": sweep_dir,
        "silver_bullet_active": sb_active,
        "sb_quality": sb_quality,
        "pdhl_info": pdhl_info,
    })


@app.route("/api/trades")
def api_trades():
    if bot_instance is None:
        return jsonify({"trades": []})
    return jsonify(bot_instance.trade_manager.get_stats())


@app.route("/api/stop", methods=["POST"])
def api_stop():
    if bot_instance is None:
        return jsonify({"success": False, "reason": "bot not running"})
    bot_instance.kill_switch.manual_stop("dashboard_manual_stop")
    bot_instance.running = False
    return jsonify({"success": True, "message": "Bot stopped by dashboard"})


def start_dashboard(bot=None, port=5000):
    global bot_instance
    bot_instance = bot
    logger.info(f"DASHBOARD_START | port={port} | url=http://localhost:{port}")
    app.run(host="0.0.0.0", port=port, debug=False, use_reloader=False)
