"""
EMA Crossover + RSI Filter Trading Bot
Strategy: Trend Following with EMA 50/200 crossover + RSI 14 filter
Timeframe: 4H
Buy: EMA50 crosses above EMA200 AND RSI < 70
Sell: EMA50 crosses below EMA200

Market Data: Yahoo Finance (free, no subscription needed)
Trade Execution: Alpaca Paper Trading API
"""

import requests
import json
import time
import yfinance as yf
from datetime import datetime, timezone, timedelta


def calc_ema(closes, period):
    """Calculate EMA for a list of closing prices."""
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
    """Calculate RSI for a list of closing prices."""
    if len(closes) < period + 1:
        return []
    
    gains = []
    losses = []
    
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


def get_4h_bars_yahoo(symbol, period="6mo"):
    """
    Get 4-hour bars from Yahoo Finance.
    Yahoo provides '1h' interval, so we need to resample to 4h.
    """
    ticker = yf.Ticker(symbol)
    
    # Get 1-hour bars
    df = ticker.history(period=period, interval="1h")
    
    if df.empty or len(df) < 200:
        print(f"  Not enough 1h bars ({len(df)}), trying daily...")
        df = ticker.history(period="1y", interval="1d")
        if df.empty or len(df) < 200:
            return None
        # For daily, use 50/200 day EMA instead
        return _resample_daily(df, period="1y")
    
    # Resample 1h -> 4h
    df_4h = df.resample("4h").agg({
        "Open": "first",
        "High": "max",
        "Low": "min",
        "Close": "last",
        "Volume": "sum"
    }).dropna()
    
    bars = []
    for _, row in df_4h.iterrows():
        bars.append({
            "timestamp": row.name,
            "o": float(row["Open"]),
            "h": float(row["High"]),
            "l": float(row["Low"]),
            "c": float(row["Close"]),
            "v": float(row["Volume"])
        })
    
    return bars


def _resample_daily(df, period="1y"):
    """Fallback: use daily bars when 4h data unavailable."""
    bars = []
    for _, row in df.iterrows():
        bars.append({
            "timestamp": row.name,
            "o": float(row["Open"]),
            "h": float(row["High"]),
            "l": float(row["Low"]),
            "c": float(row["Close"]),
            "v": float(row["Volume"])
        })
    return bars


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
        resp = requests.get(f"{self.base_url}{endpoint}", headers=self.headers, params=params)
        resp.raise_for_status()
        return resp.json()
    
    def _post(self, endpoint, data=None):
        resp = requests.post(f"{self.base_url}{endpoint}", headers=self.headers, json=data)
        resp.raise_for_status()
        return resp.json()
    
    def _delete(self, endpoint):
        resp = requests.delete(f"{self.base_url}{endpoint}", headers=self.headers)
        resp.raise_for_status()
        return resp.json() if resp.content else {}
    
    def get_account(self):
        return self._get("/v2/account")
    
    def get_positions(self):
        return self._get("/v2/positions")
    
    def market_buy(self, symbol, qty):
        data = {
            "symbol": symbol,
            "qty": str(qty),
            "side": "buy",
            "type": "market",
            "time_in_force": "gtc"
        }
        return self._post("/v2/orders", data)
    
    def market_sell(self, symbol, qty):
        data = {
            "symbol": symbol,
            "qty": str(qty),
            "side": "sell",
            "type": "market",
            "time_in_force": "gtc"
        }
        return self._post("/v2/orders", data)
    
    def close_position(self, symbol):
        return self._delete(f"/v2/positions/{symbol}")


