"""
Strategy Optimizer - sweeps parameter combinations and finds the best setup.
Tests EMA periods, RSI levels, SL/TP, and filters to maximize profit.
"""

import sys, os
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

import yfinance as yf
import json
from datetime import datetime, timezone
from itertools import product

from bot import calc_ema, calc_rsi


def get_historical_data(symbol, period="5y"):
    ticker = yf.Ticker(symbol)
    df = ticker.history(period=period)
    return df if not df.empty else None


def backtest_single(df, ema_fast, ema_slow, rsi_period, rsi_overbought, 
                    sl_pct, tp_pct, position_pct, use_trailing=False, trailing_pct=0.03,
                    require_volume=False, volume_threshold=1.2):
    """
    Backtest with given parameters.
    Returns: dict with performance metrics
    """
    if len(df) < max(ema_slow, rsi_period) + 20:
        return None
    
    closes = df["Close"].tolist()
    highs = df["High"].tolist()
    lows = df["Low"].tolist()
    volumes = df["Volume"].tolist()
    dates = df.index.tolist()
    
    ema_f_vals = calc_ema(closes, ema_fast)
    ema_s_vals = calc_ema(closes, ema_slow)
    rsi_vals = calc_rsi(closes, rsi_period)
    
    fast_off = ema_fast - 1
    slow_off = ema_slow - 1
    rsi_off = rsi_period
    
    cash = 100000
    position = None
    trades = []
    
    avg_vol = sum(volumes[:len(volumes)//3]) / (len(volumes)//3) if volumes else 1
    
    start_idx = max(fast_off, slow_off, rsi_off) + 1
    
    for i in range(start_idx, len(closes)):
        price = closes[i]
        high = highs[i]
        low = lows[i]
        vol = volumes[i]
        
        ema_f = ema_f_vals[i - fast_off] if (i - fast_off) < len(ema_f_vals) else None
        ema_s = ema_s_vals[i - slow_off] if (i - slow_off) < len(ema_s_vals) else None
        rsi = rsi_vals[i - rsi_off] if (i - rsi_off) < len(rsi_vals) else None
        
        if ema_f is None or ema_s is None or rsi is None:
            continue
        
        prev_ema_f = ema_f_vals[i - fast_off - 1] if (i - fast_off - 1) >= 0 else None
        prev_ema_s = ema_s_vals[i - slow_off - 1] if (i - slow_off - 1) >= 0 else None
        
        if prev_ema_f is None or prev_ema_s is None:
            continue
        
        # Position management
        if position is not None:
            # Update trailing stop
            if use_trailing:
                trail_stop = position["entry_price"] * (1 + trailing_pct)
                if price > trail_stop:
                    position["stop_loss"] = price * (1 - trailing_pct)
            
            # Check SL
            if low <= position["stop_loss"]:
                exit_price = position["stop_loss"]
                pnl_pct = (exit_price - position["entry_price"]) / position["entry_price"] * 100
                cash += exit_price * position["shares"]
                trades.append({"pnl_pct": pnl_pct, "type": "SL", "hold": (dates[i] - position["entry_date"]).days})
                position = None
            # Check TP
            elif high >= position["take_profit"]:
                exit_price = position["take_profit"]
                pnl_pct = (exit_price - position["entry_price"]) / position["entry_price"] * 100
                cash += exit_price * position["shares"]
                trades.append({"pnl_pct": pnl_pct, "type": "TP", "hold": (dates[i] - position["entry_date"]).days})
                position = None
            # Death cross exit
            elif prev_ema_f >= prev_ema_s and ema_f < ema_s:
                pnl_pct = (price - position["entry_price"]) / position["entry_price"] * 100
                cash += price * position["shares"]
                trades.append({"pnl_pct": pnl_pct, "type": "DC", "hold": (dates[i] - position["entry_date"]).days})
                position = None
        
        # Buy signal
        if position is None:
            was_bearish = prev_ema_f <= prev_ema_s
            is_bullish = ema_f > ema_s
            golden_cross = was_bearish and is_bullish
            
            # Volume filter
            vol_ok = True
            if require_volume:
                vol_ok = vol >= avg_vol * volume_threshold
            
            if golden_cross and rsi < rsi_overbought and vol_ok:
                shares = int((cash * position_pct) / price)
                if shares > 0:
                    cash -= shares * price
                    position = {
                        "shares": shares,
                        "entry_price": price,
                        "entry_date": dates[i],
                        "stop_loss": price * (1 - sl_pct),
                        "take_profit": price * (1 + tp_pct)
                    }
    
    # Close remaining
    if position:
        pnl_pct = (closes[-1] - position["entry_price"]) / position["entry_price"] * 100
        cash += closes[-1] * position["shares"]
        trades.append({"pnl_pct": pnl_pct, "type": "EOT", "hold": (dates[-1] - position["entry_date"]).days})
    
    final = cash
    total_return = (final - 100000) / 100000 * 100
    wins = [t for t in trades if t["pnl_pct"] > 0]
    losses = [t for t in trades if t["pnl_pct"] <= 0]
    win_rate = len(wins) / len(trades) * 100 if trades else 0
    
    # Max drawdown
    equity = 100000
    max_eq = 100000
    max_dd = 0
    for t in trades:
        equity *= (1 + t["pnl_pct"] / 100)
        if equity > max_eq:
            max_eq = equity
        dd = (max_eq - equity) / max_eq * 100
        if dd > max_dd:
            max_dd = dd
    
    # Profit factor
    gross_profit = sum(t["pnl_pct"] for t in wins)
    gross_loss = abs(sum(t["pnl_pct"] for t in losses))
    profit_factor = gross_profit / gross_loss if gross_loss > 0 else float('inf')
    
    avg_hold = sum(t["hold"] for t in trades if t["hold"] > 0) / max(1, len([t for t in trades if t["hold"] > 0]))
    
    # Score: prioritize total return, penalize low trade count and high drawdown
    trade_penalty = max(0, 5 - len(trades)) * 2  # Penalty for too few trades
    score = total_return - max_dd * 0.5 - trade_penalty
    
    return {
        "total_return": total_return,
        "total_trades": len(trades),
        "win_rate": win_rate,
        "max_drawdown": max_dd,
        "profit_factor": profit_factor,
        "avg_hold_days": avg_hold,
        "score": score,
        "final_equity": final
    }


def optimize():
    """Run optimization sweep."""
    
    # Use a diverse set of symbols
    symbols = ["AAPL", "MSFT", "GOOGL", "AMZN", "TSLA", "SPY", "QQQ", "NVDA", "META", "JPM"]
    
    print(f"\n{'='*80}")
    print(f"  STRATEGY OPTIMIZER")
    print(f"  Testing parameter combinations across {len(symbols)} symbols")
    print(f"{'='*80}")
    
    # Fetch all data first
    print(f"\n  Fetching historical data...")
    all_data = {}
    for sym in symbols:
        df = get_historical_data(sym, period="5y")
        if df is not None and len(df) > 250:
            all_data[sym] = df
            print(f"    {sym}: {len(df)} bars")
        else:
            print(f"    {sym}: SKIP (not enough data)")
    
    if not all_data:
        print("  No data available!")
        return
    
    # Parameter ranges to test
    # We'll test strategically, not exhaustively (too many combos)
    
    param_sets = []
    
    # Strategy A: Classic EMA crossover (slower)
    for ef, es in [(9, 21), (10, 30), (12, 26), (20, 50), (50, 200)]:
        for rsi_ob in [60, 70, 80]:
            for sl in [0.03, 0.05, 0.08, 0.10]:
                for tp in [0.04, 0.06, 0.08, 0.12, 0.15]:
                    param_sets.append({
                        "ema_fast": ef, "ema_slow": es,
                        "rsi_period": 14, "rsi_overbought": rsi_ob,
                        "sl_pct": sl, "tp_pct": tp,
                        "position_pct": 0.25,
                        "use_trailing": False,
                        "require_volume": False
                    })
    
    # Strategy B: Trailing stop variants
    for ef, es in [(12, 26), (20, 50)]:
        for sl in [0.05, 0.08]:
            for tp in [0.10, 0.15, 0.20]:
                for trail in [0.03, 0.05, 0.08]:
                    param_sets.append({
                        "ema_fast": ef, "ema_slow": es,
                        "rsi_period": 14, "rsi_overbought": 80,
                        "sl_pct": sl, "tp_pct": tp,
                        "position_pct": 0.25,
                        "use_trailing": True,
                        "trailing_pct": trail,
                        "require_volume": False
                    })
    
    # Strategy C: No fixed TP (let winners run, exit only on death cross or SL)
    for ef, es in [(9, 21), (12, 26), (20, 50), (50, 200)]:
        for sl in [0.05, 0.08, 0.10]:
            param_sets.append({
                "ema_fast": ef, "ema_slow": es,
                "rsi_period": 14, "rsi_overbought": 80,
                "sl_pct": sl, "tp_pct": 999.0,  # No TP
                "position_pct": 0.25,
                "use_trailing": False,
                "require_volume": False
            })
    
    print(f"\n  Testing {len(param_sets)} parameter combinations...")
    print(f"  (This may take a few minutes)\n")
    
    all_results = []
    best_score = -999999
    best_params = None
    best_results = None
    
    for idx, params in enumerate(param_sets):
        if (idx + 1) % 50 == 0:
            print(f"    Progress: {idx+1}/{len(param_sets)} ...")
        
        symbol_results = []
        total_return = 0
        total_trades = 0
        valid = True
        
        for sym, df in all_data.items():
            r = backtest_single(df, **params)
            if r is None:
                valid = False
                break
            symbol_results.append(r)
            total_return += r["total_return"]
            total_trades += r["total_trades"]
        
        if not valid or total_trades < 3:
            continue
        
        avg_return = total_return / len(symbol_results)
        avg_score = sum(r["score"] for r in symbol_results) / len(symbol_results)
        avg_dd = sum(r["max_drawdown"] for r in symbol_results) / len(symbol_results)
        avg_wr = sum(r["win_rate"] for r in symbol_results) / len(symbol_results)
        
        result = {
            "params": params,
            "avg_return": avg_return,
            "avg_score": avg_score,
            "avg_drawdown": avg_dd,
            "avg_win_rate": avg_wr,
            "total_trades": total_trades,
            "symbol_results": symbol_results
        }
        all_results.append(result)
        
        if avg_score > best_score:
            best_score = avg_score
            best_params = params
            best_results = result
    
    # Sort by score
    all_results.sort(key=lambda x: x["avg_score"], reverse=True)
    
    print(f"\n{'='*80}")
    print(f"  TOP 10 PARAMETER SETS")
    print(f"{'='*80}")
    
    print(f"\n  {'#':>3} {'Return':>9} {'Trades':>7} {'Win%':>7} {'MaxDD':>8} {'Score':>8} {'EMA':>10} {'SL':>5} {'TP':>5} {'Trail':>5} {'RSI<':>5}")
    print(f"  {'-'*3} {'-'*9} {'-'*7} {'-'*7} {'-'*8} {'-'*8} {'-'*10} {'-'*5} {'-'*5} {'-'*5} {'-'*5}")
    
    for i, r in enumerate(all_results[:10]):
        p = r["params"]
        trail = "Y" if p.get("use_trailing") else "N"
        trail_val = f"{p.get('trailing_pct', 0)*100:.0f}" if p.get("use_trailing") else "-"
        tp_val = f"{p['tp_pct']*100:.0f}" if p['tp_pct'] < 100 else "None"
        if p['tp_pct'] >= 100 and isinstance(p['tp_pct'], (int, float)):
            tp_val = "None"
        elif p['tp_pct'] is None:
            tp_val = "None"
        
        print(f"  {i+1:>3} {r['avg_return']:>+8.1f}% {r['total_trades']:>7} "
              f"{r['avg_win_rate']:>6.1f}% {r['avg_drawdown']:>7.1f}% "
              f"{r['avg_score']:>7.1f} {p['ema_fast']}/{p['ema_slow']:<6} "
              f"{p['sl_pct']*100:>4.0f}% {tp_val:>4} {trail_val:>4} {p['rsi_overbought']:>5}")
    
    # Best params detail
    print(f"\n{'='*80}")
    print(f"  BEST PARAMETER SET")
    print(f"{'='*80}")
    
    p = best_params
    print(f"\n  EMA Fast:      {p['ema_fast']}")
    print(f"  EMA Slow:      {p['ema_slow']}")
    print(f"  RSI Period:    {p['rsi_period']}")
    print(f"  RSI Overbought: {p['rsi_overbought']}")
    print(f"  Stop Loss:     {p['sl_pct']*100:.0f}%")
    if p['tp_pct'] >= 100:
        tp_str = "No fixed TP (death cross exit only)"
    else:
        tp_str = f"{p['tp_pct']*100:.0f}%"
    print(f"  Take Profit:   {tp_str}")
    print(f"  Trailing Stop: {'Yes' if p.get('use_trailing') else 'No'}")
    if p.get("use_trailing"):
        print(f"  Trail Distance: {p.get('trailing_pct', 0)*100:.0f}%")
    print(f"  Position Size: {p['position_pct']*100:.0f}%")
    print(f"\n  Avg Return:    {best_results['avg_return']:+.1f}%")
    print(f"  Total Trades:  {best_results['total_trades']}")
    print(f"  Avg Win Rate:  {best_results['avg_win_rate']:.1f}%")
    print(f"  Avg Max DD:    {best_results['avg_drawdown']:.1f}%")
    print(f"  Score:         {best_results['avg_score']:.1f}")
    
    print(f"\n  Per-symbol breakdown:")
    for sr in best_results["symbol_results"]:
        print(f"    Return: {sr['total_return']:+.1f}% | Trades: {sr['total_trades']} | "
              f"WR: {sr['win_rate']:.1f}% | DD: {sr['max_drawdown']:.1f}% | PF: {sr['profit_factor']:.2f}")
    
    # Save best params
    best_output = {
        "best_params": best_params,
        "best_score": best_score,
        "best_results_summary": {
            "avg_return": best_results["avg_return"],
            "total_trades": best_results["total_trades"],
            "avg_win_rate": best_results["avg_win_rate"],
            "avg_drawdown": best_results["avg_drawdown"]
        },
        "top_10": [{
            "params": r["params"],
            "avg_return": r["avg_return"],
            "total_trades": r["total_trades"],
            "avg_score": r["avg_score"]
        } for r in all_results[:10]],
        "run_at": datetime.now(timezone.utc).isoformat()
    }
    
    with open("optimizer_results.json", "w") as f:
        json.dump(best_output, f, indent=2)
    
    print(f"\n  Results saved to: optimizer_results.json")
    print(f"{'='*80}\n")
    
    return best_params


if __name__ == "__main__":
    optimize()
