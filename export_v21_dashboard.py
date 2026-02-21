#!/usr/bin/env python3
"""
Export V21 rebalancer state to lightweight dashboard JSON.
Strips per-trade arrays (~96% of file size) and pre-computes aggregates.
"""

import json
import os
from pathlib import Path

STATE_PATH = Path.home() / ".insider_researcher" / "rebalancer_v21_state.json"
OUTPUT_PATH = Path(__file__).parent / "data" / "rebalancer_v21_dashboard.json"


def compute_window_summary(trades):
    """Pre-compute per-window trade aggregates from the trades array."""
    n_trades = len(trades)
    if n_trades == 0:
        return {"maker_trades": 0, "taker_trades": 0, "maker_pct": 0,
                "fee_savings": 0, "max_bn_bps": 0, "avg_bn_bps": 0,
                "avg_combined_ask": 0, "phases": {}}

    maker_count = sum(1 for t in trades if t.get("is_maker"))
    taker_count = n_trades - maker_count

    # Fee savings: for each maker fill, we saved the taker fee + earned 20% rebate
    fee_savings = 0.0
    for t in trades:
        if t.get("is_maker"):
            fp = t.get("fill_price", t.get("ask", 0))
            tokens = t.get("tokens", 0)
            if 0 < fp < 1 and tokens > 0:
                fee = tokens * fp * 0.25 * (fp * (1 - fp)) ** 2
                fee_savings += fee * 1.20  # fee avoided + 20% rebate

    # BN momentum stats
    bn_vals = [abs(t.get("bn_momentum_bps", 0)) for t in trades]
    max_bn = max(bn_vals) if bn_vals else 0
    avg_bn = sum(bn_vals) / len(bn_vals) if bn_vals else 0

    # Combined ask average
    ca_vals = [t.get("combined_ask", 0) for t in trades if t.get("combined_ask", 0) > 0]
    avg_ca = sum(ca_vals) / len(ca_vals) if ca_vals else 0

    # Phase breakdown
    phases = {}
    for t in trades:
        p = t.get("phase", "unknown")
        phases[p] = phases.get(p, 0) + 1

    return {
        "maker_trades": maker_count,
        "taker_trades": taker_count,
        "maker_pct": round(maker_count / n_trades * 100, 1),
        "fee_savings": round(fee_savings, 4),
        "max_bn_bps": round(max_bn, 1),
        "avg_bn_bps": round(avg_bn, 1),
        "avg_combined_ask": round(avg_ca, 4),
        "phases": phases,
    }


def main():
    if not STATE_PATH.exists():
        print(f"State file not found: {STATE_PATH}")
        return

    with open(STATE_PATH) as f:
        state = json.load(f)

    windows = []
    for pos in state.get("positions", []):
        trades = pos.get("trades", [])
        summary = compute_window_summary(trades)

        # Compute total_usd and VWAP
        up_usd = pos.get("up_usd", 0)
        dn_usd = pos.get("down_usd", 0)
        up_tok = pos.get("up_tokens", 0)
        dn_tok = pos.get("down_tokens", 0)
        total_usd = up_usd + dn_usd

        winning_tok = max(up_tok, dn_tok)
        vwap_ratio = round(total_usd / winning_tok, 4) if winning_tok > 0 else 0

        won_side = pos.get("won_side", "")
        payout = up_tok if won_side == "Up" else dn_tok if won_side == "Down" else 0
        pnl = round(payout - total_usd, 2) if pos.get("resolved") else 0

        w = {
            "slug": pos.get("slug", ""),
            "title": pos.get("title", ""),
            "window_start": pos.get("window_start", 0),
            "window_end": pos.get("window_end", 0),
            "strike": round(pos.get("strike", 0), 2),
            "bn_strike": round(pos.get("bn_strike", 0), 2),
            "up_usd": round(up_usd, 2),
            "up_tokens": round(up_tok, 1),
            "down_usd": round(dn_usd, 2),
            "down_tokens": round(dn_tok, 1),
            "n_trades": pos.get("n_trades", len(trades)),
            "resolved": pos.get("resolved", False),
            "won_side": won_side,
            "pnl_usd": pnl,
            "payout_usd": round(payout, 2),
            "lean": pos.get("lean", ""),
            "lean_strength": round(pos.get("lean_strength", 0), 4),
            "combined_vwap": vwap_ratio,
            "total_usd": round(total_usd, 2),
            "effective_budget": pos.get("effective_budget", 0),
            "vol_multiplier": pos.get("vol_multiplier", 1.0),
            "hour_multiplier": pos.get("hour_multiplier", 1.0),
            "trend_r2": round(pos.get("trend_r2", 0), 3),
            "bn_gate_passed": pos.get("bn_gate_passed", False),
            "neutral_only": pos.get("neutral_only", False),
        }
        w.update(summary)
        windows.append(w)

    output = {
        "budget": state.get("budget", 0),
        "available": state.get("available", 0),
        "trades_taken": state.get("trades_taken", 0),
        "windows_seen": state.get("windows_seen", 0),
        "updated_at": state.get("updated_at", 0),
        "windows": windows,
    }

    OUTPUT_PATH.parent.mkdir(parents=True, exist_ok=True)
    with open(OUTPUT_PATH, "w") as f:
        json.dump(output, f, separators=(",", ":"))

    raw_size = STATE_PATH.stat().st_size / 1024
    out_size = OUTPUT_PATH.stat().st_size / 1024
    print(f"Exported {len(windows)} windows: {raw_size:.0f}KB -> {out_size:.0f}KB "
          f"({out_size/raw_size*100:.1f}%)")


if __name__ == "__main__":
    main()
