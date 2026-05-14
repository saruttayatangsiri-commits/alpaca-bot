import requests
from config import ALPACA_API_KEY, ALPACA_API_SECRET

headers = {
    'APCA-API-KEY-ID': ALPACA_API_KEY,
    'APCA-API-SECRET-KEY': ALPACA_API_SECRET,
}

for tf in ['1Min', '5Min', '15Min', '1Hour', '1Day', '4Hour']:
    url = f'https://data.alpaca.markets/v2/stocks/AAPL/bars?timeframe={tf}&limit=3'
    r = requests.get(url, headers=headers, timeout=10)
    data = r.json()
    bars = data.get('bars')
    if bars:
        print(f'{tf}: OK - {len(bars)} bars, latest close: {bars[-1].get("c", "?")}')
    else:
        print(f'{tf}: bars=null (no data for this timeframe)')
