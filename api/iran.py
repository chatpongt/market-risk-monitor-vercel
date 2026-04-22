"""
Vercel Serverless Function — weekly historical market data for the
Iran Conflict Dashboard.  Endpoint: /api/iran
"""

from http.server import BaseHTTPRequestHandler
import json
import urllib.request
import urllib.parse
from datetime import datetime, timezone

TICKERS = {
    "BRENT":  "BZ=F",
    "WTI":    "CL=F",
    "GOLD":   "GC=F",
    "NATGAS": "NG=F",
    "COPPER": "HG=F",
    "ALU":    "ALI=F",
    "VIX":    "^VIX",
    "US10Y":  "^TNX",
    "DXY":    "DX-Y.NYB",
    "USDTHB": "USDTHB=X",
    "SPX":    "^GSPC",
}

HEADERS = {"User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36"}
N_POINTS = 6


def fetch_history(symbol: str) -> dict:
    url = (
        f"https://query1.finance.yahoo.com/v8/finance/chart/"
        f"{urllib.parse.quote(symbol, safe='')}?range=2mo&interval=1wk"
    )
    req = urllib.request.Request(url, headers=HEADERS)
    try:
        with urllib.request.urlopen(req, timeout=10) as resp:
            data = json.loads(resp.read().decode())
        result = data.get("chart", {}).get("result", [None])[0]
        if not result:
            return {}
        timestamps = result.get("timestamp", [])
        closes = result.get("indicators", {}).get("quote", [{}])[0].get("close", [])
        pairs = [
            (datetime.fromtimestamp(ts, tz=timezone.utc).strftime("%-d %b"), round(c, 4))
            for ts, c in zip(timestamps, closes)
            if c is not None
        ]
        if not pairs:
            return {}
        pairs = pairs[-N_POINTS:]
        labels, values = zip(*pairs)
        return {"labels": list(labels), "values": list(values)}
    except Exception:
        return {}


class handler(BaseHTTPRequestHandler):
    def do_GET(self):
        results = {}
        for name, symbol in TICKERS.items():
            hist = fetch_history(symbol)
            if hist:
                results[name] = hist

        self.send_response(200)
        self.send_header("Content-Type", "application/json")
        self.send_header("Access-Control-Allow-Origin", "*")
        self.send_header("Cache-Control", "s-maxage=3600, stale-while-revalidate=7200")
        self.end_headers()
        self.wfile.write(json.dumps({"data": results}).encode())

    def do_OPTIONS(self):
        self.send_response(200)
        self.send_header("Access-Control-Allow-Origin", "*")
        self.send_header("Access-Control-Allow-Methods", "GET, OPTIONS")
        self.end_headers()
