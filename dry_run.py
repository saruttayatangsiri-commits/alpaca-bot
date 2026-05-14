"""
Dry run - shows strategy signals WITHOUT executing any trades.
"""

import sys, os
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

from config import (
    ALPACA_API_KEY, ALPACA_API_SECRET, ALPACA_BASE_URL,
    EMA_FAST, EMA_SLOW, RSI_PERIOD, RSI_OVERBOUGHT, SYMBOLS
)

from bot import Strategy, get_4h_bars_yahoo, calc_ema, calc_rsi
from datetime import datetime, timezone

print(f"\n{'='*80}")
print(f"  DRY RUN - EMA Crossover + RSI Filter (NO TRADES)")
print(f"  Time: {datetime.now(timezone.utc).strftime('%Y-%m-%d %H:%M UTC')}")
print(f"  Strategy: EMA {EMA_FAST}/{EMA_SLOW} Cross + RSI {RSI_PERIOD} < {RSI_OVERBOUGHT}")
print(f"  Timeframe: 4H | Data Source: Yahoo Finance")
print(f"{'='*80}")

buy_signals = []
sell_signals = []
results = []

for symbol in SYMBOLS:
    print(f"\n  Analyzing {symbol}...")
    
    bars = get_4h_bars_yahoo(symbol, period="6mo")
    if bars is None or len(bars) < 220:
        print(f"    Not enough data ({len(bars) if bars else 0} bars), need 220+")
        continue
    
    closes = [b["c"] for b in bars]
    
    ema_fast_vals = calc_ema(closes, EMA_FAST)
    ema_slow_vals = calc_ema(closes, EMA_SLOW)
    rsi_vals = calc_rsi(closes, RSI_PERIOD)
    
    latest_close = closes[-1]
    latest_ema_fast = ema_fast_vals[-1]
    latest_ema_slow = ema_slow_vals[-1]
    prev_ema_fast = ema_fast_vals[-2]
    prev_ema_slow = ema_slow_vals[-2]
    latest_rsi = rsi_vals[-1]
    
    was_bearish = prev_ema_fast <= prev_ema_slow
    is_bullish = latest_ema_fast > latest_ema_slow
    golden_cross = was_bearish and is_bullish
    
    was_bullish = prev_ema_fast >= prev_ema_slow
    is_bearish = latest_ema_fast < latest_ema_slow
    death_cross = was_bullish and is_bearish
    
    signal = "HOLD"
    reason = ""
    
    if golden_cross:
        if latest_rsi < RSI_OVERBOUGHT:
            signal = "BUY"
            reason = f"Golden Cross + RSI({latest_rsi:.1f}) < {RSI_OVERBOUGHT}"
        else:
            signal = "HOLD"
            reason = f"Golden Cross but RSI({latest_rsi:.1f}) >= {RSI_OVERBOUGHT} (overbought)"
    elif death_cross:
        signal = "SELL"
        reason = "Death Cross"
    elif is_bullish:
        signal = "HOLD"
        reason = "Bullish trend (no new cross)"
    else:
        signal = "HOLD"
        reason = "Bearish trend (no new cross)"
    
    print(f"    Price: ${latest_close:.2f} | EMA50: {latest_ema_fast:.2f} | "
          f"EMA200: {latest_ema_slow:.2f} | RSI: {latest_rsi:.1f}")
    print(f"    Signal: {signal} - {reason}")
    
    results.append({"symbol": symbol, "close": latest_close, "ema_fast": latest_ema_fast,
                    "ema_slow": latest_ema_slow, "rsi": latest_rsi, "signal": signal, "reason": reason})
    
    if signal == "BUY":
        buy_signals.append({"symbol": symbol, "close": latest_close, "rsi": latest_rsi})
    elif signal == "SELL":
        sell_signals.append({"symbol": symbol, "close": latest_close, "rsi": latest_rsi})

print(f"\n{'='*80}")
print(f"  SUMMARY")
print(f"{'='*80}")

if buy_signals:
    print(f"\n  BUY SIGNALS ({len(buy_signals)}):")
    for s in buy_signals:
        print(f"    >> {s['symbol']} @ ${s['close']:.2f} (RSI: {s['rsi']:.1f})")

if sell_signals:
    print(f"\n  SELL SIGNALS ({len(sell_signals)}):")
    for s in sell_signals:
        print(f"    >> {s['symbol']} @ ${s['close']:.2f} (RSI: {s['rsi']:.1f})")

no_action = len(results) - len(buy_signals) - len(sell_signals)
print(f"\n  HOLD/NO ACTION: {no_action}")
print(f"{'='*80}")
print(f"  DRY RUN COMPLETE - No trades executed")
print(f"{'='*80}\n")
