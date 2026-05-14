"""
Fast Bot Backtest - EMA 9/21 on daily data
Tests the fast strategy parameters
"""

import sys, os
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

import yfinance as yf
from bot import calc_ema, calc_rsi

# Fast bot parameters
EMA_FAST = 9
EMA_SLOW = 21
RSI_PERIOD = 14
RSI_OVERBOUGHT = 80
STOP_LOSS_PCT = 0.05
TAKE_PROFIT_PCT = None
POSITION_SIZE_PCT = 0.15


def get_data(symbol, period="5y"):
    ticker = yf.Ticker(symbol)
    df = ticker.history(period=period)
    return df if not df.empty else None


def backtest(df, initial_capital=100000):
    if len(df) < EMA_SLOW + 20:
        return None
    
    closes = df["Close"].tolist()
    highs = df["High"].tolist()
    lows = df["Low"].tolist()
    dates = df.index.tolist()
    
    ema_f = calc_ema(closes, EMA_FAST)
    ema_s = calc_ema(closes, EMA_SLOW)
    rsi = calc_rsi(closes, RSI_PERIOD)
    
    fast_off = EMA_FAST - 1
    slow_off = EMA_SLOW - 1
    rsi_off = RSI_PERIOD
    
    cash = initial_capital
    position = None
    trades = []
    
    start_idx = max(fast_off, slow_off, rsi_off) + 1
    
    for i in range(start_idx, len(closes)):
        price = closes[i]
        high = highs[i]
        low = lows[i]
        
        ef = ema_f[i - fast_off] if (i - fast_off) < len(ema_f) else None
        es = ema_s[i - slow_off] if (i - slow_off) < len(ema_s) else None
        r = rsi[i - rsi_off] if (i - rsi_off) < len(rsi) else None
        
        if ef is None or es is None or r is None:
            continue
        
        prev_ef = ema_f[i - fast_off - 1] if (i - fast_off - 1) >= 0 else None
        prev_es = ema_s[i - slow_off - 1] if (i - slow_off - 1) >= 0 else None
        
        if prev_ef is None or prev_es is None:
            continue
        
        # Position management
        if position is not None:
            if low <= position["stop_loss"]:
                exit_price = position["stop_loss"]
                pnl_pct = (exit_price - position["entry_price"]) / position["entry_price"] * 100
                cash += exit_price * position["shares"]
                trades.append({"pnl_pct": pnl_pct, "type": "SL", "hold": (dates[i] - position["entry_date"]).days})
                position = None
            elif prev_ef >= prev_es and ef < es:
                pnl_pct = (price - position["entry_price"]) / position["entry_price"] * 100
                cash += price * position["shares"]
                trades.append({"pnl_pct": pnl_pct, "type": "DC", "hold": (dates[i] - position["entry_date"]).days})
                position = None
        
        # Buy signal
        if position is None:
            was_bearish = prev_ef <= prev_es
            is_bullish = ef > es
            golden_cross = was_bearish and is_bullish
            
            if golden_cross and r < RSI_OVERBOUGHT:
                shares = int((cash * POSITION_SIZE_PCT) / price)
                if shares > 0:
                    cash -= shares * price
                    position = {
                        "shares": shares,
                        "entry_price": price,
                        "entry_date": dates[i],
                        "stop_loss": price * (1 - STOP_LOSS_PCT)
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
    eq = 100000
    max_eq = 100000
    max_dd = 0
    for t in trades:
        eq *= (1 + t["pnl_pct"] / 100)
        if eq > max_eq:
            max_eq = eq
        dd = (max_eq - eq) / max_eq * 100
        if dd > max_dd:
            max_dd = dd
    
    gross_profit = sum(t["pnl_pct"] for t in wins)
    gross_loss = abs(sum(t["pnl_pct"] for t in losses))
    profit_factor = gross_profit / gross_loss if gross_loss > 0 else float('inf')
    
    hold_days = [t["hold"] for t in trades if t["hold"] > 0]
    avg_hold = sum(hold_days) / len(hold_days) if hold_days else 0
    
    return {
        "total_return": total_return,
        "total_trades": len(trades),
        "wins": len(wins),
        "losses": len(losses),
        "win_rate": win_rate,
        "max_drawdown": max_dd,
        "profit_factor": profit_factor,
        "avg_hold_days": avg_hold,
        "trades": trades
    }


def main():
    symbols = ["AAPL", "MSFT", "GOOGL", "AMZN", "TSLA", "SPY", "QQQ", "NVDA"]
    
    print(f"\n{'='*80}")
    print(f"  FAST BOT BACKTEST - EMA 9/21 + RSI 14 < 80")
    print(f"  SL: {STOP_LOSS_PCT*100:.0f}% | TP: None | Position Size: {POSITION_SIZE_PCT*100:.0f}%")
    print(f"  Timeframe: Daily")
    print(f"{'='*80}")
    
    results = []
    for symbol in symbols:
        print(f"\n  Backtesting {symbol}...", end=" ")
        df = get_data(symbol, period="5y")
        if df is None or len(df) < EMA_SLOW + 20:
            print("SKIP (not enough data)")
            continue
        
        r = backtest(df)
        if r:
            results.append(r)
            print(f"Return: {r['total_return']:+.1f}% | Trades: {r['total_trades']} | "
                  f"Win Rate: {r['win_rate']:.1f}% | Max DD: {r['max_drawdown']:.1f}% | "
                  f"Avg Hold: {r['avg_hold_days']:.0f}d")
    
    if not results:
        print("\n  No results!")
        return
    
    avg_ret = sum(r["total_return"] for r in results) / len(results)
    avg_trades = sum(r["total_trades"] for r in results) / len(results)
    avg_wr = sum(r["win_rate"] for r in results) / len(results)
    avg_dd = sum(r["max_drawdown"] for r in results) / len(results)
    avg_pf = sum(r["profit_factor"] for r in results) / len(results)
    avg_hold = sum(r["avg_hold_days"] for r in results) / len(results)
    
    total_trades = sum(r["total_trades"] for r in results)
    
    print(f"\n{'='*80}")
    print(f"  SUMMARY")
    print(f"{'='*80}")
    print(f"\n  Avg Return:    {avg_ret:+.1f}%")
    print(f"  Total Trades:  {total_trades} ({avg_trades:.0f} per symbol)")
    print(f"  Avg Win Rate:  {avg_wr:.1f}%")
    print(f"  Avg Max DD:    {avg_dd:.1f}%")
    print(f"  Avg Hold:      {avg_hold:.0f} days")
    print(f"  Avg Profit Factor: {avg_pf:.2f}")
    
    print(f"\n  vs EMA 50/200:")
    print(f"    EMA 9/21:  {total_trades} trades, {avg_ret:+.1f}% return, {avg_wr:.1f}% WR, {avg_dd:.1f}% DD")
    print(f"    EMA 50/200: 20 trades, +22.5% return, 65.0% WR, 25.7% DD (5y backtest)")
    print(f"{'='*80}\n")


if __name__ == "__main__":
    main()
