"""
Virtual Portfolio Tracker - tracks simulated P&L from paper trades
"""

import json
import os
from datetime import datetime, timezone

class PortfolioTracker:
    def __init__(self, log_file="trade_log.json"):
        self.log_file = log_file
        self.trades = self._load_trades()
    
    def _load_trades(self):
        try:
            with open(self.log_file, "r") as f:
                return json.load(f)
        except (FileNotFoundError, json.JSONDecodeError):
            return []
    
    def get_summary(self):
        if not self.trades:
            return "No trades yet."
        
        buys = [t for t in self.trades if t["type"] == "BUY"]
        sells = [t for t in self.trades if t["type"] == "SELL"]
        
        summary = f"\n  TRADE LOG SUMMARY ({len(buys)} buys, {len(sells)} sells)"
        summary += f"\n  {'-'*60}"
        
        for t in self.trades[-20:]:  # Last 20 trades
            ts = t.get("timestamp", "?")[:19]
            summary += f"\n  [{ts}] {t['type']:>4} {t.get('symbol','?'):6} "
            if "qty" in t:
                summary += f"{t['qty']}sh @ ${t.get('price',0):.2f}"
            summary += f" | {t.get('reason','')}"
        
        return summary


if __name__ == "__main__":
    tracker = PortfolioTracker()
    print(tracker.get_summary())
