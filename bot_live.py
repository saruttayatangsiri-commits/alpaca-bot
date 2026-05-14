"""
Alpaca Paper Trading Bot - Live Version
EMA 50/200 Crossover + RSI Filter + Stop Loss + Telegram Alerts
Data logging for analysis
"""

import requests
import json
import time
import yfinance as yf
from datetime import datetime, timezone
import os

# ─── Config ─────────────────────────────────────────────────────
import sys
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from config import (
    ALPACA_API_KEY, ALPACA_API_SECRET, ALPACA_BASE_URL,
    EMA_FAST, EMA_SLOW, RSI_PERIOD, RSI_OVERBOUGHT,
    SYMBOLS, MAX_POSITIONS, POSITION_SIZE_PCT,
    STOP_LOSS_PCT, TAKE_PROFIT_PCT, CHECK_INTERVAL_MINUTES
)

# Telegram Config
TELEGRAM_BOT_TOKEN = "8551276424:AAEeNzRJ_rwyo8tYw57D9cmQQEQ2fxqz0Lo"  # Trading_future bot
TELEGRAM_CHAT_ID = "8685944200"

# ─── Data Logging ───────────────────────────────────────────────
class DataLogger:
    """Log all market data and signals for later analysis."""
    def __init__(self, filename="live_data.jsonl"):
        self.filename = filename

    def log_scan(self, symbol, data):
        entry = {
            "type": "scan",
            "timestamp": datetime.now(timezone.utc).isoformat(),
            "symbol": symbol,
            **data
        }
        with open(self.filename, "a") as f:
            f.write(json.dumps(entry) + "\n")

    def log_trade(self, action, symbol, details):
        entry = {
            "type": "trade",
            "timestamp": datetime.now(timezone.utc).isoformat(),
            "action": action,
            "symbol": symbol,
            **details
        }
        with open(self.filename, "a") as f:
            f.write(json.dumps(entry) + "\n")
        # Also append to trade_log.json for easy viewing
        log_file = "trade_log.json"
        logs = []
        try:
            with open(log_file, "r") as f:
                logs = json.load(f)
        except (FileNotFoundError, json.JSONDecodeError):
            pass
        logs.append(entry)
        with open(log_file, "w") as f:
            json.dump(logs, f, indent=2)

# ─── Telegram ───────────────────────────────────────────────────
class TelegramNotifier:
    def __init__(self, bot_token, chat_id):
        self.bot_token = bot_token
        self.chat_id = chat_id
        self.base_url = f"https://api.telegram.org/bot{bot_token}"

    def send(self, message, parse_mode="Markdown"):
        try:
            url = f"{self.base_url}/sendMessage"
            data = {
                "chat_id": self.chat_id,
                "text": message[:4000],  # Telegram limit
                "parse_mode": parse_mode
            }
            resp = requests.post(url, json=data, timeout=10)
            if resp.status_code == 200:
                print(f"    [Telegram] ✅ Sent")
            else:
                print(f"    [Telegram] ❌ Failed: {resp.text[:200]}")
        except Exception as e:
            print(f"    [Telegram] ❌ Error: {e}")

# ─── Yahoo Finance Data ─────────────────────────────────────────
def get_daily_bars(symbol, period="2y"):
    """Get daily bars from Yahoo Finance."""
    try:
        ticker = yf.Ticker(symbol)
        df = ticker.history(period=period, interval="1d")
        if df.empty or len(df) < 220:
            return None
        bars = []
        for _, row in df.iterrows():
            bars.append({
                "timestamp": str(row.name),
                "o": float(row["Open"]),
                "h": float(row["High"]),
                "l": float(row["Low"]),
                "c": float(row["Close"]),
                "v": float(row["Volume"])
            })
        return bars
    except Exception as e:
        print(f"    Error fetching {symbol}: {e}")
        return None

def calc_ema(closes, period):
    if len(closes) < period:
        return []
    k = 2.0 / (period + 1)
    ema_values = []
    sma = sum(closes[:period]) / period
    ema_values.append(sma)
    for i in range(period, len(closes)):
        ema = closes[i] * k + ema_values[-1] * (1 - k)
        ema_values.append(ema)
    return ema_values

def calc_rsi(closes, period=14):
    if len(closes) < period + 1:
        return []
    gains, losses = [], []
    for i in range(1, len(closes)):
        diff = closes[i] - closes[i-1]
        gains.append(max(0, diff))
        losses.append(max(0, -diff))
    avg_gain = sum(gains[:period]) / period
    avg_loss = sum(losses[:period]) / period
    rsi_values = []
    if avg_loss == 0:
        rsi_values.append(100.0)
    else:
        rs = avg_gain / avg_loss
        rsi_values.append(100 - (100 / (1 + rs)))
    for i in range(period, len(gains)):
        avg_gain = (avg_gain * (period - 1) + gains[i]) / period
        avg_loss = (avg_loss * (period - 1) + losses[i]) / period
        if avg_loss == 0:
            rsi_values.append(100.0)
        else:
            rs = avg_gain / avg_loss
            rsi_values.append(100 - (100 / (1 + rs)))
    return rsi_values

