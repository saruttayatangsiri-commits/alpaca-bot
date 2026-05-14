# EMA Crossover Paper Trading Bot

Strategy: EMA 50/200 Crossover + RSI 14 Filter on 4H Timeframe

## Rules
- BUY: EMA 50 crosses above EMA 200 (Golden Cross) AND RSI 14 < 70
- SELL: EMA 50 crosses below EMA 200 (Death Cross)
- Max 3 concurrent positions, 25% buying power per trade

## Setup

1. Sign up at https://app.alpaca.markets/signup (free)
2. Get your Paper Trading API keys from the dashboard
3. Edit config.py and paste your keys
4. pip install -r requirements.txt
5. python3 test_connection.py  (verify connection)
6. python3 bot.py  (start trading)

## Files
- config.py - API keys and strategy parameters
- bot.py - Main trading bot
- test_connection.py - API connection test
- trade_log.json - Auto-created trade history

## Strategy Parameters (editable in config.py)
- EMA_FAST = 50
- EMA_SLOW = 200  
- RSI_PERIOD = 14
- RSI_OVERBOUGHT = 70
- SYMBOLS = your watchlist
- MAX_POSITIONS = 3
- POSITION_SIZE_PCT = 0.25 (25% per trade)
- CHECK_INTERVAL_MINUTES = 240 (every 4 hours)
