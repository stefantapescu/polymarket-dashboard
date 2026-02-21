"""
Polymarket Trading Dashboard — Vercel Serverless
==================================================
Reads bot state from data/ JSON files. Auto-refreshes every 30s.
Per-bot detail pages with charts and statistics.
"""

import json
import os
from datetime import datetime, timezone
from pathlib import Path
from flask import Flask, render_template_string

app = Flask(__name__)

DATA_DIR = Path(__file__).parent.parent / "data"

# ──────────────────────────────────────────────────────────────────────
# Bot registry
# ──────────────────────────────────────────────────────────────────────

BOT_REGISTRY = {
    "reversal": {
        "name": "BTC Reversal Sniper",
        "desc": "Buys cheap (losing) side of BTC 5-min Up/Down markets when Binance momentum is weak, betting on mean reversion",
        "icon": "↩",
    },
    "polymanager": {
        "name": "Liquidity Rewards Farmer",
        "desc": "Two-sided market maker on political/event markets to earn daily USDC liquidity rewards",
        "icon": "💧",
    },
    "candidate2": {
        "name": "Elon Tweet Sniper",
        "desc": "Models Elon Musk tweet frequency with Normal(VMR=16) distribution, buys mispriced tweet-count brackets",
        "icon": "🐦",
    },
}

# ──────────────────────────────────────────────────────────────────────
# Data loaders
# ──────────────────────────────────────────────────────────────────────

def load_json(path):
    try:
        with open(path) as f:
            return json.load(f)
    except Exception:
        return None


def load_v4_reversal():
    state = load_json(DATA_DIR / "dual_whale_v4_state.json")
    if not state:
        return None

    bot = {
        "id": "reversal",
        "name": BOT_REGISTRY["reversal"]["name"],
        "desc": BOT_REGISTRY["reversal"]["desc"],
        "icon": BOT_REGISTRY["reversal"]["icon"],
        "file": "dual_whale_v4_multi.py",
        "mode": "LIVE",
        "variants": {},
        "trades": [],
        "summary": {},
    }

    variant_names = {
        "A": "BN-Only (|BN|>=5)",
        "B": "BN-Loose (|BN|>=3)",
        "C": "Dual Whale + BN",
        "D": "Max Confidence",
        "E": "Rev Wide (|BN| 3-10)",
        "F": "Rev Core (|BN| 5-10)",
        "G": "Rev Tight (|BN| 3-4.5)",
    }

    for vk, vs in state.get("variants", {}).items():
        if vs.get("trades", 0) == 0 and vs.get("bn_gate", 0) == 0:
            continue
        bot["variants"][vk] = {
            "name": variant_names.get(vk, f"V{vk}"),
            "wins": vs.get("wins", 0),
            "losses": vs.get("losses", 0),
            "trades": vs.get("trades", 0),
            "pnl": vs.get("pnl", 0),
            "skips": vs.get("skips", 0) + vs.get("bn_gate", 0),
        }

    for w in state.get("windows", []):
        for vk in ["A", "B", "C", "D", "E", "F", "G"]:
            vt = w.get(f"v_{vk}", {})
            if vt.get("action") != "TRADE":
                continue
            winner = vt.get("winner")
            pnl = vt.get("pnl", 0)
            trade = {
                "variant": vk,
                "variant_name": variant_names.get(vk, f"V{vk}"),
                "slug": w.get("slug", ""),
                "time": w.get("ws", 0),
                "bn_bps": vt.get("bn_bps", 0),
                "direction": vt.get("dir", ""),
                "ask": vt.get("ask", 0),
                "cost": vt.get("cost", 0),
                "tokens": vt.get("tokens", 0),
                "live": vt.get("live", False),
                "winner": winner or "pending",
                "pnl": pnl,
                "result": "WIN" if pnl > 0 else ("LOSS" if winner else "PENDING"),
            }
            bot["trades"].append(trade)

    bot["trades"].sort(key=lambda t: t["time"], reverse=True)

    live_trades = [t for t in bot["trades"] if t["live"]]
    resolved = [t for t in live_trades if t["result"] != "PENDING"]
    wins = [t for t in resolved if t["result"] == "WIN"]
    losses = [t for t in resolved if t["result"] == "LOSS"]

    bot["summary"] = {
        "total_trades": len(live_trades),
        "resolved": len(resolved),
        "wins": len(wins),
        "losses": len(losses),
        "pending": len(live_trades) - len(resolved),
        "total_pnl": sum(t["pnl"] for t in resolved),
        "total_cost": sum(t["cost"] for t in live_trades),
        "avg_bet": sum(t["cost"] for t in live_trades) / len(live_trades) if live_trades else 0,
        "avg_win": sum(t["pnl"] for t in wins) / len(wins) if wins else 0,
        "avg_loss": sum(t["pnl"] for t in losses) / len(losses) if losses else 0,
        "biggest_win": max((t["pnl"] for t in wins), default=0),
        "biggest_loss": min((t["pnl"] for t in losses), default=0),
        "avg_bn": sum(abs(t["bn_bps"]) for t in live_trades) / len(live_trades) if live_trades else 0,
        "avg_ask": sum(t["ask"] for t in live_trades) / len(live_trades) if live_trades else 0,
    }

    return bot


