"""
Single scan - checks all symbols, checks SL/TP, and executes trades.
Designed to be run from cron (single execution, not a loop).
"""

import sys, os
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

from config import (
    ALPACA_API_KEY, ALPACA_API_SECRET, ALPACA_BASE_URL,
    EMA_FAST, EMA_SLOW, RSI_PERIOD, RSI_OVERBOUGHT,
    SYMBOLS, MAX_POSITIONS, POSITION_SIZE_PCT,
    STOP_LOSS_PCT, TAKE_PROFIT_PCT
)

from bot import AlpacaClient, Strategy
from position_tracker import (
    load_state, save_state, record_entry, check_sl_tp,
    close_position, get_open_positions, format_position_report
)
from datetime import datetime, timezone
import requests
import json

# ---------- ANALYSIS ----------
print(f"\n{'='*80}")
print(f"  STRATEGY SCAN - {datetime.now(timezone.utc).strftime('%Y-%m-%d %H:%M UTC')}")
print(f"  Strategy: EMA {EMA_FAST}/{EMA_SLOW} Cross + RSI {RSI_PERIOD} < {RSI_OVERBOUGHT}")
print(f"  SL: {STOP_LOSS_PCT*100:.0f}% | TP: {TAKE_PROFIT_PCT*100:.0f}%")
print(f"  Timeframe: 4H | Data: Yahoo Finance | Execution: Alpaca Paper")
print(f"{'='*80}")

client = AlpacaClient(ALPACA_API_KEY, ALPACA_API_SECRET, ALPACA_BASE_URL)
strategy = Strategy(client, EMA_FAST, EMA_SLOW, RSI_PERIOD, RSI_OVERBOUGHT)

# Get account info
try:
    account = client.get_account()
    equity = float(account["equity"])
    cash = float(account["cash"])
    bp = float(account["buying_power"])
    print(f"\n  Equity: ${equity:,.2f} | Cash: ${cash:,.2f} | Buying Power: ${bp:,.2f}")
except Exception as e:
    print(f"\n  Account error: {e}")
    sys.exit(1)

# Check SL/TP for open tracked positions first
print(f"\n  --- CHECKING STOP LOSS / TAKE PROFIT ---")
tracked_open = get_open_positions()
sl_tp_triggered = []

for symbol, pos in tracked_open.items():
    try:
        # Get latest price from Yahoo
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
        
        trigger = check_sl_tp(symbol, current_price)
        if trigger == "STOP_LOSS":
            sl_price = pos["stop_loss"]
            print(f"  [STOP LOSS] {symbol} @ ${current_price:.2f} (SL: ${sl_price:.2f})")
            sl_tp_triggered.append((symbol, current_price, "STOP_LOSS", sl_price))
        elif trigger == "TAKE_PROFIT":
            tp_price = pos["take_profit"]
            print(f"  [TAKE PROFIT] {symbol} @ ${current_price:.2f} (TP: ${tp_price:.2f})")
            sl_tp_triggered.append((symbol, current_price, "TAKE_PROFIT", tp_price))
        else:
            # Show position status
            entry = pos["entry_price"]
            pnl_pct = ((current_price - entry) / entry) * 100
            print(f"  [HOLDING] {symbol} @ ${current_price:.2f} | Entry ${entry:.2f} | P&L: {pnl_pct:+.1f}%")
    except Exception as e:
        print(f"  [ERROR] Checking {symbol}: {e}")

# Execute SL/TP closures
for symbol, price, reason, level in sl_tp_triggered:
    print(f"  [CLOSING] {symbol} - {reason}")
    try:
        client.close_position(symbol)
        close_position(symbol, price, reason)
        
        # Log
        log_file = "trade_log.json"
        logs = []
        try:
            with open(log_file, "r") as f:
                logs = json.load(f)
        except:
            pass
        state = load_state()
        pos = state.get(symbol, {})
        logs.append({
            "type": reason,
            "symbol": symbol,
            "entry_price": pos.get("entry_price", 0),
            "exit_price": price,
            "pnl_pct": pos.get("pnl_pct", 0),
            "timestamp": datetime.now(timezone.utc).isoformat(),
            "reason": reason
        })
        with open(log_file, "w") as f:
            json.dump(logs, f, indent=2)
        print(f"  [OK] {reason} executed for {symbol}")
    except Exception as e:
        print(f"  [ERROR] Closing {symbol}: {e}")

