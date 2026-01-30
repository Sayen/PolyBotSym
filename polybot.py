import requests
import json
import time
import threading
import webbrowser
import os
import concurrent.futures
import uuid
from collections import deque
from datetime import datetime, timezone
from flask import Flask, render_template_string, request, redirect, url_for, jsonify

# --- KONFIGURATION ---
DATA_FILE = "polybot_data.json"

# Globale Server-Einstellungen
GLOBAL_CONFIG = {
    "port": 5111,
    "api_fetch_limit": 3000,
    "check_interval": 30
}

# --- LOGGING ---
log_buffer = deque(maxlen=200)

def sys_log(msg):
    ts = datetime.now().strftime("%H:%M:%S")
    print(f"[SYSTEM] {msg}")
    log_buffer.appendleft(f"[{ts}] {msg}")

# --- STRATEGIE KLASSE ---
class Strategy:
    def __init__(self, data=None):
        if data:
            self.__dict__.update(data)
            if not hasattr(self, 'initial_balance'):
                self.initial_balance = getattr(self, 'balance', 1000.0)
        else:
            self.id = str(uuid.uuid4())[:8]
            self.name = "Neue Strategie"
            self.is_running = False
            self.balance = 1000.0
            self.initial_balance = 1000.0
            
            self.category_filter = ""
            self.min_prob = 0.90
            self.max_prob = 0.98
            self.max_time_min = 30
            self.min_liquidity = 5000.0
            self.max_spread = 0.05
            self.stop_loss_trigger = 0.75
            self.bet_percentage = 0.05
            
            self.active_bets = []
            self.history = []
            self.wins = 0
            self.losses = 0
            self.logs = []

    def reset_stats(self):
        self.balance = self.initial_balance
        self.active_bets = []
        self.history = []
        self.wins = 0
        self.losses = 0
        self.logs = []
        self.log("♻️ Statistik & Historie zurückgesetzt.")

    def log(self, msg):
        ts = datetime.now().strftime("%H:%M:%S")
        entry = f"[{ts}] {msg}"
        self.logs.insert(0, entry)
        if len(self.logs) > 100: self.logs.pop()
        sys_log(f"[{self.name}] {msg}")

    def get_equity(self):
        portfolio_val = 0.0
        for bet in self.active_bets:
            shares = bet["amount"] / bet["entry_price"]
            curr = bet.get("current_price", bet["entry_price"])
            portfolio_val += shares * curr
        return self.balance + portfolio_val

    def to_dict(self):
        return self.__dict__

# --- DATA MANAGER ---
strategies = {} 

def save_data():
    try:
        data = {id: s.to_dict() for id, s in strategies.items()}
        with open(DATA_FILE, 'w') as f:
            json.dump(data, f, indent=4)
    except Exception as e:
        sys_log(f"Fehler beim Speichern: {e}")

def load_data():
    global strategies
    if os.path.exists(DATA_FILE):
        try:
            with open(DATA_FILE, 'r') as f:
                raw = json.load(f)
                strategies = {} 
                for id, data in raw.items():
                    strategies[id] = Strategy(data)
            sys_log(f"{len(strategies)} Strategien geladen.")
        except Exception as e:
            sys_log(f"Ladefehler: {e}")

# --- FLASK SERVER ---
app = Flask(__name__)
app.secret_key = "polybot_secret"

