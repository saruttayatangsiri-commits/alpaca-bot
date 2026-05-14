"""
Quick test script - verifies API connection and shows account info.
Run this FIRST before running the bot.
"""

import sys, os
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

from config import ALPACA_API_KEY, ALPACA_API_SECRET, ALPACA_BASE_URL

if ALPACA_API_KEY == "YOUR_API_KEY_HERE":
    print("\nERROR: Please set your API keys in config.py first!")
    print("Get them from: https://app.alpaca.markets/paper/dashboard/overview\n")
    sys.exit(1)

import requests

headers = {
    "APCA-API-KEY-ID": ALPACA_API_KEY,
    "APCA-API-SECRET-KEY": ALPACA_API_SECRET,
}

print("\n" + "="*50)
print("  TESTING ALPACA CONNECTION")
print("="*50)

# Test account
try:
    resp = requests.get(f"{ALPACA_BASE_URL}/v2/account", headers=headers)
    resp.raise_for_status()
    account = resp.json()
    print(f"\n  Connected! Paper account confirmed.")
    print(f"  Status: {account['status']}")
    print(f"  Equity: ${float(account['equity']):,.2f}")
    print(f"  Cash: ${float(account['cash']):,.2f}")
    print(f"  Buying Power: ${float(account['buying_power']):,.2f}")
    print(f"  Trading: {account['trading_blocked']}")
except Exception as e:
    print(f"\n  FAILED: {e}")
    print("  Check your API keys in config.py\n")
    sys.exit(1)

# Test market data (no auth needed for some endpoints)
try:
    resp = requests.get(f"{ALPACA_BASE_URL}/v2/stocks/AAPL/quotes/latest", headers=headers)
    resp.raise_for_status()
    quote = resp.json()
    print(f"\n  Market data OK")
    print(f"  AAPL latest quote: ${float(quote['ask_price']):.2f}")
except Exception as e:
    print(f"\n  Market data error: {e}")

print("\n" + "="*50)
print("  ALL GOOD! Ready to run the bot.")
print("  Run: python3 bot.py")
print("="*50 + "\n")
