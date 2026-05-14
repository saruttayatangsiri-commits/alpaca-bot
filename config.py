"""
Trading Bot Configuration
Strategy: EMA 50/200 Crossover + RSI 14 Filter on 4H Timeframe
"""

# Alpaca Paper Trading API Keys
# Get from: https://app.alpaca.markets/paper/dashboard/overview
ALPACA_API_KEY = "PKSUNH4CMOBS5B6AFX5AHDJE5Z"
ALPACA_API_SECRET = "4HkMRdxELD93nEm5LYuhJSdKDkqzSiBXfWdT84wPQznA"
ALPACA_BASE_URL = "https://paper-api.alpaca.markets"  # Paper trading URL

# Strategy Parameters
TIMEFRAME = "4H"
EMA_FAST = 50
EMA_SLOW = 200
RSI_PERIOD = 14
RSI_OVERBOUGHT = 80   # Don't buy if RSI >= this (optimized from 70)

# Trade Management
SYMBOLS = ["AAPL", "MSFT", "GOOGL", "AMZN", "TSLA", "SPY", "QQQ", "NVDA"]  # Add your symbols
MAX_POSITIONS = 3  # Max concurrent positions
POSITION_SIZE_PCT = 0.25  # 25% of buying power per trade

# Risk Management
STOP_LOSS_PCT = 0.10   # 10% stop loss from entry price (optimized)
TAKE_PROFIT_PCT = None  # No fixed TP - let winners run, exit on Death Cross

# Polling
CHECK_INTERVAL_MINUTES = 240  # 4 hours (match timeframe)
# For testing, you can set this to 1 or 5 minutes
