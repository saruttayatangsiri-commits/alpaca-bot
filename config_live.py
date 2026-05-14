"""
Trading Bot Configuration — LIVE MODE
Strategy: EMA 50/200 Crossover + RSI 14 Filter
"""

# Alpaca Paper Trading API Keys
ALPACA_API_KEY = "PKSUNH4CMOBS5B6AFX5AHDJE5Z"
ALPACA_API_SECRET = "4HkMRdxELD93nEm5LYuhJSdKDkqzSiBXfWdT84wPQznA"
ALPACA_BASE_URL = "https://paper-api.alpaca.markets"

# Telegram Alert
TELEGRAM_BOT_TOKEN = "8551276424:AAHbF3qZz0Lo"  # ต้อง confirm token ที่ถูกต้อง
TELEGRAM_CHAT_ID = "8685944200"

# Strategy Parameters
EMA_FAST = 50
EMA_SLOW = 200
RSI_PERIOD = 14
RSI_OVERBOUGHT = 80

# Trade Management
SYMBOLS = ["AAPL", "MSFT", "GOOGL", "AMZN", "TSLA", "SPY", "QQQ", "NVDA"]
MAX_POSITIONS = 3
POSITION_SIZE_PCT = 0.25

# Risk Management
STOP_LOSS_PCT = 0.10
TAKE_PROFIT_PCT = None

# Polling — every 4 hours (matching 4H timeframe)
CHECK_INTERVAL_MINUTES = 240