# ─── Alpaca Client ──────────────────────────────────────────────
class AlpacaClient:
    def __init__(self, api_key, api_secret, base_url):
        self.api_key = api_key
        self.api_secret = api_secret
        self.base_url = base_url
        self.headers = {
            "APCA-API-KEY-ID": api_key,
            "APCA-API-SECRET-KEY": api_secret,
            "Content-Type": "application/json"
        }

    def _get(self, endpoint, params=None):
        resp = requests.get(f"{self.base_url}{endpoint}", headers=self.headers, params=params, timeout=15)
        resp.raise_for_status()
        return resp.json()

    def _post(self, endpoint, data=None):
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
        return self._get("/v2/positions")

    def get_clock(self):
        return self._get("/v2/clock")

    def market_buy(self, symbol, qty):
        data = {
            "symbol": symbol, "qty": str(qty),
            "side": "buy", "type": "market", "time_in_force": "gtc"
        }
        return self._post("/v2/orders", data)

    def market_sell(self, symbol, qty):
        data = {
            "symbol": symbol, "qty": str(qty),
            "side": "sell", "type": "market", "time_in_force": "gtc"
        }
        return self._post("/v2/orders", data)

    def close_position(self, symbol):
        return self._delete(f"/v2/positions/{symbol}")

# ─── Strategy ───────────────────────────────────────────────────
class Strategy:
    def __init__(self, ema_fast, ema_slow, rsi_period, rsi_overbought, stop_loss_pct):
        self.ema_fast = ema_fast
        self.ema_slow = ema_slow
        self.rsi_period = rsi_period
        self.rsi_overbought = rsi_overbought
        self.stop_loss_pct = stop_loss_pct

    def analyze(self, symbol):
        bars = get_daily_bars(symbol, period="2y")
        if bars is None or len(bars) < 220:
            return {"symbol": symbol, "signal": "NO_DATA", "reason": "Not enough data"}

        closes = [b["c"] for b in bars]
        ema_fast_vals = calc_ema(closes, self.ema_fast)
        ema_slow_vals = calc_ema(closes, self.ema_slow)
        rsi_vals = calc_rsi(closes, self.rsi_period)

        latest_close = closes[-1]
        latest_ema_fast = ema_fast_vals[-1]
        latest_ema_slow = ema_slow_vals[-1]
        prev_ema_fast = ema_fast_vals[-2]
        prev_ema_slow = ema_slow_vals[-2]
        latest_rsi = rsi_vals[-1] if rsi_vals else 50

        # Crossover detection
        was_bearish = prev_ema_fast <= prev_ema_slow
        is_bullish = latest_ema_fast > latest_ema_slow
        golden_cross = was_bearish and is_bullish

        was_bullish = prev_ema_fast >= prev_ema_slow
        is_bearish = latest_ema_fast < latest_ema_slow
        death_cross = was_bullish and is_bearish

        if golden_cross:
            if latest_rsi < self.rsi_overbought:
                signal = "BUY"
                reason = f"Golden Cross + RSI({latest_rsi:.1f}) < {self.rsi_overbought}"
            else:
                signal = "HOLD"
                reason = f"Golden Cross but RSI({latest_rsi:.1f}) >= {self.rsi_overbought}"
        elif death_cross:
            signal = "SELL"
            reason = "Death Cross"
        elif is_bullish:
            signal = "HOLD"
            reason = "Bullish trend (no new cross)"
        else:
            signal = "HOLD"
            reason = "Bearish trend"

        return {
            "symbol": symbol, "close": latest_close,
            "ema_fast": latest_ema_fast, "ema_slow": latest_ema_slow,
            "rsi": latest_rsi, "signal": signal, "reason": reason,
            "is_bullish": is_bullish
        }

    def check_stop_loss(self, current_price, entry_price):
        """Check if stop loss is hit."""
        loss_pct = (current_price - entry_price) / entry_price
        return loss_pct <= -self.stop_loss_pct

