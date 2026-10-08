"""Scanner B: Trend-join Long, evaluated directly from Yahoo data (same rules as tradingview/trend_join_long.pine).

Valid entry, only after 10:00 AM New York time, when the latest price is
  1. above yesterday's daily high,
  2. with yesterday's close above the 200-day SMA (as of yesterday), and
  3. above today's pre-market high and the high of day set before the latest 1-minute bar.
"""
import sys
from datetime import time as dtime

import requests

from scanner import NY, Yahoo

EARLIEST = dtime(10, 0)
OPEN = dtime(9, 30)
SMA_LEN = 200


def evaluate(daily, intraday, day, now):
    """daily: [(datetime, high, close)] daily bars; intraday: [(datetime, high, close)] 1m bars incl. pre-market.
    Returns the setup dict if all criteria pass, else None."""
    if now.time() < EARLIEST:
        return None
    prior = sorted((d for d in daily if d[0].date() < day), key=lambda d: d[0])
    if len(prior) < SMA_LEN:
        return None
    prev_high, prev_close = prior[-1][1], prior[-1][2]
    sma = sum(d[2] for d in prior[-SMA_LEN:]) / SMA_LEN
    today = [b for b in intraday if b[0].date() == day]
    pre = [b for b in today if b[0].time() < OPEN]
    reg = [b for b in today if b[0].time() >= OPEN]
    if not pre or not reg or len(today) < 2:
        return None
    pre_high = max(b[1] for b in pre)
    price = reg[-1][2]
    prior_hod = max(b[1] for b in today[:-1])
    if not (price > prev_high and prev_close > sma and price > pre_high and price > prior_hod):
        return None
    return {"entry": round(price, 2), "prev_day_high": round(prev_high, 2), "premarket_high": round(pre_high, 2),
            "hod": round(prior_hod, 2), "sma200": round(sma, 2)}


def run(universe, day, now, yahoo=None):
    """universe: {ticker: pre-market row}. Returns list of hits with gap/catalyst attached."""
    y = yahoo or Yahoo()
    hits = []
    for sym, row in universe.items():
        try:
            setup = evaluate(y.bars(sym, "1d", "2y"), y.bars(sym, "1m", "1d", prepost=True), day, now)
        except (requests.RequestException, KeyError, IndexError, ValueError) as e:
            print(f"warn: strategy check failed for {sym}: {e}", file=sys.stderr)
            continue
        if setup:
            hits.append({"ticker": sym, "gap_pct": row.get("gap_pct"), "catalyst": row.get("catalyst", ""), **setup})
    return hits