# Get current positions from Alpaca
try:
    alpaca_positions = client.get_positions()
    pos_symbols = {p["symbol"] for p in alpaca_positions}
except:
    pos_symbols = set()

print(f"\n  --- ANALYSIS ---")
results = []
for symbol in SYMBOLS:
    result = strategy.analyze_symbol(symbol)
    if result:
        results.append(result)

print(f"\n  {'Symbol':<8} {'Price':>10} {'EMA50':>10} {'EMA200':>10} {'RSI':>8} {'Signal':>8}")
print(f"  {'-'*8} {'-'*10} {'-'*10} {'-'*10} {'-'*8} {'-'*8}")
for r in results:
    print(f"  {r['symbol']:<8} ${r['close']:>9.2f} {r['ema_fast']:>10.2f} "
          f"{r['ema_slow']:>10.2f} {r['rsi']:>7.1f} {r['signal']:>8}")

# Execute strategy trades
print(f"\n  --- STRATEGY TRADES ---")
for result in results:
    symbol = result["symbol"]
    
    if result["signal"] == "BUY":
        if symbol in pos_symbols:
            print(f"  [SKIP] Already holding {symbol} (Alpaca)")
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
        if TAKE_PROFIT_PCT is not None:
            tp_price = entry_price * (1 + TAKE_PROFIT_PCT)
        else:
            tp_price = None
        
        if tp_price is not None:
            print(f"  [BUY] {symbol}: {qty} shares @ ~${entry_price:.2f}")
            print(f"        SL: ${sl_price:.2f} ({STOP_LOSS_PCT*100:.0f}%) | TP: ${tp_price:.2f}")
        else:
            print(f"  [BUY] {symbol}: {qty} shares @ ~${entry_price:.2f}")
            print(f"        SL: ${sl_price:.2f} ({STOP_LOSS_PCT*100:.0f}%) | TP: None (Death Cross exit)")
        
        try:
            order = client.market_buy(symbol, qty)
            record_entry(symbol, entry_price, qty, sl_price, tp_price, result["reason"])
            
            log_file = "trade_log.json"
            logs = []
            try:
                with open(log_file, "r") as f:
                    logs = json.load(f)
            except:
                pass
            logs.append({
                "type": "BUY", "symbol": symbol, "qty": qty,
                "price": entry_price, "stop_loss": sl_price, "take_profit": tp_price,
                "timestamp": datetime.now(timezone.utc).isoformat(),
                "reason": result["reason"]
            })
            with open(log_file, "w") as f:
                json.dump(logs, f, indent=2)
            print(f"  [OK] Order placed + position tracked")
        except Exception as e:
            print(f"  [ERROR] {e}")
    
    elif result["signal"] == "SELL":
        if symbol not in pos_symbols:
            print(f"  [SKIP] Not holding {symbol}")
            continue
        
        print(f"  [SELL] {symbol}: Death Cross signal")
        try:
            client.close_position(symbol)
            close_position(symbol, result["close"], "Death Cross")
            print(f"  [OK] Position closed")
        except Exception as e:
            print(f"  [ERROR] {e}")
    else:
        pass  # No action needed

# Position report
print(format_position_report())

# Final account status
print(f"\n{'='*80}")
try:
    account = client.get_account()
    equity = float(account["equity"])
    cash = float(account["cash"])
    bp = float(account["buying_power"])
    print(f"  FINAL: Equity ${equity:,.2f} | Cash ${cash:,.2f} | Buying Power ${bp:,.2f}")
    
    positions = client.get_positions()
    if positions:
        print(f"  Open Positions ({len(positions)}):")
        for p in positions:
            pnl = float(p.get("unrealized_pl", 0))
            print(f"    {p['symbol']}: {p['qty']} shares | P&L: ${pnl:+.2f}")
    else:
        print(f"  Open Positions: None")
except:
    pass
print(f"{'='*80}\n")