HTML_TEMPLATE = """
<!DOCTYPE html>
<html lang="de" data-bs-theme="dark">
<head>
    <meta charset="UTF-8">
    <title>PolyBot Pro</title>
    <link href="https://cdn.jsdelivr.net/npm/bootstrap@5.3.0/dist/css/bootstrap.min.css" rel="stylesheet">
    <link rel="stylesheet" href="https://cdn.jsdelivr.net/npm/bootstrap-icons@1.10.0/font/bootstrap-icons.css">
    <script src="https://cdnjs.cloudflare.com/ajax/libs/Sortable/1.15.0/Sortable.min.js"></script>
    <style>
        body { background-color: #0d1117; font-family: 'Segoe UI', monospace; color: #c9d1d9; }
        .navbar { background-color: #161b22; border-bottom: 1px solid #30363d; }
        .card { background-color: #161b22; border: 1px solid #30363d; margin-bottom: 20px; }
        .card-header { background-color: #21262d; border-bottom: 1px solid #30363d; font-weight: 600; }
        .btn-sm { font-size: 0.8rem; }
        .table { color: #c9d1d9; --bs-table-bg: transparent; }
        .status-dot { height: 10px; width: 10px; background-color: #bbb; border-radius: 50%; display: inline-block; }
        .running { background-color: #2ea043; box-shadow: 0 0 5px #2ea043; }
        .stopped { background-color: #da3633; }
        .log-box { background: #000; color: #7ee787; font-family: monospace; padding: 10px; height: 600px; overflow-y: auto; border: 1px solid #30363d; font-size: 0.8rem; }
        .text-win { color: #2ea043; }
        .text-loss { color: #da3633; }
        a { text-decoration: none; }
        .nav-tabs .nav-link { color: #8b949e; }
        .nav-tabs .nav-link.active { background-color: #161b22; border-color: #30363d #30363d #161b22; color: #58a6ff; }
        .nav-tabs { border-bottom: 1px solid #30363d; }
        .drag-handle { cursor: grab; color: #555; }
        .drag-handle:active { cursor: grabbing; }
        .sortable-ghost { opacity: 0.4; background-color: #30363d; }
    </style>
</head>
<body>
    <nav class="navbar navbar-expand-lg navbar-dark px-4">
        <a class="navbar-brand fw-bold" href="/"><i class="bi bi-robot"></i> PolyBot <span class="text-primary">Pro Edition</span></a>
        <div class="mx-4">
            <div class="d-flex gap-2">
                <a href="/global_action/start_all" class="btn btn-outline-success btn-sm"><i class="bi bi-play-fill"></i> Alle Starten</a>
                <a href="/global_action/stop_all" class="btn btn-outline-danger btn-sm"><i class="bi bi-stop-fill"></i> Alle Stoppen</a>
                <a href="/global_action/reset_all" class="btn btn-outline-warning btn-sm" onclick="return confirm('ALLES zurücksetzen?')"><i class="bi bi-arrow-counterclockwise"></i> Alles zurücksetzen</a>
            </div>
        </div>
        <div class="ms-auto text-muted small">
            Scanne: {{ global_limit }} Märkte | Aktualisiert: <span id="lastUpdate">{{ last_update }}</span>
        </div>
    </nav>

    <div class="container-fluid p-4">
        {% if view == 'home' %}
        <div class="d-flex justify-content-between align-items-center mb-4">
            <h4>Strategie-Übersicht</h4>
            <button class="btn btn-primary" data-bs-toggle="modal" data-bs-target="#newStratModal"><i class="bi bi-plus-lg"></i> Neue Strategie</button>
        </div>
        <div class="card">
            <div class="table-responsive">
                <table class="table table-hover align-middle mb-0">
                    <thead>
                        <tr class="text-muted small text-uppercase">
                            <th style="width: 30px"></th>
                            <th>Status</th><th>Name</th><th>Gesamtwert</th><th>Verfügbar</th><th>Offen</th><th>S/N</th><th>Filter</th><th class="text-end">Aktionen</th>
                        </tr>
                    </thead>
                    <tbody id="strategyList">
                        {% for id, s in strategies.items() %}
                        <tr data-id="{{ id }}" style="cursor: pointer;" onclick="window.location='/strategy/{{ id }}'">
                            <td class="drag-handle" onclick="event.stopPropagation();"><i class="bi bi-grip-vertical fs-5"></i></td>
                            <td><span class="status-dot {{ 'running' if s.is_running else 'stopped' }}"></span></td>
                            <td class="fw-bold text-white">
                                <span data-bs-toggle="tooltip" data-bs-html="true" title="
                                    <div class='text-start'>
                                        <b>Min Quote:</b> {{ s.min_prob }}<br>
                                        <b>Max Quote:</b> {{ s.max_prob }}<br>
                                        <b>Max Zeit:</b> {{ s.max_time_min }}m<br>
                                        <b>Invest:</b> {{ '%.1f'|format(s.bet_percentage*100) }}%<br>
                                        <b>Min Liquidität:</b> ${{ s.min_liquidity }}<br>
                                        <b>Stop Loss:</b> {{ s.stop_loss_trigger }}x
                                    </div>">
                                    {{ s.name }}
                                </span>
                            </td>
                            <td class="fw-bold text-primary">${{ "%.2f"|format(s.get_equity()) }}</td>
                            <td>${{ "%.2f"|format(s.balance) }}</td>
                            <td>{{ s.active_bets|length }}</td>
                            <td><span class="text-win">{{ s.wins }}</span>/<span class="text-loss">{{ s.losses }}</span></td>
                            <td class="small text-muted">{{ s.category_filter if s.category_filter else "ALLE" }}</td>
                            <td class="text-end" onclick="event.stopPropagation();">
                                {% if s.is_running %}
                                <a href="/action/stop/{{ id }}" class="btn btn-outline-danger btn-sm" title="Stoppen"><i class="bi bi-pause-fill"></i></a>
                                {% else %}
                                <a href="/action/start/{{ id }}" class="btn btn-outline-success btn-sm" title="Starten"><i class="bi bi-play-fill"></i></a>
                                {% endif %}
                                <a href="/action/reset/{{ id }}" class="btn btn-outline-warning btn-sm" onclick="return confirm('Zurücksetzen?')" title="Zurücksetzen"><i class="bi bi-arrow-counterclockwise"></i></a>
                                <a href="/action/duplicate/{{ id }}" class="btn btn-outline-primary btn-sm" title="Duplizieren"><i class="bi bi-files"></i></a>
                                <a href="/strategy/{{ id }}#config" class="btn btn-outline-secondary btn-sm" title="Einstellungen"><i class="bi bi-gear"></i></a>
                                <a href="/action/delete/{{ id }}" class="btn btn-outline-danger btn-sm" onclick="return confirm('Löschen?')" title="Löschen"><i class="bi bi-trash"></i></a>
                            </td>
                        </tr>
                        {% else %}<tr><td colspan="9" class="text-center p-5 text-muted">Keine Strategien.</td></tr>{% endfor %}
                    </tbody>
                </table>
            </div>
        </div>
        <div class="card mt-4"><div class="card-header">System-Protokolle</div><div class="log-box">{% for line in sys_logs %}<div>{{ line }}</div>{% endfor %}</div></div>
        
        <div class="modal fade" id="newStratModal" tabindex="-1">
            <div class="modal-dialog">
                <form class="modal-content bg-dark" action="/create_strategy" method="post">
                    <div class="modal-header border-secondary"><h5 class="modal-title">Neue Strategie</h5><button type="button" class="btn-close btn-close-white" data-bs-dismiss="modal"></button></div>
                    <div class="modal-body">
                        <label class="form-label">Name</label><input type="text" class="form-control bg-dark text-white border-secondary" name="name" required>
                        <label class="form-label mt-2">Startkapital ($)</label><input type="number" class="form-control bg-dark text-white border-secondary" name="balance" value="1000">
                    </div>
                    <div class="modal-footer border-secondary"><button type="submit" class="btn btn-primary">Erstellen</button></div>
                </form>
            </div>
        </div>

        {% elif view == 'detail' %}
        <div class="d-flex align-items-center mb-4">
            <a href="/" class="btn btn-outline-secondary me-3"><i class="bi bi-arrow-left"></i> Zurück</a>
            <h3 class="m-0">{{ strat.name }} <span class="badge {{ 'bg-success' if strat.is_running else 'bg-danger' }} fs-6 align-middle ms-2">{{ 'LÄUFT' if strat.is_running else 'PAUSIERT' }}</span></h3>
            <div class="ms-auto"><a href="/action/reset/{{ strat.id }}" class="btn btn-outline-warning" onclick="return confirm('Statistik zurücksetzen?')"><i class="bi bi-arrow-counterclockwise"></i> Statistik zurücksetzen</a></div>
        </div>
        <div class="row g-3 mb-4">
            <div class="col-md-3"><div class="card p-3 text-center h-100"><small>GESAMTWERT</small><h2 class="text-primary">${{ "%.2f"|format(strat.get_equity()) }}</h2></div></div>
            <div class="col-md-3"><div class="card p-3 text-center h-100"><small>VERFÜGBAR</small><h2>${{ "%.2f"|format(strat.balance) }}</h2></div></div>
            <div class="col-md-3"><div class="card p-3 text-center h-100"><small>OFFEN</small><h2>{{ strat.active_bets|length }}</h2></div></div>
            <div class="col-md-3"><div class="card p-3 text-center h-100"><small>GEWINNRATE</small><h2>{{ strat.wins }} S / {{ strat.losses }} N</h2></div></div>
        </div>
        <ul class="nav nav-tabs mb-3" id="detailTabs">
            <li class="nav-item"><a class="nav-link active" data-bs-toggle="tab" href="#active_tab">Aktive Wetten</a></li>
            <li class="nav-item"><a class="nav-link" data-bs-toggle="tab" href="#history_tab">Historie</a></li>
            <li class="nav-item"><a class="nav-link" data-bs-toggle="tab" href="#config_tab">Konfiguration</a></li>
            <li class="nav-item"><a class="nav-link" data-bs-toggle="tab" href="#logs_tab">Protokolle</a></li>
        </ul>
        <div class="tab-content">
            <div class="tab-pane fade show active" id="active_tab">
                <div class="card"><div class="table-responsive"><table class="table table-hover align-middle mb-0">
                    <thead><tr class="text-muted small"><th>Markt</th><th>Wahl</th><th>Invest</th><th>Einstieg</th><th>Live</th><th>Wert</th><th>Zeit</th></tr></thead>
                    <tbody>
                        {% for bet in strat.active_bets %}
                        <tr>
                            <td style="max-width:300px; overflow:hidden; text-overflow:ellipsis;"><a href="https://polymarket.com/event/{{ bet.slug }}" target="_blank" class="text-white text-decoration-underline">{{ bet.title }}</a></td>
                            <td><span class="badge bg-info text-dark">{{ bet.picked_outcome }}</span></td>
                            <td>${{ "%.2f"|format(bet.amount) }}</td>
                            <td>{{ "%.1f"|format(bet.entry_price*100) }}%</td>
                            <td><span class="{{ 'text-win' if bet.current_price > bet.entry_price else 'text-loss' if bet.current_price < bet.entry_price else 'text-muted' }}">{{ "%.1f"|format(bet.current_price*100) }}%</span></td>
                            <td>${{ "%.2f"|format((bet.amount/bet.entry_price)*bet.current_price) }}</td>
                            <td>{{ bet.get('time_str', 'Berechne...') }}</td>
                        </tr>
                        {% else %}<tr><td colspan="7" class="text-center p-4 text-muted">Keine Positionen.</td></tr>{% endfor %}
                    </tbody>
                </table></div></div>
            </div>
            <div class="tab-pane fade" id="history_tab">
                <div class="card"><div class="table-responsive"><table class="table table-striped table-hover mb-0">
                    <thead><tr><th>Zeit</th><th>Status</th><th>Markt</th><th>P/L</th></tr></thead>
                    <tbody>
                        {% for h in strat.history|reverse %}
                        <tr>
                            <td>{{ h.close_time[11:19] }}</td>
                            <td><span class="badge {{ 'bg-success' if h.status=='WIN' else 'bg-danger' }}">{{ h.status }}</span></td>
                            <td style="max-width:400px; overflow:hidden; text-overflow:ellipsis;">{% if h.slug %}<a href="https://polymarket.com/event/{{ h.slug }}" target="_blank" class="text-white text-decoration-underline">{{ h.title }}</a>{% else %}{{ h.title }}{% endif %}</td>
                            <td class="{{ 'text-win' if h.pnl > 0 else 'text-loss' }} fw-bold">{{ "%.2f"|format(h.pnl) }}$</td>
                        </tr>
                        {% endfor %}
                    </tbody>
                </table></div></div>
            </div>
            <div class="tab-pane fade" id="config_tab">
                <div class="card p-4">
                    <form action="/update_strategy/{{ strat.id }}" method="post">
                        <div class="row g-3">
                            <div class="col-md-6"><label>Name</label><input type="text" class="form-control" name="name" value="{{ strat.name }}"></div>
                            <div class="col-md-6"><label>Kategorie</label><input type="text" class="form-control" name="category_filter" value="{{ strat.category_filter }}"></div>
                            <div class="col-md-3"><label>Min Quote</label><input type="number" step="0.01" class="form-control" name="min_prob" value="{{ strat.min_prob }}"></div>
                            <div class="col-md-3"><label>Max Quote</label><input type="number" step="0.01" class="form-control" name="max_prob" value="{{ strat.max_prob }}"></div>
                            <div class="col-md-3"><label>Max Zeit (Min)</label><input type="number" class="form-control" name="max_time_min" value="{{ strat.max_time_min }}"></div>
                            <div class="col-md-3"><label>Invest %</label><input type="number" step="0.01" class="form-control" name="bet_percentage" value="{{ strat.bet_percentage }}"></div>
                            <div class="col-md-6"><label>Stop Loss (x)</label><input type="number" step="0.01" class="form-control text-danger border-danger" name="stop_loss_trigger" value="{{ strat.stop_loss_trigger }}"><small class="text-muted">0 = Deaktiviert</small></div>
                            <div class="col-md-6"><label>Min Liq ($)</label><input type="number" class="form-control" name="min_liquidity" value="{{ strat.min_liquidity }}"></div>
                            <div class="col-12 mt-3"><button type="submit" class="btn btn-primary w-100">Einstellungen Speichern</button></div>
                        </div>
                    </form>
                </div>
            </div>
            <div class="tab-pane fade" id="logs_tab"><div class="log-box">{% for line in strat.logs %}<div>{{ line }}</div>{% endfor %}</div></div>
        </div>
        {% endif %}
    </div>
    <script src="https://cdn.jsdelivr.net/npm/bootstrap@5.3.0/dist/js/bootstrap.bundle.min.js"></script>
    <script>
        document.addEventListener("DOMContentLoaded", function(){
            var tooltipTriggerList = [].slice.call(document.querySelectorAll('[data-bs-toggle="tooltip"]'))
            var tooltipList = tooltipTriggerList.map(function (tooltipTriggerEl) {
              return new bootstrap.Tooltip(tooltipTriggerEl)
            })
            var hash = window.location.hash;
            if(hash) { var tid = hash + "_tab"; var trig = document.querySelector(`a[href="${tid}"]`); if(trig) new bootstrap.Tab(trig).show(); } 
            else { var at = localStorage.getItem('activeTab_v28'); if(at) { var t = document.querySelector(`a[href="${at}"]`); if(t) new bootstrap.Tab(t).show(); } }
            document.querySelectorAll('a[data-bs-toggle="tab"]').forEach(l => l.addEventListener('shown.bs.tab', e => { var t = e.target.getAttribute('href'); localStorage.setItem('activeTab_v28', t); history.replaceState(null,null, t.replace("_tab","")); }));
            var el = document.getElementById('strategyList');
            if(el){ new Sortable(el, { handle: '.drag-handle', animation: 150, ghostClass: 'sortable-ghost', onEnd: function (evt) { var order = []; document.querySelectorAll('#strategyList tr').forEach(tr => order.push(tr.getAttribute('data-id'))); fetch('/reorder_strategies', { method: 'POST', headers: {'Content-Type': 'application/json'}, body: JSON.stringify({order: order}) }); } }); }
            setInterval(function() { if (!document.getElementById('detailTabs')) { if(!document.querySelector('.modal.show')) window.location.reload(); return; } var cfg = document.getElementById('config_tab'); if (cfg && cfg.classList.contains('active')) return; window.location.reload(); }, 10000);
        });
    </script>
</body>
</html>
"""

