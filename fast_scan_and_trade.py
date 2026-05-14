"""
Fast EMA 9/21 Trading Bot - Single Scan + Auto Execute
Designed for cron (single execution, not a loop)
More frequent signals than EMA 50/200
"""

import sys, os
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

from fast_config import (
    ALPACA_API_KEY, ALPACA_API_SECRET, ALPACA_BASE_URL,
    EMA_FAST, EMA_SLOW, RSI_PERIOD, RSI_OVERBOUGHT,
    SYMBOLS, MAX_POSITIONS, POSITION_SIZE_PCT,
    STOP_LOSS_PCT, TAKE_PROFIT_PCT
)

from bot import AlpacaClient, Strategy, get_4h_bars_yahoo
from position_tracker import (
    load_state, save_state, record_entry, check_sl_tp,
    close_position, get_open_positions, format_position_report
)
from datetime import datetime, timezone
import requests
import json

# ---------- State File (separate from main bot) ----------
FAST_STATE_FILE = "fast_positions_state.json"
FAST_LOG_FILE = "fast_trade_log.json"

def load_fast_state():
    try:
        with open(FAST_STATE_FILE, "r") as f:
            return json.load(f)
    except (FileNotFoundError, json.JSONDecodeError):
        return {}

def save_fast_state(state):
    with open(FAST_STATE_FILE, "w") as f:
        json.dump(state, f, indent=2)

def record_fast_entry(symbol, entry_price, qty, stop_loss, take_profit, reason=""):
    state = load_fast_state()
    state[symbol] = {
        "entry_price": entry_price, "qty": qty,
        "stop_loss": stop_loss, "take_profit": take_profit,
        "reason": reason,
        "entry_time": datetime.now(timezone.utc).isoformat(),
        "status": "open"
    }
    save_fast_state(state)

def check_fast_sl_tp(symbol, current_price):
    state = load_fast_state()
    if symbol not in state or state[symbol]["status"] != "open":
        return None
    entry = state[symbol]["entry_price"]
    sl = state[symbol]["stop_loss"]
    tp = state[symbol].get("take_profit")
    if current_price <= sl:
        return "STOP_LOSS"
    elif tp is not None and current_price >= tp:
        return "TAKE_PROFIT"
    return None

def close_fast_position(symbol, exit_price, exit_reason):
    state = load_fast_state()
    if symbol in state:
        state[symbol]["exit_price"] = exit_price
        state[symbol]["exit_time"] = datetime.now(timezone.utc).isoformat()
        state[symbol]["exit_reason"] = exit_reason
        state[symbol]["pnl_pct"] = ((exit_price - state[symbol]["entry_price"]) / state[symbol]["entry_price"]) * 100
        state[symbol]["status"] = "closed"
        save_fast_state(state)

def get_fast_open_positions():
    state = load_fast_state()
    return {k: v for k, v in state.items() if v["status"] == "open"}

# ---------- MAIN ----------
print(f"\n{'='*80}")
print(f"  FAST BOT SCAN - {datetime.now(timezone.utc).strftime('%Y-%m-%d %H:%M UTC')}")
print(f"  Strategy: EMA {EMA_FAST}/{EMA_SLOW} Cross + RSI {RSI_PERIOD} < {RSI_OVERBOUGHT}")
print(f"  SL: {STOP_LOSS_PCT*100:.0f}% | TP: None (exit on crossover back)")
print(f"  Timeframe: 1H | Data: Yahoo Finance | Execution: Alpaca Paper")
print(f"{'='*80}")

client = AlpacaClient(ALPACA_API_KEY, ALPACA_API_SECRET, ALPACA_BASE_URL)
strategy = Strategy(client, EMA_FAST, EMA_SLOW, RSI_PERIOD, RSI_OVERBOUGHT)

# Account info
try:
    account = client.get_account()
    equity = float(account["equity"])
    cash = float(account["cash"])
    bp = float(account["buying_power"])
    print(f"\n  Equity: ${equity:,.2f} | Cash: ${cash:,.2f} | Buying Power: ${bp:,.2f}")
except Exception as e:
    print(f"\n  Account error: {e}")
    sys.exit(1)

# Check SL/TP
print(f"\n  --- CHECKING STOP LOSS ---")
tracked_open = get_fast_open_positions()
sl_tp_triggered = []

for symbol, pos in tracked_open.items():
    try:
        ticker_data = requests.get(
            f"https://query2.finance.yahoo.com/v8/finance/chart/{symbol}?interval=1d&range=1d",
            headers={"User-Agent": "Mozilla/5.0"},
            timeout=10
        ).json()
        result = ticker_data.get("chart", {}).get("result", [{}])[0]
        meta = result.get("meta", {})
        current_price = meta.get("regularMarketPrice", meta.get("previousClose", 0))
        
        if current_price <= 0:
            continue
        
        trigger = check_fast_sl_tp(symbol, current_price)
        if trigger == "STOP_LOSS":
            print(f"  [STOP LOSS] {symbol} @ ${current_price:.2f} (SL: ${pos['stop_loss']:.2f})")
            sl_tp_triggered.append((symbol, current_price, "STOP_LOSS"))
        elif trigger == "TAKE_PROFIT":
            print(f"  [TAKE PROFIT] {symbol} @ ${current_price:.2f} (TP: ${pos['take_profit']:.2f})")
            sl_tp_triggered.append((symbol, current_price, "TAKE_PROFIT"))
        else:
            entry = pos["entry_price"]
            pnl_pct = ((current_price - entry) / entry) * 100
            print(f"  [HOLDING] {symbol} @ ${current_price:.2f} | Entry ${entry:.2f} | P&L: {pnl_pct:+.1f}%")
    except Exception as e:
        print(f"  [ERROR] Checking {symbol}: {e}")