def load_polymanager():
    state = load_json(DATA_DIR / "polymanager_state.json")
    if not state:
        return None

    bot = {
        "id": "polymanager",
        "name": BOT_REGISTRY["polymanager"]["name"],
        "desc": BOT_REGISTRY["polymanager"]["desc"],
        "icon": BOT_REGISTRY["polymanager"]["icon"],
        "file": "polymanager.py",
        "mode": state.get("mode", "?"),
        "variants": {},
        "trades": [],
        "summary": {
            "cycle_count": state.get("cycle_count", 0),
            "rebalance_count": state.get("rebalance_count", 0),
            "total_fills": state.get("total_fills", 0),
            "total_deployed": state.get("total_deployed", 0),
            "started_at": state.get("started_at", ""),
            "updated_at": state.get("updated_at", ""),
            "total_pnl": 0,
            "avg_bet": 0,
        },
        "markets": state.get("markets", {}),
    }
    return bot


def load_candidate2():
    state = load_json(DATA_DIR / "elon_tweet_bot_state.json")
    if not state:
        return None

    bot = {
        "id": "candidate2",
        "name": BOT_REGISTRY["candidate2"]["name"],
        "desc": BOT_REGISTRY["candidate2"]["desc"],
        "icon": BOT_REGISTRY["candidate2"]["icon"],
        "file": "candidate_2_bot.py",
        "mode": "LIVE",
        "variants": {},
        "trades": [],
        "summary": {
            "budget": state.get("budget", 0),
            "spent": state.get("spent", 0),
            "total_pnl": state.get("total_pnl", 0),
            "cycle_count": state.get("cycle_count", 0),
            "positions": len(state.get("positions", [])),
            "avg_bet": 0,
        },
        "positions": state.get("positions", []),
        "trades_log": state.get("trades_log", []),
    }

    all_costs = []
    for t in state.get("trades_log", []):
        cost = t.get("size_usd", 0)
        all_costs.append(cost)
        bot["trades"].append({
            "variant": "event",
            "variant_name": "Tweet Model",
            "slug": t.get("bracket_slug", t.get("event_slug", "")),
            "time": 0,
            "bn_bps": 0,
            "direction": t.get("side", ""),
            "ask": t.get("entry_price", 0),
            "cost": cost,
            "tokens": t.get("size_tokens", 0),
            "live": True,
            "winner": "",
            "pnl": t.get("pnl", 0),
            "result": "WIN" if t.get("pnl", 0) > 0 else "LOSS" if t.get("pnl", 0) < 0 else "PENDING",
        })

    bot["trades"].reverse()
    if all_costs:
        bot["summary"]["avg_bet"] = sum(all_costs) / len(all_costs)

    return bot


def load_all_bots():
    bots = []
    for loader in [load_v4_reversal, load_polymanager, load_candidate2]:
        bot = loader()
        if bot:
            bots.append(bot)
    return bots


# ──────────────────────────────────────────────────────────────────────
# Helpers
# ──────────────────────────────────────────────────────────────────────

def ts_format_filter(ts):
    try:
        dt = datetime.fromtimestamp(ts, tz=timezone.utc)
        return dt.strftime("%m/%d %H:%M")
    except Exception:
        return str(ts)

app.jinja_env.filters["ts_format"] = ts_format_filter


def compute_globals(bots):
    pnl = trades = wins = losses = pending = 0
    for bot in bots:
        s = bot.get("summary", {})
        pnl += s.get("total_pnl", 0)
        trades += s.get("total_trades", s.get("positions", 0))
        wins += s.get("wins", 0)
        losses += s.get("losses", 0)
        pending += s.get("pending", 0)
    wr = (wins / (wins + losses) * 100) if (wins + losses) > 0 else 0
    return dict(pnl=pnl, trades=trades, wins=wins, losses=losses, pending=pending, wr=wr)