# --- ROUTES ---
@app.route("/")
def home(): return render_template_string(HTML_TEMPLATE, view='home', strategies=strategies, sys_logs=log_buffer, global_limit=GLOBAL_CONFIG['api_fetch_limit'], last_update=datetime.now().strftime("%H:%M:%S"))
@app.route("/strategy/<id>")
def strategy_detail(id): return render_template_string(HTML_TEMPLATE, view='detail', strat=strategies.get(id), sys_logs=log_buffer, global_limit=GLOBAL_CONFIG['api_fetch_limit'], last_update=datetime.now().strftime("%H:%M:%S")) if id in strategies else redirect("/")
@app.route("/create_strategy", methods=["POST"])
def create_strategy():
    s = Strategy(); s.name = request.form.get("name")
    try: s.balance = s.initial_balance = float(request.form.get("balance"))
    except: pass
    strategies[s.id] = s; save_data(); return redirect("/")
@app.route("/update_strategy/<id>", methods=["POST"])
def update_strategy(id):
    if id in strategies:
        s = strategies[id]
        try:
            s.name = request.form.get("name")
            s.category_filter = request.form.get("category_filter").strip()
            s.min_prob = float(request.form.get("min_prob"))
            s.max_prob = float(request.form.get("max_prob"))
            s.max_time_min = int(request.form.get("max_time_min"))
            s.bet_percentage = float(request.form.get("bet_percentage"))
            s.stop_loss_trigger = float(request.form.get("stop_loss_trigger"))
            s.min_liquidity = float(request.form.get("min_liquidity"))
            save_data()
        except: pass
    return redirect(f"/strategy/{id}#config")
