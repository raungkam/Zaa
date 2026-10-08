import json, sys
from pathlib import Path
sys.path.insert(0, str(Path(__file__).parent.parent))
import strategy_report as sr

DAY = "2026-10-08"
ALERT = {"signal": "trend_join_long", "ticker": "AAA", "price": 10.5, "prev_day_high": 10.0,
         "prev_close": 9.5, "sma200": 8.0, "premarket_high": 10.3, "prev_bar_hod": 10.4}


def setup(tmp_path):
    (tmp_path / f"premarket_{DAY}.json").write_text(json.dumps({"results": [
        {"ticker": "AAA", "price": 10, "gap_pct": 11.1, "catalyst": "Beat earnings."}]}))


def test_valid_signal_recorded_once(tmp_path):
    setup(tmp_path)
    assert sr.record_signal(ALERT, DAY, tmp_path)["catalyst"] == "Beat earnings."
    assert sr.record_signal(ALERT, DAY, tmp_path) is None  # duplicate
    assert "AAA" in sr.format_report(DAY, tmp_path)


def test_rejections(tmp_path):
    setup(tmp_path)
    assert sr.record_signal({**ALERT, "ticker": "NASDAQ:ZZZ"}, DAY, tmp_path) is None   # not in scan
    for k, v in [("price", 9.9), ("prev_close", 7.0), ("premarket_high", 10.6), ("prev_bar_hod", 10.6)]:
        assert sr.record_signal({**ALERT, k: v}, DAY, tmp_path) is None, k


def test_watchlist(tmp_path):
    setup(tmp_path)
    p, n = sr.write_watchlist(DAY, tmp_path)
    assert n == 1 and p.read_text().strip() == "AAA"