# ─── Trading Bot ────────────────────────────────────────────────
class TradingBot:
    def __init__(self):
        self.client = AlpacaClient(ALPACA_API_KEY, ALPACA_API_SECRET, ALPACA_BASE_URL)
        self.strategy = Strategy(EMA_FAST, EMA_SLOW, RSI_PERIOD, RSI_OVERBOUGHT, STOP_LOSS_PCT)
        self.logger = DataLogger()
        self.notifier = TelegramNotifier(TELEGRAM_BOT_TOKEN, TELEGRAM_CHAT_ID)
        self.trade_entries = {}  # symbol -> {entry_price, entry_time, shares}

    def run_scan(self):
        now = datetime.now(timezone.utc)
        print(f"\n{'='*80}")
        print(f"  SCAN @ {now.strftime('%Y-%m-%d %H:%M UTC')}")
        print(f"  Strategy: EMA {EMA_FAST}/{EMA_SLOW} + RSI {RSI_PERIOD} < {RSI_OVERBOUGHT}")
        print(f"  Stop Loss: {STOP_LOSS_PCT*100:.0f}% | Max Positions: {MAX_POSITIONS}")
        print(f"{'='*80}")

        # Check account
        try:
            account = self.client.get_account()
            equity = float(account["equity"])
            cash = float(account["cash"])
            bp = float(account["buying_power"])
            print(f"\n  Account: Equity ${equity:,.2f} | Cash ${cash:,.2f} | BP ${bp:,.2f}")
        except Exception as e:
            print(f"\n  ❌ Account Error: {e}")
            return

        # Get positions
        try:
            positions = self.client.get_positions()
            pos_map = {}
            for p in positions:
                pos_map[p["symbol"]] = {
                    "qty": float(p["qty"]),
                    "avg_entry": float(p["avg_entry_price"]),
                    "current_price": float(p["current_price"]),
                    "unrealized_pl": float(p.get("unrealized_pl", 0)),
                    "unrealized_pl_pct": float(p.get("unrealized_plpc", 0)) * 100
                }
            print(f"  Open Positions: {len(pos_map)}")
            for sym, p in pos_map.items():
                print(f"    {sym}: {p['qty']:.0f} shares @ ${p['avg_entry']:.2f} | "
                      f"Current: ${p['current_price']:.2f} | P&L: ${p['unrealized_pl']:+.2f} ({p['unrealized_pl_pct']:+.1f}%)")
        except Exception as e:
            print(f"  ❌ Position Error: {e}")
            pos_map = {}

        # Analyze all symbols
        results = []
        for symbol in SYMBOLS:
            result = self.strategy.analyze(symbol)
            results.append(result)
            self.logger.log_scan(symbol, result)

            icon = "BUY" if result["signal"] == "BUY" else ("SELL" if result["signal"] == "SELL" else "HOLD")
            price_str = f"${result.get('close', 0):,.2f}" if "close" in result else "N/A"
            rsi_str = f"{result.get('rsi', 0):.1f}" if "rsi" in result else "N/A"
            print(f"  {icon:<5} {symbol:<8} {price_str:>12} | RSI: {rsi_str:>6} | {result['reason']}")

        # Execute trades
        alerts = []
        for result in results:
            symbol = result["symbol"]
            signal = result["signal"]

            if signal == "BUY":
                if symbol in pos_map:
                    print(f"    [SKIP] Already holding {symbol}")
                    continue
                if len(pos_map) >= MAX_POSITIONS:
                    print(f"    [SKIP] Max positions ({MAX_POSITIONS}) reached")
                    continue
                self._execute_buy(symbol, result, alerts)
                pos_map[symbol] = True  # Prevent double-buy

            elif signal == "SELL":
                if symbol not in pos_map:
                    print(f"    [SKIP] Not holding {symbol}")
                    continue
                self._execute_sell(symbol, "Death Cross signal", alerts)
                if symbol in pos_map:
                    del pos_map[symbol]

            # Check stop loss for open positions
            if symbol in pos_map and isinstance(pos_map[symbol], dict):
                p = pos_map[symbol]
                current = result.get("close", 0)
                if current > 0 and self.strategy.check_stop_loss(current, p["avg_entry"]):
                    self._execute_sell(symbol, f"Stop Loss hit ({(current/p['avg_entry']-1)*100:.1f}%)", alerts)
                    if symbol in pos_map:
                        del pos_map[symbol]

        # Summary
        try:
            account = self.client.get_account()
            equity = float(account["equity"])
        except:
            equity = 0

        summary = f"{'='*80}\n"
        summary += f"  SCAN COMPLETE | Equity: ${equity:,.2f} | Positions: {len([k for k,v in pos_map.items() if v is not True])}\n"
        summary += f"{'='*80}"
        print(summary)

        if alerts:
            msg = f"📊 **Alpaca Scan** - {now.strftime('%H:%M UTC')}\n\n" + "\n".join(alerts)
            msg += f"\n\n💰 Equity: ${equity:,.2f}"
            self.notifier.send(msg)

        return results

    def _execute_buy(self, symbol, result, alerts):
        try:
            account = self.client.get_account()
            bp = float(account["buying_power"])
            pos_value = bp * POSITION_SIZE_PCT
            qty = max(1, int(pos_value / result["close"]))
            price = result["close"]

            print(f"\n  🟢 BUY {symbol}: {qty} shares @ ~${price:.2f} (${pos_value:.0f})")

            order = self.client.market_buy(symbol, qty)
            self.trade_entries[symbol] = {
                "entry_price": price,
                "entry_time": datetime.now(timezone.utc).isoformat(),
                "shares": qty
            }

            sl_price = price * (1 - STOP_LOSS_PCT)
            self.logger.log_trade("BUY", symbol, {
                "qty": qty, "price": price, "sl_price": sl_price,
                "reason": result["reason"]
            })

            alert_msg = f"🟢 **BUY** {symbol}\n💰 {qty} shares @ ${price:.2f}\n📊 {result['reason']}\n🛑 SL: ${sl_price:.2f} ({STOP_LOSS_PCT*100:.0f}%)"
            alerts.append(alert_msg)

        except Exception as e:
            print(f"  ❌ Buy failed: {e}")

    def _execute_sell(self, symbol, reason, alerts):
        try:
            pos = self.client.get_positions()
            pos_data = None
            for p in pos:
                if p["symbol"] == symbol:
                    pos_data = p
                    break

            if pos_data:
                qty = float(pos_data["qty"])
                current = float(pos_data["current_price"])
                entry = float(pos_data["avg_entry_price"])
                pnl = (current - entry) * qty
                pnl_pct = (current / entry - 1) * 100
            else:
                qty = 0
                current = 0
                pnl = 0
                pnl_pct = 0

            print(f"\n  🔴 SELL {symbol}: {qty:.0f} shares @ ~${current:.2f} | P&L: ${pnl:+.2f} ({pnl_pct:+.1f}%)")

            self.client.close_position(symbol)
            self.logger.log_trade("SELL", symbol, {
                "price": current, "pnl": pnl, "pnl_pct": pnl_pct,
                "reason": reason
            })

            direction = "PROFIT" if pnl > 0 else "LOSS"
            alert_msg = f"🔴 **SELL** {symbol}\n{'💸' if pnl > 0 else '💔'} {direction}: ${pnl:+.2f} ({pnl_pct:+.1f}%)\n📋 {reason}"
            alerts.append(alert_msg)

            if symbol in self.trade_entries:
                del self.trade_entries[symbol]

        except Exception as e:
            print(f"  ❌ Sell failed: {e}")

    def run_loop(self):
        print(f"\n  {'='*80}")
        print(f"  🤖 ALPACA PAPER TRADING BOT - LIVE")
        print(f"  {'='*80}")
        print(f"  Starting at {datetime.now(timezone.utc).strftime('%Y-%m-%d %H:%M UTC')}")
        print(f"  Check interval: {CHECK_INTERVAL_MINUTES} minutes")
        print(f"  Press Ctrl+C to stop")

        self.notifier.send(
            f"🤖 **Bot Started!**\n"
            f"Strategy: EMA {EMA_FAST}/{EMA_SLOW} + RSI filter\n"
            f"Symbols: {', '.join(SYMBOLS)}\n"
            f"Check every: {CHECK_INTERVAL_MINUTES}min\n"
            f"Stop Loss: {STOP_LOSS_PCT*100:.0f}%"
        )

        scan_count = 0
        while True:
            try:
                scan_count += 1
                print(f"\n  --- Scan #{scan_count} ---")
                self.run_scan()

                next_check = datetime.now(timezone.utc).timestamp() + CHECK_INTERVAL_MINUTES * 60
                print(f"\n  Next scan in {CHECK_INTERVAL_MINUTES} minutes...")
                time.sleep(CHECK_INTERVAL_MINUTES * 60)

            except KeyboardInterrupt:
                print(f"\n\n  {'='*80}")
                print(f"  Bot stopped after {scan_count} scans")
                print(f"  {'='*80}")
                self.notifier.send(f"🛑 **Bot Stopped**\nTotal scans: {scan_count}")
                break
            except Exception as e:
                print(f"\n  ❌ ERROR: {e}")
                import traceback
                traceback.print_exc()
                self.notifier.send(f"⚠️ **Bot Error**\n{str(e)[:500]}")
                print(f"  Retrying in 5 minutes...")
                time.sleep(300)

if __name__ == "__main__":
    if ALPACA_API_KEY == "YOUR_API_KEY_HERE" or ALPACA_API_KEY == "":
        print("ERROR: Set API keys in config.py first")
        sys.exit(1)

    bot = TradingBot()
    mode = sys.argv[1] if len(sys.argv) > 1 else "loop"

    if mode == "scan":
        bot.run_scan()
    elif mode == "loop":
        bot.run_loop()
    else:
        print("Usage: python bot_live.py [scan|loop]")