@app.route("/action/duplicate/<id>")
def duplicate_strategy(id):
    global strategies
    if id in strategies:
        source = strategies[id]

        # Daten kopieren
        data = source.to_dict().copy()

        # Neue ID
        new_id = str(uuid.uuid4())[:8]
        data["id"] = new_id

        # Name anpassen (nur einmal "(Kopie)")
        if not data["name"].endswith(" (Kopie)"):
            data["name"] = data["name"] + " (Kopie)"

        # Status zurücksetzen
        data["is_running"] = False
        data["active_bets"] = []
        data["history"] = []
        data["wins"] = 0
        data["losses"] = 0
        data["logs"] = []

        # Balance auf Initialwert zurücksetzen
        initial = data.get("initial_balance", 1000.0)
        data["balance"] = initial
        data["initial_balance"] = initial

        new_strat = Strategy(data)
        new_strat.log(f"Kopie von '{source.name}' erstellt.")

        # Einsortieren (direkt unter der Quelle)
        new_strategies = {}
        for key, val in strategies.items():
            new_strategies[key] = val
            if key == id:
                new_strategies[new_id] = new_strat

        strategies = new_strategies
        save_data()

    return redirect("/")
@app.route("/reorder_strategies", methods=["POST"])
def reorder_strategies():
    global strategies; order = request.json.get('order', [])
    new_map = {uid: strategies[uid] for uid in order if uid in strategies}
    for uid, s in strategies.items():
        if uid not in new_map: new_map[uid] = s
    strategies = new_map; save_data(); return jsonify({"status":"ok"})
