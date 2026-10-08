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

## Trend-join Long strategy scanner (TradingView)

Filters the pre-market scan results. A valid entry fires once per day per ticker, after 10:00 exchange time, when
the confirmed bar close is:
1. above yesterday's daily high,
2. with yesterday's close above the daily 200 SMA (as of yesterday), and
3. above today's pre-market high **and** the high of day so far (pre-market + regular session, prior bars).

Workflow:
1. `python scanner.py` then `python strategy_report.py watchlist` -> `results/watchlist_DATE.txt`; import it in TradingView (Watchlist > Import list).
2. Add `tradingview/trend_join_long.pine` to an intraday chart (1-5 min) with **extended hours on**.
3. Create an alert on the indicator ("Any alert() function call") for the watchlist, with a webhook to your public URL
   (TradingView needs HTTPS/port 80/443, so put a reverse proxy or tunnel in front of the receiver; webhooks and watchlist alerts need a paid TradingView plan).
4. `python strategy_report.py serve` receives alerts, drops any ticker not in the day's pre-market scan, re-checks the three criteria,
   and saves `results/signals_DATE.json` (price, gap %, catalyst, levels). `python strategy_report.py report` prints the day's signals.
