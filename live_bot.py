"""
Alpaca Paper Trading Bot — LIVE MODE
EMA 50/200 Crossover + RSI Filter + Telegram Alerts
Auto-logs all trades to CSV for analysis
"""

import requests
import json
import time
import csv
import os
import yfinance as yf
from datetime import datetime, timezone
from config_live import (
    ALPACA_API_KEY, ALPACA_API_SECRET, ALPACA_BASE_URL,
    TELEGRAM_BOT_TOKEN, TELEGRAM_CHAT_ID,
    EMA_FAST, EMA_SLOW, RSI_PERIOD, RSI_OVERBOUGHT,
    SYMBOLS, MAX_POSITIONS, POSITION_SIZE_PCT,
    STOP_LOSS_PCT, CHECK_INTERVAL_MINUTES
)

# ─── Paths ───────────────────────────────────────────────────────
LOG_CSV = "live_trades.csv"
STATE_FILE = "live_state.json"

# ─── Telegram ────────────────────────────────────────────────────
def send_telegram(msg):
    """Send message to Telegram."""
    if not TELEGRAM_BOT_TOKEN or not TELEGRAM_CHAT_ID:
        return
    url = f"https://api.telegram.org/bot{TELEGRAM_BOT_TOKEN}/sendMessage"
    data = {"chat_id": TELEGRAM_CHAT_ID, "text": msg, "parse_mode": "Markdown"}
    try:
        resp = requests.post(url, json=data, timeout=10)
        if resp.status_code != 200:
            print(f"  [Telegram] Failed: {resp.text[:100]}")
    except Exception as e:
        print(f"  [Telegram] Error: {e}")

def send_alert(title, details):
    """Send formatted alert to Telegram."""
    now = datetime.now().strftime("%d/%m %H:%M")
    msg = f"📊 *{title}*\n"
    msg += f"⏰ {now}\n\n"
    for k, v in details.items():
        msg += f"• *{k}:* {v}\n"
    send_telegram(msg)

# ─── CSV Logger ──────────────────────────────────────────────────
def init_csv():
    """Create CSV file with headers if it doesn't exist."""
    if not os.path.exists(LOG_CSV):
        with open(LOG_CSV, "w", newline="") as f:
            writer = csv.writer(f)
            writer.writerow([
                "timestamp", "type", "symbol", "qty", "entry_price",
                "exit_price", "pnl", "pnl_pct", "reason", "ema50",
                "ema200", "rsi", "portfolio_value"
            ])

def log_trade(**kwargs):
    """Append trade to CSV."""
    defaults = {
        "timestamp": datetime.now().isoformat(),
        "type": "", "symbol": "", "qty": 0, "entry_price": 0,
        "exit_price": 0, "pnl": 0, "pnl_pct": 0, "reason": "",
        "ema50": 0, "ema200": 0, "rsi": 0, "portfolio_value": 0
    }
    defaults.update(kwargs)
    with open(LOG_CSV, "a", newline="") as f:
        writer = csv.writer(f)
        writer.writerow([defaults[k] for k in defaults.keys()])

# ─── State ───────────────────────────────────────────────────────
def save_state(portfolio_value, positions):
    state = {
        "portfolio_value": portfolio_value,
        "positions": positions,
        "last_update": datetime.now().isoformat()
    }
    with open(STATE_FILE, "w") as f:
        json.dump(state, f, indent=2)

def load_state():
    if os.path.exists(STATE_FILE):
        with open(STATE_FILE) as f:
            return json.load(f)
    return None

# ─── Indicators ──────────────────────────────────────────────────
def calc_ema(closes, period):
    if len(closes) < period:
        return []
    k = 2.0 / (period + 1)
    ema = [sum(closes[:period]) / period]
    for i in range(period, len(closes)):
        ema.append(closes[i] * k + ema[-1] * (1 - k))
    return ema

def calc_rsi(closes, period=14):
    if len(closes) < period + 1:
        return []
    gains, losses = [], []
    for i in range(1, len(closes)):
        diff = closes[i] - closes[i-1]
        gains.append(max(0, diff))
        losses.append(max(0, -diff))
    avg_g = sum(gains[:period]) / period
    avg_l = sum(losses[:period]) / period
    rsi = []
    if avg_l == 0:
        rsi.append(100.0)
    else:
        rsi.append(100 - (100 / (1 + avg_g / avg_l)))
    for i in range(period, len(gains)):
        avg_g = (avg_g * (period-1) + gains[i]) / period
        avg_l = (avg_l * (period-1) + losses[i]) / period
        if avg_l == 0:
            rsi.append(100.0)
        else:
            rsi.append(100 - (100 / (1 + avg_g / avg_l)))
    return rsi

def get_daily_bars(symbol, period="2y"):
    """Get daily bars from Yahoo Finance."""
    try:
        ticker = yf.Ticker(symbol)
        df = ticker.history(period=period, interval="1d")
        if df.empty or len(df) < EMA_SLOW + 10:
            return None
        return [
            {"timestamp": str(idx.date()), "c": float(row["Close"])}
            for idx, row in df.iterrows()
        ]
    except Exception as e:
        print(f"  Error fetching {symbol}: {e}")
        return None

