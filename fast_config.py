"""
Fast EMA Crossover Bot Configuration
Strategy: EMA 9/21 Crossover + RSI 14 Filter on 1H Timeframe
Much faster signals than EMA 50/200 - generates 50-100+ trades/year
"""

# Alpaca Paper Trading API Keys
ALPACA_API_KEY = "PKSUNH4CMOBS5B6AFX5AHDJE5Z"
ALPACA_API_SECRET = "4HkMRdxELD93nEm5LYuhJSdKDkqzSiBXfWdT84wPQznA"
ALPACA_BASE_URL = "https://paper-api.alpaca.markets"

# Strategy Parameters - FAST
TIMEFRAME = "1H"
EMA_FAST = 9
EMA_SLOW = 21
RSI_PERIOD = 14
RSI_OVERBOUGHT = 80

# Trade Management
SYMBOLS = ["AAPL", "MSFT", "GOOGL", "AMZN", "TSLA", "SPY", "QQQ", "NVDA"]
MAX_POSITIONS = 5  # More positions allowed for fast strategy
POSITION_SIZE_PCT = 0.15  # 15% per trade (smaller since more trades)

# Risk Management (optimized for 9/21 EMA)
STOP_LOSS_PCT = 0.05   # 5% stop loss
TAKE_PROFIT_PCT = None  # No fixed TP - let winners run, exit on crossover back

# Polling
CHECK_INTERVAL_MINUTES = 60  # 1 hour (matches timeframe)