def get_bn_buckets(bot):
    if not bot or "Reversal" not in bot["name"]:
        return []
    resolved = [t for t in bot["trades"] if t.get("live") and t["result"] != "PENDING"]
    buckets = []
    for lo, hi in [(3, 4), (4, 5), (5, 6), (6, 7), (7, 8), (8, 9), (9, 10)]:
        bt = [t for t in resolved if lo <= abs(t.get("bn_bps", 0)) < hi]
        w = sum(1 for t in bt if t["result"] == "WIN")
        l = len(bt) - w
        p = sum(t["pnl"] for t in bt)
        wr = (w / (w + l) * 100) if (w + l) > 0 else 0
        buckets.append(dict(label=f"{lo}-{hi}", wins=w, losses=l, pnl=p, wr=wr, total=w + l))
    return buckets


def get_cum_pnl(bot):
    if not bot:
        return []
    resolved = [t for t in bot["trades"] if t.get("live") and t["result"] != "PENDING"]
    resolved.sort(key=lambda t: t["time"])
    cum = 0
    pts = []
    for t in resolved:
        cum += t["pnl"]
        pts.append(dict(cum=round(cum, 2), pnl=round(t["pnl"], 2), idx=len(pts) + 1))
    return pts


# ──────────────────────────────────────────────────────────────────────
# CSS + JS (shared)
# ──────────────────────────────────────────────────────────────────────

SHARED_CSS = """
:root {
    --bg: #0d1117; --bg2: #161b22; --bg3: #21262d;
    --text: #c9d1d9; --text2: #8b949e; --border: #30363d;
    --green: #3fb950; --red: #f85149; --yellow: #d29922;
    --blue: #58a6ff; --purple: #bc8cff; --orange: #f0883e;
}
* { margin: 0; padding: 0; box-sizing: border-box; }
body { font-family: -apple-system, BlinkMacSystemFont, 'Segoe UI', Helvetica, monospace;
       background: var(--bg); color: var(--text); }
a { color: var(--blue); text-decoration: none; }
a:hover { text-decoration: underline; }
.container { max-width: 1200px; margin: 0 auto; padding: 20px; }
.nav { background: var(--bg2); border-bottom: 1px solid var(--border); padding: 12px 20px;
       display: flex; align-items: center; gap: 20px; position: sticky; top: 0; z-index: 100; }
.nav-brand { font-weight: 700; color: var(--blue); font-size: 1.1em; }
.nav a { color: var(--text2); font-size: 0.85em; }
.nav a:hover, .nav a.active { color: var(--text); }
.subtitle { color: var(--text2); margin-bottom: 20px; font-size: 0.82em; }
h1 { font-size: 1.4em; margin-bottom: 4px; }
h2 { font-size: 1.1em; margin-bottom: 12px; color: var(--text); }
.green { color: var(--green); } .red { color: var(--red); }
.yellow { color: var(--yellow); } .blue { color: var(--blue); }
.purple { color: var(--purple); } .orange { color: var(--orange); }

.grid { display: grid; grid-template-columns: repeat(auto-fit, minmax(180px, 1fr));
        gap: 10px; margin-bottom: 20px; }
.card { background: var(--bg2); border: 1px solid var(--border);
        border-radius: 8px; padding: 14px; }
.card h3 { font-size: 0.65em; color: var(--text2); text-transform: uppercase;
           letter-spacing: 1px; margin-bottom: 5px; }
.card .value { font-size: 1.6em; font-weight: 700; }
.card .sub { font-size: 0.75em; color: var(--text2); margin-top: 3px; }

.section { background: var(--bg2); border: 1px solid var(--border);
           border-radius: 8px; margin-bottom: 16px; overflow: hidden; }
.section-header { padding: 14px 16px; border-bottom: 1px solid var(--border);
                  display: flex; justify-content: space-between; align-items: center; }
.section-header h2 { margin: 0; }
.badge { display: inline-block; padding: 2px 8px; border-radius: 12px;
         font-size: 0.68em; font-weight: 600; }
.badge-live { background: rgba(63,185,80,0.15); color: var(--green); }

.bot-card { background: var(--bg2); border: 1px solid var(--border); border-radius: 8px;
            padding: 16px; display: flex; gap: 16px; align-items: center;
            transition: border-color 0.2s; cursor: pointer; }
.bot-card:hover { border-color: var(--blue); }
.bot-icon { font-size: 2em; width: 50px; text-align: center; }
.bot-info { flex: 1; }
.bot-info h3 { font-size: 1em; margin-bottom: 3px; }
.bot-info p { font-size: 0.78em; color: var(--text2); }
.bot-stats { text-align: right; }
.bot-stats .pnl { font-size: 1.3em; font-weight: 700; }
.bot-stats .detail { font-size: 0.75em; color: var(--text2); }

table { width: 100%; border-collapse: collapse; font-size: 0.8em; }
th { background: var(--bg3); padding: 8px 10px; text-align: left;
     font-size: 0.68em; text-transform: uppercase; letter-spacing: 1px;
     color: var(--text2); position: sticky; top: 0; }
td { padding: 6px 10px; border-bottom: 1px solid var(--border); }
tr:hover { background: rgba(88,166,255,0.04); }
.trade-win { border-left: 3px solid var(--green); }
.trade-loss { border-left: 3px solid var(--red); }
.trade-pending { border-left: 3px solid var(--yellow); }
.table-wrap { max-height: 600px; overflow-y: auto; }

.chart-container { padding: 16px; }
.bar-chart { display: flex; align-items: flex-end; gap: 1px; height: 100px; }
.bar { min-width: 3px; border-radius: 1px 1px 0 0; transition: height 0.3s; }
.bar-green { background: var(--green); }
.bar-red { background: var(--red); opacity: 0.7; }

.dist-row { display: flex; align-items: center; margin-bottom: 3px; font-size: 0.8em; font-family: monospace; }
.dist-label { width: 65px; color: var(--text2); }
.dist-bar { height: 16px; border-radius: 2px; margin: 0 4px; min-width: 1px; }
.dist-val { width: 45px; text-align: right; }
.dist-wr { width: 50px; text-align: right; }
.dist-pnl { width: 60px; text-align: right; }

.snapshot-notice { background: var(--bg3); border: 1px solid var(--border);
                   border-radius: 6px; padding: 8px 14px; margin-bottom: 16px;
                   font-size: 0.78em; color: var(--text2); }
.snapshot-notice strong { color: var(--yellow); }

footer { text-align: center; padding: 20px; color: var(--text2); font-size: 0.7em; }
"""