# ─── Alpaca API ──────────────────────────────────────────────────
class AlpacaClient:
    def __init__(self):
        self.base_url = ALPACA_BASE_URL
        self.headers = {
            "APCA-API-KEY-ID": ALPACA_API_KEY,
            "APCA-API-SECRET-KEY": ALPACA_API_SECRET,
            "Content-Type": "application/json"
        }

    def _get(self, endpoint):
        resp = requests.get(f"{self.base_url}{endpoint}", headers=self.headers, timeout=15)
        resp.raise_for_status()
        return resp.json()

    def _post(self, endpoint, data):
        resp = requests.post(f"{self.base_url}{endpoint}", headers=self.headers, json=data, timeout=15)
        resp.raise_for_status()
        return resp.json()

    def _delete(self, endpoint):
        resp = requests.delete(f"{self.base_url}{endpoint}", headers=self.headers, timeout=15)
        resp.raise_for_status()
        return resp.json() if resp.content else {}

    def get_account(self):
        return self._get("/v2/account")

    def get_positions(self):
        try:
            return self._get("/v2/positions")
        except:
            return []

    def market_buy(self, symbol, qty):
        return self._post("/v2/orders", {
            "symbol": symbol, "qty": str(qty),
            "side": "buy", "type": "market", "time_in_force": "gtc"
        })

    def market_sell(self, symbol, qty):
        return self._post("/v2/orders", {
            "symbol": symbol, "qty": str(qty),
            "side": "sell", "type": "market", "time_in_force": "gtc"
        })

    def close_position(self, symbol):
        return self._delete(f"/v2/positions/{symbol}")

# ─── Strategy ────────────────────────────────────────────────────
def analyze_symbol(symbol):
    """Analyze one symbol and return signal."""
    bars = get_daily_bars(symbol, period="2y")
    if bars is None or len(bars) < EMA_SLOW + 10:
        return {"symbol": symbol, "signal": "NO_DATA", "reason": "Not enough data"}

    closes = [b["c"] for b in bars]
    ema50 = calc_ema(closes, EMA_FAST)
    ema200 = calc_ema(closes, EMA_SLOW)
    rsi_vals = calc_rsi(closes, RSI_PERIOD)

    if len(ema50) < 2 or len(ema200) < 2 or len(rsi_vals) < 1:
        return {"symbol": symbol, "signal": "NO_DATA", "reason": "Indicator calc failed"}

    price = closes[-1]
    e50 = ema50[-1]
    e200 = ema200[-1]
    e50_prev = ema50[-2]
    e200_prev = ema200[-2]
    rsi = rsi_vals[-1]

    was_bearish = e50_prev <= e200_prev
    is_bullish = e50 > e200
    golden_cross = was_bearish and is_bullish

    was_bullish = e50_prev >= e200_prev
    is_bearish = e50 < e200
    death_cross = was_bullish and is_bearish

    if golden_cross:
        if rsi < RSI_OVERBOUGHT:
            return {"symbol": symbol, "signal": "BUY", "price": price,
                    "ema50": e50, "ema200": e200, "rsi": rsi,
                    "reason": f"Golden Cross + RSI {rsi:.1f}"}
        else:
            return {"symbol": symbol, "signal": "HOLD", "price": price,
                    "ema50": e50, "ema200": e200, "rsi": rsi,
                    "reason": f"Golden Cross but RSI {rsi:.1f} overbought"}
    elif death_cross:
        return {"symbol": symbol, "signal": "SELL", "price": price,
                "ema50": e50, "ema200": e200, "rsi": rsi,
                "reason": "Death Cross"}
    elif is_bullish:
        return {"symbol": symbol, "signal": "HOLD", "price": price,
                "ema50": e50, "ema200": e200, "rsi": rsi,
                "reason": "Bullish trend (no cross)"}
    else:
        return {"symbol": symbol, "signal": "HOLD", "price": price,
                "ema50": e50, "ema200": e200, "rsi": rsi,
                "reason": "Bearish trend"}

