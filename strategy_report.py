#!/usr/bin/env python3
"""Glue between the pre-market scanner and the TradingView 'Trend-join Long' indicator.

  python strategy_report.py watchlist [--date D]   write a TradingView-importable watchlist
                                                   of today's pre-market scan results
  python strategy_report.py serve [--port 8080]    webhook receiver for TradingView alerts;
                                                   keeps only tickers from the pre-market scan
                                                   and writes results/signals_YYYY-MM-DD.json
  python strategy_report.py report [--date D]      print the day's valid signals
"""
import argparse
import json
from datetime import datetime
from http.server import BaseHTTPRequestHandler, HTTPServer
from pathlib import Path

from scanner import NY

RESULTS = Path(__file__).parent / "results"
REQUIRED = ("signal", "ticker", "price")


def _today():
    return datetime.now(NY).date().isoformat()


def load_scan(day, results=RESULTS):
    p = Path(results) / f"premarket_{day}.json"
    return {r["ticker"]: r for r in json.loads(p.read_text())["results"]} if p.exists() else {}


def write_watchlist(day, results=RESULTS):
    scan = load_scan(day, results)
    path = Path(results) / f"watchlist_{day}.txt"
    path.write_text(",".join(scan) + "\n")  # TradingView: Watchlist > Import list
    return path, len(scan)


def record_signal(alert, day, results=RESULTS):
    """Validate a TradingView alert against the pre-market scan; append to the day's file.
    Returns the stored record or None if rejected."""
    if any(k not in alert for k in REQUIRED) or alert["signal"] != "trend_join_long":
        return None
    ticker = str(alert["ticker"]).split(":")[-1].upper()
    scan = load_scan(day, results)
    if ticker not in scan:
        return None
    # Re-verify the three criteria server-side from the numbers in the alert.
    try:
        p = float(alert["price"])
        ok = (p > float(alert["prev_day_high"]) and float(alert["prev_close"]) > float(alert["sma200"])
              and p > float(alert["premarket_high"]) and p > float(alert["prev_bar_hod"]))
    except (KeyError, TypeError, ValueError):
        return None
    if not ok:
        return None
    path = Path(results) / f"signals_{day}.json"
    data = json.loads(path.read_text()) if path.exists() else {"date": day, "signals": []}
    if any(s["ticker"] == ticker for s in data["signals"]):  # one entry per ticker per day
        return None
    rec = {**alert, "ticker": ticker, "gap_pct": scan[ticker]["gap_pct"],
           "catalyst": scan[ticker]["catalyst"],
           "received_at": datetime.now(NY).isoformat(timespec="seconds")}
    data["signals"].append(rec)
    path.write_text(json.dumps(data, indent=2) + "\n")
    return rec


def format_report(day, results=RESULTS):
    p = Path(results) / f"signals_{day}.json"
    sigs = json.loads(p.read_text())["signals"] if p.exists() else []
    if not sigs:
        return f"Trend-join Long {day}: no valid signals."
    lines = [f"Trend-join Long signals {day}", f"{'Ticker':<8}{'Entry':>9}{'Gap %':>9}  Catalyst", "-" * 70]
    lines += [f"{s['ticker']:<8}{'$' + format(float(s['price']), '.2f'):>9}"
              f"{format(s['gap_pct'], '+.2f') + '%':>9}  {s['catalyst']}" for s in sigs]
    return "\n".join(lines)


class Handler(BaseHTTPRequestHandler):
    def do_POST(self):
        try:
            alert = json.loads(self.rfile.read(int(self.headers.get("Content-Length", 0))))
        except ValueError:
            alert = {}
        rec = record_signal(alert, _today()) if isinstance(alert, dict) else None
        self.send_response(200 if rec else 202)
        self.end_headers()
        if rec:
            print(format_report(_today()), flush=True)


def main():
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("cmd", choices=["watchlist", "serve", "report"])
    ap.add_argument("--date", default=None)
    ap.add_argument("--port", type=int, default=8080)
    a = ap.parse_args()
    day = a.date or _today()
    if a.cmd == "watchlist":
        path, n = write_watchlist(day)
        print(f"{n} tickers -> {path}")
    elif a.cmd == "report":
        print(format_report(day))
    else:
        print(f"Listening for TradingView webhooks on :{a.port}")
        HTTPServer(("", a.port), Handler).serve_forever()


if __name__ == "__main__":
    main()