# ──────────────────────────────────────────────────────────────────────
# Templates
# ──────────────────────────────────────────────────────────────────────

NAV_HTML = """
<nav class="nav">
    <span class="nav-brand">Polymarket Dashboard</span>
    <a href="/" class="{{ 'active' if active == 'home' }}">Overview</a>
    {% for bot in bots %}
    <a href="/bot/{{ bot.id }}" class="{{ 'active' if active == bot.id }}">{{ bot.icon }} {{ bot.name }}</a>
    {% endfor %}
</nav>
"""

HOME_TEMPLATE = """
<!DOCTYPE html>
<html lang="en"><head>
<meta charset="UTF-8"><meta name="viewport" content="width=device-width, initial-scale=1.0">
<title>Polymarket Dashboard</title>
<style>""" + SHARED_CSS + """</style>
</head><body>
""" + NAV_HTML + """
<div class="container">
    <h1>Trading Overview</h1>
    <p class="subtitle">Data snapshot: {{ now }}</p>

    <div class="snapshot-notice">
        <strong>Note:</strong> This dashboard shows a snapshot of live trading data.
        Data is updated periodically via automated sync.
    </div>

    <div class="grid">
        <div class="card">
            <h3>Total P&L</h3>
            <div class="value {{ 'green' if g.pnl >= 0 else 'red' }}">${{ "%.2f"|format(g.pnl) }}</div>
            <div class="sub">All live bots combined</div>
        </div>
        <div class="card">
            <h3>Win Rate</h3>
            <div class="value {{ 'green' if g.wr > 15 else 'yellow' }}">{{ "%.1f"|format(g.wr) }}%</div>
            <div class="sub">{{ g.wins }}W / {{ g.losses }}L</div>
        </div>
        <div class="card">
            <h3>Live Trades</h3>
            <div class="value">{{ g.trades }}</div>
            <div class="sub">{{ g.pending }} pending</div>
        </div>
        <div class="card">
            <h3>Active Bots</h3>
            <div class="value blue">{{ bots|length }}</div>
            <div class="sub">Running with real money</div>
        </div>
    </div>

    <h2>Bots</h2>
    <div class="grid" style="grid-template-columns: 1fr;">
        {% for bot in bots %}
        <a href="/bot/{{ bot.id }}" style="text-decoration: none; color: inherit;">
        <div class="bot-card">
            <div class="bot-icon">{{ bot.icon }}</div>
            <div class="bot-info">
                <h3>{{ bot.name }}</h3>
                <p>{{ bot.desc }}</p>
            </div>
            <div class="bot-stats">
                <div class="pnl {{ 'green' if bot.summary.get('total_pnl', 0) >= 0 else 'red' }}">
                    ${{ "%.2f"|format(bot.summary.get('total_pnl', 0)) }}
                </div>
                <div class="detail">
                    {% if bot.summary.get('wins') is not none and bot.summary.get('losses') is not none %}
                    {{ bot.summary.get('wins', 0) }}W / {{ bot.summary.get('losses', 0) }}L
                    {% endif %}
                    <span class="badge badge-live">{{ bot.mode }}</span>
                </div>
            </div>
        </div>
        </a>
        {% endfor %}
    </div>

    {% if cum_pnl %}
    <div class="section">
        <div class="section-header"><h2>Reversal Bot — Cumulative P&L</h2></div>
        <div class="chart-container">
            <div class="bar-chart">
                {% for pt in cum_pnl %}
                {% set h = ((pt.cum / max_cum * 80)|int)|abs if max_cum > 0 else 1 %}
                <div class="bar {{ 'bar-green' if pt.cum >= 0 else 'bar-red' }}"
                     style="height: {{ h if h > 0 else 1 }}px; flex: 1;"
                     title="Trade #{{ pt.idx }}: P&L ${{ pt.pnl }}, Cum ${{ pt.cum }}"></div>
                {% endfor %}
            </div>
            <div style="display:flex; justify-content:space-between; font-size:0.7em; color:var(--text2); margin-top:4px;">
                <span>Trade #1</span>
                <span>Current: <strong class="{{ 'green' if cum_pnl[-1].cum >= 0 else 'red' }}">${{ "%.2f"|format(cum_pnl[-1].cum) }}</strong></span>
                <span>Trade #{{ cum_pnl|length }}</span>
            </div>
        </div>
    </div>
    {% endif %}
</div>
<footer>Polymarket Trading System v2.0</footer>
</body></html>
"""

