"""
Backtest Engine - tests the EMA Crossover + RSI strategy on historical data
with Stop Loss and Take Profit simulation.
"""

import sys, os, json
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

import yfinance as yf
import pandas as pd
from datetime import datetime, timezone

from config import EMA_FAST, EMA_SLOW, RSI_PERIOD, RSI_OVERBOUGHT, STOP_LOSS_PCT, TAKE_PROFIT_PCT, POSITION_SIZE_PCT
from bot import calc_ema, calc_rsi


def get_historical_data(symbol, period="3y"):
    """Get daily historical data from Yahoo Finance."""
    ticker = yf.Ticker(symbol)
    df = ticker.history(period=period)
    if df.empty:
        return None
    return df


def backtest_symbol(symbol, df, initial_capital=100000):
    """
    Backtest a single symbol with the strategy.
    
    Rules:
    - BUY: EMA50 crosses above EMA200 AND RSI < 70
    - SELL: EMA50 crosses below EMA200 (Death Cross)
    - Stop Loss: 2% below entry
    - Take Profit: 4% above entry
    """
    if len(df) < EMA_SLOW + 20:
        return None
    
    closes = df["Close"].tolist()
    highs = df["High"].tolist()
    lows = df["Low"].tolist()
    dates = df.index.tolist()
    
    # Calculate indicators
    ema_fast_vals = calc_ema(closes, EMA_FAST)
    ema_slow_vals = calc_ema(closes, EMA_SLOW)
    rsi_vals = calc_rsi(closes, RSI_PERIOD)
    
    # Offset arrays to align with price data
    fast_offset = EMA_FAST - 1  # EMA starts at index EMA_FAST-1
    slow_offset = EMA_SLOW - 1  # EMA starts at index EMA_SLOW-1
    rsi_offset = RSI_PERIOD     # RSI starts at index RSI_PERIOD
    
    cash = initial_capital
    position = None  # {shares, entry_price, entry_date, stop_loss, take_profit}
    trades = []
    equity_curve = []
    
    # Start from when all indicators are available
    start_idx = max(fast_offset, slow_offset, rsi_offset) + 1
    
    for i in range(start_idx, len(closes)):
        date = dates[i]
        price = closes[i]
        high = highs[i]
        low = lows[i]
        
        # Get indicator values (with offset alignment)
        ema_f = ema_fast_vals[i - fast_offset] if (i - fast_offset) < len(ema_fast_vals) else None
        ema_s = ema_slow_vals[i - slow_offset] if (i - slow_offset) < len(ema_slow_vals) else None
        rsi = rsi_vals[i - rsi_offset] if (i - rsi_offset) < len(rsi_vals) else None
        
        if ema_f is None or ema_s is None or rsi is None:
            equity_curve.append({"date": date, "equity": cash})
            continue
        
        prev_ema_f = ema_fast_vals[i - fast_offset - 1] if (i - fast_offset - 1) >= 0 else None
        prev_ema_s = ema_slow_vals[i - slow_offset - 1] if (i - slow_offset - 1) >= 0 else None
        
        if prev_ema_f is None or prev_ema_s is None:
            equity_curve.append({"date": date, "equity": cash})
            continue
        
        # Check if in position
        if position is not None:
            # Check Stop Loss first (intra-bar)
            if low <= position["stop_loss"]:
                exit_price = position["stop_loss"]
                pnl = (exit_price - position["entry_price"]) * position["shares"]
                pnl_pct = (exit_price - position["entry_price"]) / position["entry_price"] * 100
                cash += exit_price * position["shares"]
                trades.append({
                    "type": "STOP_LOSS",
                    "symbol": symbol,
                    "entry_date": str(position["entry_date"])[:10],
                    "exit_date": str(date)[:10],
                    "entry_price": position["entry_price"],
                    "exit_price": exit_price,
                    "shares": position["shares"],
                    "pnl": pnl,
                    "pnl_pct": pnl_pct,
                    "hold_days": (date - position["entry_date"]).days
                })
                position = None
            
            # Check Take Profit (intra-bar) - only if TP is set
            elif TAKE_PROFIT_PCT is not None and high >= position["take_profit"]:
                exit_price = position["take_profit"]
                pnl = (exit_price - position["entry_price"]) * position["shares"]
                pnl_pct = (exit_price - position["entry_price"]) / position["entry_price"] * 100
                cash += exit_price * position["shares"]
                trades.append({
                    "type": "TAKE_PROFIT",
                    "symbol": symbol,
                    "entry_date": str(position["entry_date"])[:10],
                    "exit_date": str(date)[:10],
                    "entry_price": position["entry_price"],
                    "exit_price": exit_price,
                    "shares": position["shares"],
                    "pnl": pnl,
                    "pnl_pct": pnl_pct,
                    "hold_days": (date - position["entry_date"]).days
                })
                position = None
            
            # Check Death Cross (close-based)
            elif prev_ema_f >= prev_ema_s and ema_f < ema_s:
                exit_price = price
                pnl = (exit_price - position["entry_price"]) * position["shares"]
                pnl_pct = (exit_price - position["entry_price"]) / position["entry_price"] * 100
                cash += exit_price * position["shares"]
                trades.append({
                    "type": "DEATH_CROSS",
                    "symbol": symbol,
                    "entry_date": str(position["entry_date"])[:10],
                    "exit_date": str(date)[:10],
                    "entry_price": position["entry_price"],
                    "exit_price": exit_price,
                    "shares": position["shares"],
                    "pnl": pnl,
                    "pnl_pct": pnl_pct,
                    "hold_days": (date - position["entry_date"]).days
                })
                position = None
        
        # Check for buy signal (only if not in position)
        if position is None:
            # Golden cross: was below, now above
            was_bearish = prev_ema_f <= prev_ema_s
            is_bullish = ema_f > ema_s
            golden_cross = was_bearish and is_bullish
            
            if golden_cross and rsi < RSI_OVERBOUGHT:
                # Buy
                shares = int((cash * POSITION_SIZE_PCT) / price)
                if shares > 0:
                    cost = shares * price
                    cash -= cost
                    if TAKE_PROFIT_PCT is not None:
                        tp = price * (1 + TAKE_PROFIT_PCT)
                    else:
                        tp = None
                    position = {
                        "shares": shares,
                        "entry_price": price,
                        "entry_date": date,
                        "stop_loss": price * (1 - STOP_LOSS_PCT),
                        "take_profit": tp
                    }
        
        # Track equity
        current_equity = cash
        if position:
            current_equity += position["shares"] * price
        equity_curve.append({"date": date, "equity": current_equity})
    
    # Close any remaining position at end
    if position:
        exit_price = closes[-1]
        pnl = (exit_price - position["entry_price"]) * position["shares"]
        pnl_pct = (exit_price - position["entry_price"]) / position["entry_price"] * 100
        cash += exit_price * position["shares"]
        trades.append({
            "type": "END_OF_TEST",
            "symbol": symbol,
            "entry_date": str(position["entry_date"])[:10],
            "exit_date": str(dates[-1])[:10],
            "entry_price": position["entry_price"],
            "exit_price": exit_price,
            "shares": position["shares"],
            "pnl": pnl,
            "pnl_pct": pnl_pct,
            "hold_days": (dates[-1] - position["entry_date"]).days
        })
    
    final_equity = cash
    total_return = (final_equity - initial_capital) / initial_capital * 100
    
    # Calculate stats
    wins = [t for t in trades if t["pnl"] > 0]
    losses = [t for t in trades if t["pnl"] <= 0]
    win_rate = len(wins) / len(trades) * 100 if trades else 0
    
    # Max drawdown
    max_equity = initial_capital
    max_dd = 0
    for eq in equity_curve:
        if eq["equity"] > max_equity:
            max_equity = eq["equity"]
        dd = (max_equity - eq["equity"]) / max_equity * 100
        if dd > max_dd:
            max_dd = dd
    
    # Average hold time
    hold_days = [t["hold_days"] for t in trades if t["hold_days"] > 0]
    avg_hold = sum(hold_days) / len(hold_days) if hold_days else 0
    
    # Trade type breakdown
    sl_trades = len([t for t in trades if t["type"] == "STOP_LOSS"])
    tp_trades = len([t for t in trades if t["type"] == "TAKE_PROFIT"])
    dc_trades = len([t for t in trades if t["type"] == "DEATH_CROSS"])
    end_trades = len([t for t in trades if t["type"] == "END_OF_TEST"])
    
    return {
        "symbol": symbol,
        "initial_capital": initial_capital,
        "final_equity": final_equity,
        "total_return_pct": total_return,
        "total_trades": len(trades),
        "wins": len(wins),
        "losses": len(losses),
        "win_rate": win_rate,
        "max_drawdown_pct": max_dd,
        "avg_hold_days": avg_hold,
        "sl_hits": sl_trades,
        "tp_hits": tp_trades,
        "death_cross_exits": dc_trades,
        "trades": trades,
        "equity_curve": equity_curve
    }


