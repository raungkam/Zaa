import json, sys
from datetime import date
from pathlib import Path
sys.path.insert(0, str(Path(__file__).parent.parent))
import scanner


def test_filters_and_sorting():
    quotes = {
        "AAA": {"preMarketPrice": 10.0, "regularMarketPreviousClose": 9.0},   # +11.1%
        "BBB": {"preMarketPrice": 2.9, "preMarketChangePercent": 20},         # price too low
        "CCC": {"preMarketPrice": 5.0, "preMarketChangePercent": 4.9},        # gap too small
        "DDD": {"preMarketPrice": 5.0, "preMarketChangePercent": 8},          # volume too low
        "EEE": {"preMarketPrice": 6.0, "preMarketChangePercent": 5.01},       # ok
        "FFF": {"preMarketPrice": 3.0, "preMarketChangePercent": 9},          # price == 3, excluded
    }
    vols = {"AAA": 60000, "BBB": 1e6, "CCC": 1e6, "DDD": 50000, "EEE": 50001, "FFF": 1e6}
    rows = scanner.build_results(quotes, vols)
    assert [r["ticker"] for r in rows] == ["AAA", "EEE"]
    assert rows[0]["gap_pct"] == 11.11


def test_first_sentence():
    assert scanner._first_sentence("<p>Acme jumps on FDA nod. More text.</p>") == "Acme jumps on FDA nod."


def test_save_and_format(tmp_path):
    rows = [{"ticker": "AAA", "price": 10.0, "gap_pct": 11.11,
             "premarket_volume": 60000, "catalyst": "Beat earnings."}]
    p = scanner.save(rows, date(2026, 10, 8), tmp_path)
    assert p.name == "premarket_2026-10-08.json"
    assert json.loads(p.read_text())["results"][0]["ticker"] == "AAA"
    assert "AAA" in scanner.format_table(rows) and "+11.11%" in scanner.format_table(rows)