BOT_TEMPLATE = """
<!DOCTYPE html>
<html lang="en"><head>
<meta charset="UTF-8"><meta name="viewport" content="width=device-width, initial-scale=1.0">
<title>{{ bot.name }} — Dashboard</title>
<style>""" + SHARED_CSS + """</style>
</head><body>
""" + NAV_HTML + """
<div class="container">
    <h1>{{ bot.icon }} {{ bot.name }}</h1>
    <p class="subtitle">{{ bot.desc }} — {{ bot.file }} — {{ now }}</p>

    <div class="grid">
        <div class="card">
            <h3>Net P&L</h3>
            <div class="value {{ 'green' if bot.summary.get('total_pnl',0) >= 0 else 'red' }}">
                ${{ "%.2f"|format(bot.summary.get('total_pnl', 0)) }}
            </div>
        </div>
        {% if bot.summary.get('wins') is not none %}
        <div class="card">
            <h3>Win Rate</h3>
            {% set wr = (bot.summary.wins / bot.summary.resolved * 100) if bot.summary.get('resolved',0) > 0 else 0 %}
            <div class="value {{ 'green' if wr > 15 else 'yellow' }}">{{ "%.1f"|format(wr) }}%</div>
            <div class="sub">{{ bot.summary.wins }}W / {{ bot.summary.losses }}L</div>
        </div>
        {% endif %}
        {% if bot.summary.get('avg_bet', 0) > 0 %}
        <div class="card">
            <h3>Avg Bet Size</h3>
            <div class="value">${{ "%.2f"|format(bot.summary.avg_bet) }}</div>
        </div>
        {% endif %}
        {% if bot.summary.get('avg_win', 0) != 0 %}
        <div class="card">
            <h3>Avg Win</h3>
            <div class="value green">${{ "%.2f"|format(bot.summary.avg_win) }}</div>
        </div>
        <div class="card">
            <h3>Avg Loss</h3>
            <div class="value red">${{ "%.2f"|format(bot.summary.avg_loss) }}</div>
        </div>
        {% endif %}
        {% if bot.summary.get('biggest_win', 0) > 0 %}
        <div class="card">
            <h3>Biggest Win</h3>
            <div class="value green">${{ "%.2f"|format(bot.summary.biggest_win) }}</div>
        </div>
        <div class="card">
            <h3>Biggest Loss</h3>
            <div class="value red">${{ "%.2f"|format(bot.summary.biggest_loss) }}</div>
        </div>
        {% endif %}
        {% if bot.summary.get('total_cost', 0) > 0 %}
        <div class="card">
            <h3>Total Risked</h3>
            <div class="value">${{ "%.2f"|format(bot.summary.total_cost) }}</div>
            <div class="sub">{{ bot.summary.get('pending', 0) }} pending</div>
        </div>
        {% endif %}
        {% if bot.summary.get('avg_bn', 0) > 0 %}
        <div class="card">
            <h3>Avg |BN|</h3>
            <div class="value">{{ "%.1f"|format(bot.summary.avg_bn) }} bps</div>
        </div>
        <div class="card">
            <h3>Avg Ask</h3>
            <div class="value">${{ "%.3f"|format(bot.summary.avg_ask) }}</div>
        </div>
        {% endif %}
        {% if bot.summary.get('budget', 0) > 0 %}
        <div class="card">
            <h3>Budget</h3>
            <div class="value">${{ "%.0f"|format(bot.summary.budget) }}</div>
        </div>
        <div class="card">
            <h3>Spent</h3>
            <div class="value">${{ "%.2f"|format(bot.summary.spent) }}</div>
        </div>
        <div class="card">
            <h3>Positions</h3>
            <div class="value">{{ bot.summary.positions }}</div>
        </div>
        {% endif %}
        {% if bot.summary.get('cycle_count', 0) > 0 %}
        <div class="card">
            <h3>Cycles</h3>
            <div class="value">{{ bot.summary.cycle_count }}</div>
        </div>
        {% endif %}
        {% if bot.summary.get('rebalance_count', 0) > 0 %}
        <div class="card">
            <h3>Rebalances</h3>
            <div class="value">{{ bot.summary.rebalance_count }}</div>
        </div>
        <div class="card">
            <h3>Deployed</h3>
            <div class="value">${{ "%.0f"|format(bot.summary.total_deployed) }}</div>
        </div>
        {% endif %}
    </div>

    {% if bot.variants %}
    <div class="section">
        <div class="section-header"><h2>Strategy Variants</h2></div>
        <table>
            <thead><tr><th>Variant</th><th>Trades</th><th>W/L</th><th>Win Rate</th><th>P&L</th><th>Skipped</th></tr></thead>
            <tbody>
            {% for vk, vs in bot.variants.items() %}
            <tr>
                <td><strong class="purple">V{{ vk }}</strong> {{ vs.name }}</td>
                <td>{{ vs.trades }}</td>
                <td>{{ vs.wins }}W / {{ vs.losses }}L</td>
                <td class="{{ 'green' if vs.trades > 0 and vs.wins/vs.trades > 0.15 else 'yellow' }}">
                    {{ "%.1f"|format(vs.wins/vs.trades*100) if vs.trades > 0 else 0 }}%
                </td>
                <td class="{{ 'green' if vs.pnl >= 0 else 'red' }}">${{ "%.2f"|format(vs.pnl) }}</td>
                <td style="color:var(--text2)">{{ vs.skips }}</td>
            </tr>
            {% endfor %}
            </tbody>
        </table>
    </div>
    {% endif %}

    {% if cum_pnl %}
    <div class="section">
        <div class="section-header"><h2>Cumulative P&L</h2></div>
        <div class="chart-container">
            <div style="display:flex; align-items:center; gap:8px; margin-bottom:8px;">
                <div style="width:10px;height:10px;background:var(--green);border-radius:2px;"></div>
                <span style="font-size:0.75em;color:var(--text2);">Profitable</span>
                <div style="width:10px;height:10px;background:var(--red);border-radius:2px;margin-left:12px;"></div>
                <span style="font-size:0.75em;color:var(--text2);">Underwater</span>
            </div>
            <div class="bar-chart" style="height:120px;">
                {% for pt in cum_pnl %}
                {% set h = ((pt.cum / max_cum * 100)|int)|abs if max_cum > 0 else 1 %}
                <div class="bar {{ 'bar-green' if pt.cum >= 0 else 'bar-red' }}"
                     style="height: {{ h if h > 0 else 1 }}px; flex: 1;"
                     title="Trade #{{ pt.idx }}: ${{ pt.pnl }} -> Cum ${{ pt.cum }}"></div>
                {% endfor %}
            </div>
            <div style="display:flex; justify-content:space-between; font-size:0.7em; color:var(--text2); margin-top:4px;">
                <span>Trade #1</span>
                <span>Current: <strong class="{{ 'green' if cum_pnl[-1].cum >= 0 else 'red' }}">${{ "%.2f"|format(cum_pnl[-1].cum) }}</strong></span>
                <span>Trade #{{ cum_pnl|length }}</span>
            </div>
        </div>
    </div>
    {% endif %}

    {% if bn_buckets %}
    <div class="section">
        <div class="section-header"><h2>Win/Loss by |BN| Range</h2></div>
        <div class="chart-container">
            {% for b in bn_buckets %}
            {% if b.total > 0 %}
            <div class="dist-row">
                <span class="dist-label">|BN| {{ b.label }}</span>
                <div style="display:flex; gap:1px; flex:1;">
                    {% set max_bar = bn_max if bn_max > 0 else 1 %}
                    <div class="dist-bar" style="width:{{ (b.wins / max_bar * 200)|int }}px; background:var(--green);"></div>
                    <div class="dist-bar" style="width:{{ (b.losses / max_bar * 200)|int }}px; background:var(--red); opacity:0.6;"></div>
                </div>
                <span class="dist-val">{{ b.wins }}W/{{ b.losses }}L</span>
                <span class="dist-wr {{ 'green' if b.wr > 20 else 'yellow' }}">{{ "%.0f"|format(b.wr) }}%</span>
                <span class="dist-pnl {{ 'green' if b.pnl >= 0 else 'red' }}">${{ "%.2f"|format(b.pnl) }}</span>
            </div>
            {% endif %}
            {% endfor %}
        </div>
    </div>
    {% endif %}

    {% if bot.trades and bot.id == 'reversal' %}
    <div class="section">
        <div class="section-header"><h2>Individual Trade P&L</h2></div>
        <div class="chart-container">
            <div style="display:flex; align-items:flex-end; gap:2px; height:80px; border-bottom:1px solid var(--border);">
                {% set resolved_trades = bot.trades|selectattr('live')|rejectattr('result', 'equalto', 'PENDING')|list %}
                {% set max_pnl = 1 %}
                {% for t in resolved_trades %}{% if t.pnl|abs > max_pnl %}{% set max_pnl = t.pnl|abs %}{% endif %}{% endfor %}
                {% for t in resolved_trades|sort(attribute='time') %}
                {% set h = ((t.pnl / 20 * 60)|int)|abs %}
                <div style="flex:1; min-width:3px; display:flex; flex-direction:column; justify-content:flex-end; align-items:center; height:100%;">
                    <div style="width:100%; max-width:8px; height:{{ h if h > 1 else 1 }}px;
                                background:{{ 'var(--green)' if t.pnl > 0 else 'var(--red)' }};
                                border-radius:1px; opacity:{{ '1' if t.pnl > 0 else '0.6' }};"
                         title="V{{ t.variant }} ${{ '%.2f'|format(t.pnl) }} |BN|={{ '%.1f'|format(t.bn_bps|abs) }}"></div>
                </div>
                {% endfor %}
            </div>
            <div style="font-size:0.7em; color:var(--text2); margin-top:4px; text-align:center;">
                Each bar = one trade. Green = win, Red = loss. Height = P&L magnitude.
            </div>
        </div>
    </div>
    {% endif %}

    {% if bot.markets %}
    <div class="section">
        <div class="section-header"><h2>Active Markets</h2></div>
        <table>
            <thead><tr><th>Market</th><th>YES Bid</th><th>YES Size</th><th>NO Bid</th><th>NO Size</th></tr></thead>
            <tbody>
            {% for mname, md in bot.markets.items() %}
            <tr>
                <td><strong class="blue">{{ mname }}</strong></td>
                <td>${{ md.get('yes_bid', 0) }}</td>
                <td>{{ md.get('yes_size', 0) }} tok</td>
                <td>${{ md.get('no_bid', 0) }}</td>
                <td>{{ md.get('no_size', 0) }} tok</td>
            </tr>
            {% endfor %}
            </tbody>
        </table>
    </div>
    {% endif %}

    {% if bot.positions %}
    <div class="section">
        <div class="section-header"><h2>Open Positions</h2></div>
        <table>
            <thead><tr><th>Bracket</th><th>Side</th><th>Entry</th><th>Size $</th><th>Tokens</th></tr></thead>
            <tbody>
            {% for p in bot.positions %}
            <tr>
                <td>{{ p.get('bracket_label', p.get('bracket_slug', '')[:35]) }}</td>
                <td>{{ p.get('side', '') }}</td>
                <td>${{ "%.2f"|format(p.get('entry_price', 0)) }}</td>
                <td>${{ "%.2f"|format(p.get('size_usd', 0)) }}</td>
                <td>{{ p.get('size_tokens', 0) }}</td>
            </tr>
            {% endfor %}
            </tbody>
        </table>
    </div>
    {% endif %}

    {% if bot.trades %}
    <div class="section">
        <div class="section-header">
            <h2>Trade Log ({{ bot.trades|length }} trades)</h2>
        </div>
        <div class="table-wrap">
            <table>
                <thead><tr>
                    <th>V</th><th>Time</th><th>|BN|</th><th>Dir</th>
                    <th>Ask</th><th>Cost</th><th>Tokens</th><th>Winner</th><th>P&L</th><th>Result</th>
                </tr></thead>
                <tbody>
                {% for t in bot.trades[:200] %}
                <tr class="{{ 'trade-win' if t.result == 'WIN' else 'trade-loss' if t.result == 'LOSS' else 'trade-pending' }}">
                    <td><strong class="purple">{{ t.variant }}</strong></td>
                    <td style="font-size:0.72em;color:var(--text2);">
                        {% if t.time > 0 %}{{ t.time|ts_format }}{% else %}-{% endif %}
                    </td>
                    <td>{{ "%.1f"|format(t.bn_bps|abs) if t.bn_bps else '-' }}</td>
                    <td>{{ t.direction }}</td>
                    <td>${{ "%.3f"|format(t.ask) if t.ask else '-' }}</td>
                    <td>${{ "%.2f"|format(t.cost) }}</td>
                    <td>{{ "%.1f"|format(t.tokens) }}</td>
                    <td>{{ t.winner }}</td>
                    <td class="{{ 'green' if t.pnl > 0 else 'red' if t.pnl < 0 else '' }}">
                        ${{ "%.2f"|format(t.pnl) }}
                    </td>
                    <td>
                        {% if t.result == 'WIN' %}<span class="green">WIN</span>
                        {% elif t.result == 'LOSS' %}<span class="red">LOSS</span>
                        {% else %}<span class="yellow">...</span>{% endif %}
                    </td>
                </tr>
                {% endfor %}
                </tbody>
            </table>
        </div>
    </div>
    {% endif %}
</div>
<footer>Polymarket Trading System v2.0</footer>
</body></html>
"""


