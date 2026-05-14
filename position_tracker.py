"""
Position Tracker - tracks entry prices for Stop Loss / Take Profit
"""

import json
import os
from datetime import datetime, timezone

STATE_FILE = "positions_state.json"

def load_state():
    """Load tracked positions from state file."""
    try:
        with open(STATE_FILE, "r") as f:
            return json.load(f)
    except (FileNotFoundError, json.JSONDecodeError):
        return {}

def save_state(state):
    """Save tracked positions to state file."""
    with open(STATE_FILE, "w") as f:
        json.dump(state, f, indent=2)

def record_entry(symbol, entry_price, qty, stop_loss, take_profit, reason=""):
    """Record a new position entry."""
    state = load_state()
    state[symbol] = {
        "entry_price": entry_price,
        "qty": qty,
        "stop_loss": stop_loss,
        "take_profit": take_profit,  # Can be None (no fixed TP)
        "reason": reason,
        "entry_time": datetime.now(timezone.utc).isoformat(),
        "status": "open"
    }
    save_state(state)

def check_sl_tp(symbol, current_price):
    """
    Check if a position hit SL or TP.
    Returns: "STOP_LOSS", "TAKE_PROFIT", or None
    """
    state = load_state()
    if symbol not in state or state[symbol]["status"] != "open":
        return None
    
    entry = state[symbol]["entry_price"]
    sl = state[symbol]["stop_loss"]
    tp = state[symbol].get("take_profit")  # May be None
    
    if current_price <= sl:
        return "STOP_LOSS"
    elif tp is not None and current_price >= tp:
        return "TAKE_PROFIT"
    return None

def close_position(symbol, exit_price, exit_reason):
    """Mark a position as closed."""
    state = load_state()
    if symbol in state:
        state[symbol]["exit_price"] = exit_price
        state[symbol]["exit_time"] = datetime.now(timezone.utc).isoformat()
        state[symbol]["exit_reason"] = exit_reason
        state[symbol]["pnl_pct"] = ((exit_price - state[symbol]["entry_price"]) / state[symbol]["entry_price"]) * 100
        state[symbol]["status"] = "closed"
        save_state(state)

def get_open_positions():
    """Get all open positions."""
    state = load_state()
    return {k: v for k, v in state.items() if v["status"] == "open"}

def get_all_history():
    """Get all trade history."""
    state = load_state()
    return state

def format_position_report():
    """Generate a formatted report of positions."""
    state = load_state()
    if not state:
        return "  No tracked positions."
    
    lines = []
    open_positions = {k: v for k, v in state.items() if v["status"] == "open"}
    closed_positions = {k: v for k, v in state.items() if v["status"] == "closed"}
    
    if open_positions:
        lines.append(f"\n  OPEN POSITIONS ({len(open_positions)}):")
        for sym, pos in open_positions.items():
            sl = pos["stop_loss"]
            tp = pos.get("take_profit")
            tp_str = f"${tp:.2f}" if tp else "None (Death Cross)"
            lines.append(f"    {sym}: Entry ${pos['entry_price']:.2f} | SL ${sl:.2f} | TP {tp_str}")
    
    if closed_positions:
        lines.append(f"\n  CLOSED POSITIONS ({len(closed_positions)}):")
        for sym, pos in closed_positions.items():
            pnl = pos.get("pnl_pct", 0)
            exit_reason = pos.get("exit_reason", "?")
            lines.append(f"    {sym}: Entry ${pos['entry_price']:.2f} -> Exit ${pos['exit_price']:.2f} | "
                        f"P&L: {pnl:+.1f}% | Reason: {exit_reason}")
    
    return "\n".join(lines)

if __name__ == "__main__":
    print(format_position_report())
