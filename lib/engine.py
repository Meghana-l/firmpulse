"""
FirmPulse model engine.

A driver-based, monthly model of an alternative asset manager's own P&L:
    assets under management (AUM)  ->  fees  ->  revenue  ->  costs  ->  operating income

Everything here is SAMPLE data. The defaults describe a sample mid-size
manager. They say nothing about D. E. Shaw's (or any real firm's) economics.

Units: money is in US$ millions, rates are decimals (0.015 = 1.5%).
Pure Python, no third-party dependencies, so it runs anywhere (Vercel, tests, CLI).
"""
from __future__ import annotations

from dataclasses import dataclass, asdict, fields
from typing import Dict, List, Optional

MONTHS = ["Jan", "Feb", "Mar", "Apr", "May", "Jun", "Jul", "Aug", "Sep", "Oct", "Nov", "Dec"]


# --------------------------------------------------------------------------
# Inputs
# --------------------------------------------------------------------------
@dataclass
class Assumptions:
    fy: int = 2026

    # Fund economics
    start_aum: float = 5000.0        # $m at the start of the year
    mgmt_fee: float = 0.015          # yearly fee on assets (charged monthly)
    incentive_fee: float = 0.20      # share of profit above the high-water mark
    crystallize_every: int = 3       # incentive fee is settled every N months
    start_index: float = 100.0       # fund unit price at start of year
    start_hwm: float = 100.0         # high-water mark at start of year

    # Returns
    budget_return: float = 0.08      # planned yearly gross return
    beta: float = 0.30               # how much the fund moves with the stock market
    alpha_monthly: float = 0.001     # manager skill beyond the market (per month)
    cash_rate: float = 0.04          # yearly cash / T-bill rate (live data overrides)

    # Flows, $m per month (+ money in, - money out)
    budget_flow: float = 50.0
    actual_flow: float = 30.0        # what is really happening (run-rate)

    # People and costs
    start_headcount: float = 250.0
    budget_hires: float = 1.0        # people added per month, plan
    actual_hires: float = 0.6        # people added per month, reality
    budget_comp: float = 0.180       # base pay per head per year, $m
    actual_comp: float = 0.185
    budget_tech: float = 0.040       # technology + data per head per year, $m
    actual_tech: float = 0.044
    occupancy: float = 8.0           # offices, $m per year
    bonus_pct: float = 0.30          # bonus pool as share of revenue
    other_pct: float = 0.05          # other costs as share of revenue


# Sensible bounds so a public web form cannot send nonsense to the model.
BOUNDS = {
    "fy": (2000, 2100),
    "start_aum": (1.0, 1_000_000.0),
    "mgmt_fee": (0.0, 0.05),
    "incentive_fee": (0.0, 0.50),
    "crystallize_every": (1, 12),
    "start_index": (1.0, 10_000.0),
    "start_hwm": (1.0, 10_000.0),
    "budget_return": (-0.5, 1.0),
    "beta": (-1.0, 2.0),
    "alpha_monthly": (-0.05, 0.05),
    "cash_rate": (0.0, 0.25),
    "budget_flow": (-100_000.0, 100_000.0),
    "actual_flow": (-100_000.0, 100_000.0),
    "start_headcount": (1.0, 100_000.0),
    "budget_hires": (-100.0, 1000.0),
    "actual_hires": (-100.0, 1000.0),
    "budget_comp": (0.0, 5.0),
    "actual_comp": (0.0, 5.0),
    "budget_tech": (0.0, 5.0),
    "actual_tech": (0.0, 5.0),
    "occupancy": (0.0, 10_000.0),
    "bonus_pct": (0.0, 1.0),
    "other_pct": (0.0, 1.0),
}