def print_results(results):
    """Print formatted backtest results."""
    print(f"\n{'='*90}")
    print(f"  BACKTEST RESULTS")
    print(f"  Strategy: EMA {EMA_FAST}/{EMA_SLOW} Cross + RSI {RSI_PERIOD} < {RSI_OVERBOUGHT}")
    if TAKE_PROFIT_PCT is not None:
        tp_str = f"{TAKE_PROFIT_PCT*100:.0f}%"
    else:
        tp_str = "None (Death Cross exit)"
    print(f"  Stop Loss: {STOP_LOSS_PCT*100:.0f}% | Take Profit: {tp_str}")
    print(f"  Position Size: {POSITION_SIZE_PCT*100:.0f}% per trade | Timeframe: Daily")
    print(f"{'='*90}")
    
    # Summary table
    print(f"\n  {'Symbol':<8} {'Return':>10} {'Trades':>8} {'Win%':>8} {'Max DD':>10} {'Avg Hold':>10} {'SL':>5} {'TP':>5} {'DC':>5}")
    print(f"  {'-'*8} {'-'*10} {'-'*8} {'-'*8} {'-'*10} {'-'*10} {'-'*5} {'-'*5} {'-'*5}")
    
    total_return = 0
    total_trades = 0
    total_wins = 0
    max_dd_overall = 0
    
    for r in results:
        print(f"  {r['symbol']:<8} {r['total_return_pct']:>+9.1f}% {r['total_trades']:>8} "
              f"{r['win_rate']:>7.1f}% {r['max_drawdown_pct']:>9.1f}% "
              f"{r['avg_hold_days']:>8.1f}d {r['sl_hits']:>5} {r['tp_hits']:>5} {r['death_cross_exits']:>5}")
        total_return += r["total_return_pct"]
        total_trades += r["total_trades"]
        total_wins += r["wins"]
        if r["max_drawdown_pct"] > max_dd_overall:
            max_dd_overall = r["max_drawdown_pct"]
    
    avg_return = total_return / len(results) if results else 0
    overall_win_rate = total_wins / total_trades * 100 if total_trades else 0
    
    print(f"  {'-'*8} {'-'*10} {'-'*8} {'-'*8} {'-'*10} {'-'*10} {'-'*5} {'-'*5} {'-'*5}")
    print(f"  {'AVG':<8} {avg_return:>+9.1f}% {total_trades:>8} "
          f"{overall_win_rate:>7.1f}% {max_dd_overall:>9.1f}%")
    
    # Trade breakdown
    print(f"\n  EXIT BREAKDOWN:")
    total_sl = sum(r["sl_hits"] for r in results)
    total_tp = sum(r["tp_hits"] for r in results)
    total_dc = sum(r["death_cross_exits"] for r in results)
    total_end = sum(1 for r in results for t in r["trades"] if t["type"] == "END_OF_TEST")
    
    print(f"    Stop Loss hits:    {total_sl}")
    print(f"    Take Profit hits:  {total_tp}")
    print(f"    Death Cross exits: {total_dc}")
    print(f"    Still open (EOT):  {total_end}")
    
    # Recent trades
    print(f"\n  RECENT TRADES (last 20):")
    all_trades = []
    for r in results:
        all_trades.extend(r["trades"])
    
    # Sort by exit date
    all_trades.sort(key=lambda x: x["exit_date"], reverse=True)
    
    print(f"  {'Symbol':<8} {'Type':>12} {'Entry':>10} {'Exit':>10} {'P&L%':>8} {'Days':>6}")
    print(f"  {'-'*8} {'-'*12} {'-'*10} {'-'*10} {'-'*8} {'-'*6}")
    for t in all_trades[:20]:
        print(f"  {t['symbol']:<8} {t['type']:>12} ${t['entry_price']:>9.2f} ${t['exit_price']:>9.2f} "
              f"{t['pnl_pct']:>+7.1f}% {t['hold_days']:>5}d")
    
    print(f"\n{'='*90}\n")
    
    # Save detailed results
    output = {
        "strategy": f"EMA {EMA_FAST}/{EMA_SLOW} Cross + RSI {RSI_PERIOD} < {RSI_OVERBOUGHT}",
        "stop_loss_pct": STOP_LOSS_PCT,
        "take_profit_pct": TAKE_PROFIT_PCT,
        "position_size_pct": POSITION_SIZE_PCT,
        "results": [{k: v for k, v in r.items() if k != "equity_curve"} for r in results],
        "run_at": datetime.now(timezone.utc).isoformat()
    }
    
    with open("backtest_results.json", "w") as f:
        json.dump(output, f, indent=2, default=str)
    
    print(f"  Detailed results saved to: backtest_results.json\n")


