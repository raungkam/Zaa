import sys
from datetime import date, datetime, timedelta
from pathlib import Path
sys.path.insert(0, str(Path(__file__).parent.parent))
import run_schedule as rs, strategy_scan as ss, telegram_notify as tg
from scanner import NY


def test_slots():
    s = rs.slots(date(2026, 10, 8))  # Thursday
    a = [t.strftime("%H:%M") for k, t in s if k == "a"]
    b = [t.strftime("%H:%M") for k, t in s if k == "b"]
    assert a[0] == "08:30" and a[-1] == "14:00" and len(a) == 12
    assert b[0] == "08:35" and b[-1] == "14:35" and len(b) == 12
    assert rs.slots(date(2026, 10, 10)) == []  # Saturday


def mk(day, hh, mm):
    return datetime(day.year, day.month, day.day, hh, mm, tzinfo=NY)


def data(day, last_close=10.5):
    daily = [(mk(date(2025, 1, 1), 9, 30) + timedelta(days=i), 9.0, 8.0) for i in range(250)]
    daily[-1] = (daily[-1][0], 10.0, 9.5)  # yesterday: high 10, close 9.5, SMA ~8
    daily[-1] = (mk(day - timedelta(days=1), 9, 30), 10.0, 9.5)
    daily = [d for d in daily if d[0].date() < day - timedelta(days=1)] + [daily[-1]]
    intra = [(mk(day, 4, 0), 10.3, 10.1), (mk(day, 9, 31), 10.4, 10.2), (mk(day, 10, 1), last_close, last_close)]
    return daily, intra


def test_evaluate():
    day, now = date(2026, 10, 8), mk(date(2026, 10, 8), 10, 5)
    d, i = data(day)
    r = ss.evaluate(d, i, day, now)
    assert r and r["entry"] == 10.5 and r["premarket_high"] == 10.3 and r["hod"] == 10.4
    assert ss.evaluate(d, i, day, mk(day, 9, 59)) is None          # before 10:00
    assert ss.evaluate(*data(day, 10.35), day, now) is None         # below prior HOD
    assert ss.evaluate(*data(day, 9.9), day, now) is None           # below prev-day high


def test_formats_and_chunks():
    assert tg.format_a([]).startswith("[Scanner A: Pre-market Gappers]\n")
    assert tg.format_b([]).startswith("[Scanner B: Trend-join Long Hits]\n")
    rows = [{"ticker": "AAA", "price": 10, "gap_pct": 11.1, "catalyst": "x" * 50}] * 200
    parts = tg.chunks(tg.format_a(rows))
    assert len(parts) > 1 and all(len(p) <= 4096 for p in parts)


def test_universe_union(tmp_path):
    day = date(2026, 10, 8)
    rs.merge_universe(day, [{"ticker": "AAA"}], tmp_path)
    assert set(rs.merge_universe(day, [{"ticker": "BBB"}], tmp_path)) == {"AAA", "BBB"}
