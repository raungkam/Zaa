"""Telegram delivery + message formats. Needs env TELEGRAM_BOT_TOKEN and TELEGRAM_CHAT_ID."""
import os

import requests

LIMIT = 4000  # Telegram max is 4096 characters per message


def format_a(rows):
    body = "\n".join(f"{r['ticker']}  ${r['price']:.2f}  {r['gap_pct']:+.2f}%  {r['catalyst']}" for r in rows)
    return "[Scanner A: Pre-market Gappers]\n" + (body or "No matches.")


def format_b(hits):
    if not hits:
        return "[Scanner B: Trend-join Long Hits]\nNo valid setups."
    blocks = [f"{h['ticker']}  ENTRY ${h['entry']:.2f}\n"
              f"  Gap {h['gap_pct']:+.2f}% | Prev-day high {h['prev_day_high']:.2f} | PM high {h['premarket_high']:.2f}"
              f" | HOD {h['hod']:.2f} | 200 SMA {h['sma200']:.2f}\n  {h['catalyst']}" for h in hits]
    return "[Scanner B: Trend-join Long Hits]\n" + "\n".join(blocks)


def chunks(text, limit=LIMIT):
    """Split on line boundaries; the header only appears in the first chunk."""
    out, cur = [], ""
    for line in text.split("\n"):
        if cur and len(cur) + len(line) + 1 > limit:
            out.append(cur)
            cur = ""
        cur += ("\n" if cur else "") + line[:limit]
    return out + [cur] if cur else out


def send(text):
    token, chat = os.environ.get("TELEGRAM_BOT_TOKEN"), os.environ.get("TELEGRAM_CHAT_ID")
    if not token or not chat:
        raise RuntimeError("set TELEGRAM_BOT_TOKEN and TELEGRAM_CHAT_ID")
    for part in chunks(text):
        r = requests.post(f"https://api.telegram.org/bot{token}/sendMessage",
                          json={"chat_id": chat, "text": part}, timeout=20)
        r.raise_for_status()
