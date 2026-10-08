#!/usr/bin/env python3
"""Pre-market gap scanner.

Finds stocks gapping up > 5% vs. the previous close, priced above $3, with
pre-market volume above 50,000 shares. Candidates and pre-market quotes come
from Yahoo Finance; one-sentence news catalysts come from Benzinga.
Each run is saved to results/premarket_YYYY-MM-DD.json.

Usage:
    python scanner.py [--date YYYY-MM-DD] [--out-dir results] [--max-candidates 100]

Optional env var BENZINGA_API_KEY enables the official Benzinga news API;
without it the public Benzinga RSS feed / ticker pages are used as a fallback.
"""
import argparse
import json
import os
import re
import sys
import xml.etree.ElementTree as ET
from datetime import datetime, time as dtime
from pathlib import Path
from zoneinfo import ZoneInfo

import requests

MIN_GAP_PCT = 5.0
MIN_PRICE = 3.0
MIN_PREMARKET_VOLUME = 50_000
NO_CATALYST = "No news catalyst found."

UA = {"User-Agent": "Mozilla/5.0 (X11; Linux x86_64) AppleWebKit/537.36 "
                    "(KHTML, like Gecko) Chrome/124.0 Safari/537.36"}
YF_QUERY = "https://query1.finance.yahoo.com"
NY = ZoneInfo("America/New_York")


# --------------------------------------------------------------------------
# Yahoo Finance
# --------------------------------------------------------------------------
class Yahoo:
    def __init__(self):
        self.s = requests.Session()
        self.s.headers.update(UA)
        self.crumb = None

    def _auth(self):
        """Yahoo's JSON endpoints need a session cookie + crumb."""
        if self.crumb:
            return
        self.s.get("https://fc.yahoo.com", timeout=15)  # sets cookie (404 is fine)
        r = self.s.get(f"{YF_QUERY}/v1/test/getcrumb", timeout=15)
        r.raise_for_status()
        self.crumb = r.text.strip()

    def _get(self, path, **params):
        self._auth()
        params["crumb"] = self.crumb
        r = self.s.get(f"{YF_QUERY}{path}", params=params, timeout=20)
        r.raise_for_status()
        return r.json()

    def candidates(self, max_candidates=100):
        """Tickers from Yahoo's gainers / most-active screeners (US equities)."""
        symbols = []
        for scr in ("day_gainers", "most_actives", "small_cap_gainers"):
            try:
                data = self._get("/v1/finance/screener/predefined/saved",
                                 scrIds=scr, count=max_candidates)
                quotes = data["finance"]["result"][0]["quotes"]
            except (requests.RequestException, KeyError, IndexError, ValueError) as e:
                print(f"warn: screener {scr} failed: {e}", file=sys.stderr)
                continue
            for q in quotes:
                sym = q.get("symbol")
                if sym and sym not in symbols:
                    symbols.append(sym)
        return symbols[:max_candidates * 3]

    def quotes(self, symbols):
        """Batch quote lookup -> {symbol: quote dict}."""
        out = {}
        for i in range(0, len(symbols), 50):
            chunk = symbols[i:i + 50]
            data = self._get("/v7/finance/quote", symbols=",".join(chunk))
            for q in data["quoteResponse"]["result"]:
                out[q["symbol"]] = q
        return out

    def bars(self, symbol, interval, rng, prepost=False):
        """[(datetime in New York time, high, close, volume)] for a chart request."""
        data = self._get(f"/v8/finance/chart/{symbol}", interval=interval,
                         range=rng, includePrePost=str(prepost).lower())
        res = data["chart"]["result"][0]
        q = res["indicators"]["quote"][0]
        out = []
        for ts, h, c, v in zip(res.get("timestamp") or [], q.get("high") or [],
                               q.get("close") or [], q.get("volume") or []):
            if h is not None and c is not None:
                out.append((datetime.fromtimestamp(ts, NY), h, c, v or 0))
        return out

    def premarket_volume(self, symbol, day):
        """Sum 1-minute volume between 04:00 and 09:30 ET on `day` (a date)."""
        data = self._get(f"/v8/finance/chart/{symbol}", interval="1m",
                         range="1d", includePrePost="true")
        res = data["chart"]["result"][0]
        stamps = res.get("timestamp") or []
        vols = res["indicators"]["quote"][0].get("volume") or []
        total = 0
        for ts, v in zip(stamps, vols):
            t = datetime.fromtimestamp(ts, NY)
            if t.date() == day and (4, 0) <= (t.hour, t.minute) < (9, 30):
                total += v or 0
        return total


# --------------------------------------------------------------------------
# Benzinga
# --------------------------------------------------------------------------
def _first_sentence(text, limit=220):
    text = re.sub(r"<[^>]+>", " ", text or "")
    text = re.sub(r"\s+", " ", text).strip()
    m = re.match(r"(.+?[.!?])(\s|$)", text)
    s = (m.group(1) if m else text).strip()
    if len(s) > limit:
        s = s[:limit - 1].rstrip() + "…"
    return s


