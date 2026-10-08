#!/usr/bin/env python3
"""Runs both scanners on a New York-time schedule (weekdays) and sends results to Telegram.

  Scanner A: 08:30, 09:00, ... 14:00  (every 30 min)
  Scanner B: 5 min after each A run (08:35 ... 14:35, last run before 15:00), on the day's A tickers

  python run_schedule.py            # long-running scheduler
  python run_schedule.py --once a   # single run (for cron / testing); also: --once b
  add --dry-run to print instead of sending to Telegram
"""
import argparse
import json
import sys
import time
import traceback
from datetime import datetime, timedelta
from pathlib import Path

import scanner
import strategy_scan
import telegram_notify as tg

RESULTS = Path(__file__).parent / "results"
A_START, A_END, STEP, B_OFFSET, B_END = (8, 30), (14, 0), 30, 5, (15, 0)
GRACE = timedelta(minutes=10)  # run a missed slot if started this late, otherwise skip it


def slots(day):
    """[(kind, datetime)] for a New York calendar date; empty on weekends."""
    if day.weekday() >= 5:
        return []
    out, t = [], datetime(day.year, day.month, day.day, *A_START, tzinfo=scanner.NY)
    end_a = t.replace(hour=A_END[0], minute=A_END[1])
    end_b = t.replace(hour=B_END[0], minute=B_END[1])
    while t <= end_a:
        out.append(("a", t))
        t += timedelta(minutes=STEP)
    t = datetime(day.year, day.month, day.day, *A_START, tzinfo=scanner.NY) + timedelta(minutes=B_OFFSET)
    while t < end_b:  # B keeps running on the latest A tickers until 15:00
        out.append(("b", t))
        t += timedelta(minutes=STEP)
    return sorted(out, key=lambda s: s[1])


def universe_path(day, results=RESULTS):
    return Path(results) / f"universe_{day.isoformat()}.json"


def load_universe(day, results=RESULTS):
    p = universe_path(day, results)
    return json.loads(p.read_text()) if p.exists() else {}


def merge_universe(day, rows, results=RESULTS):
    """Tickers seen in ANY of today's A runs (a gapper can drop out of A later but stays tradeable for B)."""
    uni = load_universe(day, results)
    for r in rows:
        uni[r["ticker"]] = r
    universe_path(day, results).write_text(json.dumps(uni, indent=2) + "\n")
    return uni


def run_a(day, out_dir=RESULTS):
    rows = scanner.run(day, out_dir, 100)
    scanner.save(rows, day, out_dir)
    merge_universe(day, rows, out_dir)
    return tg.format_a(rows)


def run_b(day, now, out_dir=RESULTS):
    uni = load_universe(day, out_dir)
    hits = strategy_scan.run(uni, day, now)
    p = Path(out_dir) / f"strategy_{day.isoformat()}.json"
    log = json.loads(p.read_text()) if p.exists() else []
    log.append({"time": now.isoformat(timespec="seconds"), "hits": hits})
    p.write_text(json.dumps(log, indent=2) + "\n")
    return tg.format_b(hits)


def execute(kind, send):
    now = datetime.now(scanner.NY)
    name = "Scanner A" if kind == "a" else "Scanner B"
    try:
        text = run_a(now.date()) if kind == "a" else run_b(now.date(), now)
    except Exception as e:  # report failures instead of silently missing a run
        traceback.print_exc()
        text = f"[{name}] run failed at {now:%H:%M} ET: {e}"
    send(text)


def main():
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--once", choices=["a", "b"])
    ap.add_argument("--dry-run", action="store_true")
    a = ap.parse_args()
    send = (lambda t: print(t + "\n")) if a.dry_run else tg.send
    if a.once:
        return execute(a.once, send)
    done, current = set(), None
    print("Scheduler started (New York time).", flush=True)
    while True:
        now = datetime.now(scanner.NY)
        if current != now.date():
            current, done = now.date(), set()
        for kind, t in slots(now.date()):
            if (kind, t) not in done and t <= now < t + GRACE:
                done.add((kind, t))
                try:
                    execute(kind, send)
                except Exception:  # e.g. Telegram down: log and keep the scheduler alive
                    traceback.print_exc()
        time.sleep(15)


if __name__ == "__main__":
    sys.exit(main())