def main():
    from config import SYMBOLS
    
    period = "3y"
    if len(sys.argv) > 1:
        period = sys.argv[1]
    
    # Allow testing specific symbols
    symbols = SYMBOLS
    if len(sys.argv) > 2:
        symbols = sys.argv[2].split(",")
    
    print(f"\n  Running backtest on {len(symbols)} symbols...")
    print(f"  Period: {period}")
    if TAKE_PROFIT_PCT is not None:
        print(f"  SL: {STOP_LOSS_PCT*100:.0f}% | TP: {TAKE_PROFIT_PCT*100:.0f}%")
    else:
        print(f"  SL: {STOP_LOSS_PCT*100:.0f}% | TP: None (Death Cross exit)")
    
    results = []
    for symbol in symbols:
        print(f"\n  Backtesting {symbol}...")
        df = get_historical_data(symbol, period=period)
        if df is None or len(df) < EMA_SLOW + 20:
            print(f"    Not enough data for {symbol}")
            continue
        
        result = backtest_symbol(symbol, df)
        if result:
            results.append(result)
            print(f"    Return: {result['total_return_pct']:+.1f}% | "
                  f"Trades: {result['total_trades']} | "
                  f"Win Rate: {result['win_rate']:.1f}%")
    
    if results:
        print_results(results)
    else:
        print("\n  No results generated. Check data availability.")


if __name__ == "__main__":
    main()