class Strategy:
    def __init__(self, client, ema_fast, ema_slow, rsi_period, rsi_overbought):
        self.client = client
        self.ema_fast = ema_fast
        self.ema_slow = ema_slow
        self.rsi_period = rsi_period
        self.rsi_overbought = rsi_overbought
    
    def analyze_symbol(self, symbol):
        print(f"  Analyzing {symbol}...", end=" ")
        
        bars = get_4h_bars_yahoo(symbol, period="6mo")
        if bars is None or len(bars) < 220:
            print(f"Not enough data ({len(bars) if bars else 0} bars)")
            return None
        
        closes = [b["c"] for b in bars]
        
        ema_fast_vals = calc_ema(closes, self.ema_fast)
        ema_slow_vals = calc_ema(closes, self.ema_slow)
        rsi_vals = calc_rsi(closes, self.rsi_period)
        
        latest_close = closes[-1]
        latest_ema_fast = ema_fast_vals[-1]
        latest_ema_slow = ema_slow_vals[-1]
        prev_ema_fast = ema_fast_vals[-2]
        prev_ema_slow = ema_slow_vals[-2]
        latest_rsi = rsi_vals[-1]
        
        # Detect crossovers
        was_bearish = prev_ema_fast <= prev_ema_slow
        is_bullish = latest_ema_fast > latest_ema_slow
        golden_cross = was_bearish and is_bullish
        
        was_bullish = prev_ema_fast >= prev_ema_slow
        is_bearish = latest_ema_fast < latest_ema_slow
        death_cross = was_bullish and is_bearish
        
        signal = "HOLD"
        reason = ""
        
        if golden_cross:
            if latest_rsi < self.rsi_overbought:
                signal = "BUY"
                reason = f"Golden Cross + RSI({latest_rsi:.1f}) < {self.rsi_overbought}"
            else:
                signal = "HOLD"
                reason = f"Golden Cross but RSI({latest_rsi:.1f}) >= {self.rsi_overbought} (overbought)"
        elif death_cross:
            signal = "SELL"
            reason = "Death Cross"
        elif is_bullish:
            signal = "HOLD"
            reason = "Bullish trend (no new cross)"
        else:
            signal = "HOLD"
            reason = "Bearish trend (no new cross)"
        
        print(f"{signal}")
        
        return {
            "symbol": symbol,
            "close": latest_close,
            "ema_fast": latest_ema_fast,
            "ema_slow": latest_ema_slow,
            "rsi": latest_rsi,
            "signal": signal,
            "reason": reason
        }