# ─── Main Bot ────────────────────────────────────────────────────
class LiveBot:
    def __init__(self):
        self.client = AlpacaClient()
        self.scan_count = 0
        init_csv()

    def run_scan(self):
        self.scan_count += 1
        now = datetime.now().strftime("%Y-%m-%d %H:%M")
        print(f"\n{'='*70}")
        print(f"  SCAN #{self.scan_count} — {now}")
        print(f"{'='*70}")

        # Account status
        try:
            account = self.client.get_account()
            equity = float(account["equity"])
            cash = float(account["cash"])
            print(f"  Equity: ${equity:,.2f} | Cash: ${cash:,.2f}")
        except Exception as e:
            print(f"  ❌ Account error: {e}")
            return

        # Current positions
        positions = self.client.get_positions()
        held_symbols = {p["symbol"] for p in positions}
        print(f"  Open Positions: {len(positions)}/{MAX_POSITIONS}")
        for p in positions:
            pnl = float(p.get("unrealized_pl", 0))
            print(f"    {p['symbol']}: {p['qty']} shares | P&L: ${pnl:+,.2f}")

        # Scan all symbols
        results = []
        for sym in SYMBOLS:
            if sym in held_symbols:
                continue  # Already holding
            if len(held_symbols) >= MAX_POSITIONS:
                break  # Max positions reached
            res = analyze_symbol(sym)
            results.append(res)

        # Print summary
        print(f"\n  {'Symbol':<8} {'Price':>10} {'EMA50':>10} {'EMA200':>10} {'RSI':>8} {'Signal':>8}")
        print(f"  {'─'*8} {'─'*10} {'─'*10} {'─'*10} {'─'*8} {'─'*8}")
        for r in results:
            p = r.get("price", 0)
            e50 = r.get("ema50", 0)
            e200 = r.get("ema200", 0)
            rsi = r.get("rsi", 0)
            sig = r["signal"]
            print(f"  {r['symbol']:<8} ${p:>9.2f} {e50:>10.2f} {e200:>10.2f} {rsi:>7.1f} {sig:>8}")

        # Execute trades
        for r in results:
            if r["signal"] == "BUY":
                sym = r["symbol"]
                price = r["price"]
                try:
                    account = self.client.get_account()
                    bp = float(account["buying_power"])
                    alloc = bp * POSITION_SIZE_PCT
                    qty = max(1, int(alloc / price))
                    if qty == 0:
                        continue

                    print(f"\n  🟢 BUY {sym}: {qty} shares @ ~${price:.2f}")
                    order = self.client.market_buy(sym, qty)

                    log_trade(
                        type="BUY", symbol=sym, qty=qty, entry_price=price,
                        ema50=r["ema50"], ema200=r["ema200"], rsi=r["rsi"],
                        portfolio_value=float(account["equity"]), reason=r["reason"]
                    )
                    send_alert(
                        f"BUY {sym}",
                        {"Qty": qty, "Price": f"${price:.2f}",
                         "EMA50": f"{r['ema50']:.2f}", "RSI": f"{r['rsi']:.1f}",
                         "Reason": r["reason"]}
                    )
                    held_symbols.add(sym)
                except Exception as e:
                    print(f"  ❌ Buy failed: {e}")

            elif r["signal"] == "SELL":
                sym = r["symbol"]
                if sym not in held_symbols:
                    continue
                try:
                    # Find position details
                    pos = None
                    for p in positions:
                        if p["symbol"] == sym:
                            pos = p
                            break
                    if pos:
                        entry = float(pos["avg_entry_price"])
                        current = float(pos["current_price"])
                        pnl_pct = ((current - entry) / entry) * 100
                    else:
                        entry = current = pnl_pct = 0

                    print(f"\n  🔴 SELL {sym} (Death Cross)")
                    self.client.close_position(sym)

                    log_trade(
                        type="SELL", symbol=sym, exit_price=current,
                        entry_price=entry, pnl_pct=pnl_pct,
                        reason=f"Death Cross ({pnl_pct:+.1f}%)"
                    )
                    send_alert(
                        f"SELL {sym}",
                        {"Entry": f"${entry:.2f}", "Exit": f"${current:.2f}",
                         "P&L": f"{pnl_pct:+.1f}%", "Reason": "Death Cross"}
                    )
                    held_symbols.discard(sym)
                except Exception as e:
                    print(f"  ❌ Sell failed: {e}")

        # Save state
        try:
            account = self.client.get_account()
            save_state(float(account["equity"]), list(held_symbols))
        except:
            pass

        print(f"\n  ✅ Scan complete. Next scan in {CHECK_INTERVAL_MINUTES} min")

    def run(self):
        print(f"\n{'#'*70}")
        print(f"  ALPACA PAPER TRADING BOT — LIVE")
        print(f"  Strategy: EMA {EMA_FAST}/{EMA_SLOW} + RSI {RSI_OVERBOUGHT}")
        print(f"  Symbols: {', '.join(SYMBOLS)}")
        print(f"  Max Positions: {MAX_POSITIONS} | Size: {POSITION_SIZE_PCT*100:.0f}%")
        print(f"  Check Interval: {CHECK_INTERVAL_MINUTES} min")
        print(f"  Press Ctrl+C to stop")
        print(f"{'#'*70}")

        # Send startup alert
        send_alert(
            "BOT STARTED",
            {"Strategy": f"EMA {EMA_FAST}/{EMA_SLOW} + RSI",
             "Symbols": ", ".join(SYMBOLS),
             "Interval": f"{CHECK_INTERVAL_MINUTES} min"}
        )

        while True:
            try:
                self.run_scan()
                time.sleep(CHECK_INTERVAL_MINUTES * 60)
            except KeyboardInterrupt:
                print(f"\n  Bot stopped after {self.scan_count} scans")
                send_alert("BOT STOPPED", {"Scans": self.scan_count})
                break
            except Exception as e:
                print(f"\n  ❌ ERROR: {e}")
                import traceback
                traceback.print_exc()
                send_alert("BOT ERROR", {"Error": str(e)[:200]})
                time.sleep(300)

if __name__ == "__main__":
    bot = LiveBot()
    bot.run()