def benzinga_catalysts(symbols):
    """Return {symbol: one-sentence catalyst} using Benzinga news."""
    out = {}
    key = os.environ.get("BENZINGA_API_KEY")
    for sym in symbols:
        try:
            if key:
                r = requests.get(
                    "https://api.benzinga.com/api/v2/news",
                    params={"token": key, "tickers": sym, "pageSize": 1,
                            "displayOutput": "abstract"},
                    headers={"Accept": "application/json", **UA}, timeout=20)
                r.raise_for_status()
                items = r.json()
                if items:
                    it = items[0]
                    out[sym] = _first_sentence(it.get("teaser") or it.get("body")
                                               or it.get("title"))
            else:
                r = requests.get(f"https://www.benzinga.com/stock-articles/{sym}/feed",
                                 headers=UA, timeout=20)
                r.raise_for_status()
                item = ET.fromstring(r.content).find("./channel/item")
                if item is not None:
                    desc = item.findtext("description") or ""
                    out[sym] = _first_sentence(desc) or _first_sentence(
                        item.findtext("title"))
        except (requests.RequestException, ET.ParseError, ValueError) as e:
            print(f"warn: Benzinga lookup failed for {sym}: {e}", file=sys.stderr)
    return out


# --------------------------------------------------------------------------
# Filtering / output
# --------------------------------------------------------------------------
def passes(price, gap_pct, volume):
    return (gap_pct is not None and price is not None and volume is not None
            and gap_pct > MIN_GAP_PCT and price > MIN_PRICE
            and volume > MIN_PREMARKET_VOLUME)


def build_results(quotes, volumes):
    rows = []
    for sym, q in quotes.items():
        price = q.get("preMarketPrice")
        prev = q.get("regularMarketPreviousClose")
        gap = q.get("preMarketChangePercent")
        if gap is None and price and prev:
            gap = (price - prev) / prev * 100
        if passes(price, gap, volumes.get(sym)):
            rows.append({"ticker": sym, "price": round(price, 2),
                         "gap_pct": round(gap, 2),
                         "premarket_volume": int(volumes[sym])})
    rows.sort(key=lambda r: r["gap_pct"], reverse=True)
    return rows


def format_table(rows):
    if not rows:
        return "No stocks matched the criteria."
    lines = [f"{'Ticker':<8}{'Price':>9}{'Gap %':>9}  Catalyst",
             "-" * 80]
    for r in rows:
        lines.append(f"{r['ticker']:<8}{'$' + format(r['price'], '.2f'):>9}"
                     f"{format(r['gap_pct'], '+.2f') + '%':>9}  {r['catalyst']}")
    return "\n".join(lines)


def save(rows, day, out_dir):
    out_dir = Path(out_dir)
    out_dir.mkdir(parents=True, exist_ok=True)
    path = out_dir / f"premarket_{day.isoformat()}.json"
    payload = {
        "date": day.isoformat(),
        "generated_at": datetime.now(NY).isoformat(timespec="seconds"),
        "criteria": {"min_gap_pct": MIN_GAP_PCT, "min_price": MIN_PRICE,
                     "min_premarket_volume": MIN_PREMARKET_VOLUME},
        "results": [{k: r[k] for k in ("ticker", "price", "gap_pct", "catalyst")}
                    | {"premarket_volume": r["premarket_volume"]} for r in rows],
    }
    path.write_text(json.dumps(payload, indent=2) + "\n")
    return path


def run(day, out_dir, max_candidates):
    y = Yahoo()
    symbols = y.candidates(max_candidates)
    if not symbols:
        sys.exit("error: no candidates returned from Yahoo Finance")
    quotes = y.quotes(symbols)
    if datetime.now(NY).time() >= dtime(9, 30):
        # Yahoo stops updating pre-market fields at the open: gap/price now come from the regular session.
        for q in quotes.values():
            q["preMarketPrice"] = q.get("regularMarketPrice")
            q["preMarketChangePercent"] = q.get("regularMarketChangePercent")
    # Cheap pre-filter on price/gap before fetching per-symbol volume.
    quotes = {s: q for s, q in quotes.items()
              if q.get("quoteType") == "EQUITY"
              and (q.get("preMarketChangePercent") or 0) > MIN_GAP_PCT
              and (q.get("preMarketPrice") or 0) > MIN_PRICE}
    volumes = {}
    for s in quotes:
        try:
            volumes[s] = y.premarket_volume(s, day)
        except (requests.RequestException, KeyError, IndexError, ValueError) as e:
            print(f"warn: volume lookup failed for {s}: {e}", file=sys.stderr)
    rows = build_results(quotes, volumes)
    news = benzinga_catalysts([r["ticker"] for r in rows])
    for r in rows:
        r["catalyst"] = news.get(r["ticker"], NO_CATALYST)
    return rows


def main():
    ap = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    ap.add_argument("--date", help="YYYY-MM-DD (default: today, New York time)")
    ap.add_argument("--out-dir", default=str(Path(__file__).parent / "results"))
    ap.add_argument("--max-candidates", type=int, default=100)
    a = ap.parse_args()
    day = (datetime.strptime(a.date, "%Y-%m-%d").date() if a.date
           else datetime.now(NY).date())
    rows = run(day, a.out_dir, a.max_candidates)
    print(f"Pre-market scan for {day}\n")
    print(format_table(rows))
    print(f"\nSaved to {save(rows, day, a.out_dir)}")


if __name__ == "__main__":
    main()