class TradingBot:
    def __init__(self, config):
        self.client = AlpacaClient(
            config["api_key"],
            config["api_secret"],
            config["base_url"]
        )
        self.strategy = Strategy(
            self.client,
            config["ema_fast"],
            config["ema_slow"],
            config["rsi_period"],
            config["rsi_overbought"]
        )
        self.symbols = config["symbols"]
        self.max_positions = config["max_positions"]
        self.position_size_pct = config["position_size_pct"]
        self.log_file = "trade_log.json"
    
    def log_trade(self, event):
        event["timestamp"] = datetime.now(timezone.utc).isoformat()
        logs = []
        try:
            with open(self.log_file, "r") as f:
                logs = json.load(f)
        except (FileNotFoundError, json.JSONDecodeError):
            pass
        logs.append(event)
        with open(self.log_file, "w") as f:
            json.dump(logs, f, indent=2)
    
    def get_open_positions(self):
        try:
            positions = self.client.get_positions()
            return {p["symbol"]: p for p in positions}
        except Exception as e:
            print(f"  Error fetching positions: {e}")
            return {}
    
    def execute_buy(self, symbol, price):
        account = self.client.get_account()
        buying_power = float(account["buying_power"])
        position_value = buying_power * self.position_size_pct
        qty = max(1, int(position_value / price))
        
        if qty == 0:
            print(f"  [SKIP] Not enough buying power for {symbol}")
            return None
        
        print(f"  [BUY] {symbol}: {qty} shares @ ~${price:.2f} (${position_value:.2f})")
        
        try:
            order = self.client.market_buy(symbol, qty)
            self.log_trade({
                "type": "BUY", "symbol": symbol, "qty": qty,
                "price": price, "reason": "Strategy signal"
            })
            return order
        except Exception as e:
            print(f"  [ERROR] Buy failed: {e}")
            return None
    
    def execute_sell(self, symbol):
        print(f"  [SELL] {symbol}: Closing position")
        try:
            result = self.client.close_position(symbol)
            self.log_trade({
                "type": "SELL", "symbol": symbol,
                "reason": "Death Cross"
            })
            return result
        except Exception as e:
            print(f"  [ERROR] Sell failed: {e}")
            return None
    
    def run_scan(self):
        print(f"\n{'='*80}")
        print(f"  STRATEGY SCAN - {datetime.now(timezone.utc).strftime('%Y-%m-%d %H:%M UTC')}")
        print(f"  Strategy: EMA {config['ema_fast']}/{config['ema_slow']} Cross + RSI {config['rsi_period']} Filter")
        print(f"  Timeframe: 4H | RSI Overbought: {config['rsi_overbought']}")
        print(f"  Data Source: Yahoo Finance | Execution: Alpaca Paper")
        print(f"{'='*80}")
        
        positions = self.get_open_positions()
        print(f"\n  Open Positions: {len(positions)}")
        for sym, pos in positions.items():
            pnl = float(pos.get("unrealized_pl", 0))
            print(f"    {sym}: {pos['qty']} shares | P&L: ${pnl:+.2f}")
        
        results = []
        for symbol in self.symbols:
            result = self.strategy.analyze_symbol(symbol)
            if result:
                results.append(result)
        
        print(f"\n  {'Symbol':<8} {'Price':>10} {'EMA50':>10} {'EMA200':>10} {'RSI':>8} {'Signal':>8}")
        print(f"  {'-'*8} {'-'*10} {'-'*10} {'-'*10} {'-'*8} {'-'*8}")
        for r in results:
            print(f"  {r['symbol']:<8} ${r['close']:>9.2f} {r['ema_fast']:>10.2f} "
                  f"{r['ema_slow']:>10.2f} {r['rsi']:>7.1f} {r['signal']:>8}")
        
        print(f"\n  --- EXECUTING TRADES ---")
        
        for result in results:
            symbol = result["symbol"]
            
            if result["signal"] == "BUY":
                if symbol in positions:
                    print(f"  [SKIP] Already holding {symbol}")
                    continue
                if len(positions) >= self.max_positions:
                    print(f"  [SKIP] Max positions ({self.max_positions}) reached")
                    continue
                self.execute_buy(symbol, result["close"])
                positions[symbol] = True
            elif result["signal"] == "SELL":
                if symbol not in positions:
                    print(f"  [SKIP] Not holding {symbol}, ignoring sell")
                    continue
                self.execute_sell(symbol)
                del positions[symbol]
            else:
                print(f"  [NO ACTION] {symbol}: {result['reason']}")
        
        account = self.client.get_account()
        print(f"\n{'='*80}")
        print(f"  ACCOUNT: Equity ${float(account['equity']):,.2f} | "
              f"Cash ${float(account['cash']):,.2f} | "
              f"Buying Power ${float(account['buying_power']):,.2f}")
        print(f"{'='*80}")
        
        return results
    
    def run_loop(self):
        print(f"\n  Starting EMA Crossover Bot...")
        print(f"  Checking every {config['check_interval']} minutes")
        print(f"  Press Ctrl+C to stop\n")
        
        while True:
            try:
                self.run_scan()
                print(f"\n  Next scan in {config['check_interval']} minutes...")
                time.sleep(config["check_interval"] * 60)
            except KeyboardInterrupt:
                print("\n  Bot stopped.")
                break
            except Exception as e:
                print(f"\n  ERROR: {e}")
                import traceback
                traceback.print_exc()
                print(f"  Retrying in 5 minutes...")
                time.sleep(300)


if __name__ == "__main__":
    import sys
    sys.path.insert(0, "..")
    from config import (
        ALPACA_API_KEY, ALPACA_API_SECRET, ALPACA_BASE_URL,
        TIMEFRAME, EMA_FAST, EMA_SLOW, RSI_PERIOD, RSI_OVERBOUGHT,
        SYMBOLS, MAX_POSITIONS, POSITION_SIZE_PCT, CHECK_INTERVAL_MINUTES
    )
    
    config = {
        "api_key": ALPACA_API_KEY,
        "api_secret": ALPACA_API_SECRET,
        "base_url": ALPACA_BASE_URL,
        "ema_fast": EMA_FAST,
        "ema_slow": EMA_SLOW,
        "rsi_period": RSI_PERIOD,
        "rsi_overbought": RSI_OVERBOUGHT,
        "symbols": SYMBOLS,
        "max_positions": MAX_POSITIONS,
        "position_size_pct": POSITION_SIZE_PCT,
        "check_interval": CHECK_INTERVAL_MINUTES,
    }
    
    if ALPACA_API_KEY == "YOUR_API_KEY_HERE" or ALPACA_API_KEY == "":
        print("ERROR: Set API keys in config.py first")
        sys.exit(1)
    
    bot = TradingBot(config)
    bot.run_loop()
