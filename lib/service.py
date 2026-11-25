"""Shared request handling for the API routes (model, commentary, export)."""
from __future__ import annotations

from typing import Optional, Tuple

from .engine import Assumptions, assumptions_from_dict, build_outlook
from .market import get_market


def _clean_returns(raw) -> list:
    out = []
    for x in (raw or [])[:12]:
        try:
            v = float(x)
        except (TypeError, ValueError):
            break
        if v != v or abs(v) > 0.5:      # NaN or a 50%+ monthly move: not plausible, stop here
            break
        out.append(v)
    return out


def resolve_request(body: dict) -> Tuple[Assumptions, list, float, str]:
    """Turn an untrusted request body into (assumptions, market returns, cash rate, data source)."""
    a = assumptions_from_dict((body or {}).get("assumptions"))
    mk = (body or {}).get("market")
    if isinstance(mk, dict) and "monthly_market_returns" in mk:
        returns = _clean_returns(mk.get("monthly_market_returns"))
        try:
            cash = float(mk.get("cash_rate", a.cash_rate))
        except (TypeError, ValueError):
            cash = a.cash_rate
        cash = min(max(cash, 0.0), 0.25) if cash == cash else a.cash_rate
        source = "client" if mk.get("source") not in ("live", "sample") else mk["source"]
    else:
        live = get_market()
        returns, cash, source = live["monthly_market_returns"], live["cash_rate"], live["source"]
    return a, returns, cash, source


def outlook_for(body: dict) -> dict:
    a, returns, cash, source = resolve_request(body)
    out = build_outlook(a, returns, cash)
    out["market_source"] = source
    return out