# ──────────────────────────────────────────────────────────────────────
# Routes
# ──────────────────────────────────────────────────────────────────────

@app.route("/")
def home():
    bots = load_all_bots()
    g = compute_globals(bots)
    rev = next((b for b in bots if b["id"] == "reversal"), None)
    cum_pnl = get_cum_pnl(rev)
    max_cum = max((abs(p["cum"]) for p in cum_pnl), default=1)

    return render_template_string(HOME_TEMPLATE,
        bots=bots, g=g, active="home",
        now=datetime.now().strftime("%Y-%m-%d %H:%M:%S"),
        cum_pnl=cum_pnl, max_cum=max_cum)


@app.route("/bot/<bot_id>")
def bot_detail(bot_id):
    bots = load_all_bots()
    bot = next((b for b in bots if b["id"] == bot_id), None)
    if not bot:
        return "Bot not found", 404

    cum_pnl = get_cum_pnl(bot)
    max_cum = max((abs(p["cum"]) for p in cum_pnl), default=1)
    bn_buckets = get_bn_buckets(bot)
    bn_max = max((b["total"] for b in bn_buckets), default=1)

    return render_template_string(BOT_TEMPLATE,
        bot=bot, bots=bots, active=bot_id,
        now=datetime.now().strftime("%Y-%m-%d %H:%M:%S"),
        cum_pnl=cum_pnl, max_cum=max_cum,
        bn_buckets=bn_buckets, bn_max=bn_max)