def assumptions_from_dict(d: Optional[dict]) -> Assumptions:
    """Build Assumptions from untrusted input: unknown keys ignored, values clamped."""
    a = Assumptions()
    if not d:
        return a
    for f in fields(Assumptions):
        if f.name not in d:
            continue
        try:
            v = float(d[f.name])
        except (TypeError, ValueError):
            continue
        if v != v or v in (float("inf"), float("-inf")):   # NaN / inf
            continue
        lo, hi = BOUNDS[f.name]
        v = min(max(v, lo), hi)
        if f.name in ("fy", "crystallize_every"):
            v = int(round(v))
        setattr(a, f.name, v)
    return a


@dataclass
class Scenario:
    name: str
    return_adj: float = 0.0   # added to the yearly return for months not yet happened
    flow_mult: float = 1.0    # multiplies the flow run-rate for months not yet happened
    shock: float = 0.0        # one-off return in the first month not yet happened


SCENARIOS: Dict[str, Scenario] = {
    "base": Scenario("Base", 0.0, 1.0, 0.0),
    "upside": Scenario("Upside", 0.06, 1.5, 0.0),
    "downside": Scenario("Downside", -0.02, -0.5, -0.08),
}


# --------------------------------------------------------------------------
# Driver paths
# --------------------------------------------------------------------------
def monthly_budget_return(a: Assumptions) -> float:
    return (1.0 + a.budget_return) ** (1.0 / 12.0) - 1.0


@dataclass
class Drivers:
    returns: List[float]
    flows: List[float]
    hires: List[float]
    comp: float
    tech: float


def budget_drivers(a: Assumptions) -> Drivers:
    return Drivers([monthly_budget_return(a)] * 12, [a.budget_flow] * 12,
                   [a.budget_hires] * 12, a.budget_comp, a.budget_tech)


def fund_return_from_market(a: Assumptions, market_return: float, cash_rate: float) -> float:
    """Fund return = a slice of the stock market + the rest in cash + manager skill."""
    return a.alpha_monthly + a.beta * market_return + (1.0 - a.beta) * cash_rate / 12.0


def forecast_drivers(a: Assumptions, market_returns: List[float], cash_rate: float,
                     scenario: Scenario) -> Drivers:
    n = max(0, min(12, len(market_returns)))          # months that already happened
    mr_b = monthly_budget_return(a)
    returns, flows = [], []
    for i in range(12):
        if i < n:
            returns.append(fund_return_from_market(a, market_returns[i], cash_rate))
            flows.append(a.actual_flow)
        else:
            r = mr_b + scenario.return_adj / 12.0
            if i == n:
                r += scenario.shock
            returns.append(r)
            flows.append(a.actual_flow * scenario.flow_mult)
    return Drivers(returns, flows, [a.actual_hires] * 12, a.actual_comp, a.actual_tech)