@app.route("/action/<action>/<id>")
def action(action, id):
    if id in strategies:
        if action == "start": strategies[id].is_running = True
        elif action == "stop": strategies[id].is_running = False
        elif action == "delete": del strategies[id]
        elif action == "reset": strategies[id].reset_stats()
        save_data()
    return redirect("/")
@app.route("/global_action/<action>")
def global_action(action):
    for s in list(strategies.values()):
        if action == "start_all": s.is_running = True
        elif action == "stop_all": s.is_running = False
        elif action == "reset_all": s.reset_stats()
    save_data(); return redirect("/")

# --- OPTIMIERTE ENGINE ---
class Engine:
    def __init__(self):
        # OPTIMIERUNG 1: Session für Connection Reuse
        self.session = requests.Session()
        self.session.headers.update({"User-Agent": "Mozilla/5.0"})

    def fetch_markets(self):
        all_markets = []
        limit = GLOBAL_CONFIG["api_fetch_limit"]
        batch = 500
        offsets = range(0, limit, batch)
        url = "https://gamma-api.polymarket.com/markets"
        now = datetime.now(timezone.utc).isoformat()
        
        def load_batch(o):
            try:
                # Nutzt die Session
                r = self.session.get(url, params={
                    "active": "true", "closed": "false", "order": "endDate", 
                    "ascending": "true", "end_date_min": now, 
                    "limit": str(batch), "offset": str(o)
                }, timeout=10)
                if r.status_code == 200: return r.json()
            except: pass
            return []

        # Paralleles Fetching (IO Bound)
        with concurrent.futures.ThreadPoolExecutor(max_workers=20) as ex:
            futures = {ex.submit(load_batch, o): o for o in offsets}
            for f in concurrent.futures.as_completed(futures):
                res = f.result()
                if res and isinstance(res, list): all_markets.extend(res)
        return all_markets

    def update_single_bet(self, s_id, bet, now):
        """Hilfsfunktion für paralleles Update einer einzelnen Wette"""
        try:
            r = self.session.get(f"https://gamma-api.polymarket.com/markets/{bet['market_id']}", timeout=5)
            
            # --- START: ERROR / GHOST BET HANDLING ---
            if r.status_code != 200:
                bet['fail_count'] = bet.get('fail_count', 0) + 1
                # Wenn > 10 Versuche (ca. 5 Minuten) fehlschlagen -> Wette löschen + Erstatten
                if bet['fail_count'] > 10:
                    strat = strategies.get(s_id)
                    if strat:
                        strat.balance += bet['amount']
                        strat.log(f"⚠️ MARKT DEFEKT/GELÖSCHT: {bet['title']} | ${bet['amount']:.2f} erstattet.")
                    return None, True # None = Löschen
                return bet, True # Fail Count speichern
            # --- ENDE: ERROR HANDLING ---

            m = r.json()
            strat = strategies.get(s_id)
            if not strat: return bet, False 
            
            dirty = False
            bet['fail_count'] = 0 # Reset Fail Count bei Erfolg
            
            # Update Data
            try:
                outcomes = json.loads(m.get("outcomes", "[]"))
                prices = [float(p) for p in json.loads(m.get("outcomePrices", "[]"))]
                if bet["picked_outcome"] in outcomes:
                    idx = outcomes.index(bet["picked_outcome"])
                    bet["current_price"] = prices[idx]
                
                end = datetime.fromisoformat(m["endDate"].replace('Z', '+00:00'))
                seconds_left = int((end - now).total_seconds())
                bet["minutes_left"] = seconds_left // 60
                
                if seconds_left <= 0: bet["time_str"] = "Warte..."
                elif seconds_left > 3600: bet["time_str"] = f"{seconds_left // 3600}h {(seconds_left % 3600) // 60}m"
                else: bet["time_str"] = f"{seconds_left // 60}m {seconds_left % 60}s"
            except: pass

            # LOGIC CHECKS
            if strat.is_running and strat.stop_loss_trigger > 0 and bet["current_price"] < (bet["entry_price"] * strat.stop_loss_trigger) and not m.get("closed"):
                # STOP LOSS EXECUTION
                shares = bet["amount"] / bet["entry_price"]
                revenue = shares * bet["current_price"]
                loss = bet["amount"] - revenue
                strat.balance += revenue
                strat.losses += 1
                
                # DETAILED LOG
                strat.log(f"🛑 STOP-LOSS: {bet['title']} | Exit @ {bet['current_price']:.2f} | PnL: -${loss:.2f}")
                
                strat.history.append({"status":"STOP-LOSS", "title":bet["title"], "slug": bet.get("slug", ""), "pnl":-loss, "close_time": datetime.now().isoformat()})
                return None, True

            if m.get("closed") is True:
                # WIN/LOSS EXECUTION
                won = bet["current_price"] > 0.95
                revenue = (bet["amount"]/bet["entry_price"])*1.0 if won else 0
                profit = revenue - bet["amount"] if won else -bet["amount"]
                strat.balance += revenue
                if won: strat.wins += 1
                else: strat.losses += 1
                
                # DETAILED LOG
                roi = ((revenue - bet["amount"]) / bet["amount"]) * 100
                if won:
                    strat.log(f"✅ WIN: {bet['title']} | Profit: +${profit:.2f} ({roi:.1f}%)")
                else:
                    strat.log(f"❌ LOSS: {bet['title']} | Verlust: -${bet['amount']:.2f}")

                strat.history.append({"status":"WIN" if won else "LOSS", "title":bet["title"], "slug": bet.get("slug", ""), "pnl":profit, "close_time": datetime.now().isoformat()})
                return None, True

            return bet, False 
        except Exception as e:
            # Auch bei Exception den Fail Count hochzählen
            bet['fail_count'] = bet.get('fail_count', 0) + 1
            if bet['fail_count'] > 10:
                strat = strategies.get(s_id)
                if strat:
                    strat.balance += bet['amount']
                    strat.log(f"⚠️ MARKT FEHLER (NETZWERK): {bet['title']} | ${bet['amount']:.2f} erstattet.")
                return None, True
            return bet, True

    def update_active_bets(self):
        # OPTIMIERUNG 2: Paralleles Update der aktiven Wetten
        tasks = []
        now = datetime.now(timezone.utc)
        
        # Sammle alle Tasks
        for s_id, strat in list(strategies.items()):
            if not strat.active_bets: continue
            for bet in strat.active_bets:
                tasks.append((s_id, bet))
        
        if not tasks: return

        # Ausführen
        results_map = {s_id: [] for s_id in strategies} # Puffer für Ergebnisse
        dirty_flags = {s_id: False for s_id in strategies}

        with concurrent.futures.ThreadPoolExecutor(max_workers=20) as ex:
            futures = {ex.submit(self.update_single_bet, s_id, bet, now): s_id for s_id, bet in tasks}
            
            for f in concurrent.futures.as_completed(futures):
                s_id = futures[f]
                try:
                    res_bet, is_dirty = f.result()
                    if is_dirty: dirty_flags[s_id] = True
                    if res_bet: results_map[s_id].append(res_bet)
                except: pass

        # Ergebnisse zurückschreiben
        save_needed = False
        for s_id, bets in results_map.items():
            if s_id in strategies:
                if len(strategies[s_id].active_bets) != len(bets) or dirty_flags[s_id]:
                    strategies[s_id].active_bets = bets
                    save_needed = True
        
        if save_needed: save_data()

    def process_strategies(self, raw_markets):
        now = datetime.now(timezone.utc)
        
        # OPTIMIERUNG 3: Pre-Processing der Märkte (JSON Parsing nur 1x pro Loop)
        processed_markets = []
        for m in raw_markets:
            try:
                # Extrahiere Daten einmalig
                outcomes = json.loads(m.get("outcomes", "[]"))
                prices = [float(p) for p in json.loads(m.get("outcomePrices", "[]"))]
                
                best_price, best_outcome = 0, None
                for i, p in enumerate(prices):
                    if p > best_price: best_price, best_outcome = p, outcomes[i]
                
                end = datetime.fromisoformat(m["endDate"].replace('Z', '+00:00'))
                seconds_left = int((end - now).total_seconds())
                minutes_left = seconds_left // 60
                
                processed_markets.append({
                    "raw": m, # Referenz aufs Original für ID, Title etc.
                    "tags": str(m.get("tags", [])).lower(),
                    "spread": float(m.get("spread", 0)),
                    "liquidity": float(m.get("liquidity", 0)),
                    "minutes_left": minutes_left,
                    "seconds_left": seconds_left,
                    "best_price": best_price,
                    "best_outcome": best_outcome
                })
            except: continue

        # Jetzt Strategien gegen die vorverarbeiteten Märkte laufen lassen
        save_needed = False
        for s_id, strat in list(strategies.items()):
            if not strat.is_running: continue
            
            # Budget Check
            bet_amount = strat.balance * strat.bet_percentage
            if bet_amount < 1.0: continue

            # IDs der aktiven Wetten cachen für schnellen Lookup
            active_ids = {b['market_id'] for b in strat.active_bets}

            for pm in processed_markets:
                m = pm["raw"]
                if m['id'] in active_ids: continue
                
                # Checks auf vorverarbeiteten Daten (Viel schneller!)
                if strat.category_filter and strat.category_filter.lower() not in pm["tags"]: continue
                if pm["spread"] > strat.max_spread: continue
                if pm["liquidity"] < strat.min_liquidity: continue
                if pm["minutes_left"] <= 0 or pm["minutes_left"] > strat.max_time_min: continue
                
                if strat.min_prob <= pm["best_price"] <= strat.max_prob:
                    # KAUF SIGNAL
                    strat.balance -= bet_amount
                    
                    # DETAILED LOG
                    strat.log(f"🚀 KAUF: {m['question']} | ${bet_amount:.2f} auf {pm['best_outcome']} @ {pm['best_price']:.2f}")
                    
                    if pm["seconds_left"] > 3600: t_str = f"{pm['seconds_left'] // 3600}h {(pm['seconds_left'] % 3600) // 60}m"
                    else: t_str = f"{pm['seconds_left'] // 60}m {pm['seconds_left'] % 60}s"

                    strat.active_bets.append({
                        "market_id": m["id"],
                        "slug": m.get("slug",""),
                        "title": m["question"],
                        "picked_outcome": pm["best_outcome"],
                        "entry_price": pm["best_price"],
                        "current_price": pm["best_price"],
                        "amount": bet_amount,
                        "time_str": t_str,
                        "minutes_left": pm["minutes_left"],
                        "fail_count": 0
                    })
                    active_ids.add(m['id']) # Verhindert doppelkauf im gleichen Loop
                    save_needed = True
        
        if save_needed: save_data()

    def run(self):
        sys_log("🚀 PolyBot Pro Engine gestartet.")
        load_data()
        if not strategies: s = Strategy(); strategies[s.id] = s; save_data()

        while True:
            try:
                start_time = time.time()
                
                # 1. Update Active Bets (Parallel)
                self.update_active_bets()
                
                # 2. Fetch Markets (Parallel + Session)
                markets = self.fetch_markets()
                
                # 3. Process (Pre-Compiled)
                self.process_strategies(markets)
                
                duration = time.time() - start_time
                sys_log(f"Scan fertig: {len(markets)} Märkte verarbeitet ({duration:.2f}s).")
                
            except Exception as e:
                sys_log(f"Fehler im Loop: {e}")
            time.sleep(GLOBAL_CONFIG["check_interval"])

if __name__ == "__main__":
    engine = Engine()
    t = threading.Thread(target=engine.run, daemon=True)
    t.start()
    print(f"Server läuft auf http://127.0.0.1:{GLOBAL_CONFIG['port']}")
    if not os.environ.get("IS_DOCKER"):
        webbrowser.open(f"http://127.0.0.1:{GLOBAL_CONFIG['port']}")
    app.run(debug=False, port=GLOBAL_CONFIG['port'], host="0.0.0.0")