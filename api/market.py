"""
Vercel Serverless Function — fetches real market data server-side.
No CORS issues because it runs on Vercel's backend.
Endpoint: /api/market
"""

from http.server import BaseHTTPRequestHandler
import json
import math
import urllib.request
import urllib.error
import urllib.parse
from datetime import datetime, timezone


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


def _dedupe_daily(timestamps, closes):
    """Yahoo v8 API sometimes appends an intraday data point that shares
    the same calendar date as the previous daily bar.  yfinance silently
    drops this duplicate; we do the same so % change matches Streamlit."""
    if len(timestamps) < 2 or len(closes) < 2:
        return closes

    last_date = datetime.fromtimestamp(timestamps[-1], tz=timezone.utc).date()
    prev_date = datetime.fromtimestamp(timestamps[-2], tz=timezone.utc).date()

    if last_date == prev_date:
        return closes[:-1]
    return closes


def _fetch_closes(symbol: str) -> list:
    """Fetch deduplicated close series for a symbol (for MOVE calc)."""
    url = (
        f"https://query1.finance.yahoo.com/v8/finance/chart/"
        f"{urllib.parse.quote(symbol, safe='')}?range=5d&interval=1d"
    )
    req = urllib.request.Request(url, headers={
        "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36"
    })
    try:
        with urllib.request.urlopen(req, timeout=10) as resp:
            data = json.loads(resp.read().decode())
        result = data.get("chart", {}).get("result", [None])[0]
        if not result:
            return []
        raw_closes = result.get("indicators", {}).get("quote", [{}])[0].get("close", [])
        timestamps = result.get("timestamp", [])
        pairs = [(ts, c) for ts, c in zip(timestamps, raw_closes) if c is not None]
        if not pairs:
            return []
        ts_clean, closes = zip(*pairs)
        return list(_dedupe_daily(list(ts_clean), list(closes)))
    except Exception:
        return []


def _compute_move_proxy(tlt_closes: list) -> float | None:
    """Derive MOVE Index proxy from TLT historical vol (same as Streamlit)."""
    if len(tlt_closes) < 3:
        return None
    returns = [(tlt_closes[i] - tlt_closes[i - 1]) / tlt_closes[i - 1]
               for i in range(1, len(tlt_closes))]
    mean_r = sum(returns) / len(returns)
    variance = sum((r - mean_r) ** 2 for r in returns) / (len(returns) - 1)
    std_r = math.sqrt(variance)
    return round(std_r * math.sqrt(252) * 100 * 10, 1)


def fetch_quote(symbol: str) -> dict | None:
    """Fetch a single quote from Yahoo Finance v8 chart API.
    Uses OHLCV close prices (same method as Streamlit/yfinance)
    so that % change is consistent across both platforms.
    """
    url = (
        f"https://query1.finance.yahoo.com/v8/finance/chart/"
        f"{urllib.parse.quote(symbol, safe='')}?range=5d&interval=1d"
    )
    req = urllib.request.Request(url, headers={
        "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36"
    })
    try:
        with urllib.request.urlopen(req, timeout=10) as resp:
            data = json.loads(resp.read().decode())
        result = data.get("chart", {}).get("result", [None])[0]
        if not result:
            return None

        # --- Use OHLCV close series (matches yfinance behaviour) ---
        raw_closes = result.get("indicators", {}).get("quote", [{}])[0].get("close", [])
        timestamps = result.get("timestamp", [])

        # Filter out None values (holidays / missing days)
        # Keep parallel lists so timestamp index stays aligned
        pairs = [(ts, c) for ts, c in zip(timestamps, raw_closes) if c is not None]
        if not pairs:
            # No OHLCV data — fall back to meta
            meta = result.get("meta", {})
            price = meta.get("regularMarketPrice")
            return {"price": round(price, 4), "change": 0.0} if price else None

        ts_clean, closes = zip(*pairs)

        # Drop intraday duplicate (same-date extra bar)
        closes = list(_dedupe_daily(list(ts_clean), list(closes)))

        if len(closes) >= 2:
            price = closes[-1]
            prev = closes[-2]
            change = ((price - prev) / prev) * 100
            return {"price": round(price, 4), "change": round(change, 4)}

        return {"price": round(closes[0], 4), "change": 0.0}

    except Exception:
        return None


class handler(BaseHTTPRequestHandler):
    def do_GET(self):
        results = {}
        errors = []
        for display, yahoo in TICKERS.items():
            quote = fetch_quote(yahoo)
            if quote:
                results[display] = quote
            else:
                errors.append(display)

        # Derive MOVE proxy from TLT vol (same method as Streamlit)
        if "TLT" in results:
            tlt_closes = _fetch_closes("TLT")
            move = _compute_move_proxy(tlt_closes)
            if move is not None:
                results["MOVE"] = {"price": move, "change": 0.0}

        self.send_response(200)
        self.send_header("Content-Type", "application/json")
        self.send_header("Access-Control-Allow-Origin", "*")
        self.send_header("Cache-Control", "s-maxage=900, stale-while-revalidate=1800")
        self.end_headers()
        payload = {
            "data": results,
            "live": len(results) > 0,
            "fetched": len(results),
            "failed": errors,
        }
        self.wfile.write(json.dumps(payload).encode())

    def do_OPTIONS(self):
        self.send_response(200)
        self.send_header("Access-Control-Allow-Origin", "*")
        self.send_header("Access-Control-Allow-Methods", "GET, OPTIONS")
        self.end_headers()