# --------------------------------------------------------------------------
# The model
# --------------------------------------------------------------------------
def run_year(a: Assumptions, d: Drivers) -> dict:
    """Run 12 months. Returns monthly rows and full-year totals."""
    rows = []
    aum = a.start_aum
    index_prev = a.start_index
    hwm = a.start_hwm
    headcount = a.start_headcount

    for t in range(12):
        r = d.returns[t]
        begin_aum = aum
        gross_aum = begin_aum * (1.0 + r)
        mgmt = gross_aum * a.mgmt_fee / 12.0
        aum_pre = gross_aum - mgmt

        index_pre = index_prev * (1.0 + r) * (1.0 - a.mgmt_fee / 12.0)
        crystallize = ((t + 1) % a.crystallize_every == 0)
        hwm_start = hwm
        if crystallize and index_pre > hwm_start and aum_pre > 0:
            inc = a.incentive_fee * (index_pre - hwm_start) / index_pre * aum_pre
        else:
            inc = 0.0
        index_post = index_pre * (1.0 - inc / aum_pre) if aum_pre > 0 else index_pre
        if crystallize:
            hwm = max(hwm_start, index_post)

        end_aum = aum_pre - inc + d.flows[t]

        revenue = mgmt + inc
        headcount += d.hires[t]
        base_comp = headcount * d.comp / 12.0
        bonus = a.bonus_pct * revenue
        tech = headcount * d.tech / 12.0
        occupancy = a.occupancy / 12.0
        other = a.other_pct * revenue
        opex = base_comp + bonus + tech + occupancy + other
        op_inc = revenue - opex

        rows.append({
            "month": MONTHS[t], "m": t + 1,
            "fund_return": r, "begin_aum": begin_aum, "mgmt_fee": mgmt,
            "incentive_fee": inc, "flows": d.flows[t], "end_aum": end_aum,
            "index_pre": index_pre, "index_post": index_post, "hwm": hwm,
            "revenue": revenue, "headcount": headcount, "base_comp": base_comp,
            "bonus": bonus, "tech": tech, "occupancy": occupancy, "other": other,
            "opex": opex, "op_income": op_inc,
        })
        aum = end_aum
        index_prev = index_post

    def s(k):
        return sum(x[k] for x in rows)

    revenue = s("revenue")
    totals = {
        "mgmt_fee": s("mgmt_fee"), "incentive_fee": s("incentive_fee"),
        "revenue": revenue, "base_comp": s("base_comp"), "bonus": s("bonus"),
        "tech": s("tech"), "occupancy": s("occupancy"), "other": s("other"),
        "opex": s("opex"), "op_income": s("op_income"),
        "margin": (s("op_income") / revenue) if revenue > 0 else 0.0,
        "flows": s("flows"), "end_aum": rows[-1]["end_aum"],
        "end_headcount": rows[-1]["headcount"], "end_hwm": rows[-1]["hwm"],
        "end_index": rows[-1]["index_post"],
    }
    return {"rows": rows, "totals": totals}


# --------------------------------------------------------------------------
# Variance bridge: Budget -> Forecast, one driver at a time
# --------------------------------------------------------------------------
def variance_bridge(a: Assumptions, market_returns: List[float], cash_rate: float,
                    scenario: Optional[Scenario] = None) -> dict:
    """
    Swap plan drivers for real/forecast drivers one group at a time and record
    how operating income moves at each step. The steps add up exactly.
    """
    scenario = scenario or SCENARIOS["base"]
    b = budget_drivers(a)
    f = forecast_drivers(a, market_returns, cash_rate, scenario)

    budget = run_year(a, b)["totals"]["op_income"]
    step1 = run_year(a, Drivers(f.returns, b.flows, b.hires, b.comp, b.tech))["totals"]["op_income"]
    step2 = run_year(a, Drivers(f.returns, f.flows, b.hires, b.comp, b.tech))["totals"]["op_income"]
    step3 = run_year(a, f)["totals"]["op_income"]

    return {
        "budget": budget,
        "returns": step1 - budget,
        "flows": step2 - step1,
        "costs": step3 - step2,
        "forecast": step3,
    }


# --------------------------------------------------------------------------
# One call that produces everything the app / Excel / report needs
# --------------------------------------------------------------------------
def build_outlook(a: Assumptions, market_returns: List[float], cash_rate: Optional[float] = None) -> dict:
    cash = a.cash_rate if cash_rate is None else cash_rate
    market_returns = [float(x) for x in market_returns][:12]
    n = len(market_returns)

    budget = run_year(a, budget_drivers(a))
    scen_out = {}
    for key, sc in SCENARIOS.items():
        scen_out[key] = run_year(a, forecast_drivers(a, market_returns, cash, sc))
    base = scen_out["base"]

    bridge = variance_bridge(a, market_returns, cash, SCENARIOS["base"])

    return {
        "fy": a.fy,
        "completed_months": n,
        "assumptions": asdict(a),
        "budget": budget,
        "forecast": base,
        "scenarios": {k: v["totals"] for k, v in scen_out.items()},
        "scenario_rows": {k: v["rows"] for k, v in scen_out.items()},
        "bridge": bridge,
        "market_returns": market_returns,
        "cash_rate": cash,
    }


def pct_change(new: float, old: float) -> Optional[float]:
    return None if old == 0 else (new - old) / abs(old)