# Execute SL/TP
for symbol, price, reason in sl_tp_triggered:
    print(f"  [CLOSING] {symbol} - {reason}")
    try:
        client.close_position(symbol)
        close_fast_position(symbol, price, reason)
        logs = []
        try:
            with open(FAST_LOG_FILE, "r") as f:
                logs = json.load(f)
        except:
            pass
        state = load_fast_state()
        pos = state.get(symbol, {})
        logs.append({
            "type": reason, "symbol": symbol,
            "entry_price": pos.get("entry_price", 0),
            "exit_price": price, "pnl_pct": pos.get("pnl_pct", 0),
            "timestamp": datetime.now(timezone.utc).isoformat(),
            "reason": reason
        })
        with open(FAST_LOG_FILE, "w") as f:
            json.dump(logs, f, indent=2)
        print(f"  [OK] {reason} executed for {symbol}")
    except Exception as e:
        print(f"  [ERROR] Closing {symbol}: {e}")

# Get Alpaca positions
try:
    alpaca_positions = client.get_positions()
    pos_symbols = {p["symbol"] for p in alpaca_positions}
except:
    pos_symbols = set()

# Analyze symbols
print(f"\n  --- ANALYSIS ---")
results = []
for symbol in SYMBOLS:
    result = strategy.analyze_symbol(symbol)
    if result:
        results.append(result)

print(f"\n  {'Symbol':<8} {'Price':>10} {'EMA9':>10} {'EMA21':>10} {'RSI':>8} {'Signal':>8}")
print(f"  {'-'*8} {'-'*10} {'-'*10} {'-'*10} {'-'*8} {'-'*8}")
for r in results:
    print(f"  {r['symbol']:<8} ${r['close']:>9.2f} {r['ema_fast']:>10.2f} "
          f"{r['ema_slow']:>10.2f} {r['rsi']:>7.1f} {r['signal']:>8}")

# Execute trades
print(f"\n  --- STRATEGY TRADES ---")
current_positions = set(pos_symbols)

for result in results:
    symbol = result["symbol"]
    
    if result["signal"] == "BUY":
        if symbol in current_positions:
            print(f"  [SKIP] Already holding {symbol}")
            continue
        if symbol in tracked_open:
            print(f"  [SKIP] Already tracking {symbol}")
            continue
        if len(pos_symbols) + len(tracked_open) >= MAX_POSITIONS:
            print(f"  [SKIP] Max positions ({MAX_POSITIONS}) reached")
            continue
        
        account = client.get_account()
        bp = float(account["buying_power"])
        position_value = bp * POSITION_SIZE_PCT
        qty = max(1, int(position_value / result["close"]))
        
        entry_price = result["close"]
        sl_price = entry_price * (1 - STOP_LOSS_PCT)
        
        print(f"  [BUY] {symbol}: {qty} shares @ ~${entry_price:.2f}")
        print(f"        SL: ${sl_price:.2f} ({STOP_LOSS_PCT*100:.0f}%) | TP: None (exit on crossover back)")
        
        try:
            order = client.market_buy(symbol, qty)
            record_fast_entry(symbol, entry_price, qty, sl_price, None, result["reason"])
            
            logs = []
            try:
                with open(FAST_LOG_FILE, "r") as f:
                    logs = json.load(f)
            except:
                pass
            logs.append({
                "type": "BUY", "symbol": symbol, "qty": qty,
                "price": entry_price, "stop_loss": sl_price,
                "timestamp": datetime.now(timezone.utc).isoformat(),
                "reason": result["reason"]
            })
            with open(FAST_LOG_FILE, "w") as f:
                json.dump(logs, f, indent=2)
            print(f"  [OK] Order placed + position tracked")
        except Exception as e:
            print(f"  [ERROR] {e}")
    
    elif result["signal"] == "SELL":
        if symbol not in current_positions:
            print(f"  [SKIP] Not holding {symbol}")
            continue
        
        print(f"  [SELL] {symbol}: Death Cross signal")
        try:
            client.close_position(symbol)
            close_fast_position(symbol, result["close"], "Death Cross")
            print(f"  [OK] Position closed")
        except Exception as e:
            print(f"  [ERROR] {e}")
    else:
        pass

# Position report
print(f"\n  --- POSITIONS ---")
fast_open = get_fast_open_positions()
if fast_open:
    for sym, pos in fast_open.items():
        tp_str = f"${pos['take_profit']:.2f}" if pos.get("take_profit") else "None"
        print(f"  {sym}: Entry ${pos['entry_price']:.2f} | SL ${pos['stop_loss']:.2f} | TP {tp_str}")
else:
    print(f"  No open positions")

# Final status
print(f"\n{'='*80}")
try:
    account = client.get_account()
    print(f"  FINAL: Equity ${float(account['equity']):,.2f} | "
          f"Cash ${float(account['cash']):,.2f} | "
          f"Buying Power ${float(account['buying_power']):,.2f}")
except:
    pass
print(f"{'='*80}\n")
