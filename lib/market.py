"""
Market data layer.

Live sources (all server-side, keys never reach the browser):
  * FRED (St. Louis Fed)  - S&P 500 daily close, VIX, 3-month T-bill, 10-year Treasury.
                            Free key: https://fred.stlouisfed.org/docs/api/api_key.html
                            Set FRED_API_KEY.
  * Finnhub (optional)    - latest SPY quote, for a "right now" number.
                            Free key: https://finnhub.io/register   Set FINNHUB_API_KEY.

If there is no key (or a call fails) the app falls back to clearly labelled SAMPLE data
so it never shows a blank screen. The response always says which one you are looking at.
"""
from __future__ import annotations

import datetime as dt
import json
import os
import urllib.parse
import urllib.request
from typing import Callable, Dict, List, Optional

FRED_URL = "https://api.stlouisfed.org/fred/series/observations"
FINNHUB_QUOTE_URL = "https://finnhub.io/api/v1/quote"

# Plain, repeatable pseudo-market for demo mode. NOT real data.
SAMPLE_MONTHLY_RETURNS = [0.012, -0.018, 0.021, 0.008, 0.015, -0.006,
                          0.019, 0.004, -0.011, 0.017, 0.006, 0.010]


def http_get_json(url: str, headers: Optional[dict] = None, timeout: int = 8) -> dict:
    req = urllib.request.Request(url, headers=headers or {"User-Agent": "FirmPulse/1.0"})
    with urllib.request.urlopen(req, timeout=timeout) as resp:
        return json.loads(resp.read().decode("utf-8"))


def _valid(observations: List[dict]) -> List[tuple]:
    """FRED marks holidays/missing days with '.', skip those."""
    out = []
    for o in observations:
        v = o.get("value")
        if v in (None, ".", ""):
            continue
        try:
            out.append((o["date"], float(v)))
        except (KeyError, ValueError):
            continue
    return out


def month_end_closes(observations: List[dict]) -> Dict[str, float]:
    """Last valid value in each calendar month, keyed 'YYYY-MM'."""
    closes: Dict[str, float] = {}
    for date, val in sorted(_valid(observations)):
        closes[date[:7]] = val
    return closes


def completed_month_count(fy: int, today: dt.date) -> int:
    if today.year > fy:
        return 12
    if today.year < fy:
        return 0
    return today.month - 1


def monthly_returns_for_year(observations: List[dict], fy: int, today: dt.date) -> List[float]:
    """Month-end to month-end returns for the months of `fy` that are fully over."""
    closes = month_end_closes(observations)
    out: List[float] = []
    for m in range(1, completed_month_count(fy, today) + 1):
        this_key = f"{fy}-{m:02d}"
        prev_key = f"{fy - 1}-12" if m == 1 else f"{fy}-{m - 1:02d}"
        if this_key in closes and prev_key in closes and closes[prev_key] > 0:
            out.append(closes[this_key] / closes[prev_key] - 1.0)
        else:
            break          # stop at the first gap so months stay in order
    return out


def month_to_date_return(observations: List[dict], today: dt.date) -> Optional[float]:
    closes = month_end_closes(observations)
    valid = sorted(_valid(observations))
    if not valid:
        return None
    last_date, last_val = valid[-1]
    this_key = last_date[:7]
    y, m = int(this_key[:4]), int(this_key[5:7])
    prev_key = f"{y - 1}-12" if m == 1 else f"{y}-{m - 1:02d}"
    base = closes.get(prev_key)
    return (last_val / base - 1.0) if base else None


def _latest(observations: List[dict]) -> Optional[tuple]:
    valid = _valid(observations)
    return max(valid) if valid else None


def sample_market(fy: int, today: dt.date, note: str) -> dict:
    n = completed_month_count(fy, today)
    return {
        "source": "sample",
        "note": note,
        "fy": fy,
        "as_of": today.isoformat(),
        "completed_months": n,
        "monthly_market_returns": SAMPLE_MONTHLY_RETURNS[:n],
        "cash_rate": 0.04,
        "vix": 17.5,
        "us10y": 0.043,
        "sp500_last": None,
        "mtd_return": None,
        "quote": None,
    }


def get_market(env: Optional[dict] = None, today: Optional[dt.date] = None,
               fetch: Callable[..., dict] = http_get_json) -> dict:
    env = os.environ if env is None else env
    today = today or dt.datetime.now(dt.timezone.utc).date()
    fy = today.year

    key = env.get("FRED_API_KEY", "").strip()
    if not key:
        return sample_market(fy, today, "No FRED_API_KEY set. Showing SAMPLE data, not real market data.")

    def fred(series: str, start: dt.date, **extra) -> List[dict]:
        params = {"series_id": series, "api_key": key, "file_type": "json",
                  "observation_start": start.isoformat()}
        params.update(extra)
        return fetch(FRED_URL + "?" + urllib.parse.urlencode(params))["observations"]

    try:
        sp = fred("SP500", dt.date(fy - 1, 12, 1))
        returns = monthly_returns_for_year(sp, fy, today)
        mtd = month_to_date_return(sp, today)
        last_sp = _latest(sp)
        recent_start = today - dt.timedelta(days=45)
        vix = _latest(fred("VIXCLS", recent_start))
        tbill = _latest(fred("DTB3", recent_start))
        t10 = _latest(fred("DGS10", recent_start))
    except Exception as exc:  # network, bad key, rate limit, bad JSON ...
        # Report the failure type only. Never echo URLs (they contain the key).
        return sample_market(fy, today, f"Live FRED call failed ({type(exc).__name__}). Showing SAMPLE data.")

    quote = None
    fh_key = env.get("FINNHUB_API_KEY", "").strip()
    if fh_key:
        try:
            q = fetch(FINNHUB_QUOTE_URL + "?" + urllib.parse.urlencode({"symbol": "SPY", "token": fh_key}))
            if q.get("c"):
                quote = {"symbol": "SPY", "price": q["c"], "change_pct": q.get("dp"),
                         "unix_time": q.get("t")}
        except Exception:
            quote = None

    complete = completed_month_count(fy, today)
    note = "Live data from FRED (daily, end-of-day, published with a short delay)."
    if len(returns) < complete:
        note += f" Only {len(returns)} of {complete} finished months were available."
    return {
        "source": "live",
        "note": note,
        "fy": fy,
        "as_of": today.isoformat(),
        "data_through": last_sp[0] if last_sp else None,
        "completed_months": len(returns),
        "monthly_market_returns": returns,
        "cash_rate": (tbill[1] / 100.0) if tbill else 0.04,
        "vix": vix[1] if vix else None,
        "us10y": (t10[1] / 100.0) if t10 else None,
        "sp500_last": last_sp[1] if last_sp else None,
        "mtd_return": mtd,
        "quote": quote,
    }
