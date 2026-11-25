import math
import os
import sys

sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))

from lib.engine import (Assumptions, Drivers, SCENARIOS, assumptions_from_dict, budget_drivers,
                        build_outlook, monthly_budget_return, run_year, variance_bridge)


def flat(a, r=0.0, flow=0.0, hires=0.0):
    return Drivers([r] * 12, [flow] * 12, [hires] * 12, a.budget_comp, a.budget_tech)


def test_zero_return_zero_flow_only_management_fee():
    a = Assumptions()
    out = run_year(a, flat(a))["totals"]
    # AUM drifts down slightly because fees come out of it, so fee is a bit under 1.5% of 5000.
    assert 70.0 < out["mgmt_fee"] < 75.0
    assert out["incentive_fee"] == 0.0


def test_aum_roll_forward_identity():
    a = Assumptions()
    d = budget_drivers(a)
    res = run_year(a, d)
    rows = res["rows"]
    gross_pnl = sum(r["begin_aum"] * r["fund_return"] for r in rows)
    fees = res["totals"]["mgmt_fee"] + res["totals"]["incentive_fee"]
    expected_end = a.start_aum + gross_pnl - fees + sum(d.flows)
    # End AUM = start + investment gains - fees + money in/out, to the cent.
    assert math.isclose(res["totals"]["end_aum"], expected_end, rel_tol=0, abs_tol=1e-6)


def test_high_water_mark_blocks_fee_after_drawdown():
    a = Assumptions()
    # Q1 up strongly, Q2 down hard, Q3 partial recovery (still below the old peak), Q4 flat
    rets = [0.04] * 3 + [-0.06] * 3 + [0.03] * 3 + [0.0] * 3
    rows = run_year(a, Drivers(rets, [0.0] * 12, [0.0] * 12, a.budget_comp, a.budget_tech))["rows"]
    assert rows[2]["incentive_fee"] > 0            # Q1 settles a fee
    assert rows[5]["incentive_fee"] == 0.0         # Q2: loss, no fee
    assert rows[8]["incentive_fee"] == 0.0         # Q3: still under high-water mark, no fee
    assert rows[11]["incentive_fee"] == 0.0        # Q4: flat, still under


def test_high_water_mark_pays_again_after_new_peak():
    a = Assumptions()
    rets = [0.04] * 3 + [-0.03] * 3 + [0.06] * 3 + [0.0] * 3
    rows = run_year(a, Drivers(rets, [0.0] * 12, [0.0] * 12, a.budget_comp, a.budget_tech))["rows"]
    assert rows[2]["incentive_fee"] > 0
    assert rows[8]["incentive_fee"] > 0            # recovered above the old peak


def test_bridge_adds_up_exactly():
    a = Assumptions()
    market = [0.012, -0.018, 0.021, 0.008, 0.015, -0.006, 0.019, 0.004, -0.011, 0.017]
    br = variance_bridge(a, market, 0.04)
    assert math.isclose(br["budget"] + br["returns"] + br["flows"] + br["costs"], br["forecast"], abs_tol=1e-9)


def test_no_difference_when_actual_equals_budget():
    a = Assumptions()
    mr = monthly_budget_return(a)
    a.beta = 0.0
    a.alpha_monthly = mr           # fund earns exactly the planned monthly return
    a.cash_rate = 0.0
    a.actual_flow, a.actual_hires = a.budget_flow, a.budget_hires
    a.actual_comp, a.actual_tech = a.budget_comp, a.budget_tech
    br = variance_bridge(a, [0.01, 0.02, -0.01, 0.0], 0.0)
    assert abs(br["returns"]) < 1e-9 and abs(br["flows"]) < 1e-9 and abs(br["costs"]) < 1e-9


def test_scenarios_ordering():
    a = Assumptions()
    out = build_outlook(a, [0.01, 0.005, 0.012, -0.004, 0.008])
    s = out["scenarios"]
    assert s["upside"]["op_income"] > s["base"]["op_income"] > s["downside"]["op_income"]
    assert s["downside"]["end_aum"] < s["base"]["end_aum"] < s["upside"]["end_aum"]


def test_no_completed_months_forecast_uses_run_rates_only():
    a = Assumptions()
    out = build_outlook(a, [])
    assert out["completed_months"] == 0
    assert out["forecast"]["totals"]["revenue"] > 0


def test_all_twelve_months_scenarios_equal():
    a = Assumptions()
    out = build_outlook(a, [0.01] * 12)
    s = out["scenarios"]
    assert math.isclose(s["upside"]["op_income"], s["downside"]["op_income"], abs_tol=1e-9)


def test_input_clamping_and_junk_ignored():
    a = assumptions_from_dict({"start_aum": -5, "mgmt_fee": "abc", "beta": 999, "evil": 1,
                               "crystallize_every": 3.4, "alpha_monthly": float("nan")})
    assert a.start_aum == 1.0                 # clamped up to the floor
    assert a.mgmt_fee == Assumptions().mgmt_fee   # junk ignored, default kept
    assert a.beta == 2.0                      # clamped down to the ceiling
    assert a.crystallize_every == 3
    assert a.alpha_monthly == Assumptions().alpha_monthly
    assert not hasattr(a, "evil")


def test_heavy_redemptions_do_not_break():
    a = Assumptions(actual_flow=-1000.0)
    out = build_outlook(a, [0.0] * 4)
    assert out["forecast"]["totals"]["end_aum"] >= -1e9   # runs without error
