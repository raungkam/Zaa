# Pre-market stock scanner

Scans for stocks that are **up > 5%** vs. the previous close, trade **above $3**, and have
**pre-market volume > 50,000** shares.

- Candidates + pre-market price/gap/volume: Yahoo Finance (gainers / most-active / small-cap-gainer screeners, then quote + 1-minute chart data for 04:00–09:30 ET volume)
- One-sentence catalyst: Benzinga (official API if `BENZINGA_API_KEY` is set, otherwise public per-ticker RSS feed)

```
pip install -r requirements.txt
python scanner.py                 # today (New York date)
python scanner.py --date 2026-10-08
```

Output:

```
Ticker      Price    Gap %  Catalyst
AAA        $10.00  +11.11%  Acme jumps on FDA approval.
```

Each run writes `results/premarket_YYYY-MM-DD.json`. `.github/workflows/premarket-scan.yml`
runs it weekdays at 12:30 UTC (before the open) and commits the file; or use cron locally:
`30 8 * * 1-5 cd /path/to/Zaa && python3 scanner.py` (with the machine on New York time).

Notes: Yahoo/Benzinga endpoints are unofficial/unauthenticated and may change or rate-limit.
Candidates come from Yahoo's screeners, so a thinly traded gapper outside them can be missed.
