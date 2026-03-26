"""
Vercel Serverless Function — fetches real market data server-side.
No CORS issues because it runs on Vercel's backend.
Endpoint: /api/market
"""

from http.server import BaseHTTPRequestHandler
import json
import urllib.request
import urllib.error


TICKERS = {
    "SPX":    "^GSPC",
    "NDX":    "^IXIC",
    "DJI":    "^DJI",
    "VIX":    "^VIX",
    "VVIX":   "^VVIX",
    "US10Y":  "^TNX",
    "US02Y":  "^IRX",
    "DXY":    "DX-Y.NYB",
    "GOLD":   "GC=F",
    "BTC":    "BTC-USD",
    "CRUDE":  "CL=F",
    "HYG":    "HYG",
    "LQD":    "LQD",
    "COPPER": "HG=F",
    "TLT":    "TLT",
}


def fetch_quote(symbol: str) -> dict | None:
    """Fetch a single quote from Yahoo Finance v8 chart API."""
    url = f"https://query1.finance.yahoo.com/v8/finance/chart/{urllib.parse.quote(symbol)}?range=5d&interval=1d"
    req = urllib.request.Request(url, headers={"User-Agent": "Mozilla/5.0"})
    try:
        with urllib.request.urlopen(req, timeout=8) as resp:
            data = json.loads(resp.read().decode())
        result = data.get("chart", {}).get("result", [None])[0]
        if not result:
            return None
        meta = result["meta"]
        price = meta.get("regularMarketPrice")
        prev = meta.get("chartPreviousClose") or meta.get("previousClose")
        if price is None or prev is None:
            return None
        change = ((price - prev) / prev) * 100
        return {"price": round(price, 4), "change": round(change, 4)}
    except Exception:
        return None


import urllib.parse


class handler(BaseHTTPRequestHandler):
    def do_GET(self):
        results = {}
        for display, yahoo in TICKERS.items():
            quote = fetch_quote(yahoo)
            if quote:
                results[display] = quote

        self.send_response(200)
        self.send_header("Content-Type", "application/json")
        self.send_header("Access-Control-Allow-Origin", "*")
        self.send_header("Cache-Control", "s-maxage=900, stale-while-revalidate=1800")
        self.end_headers()
        self.wfile.write(json.dumps({"data": results, "live": len(results) > 0}).encode())

    def do_OPTIONS(self):
        self.send_response(200)
        self.send_header("Access-Control-Allow-Origin", "*")
        self.send_header("Access-Control-Allow-Methods", "GET, OPTIONS")
        self.end_headers()
