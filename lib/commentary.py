"""
Variance commentary: turns the numbers into plain English.

Two modes:
  * template  - always available, deterministic, no network.
  * claude    - if ANTHROPIC_API_KEY is set, Claude rewrites the same numbers as a short
                note for leadership. The prompt is built ONLY from numbers computed by the
                model (never from free text sent by a visitor), so the public endpoint
                cannot be used to push arbitrary prompts through your key.
"""
from __future__ import annotations

import json
import os
import urllib.request
from typing import Callable, Optional

ANTHROPIC_URL = "https://api.anthropic.com/v1/messages"


def _m(x: float) -> str:
    sign = "-" if x < 0 else ""
    return f"{sign}${abs(x):,.1f}m"


def _facts(outlook: dict) -> dict:
    b, f = outlook["budget"]["totals"], outlook["forecast"]["totals"]
    br = outlook["bridge"]
    drivers = [("market returns", br["returns"]), ("net flows", br["flows"]),
               ("hiring and cost rates", br["costs"])]
    drivers.sort(key=lambda x: abs(x[1]), reverse=True)
    return {
        "fy": outlook["fy"],
        "months_done": outlook["completed_months"],
        "budget_revenue": b["revenue"], "forecast_revenue": f["revenue"],
        "budget_op_income": b["op_income"], "forecast_op_income": f["op_income"],
        "budget_margin": b["margin"], "forecast_margin": f["margin"],
        "budget_incentive": b["incentive_fee"], "forecast_incentive": f["incentive_fee"],
        "budget_end_aum": b["end_aum"], "forecast_end_aum": f["end_aum"],
        "bridge": {"returns": br["returns"], "flows": br["flows"], "costs": br["costs"]},
        "biggest_driver": drivers[0][0], "biggest_driver_amount": drivers[0][1],
        "downside_op_income": outlook["scenarios"]["downside"]["op_income"],
        "upside_op_income": outlook["scenarios"]["upside"]["op_income"],
    }


def template_commentary(outlook: dict) -> str:
    f = _facts(outlook)
    gap = f["forecast_op_income"] - f["budget_op_income"]
    direction = "above" if gap >= 0 else "below"
    lines = [
        f"FY{f['fy']} outlook after {f['months_done']} completed month(s): operating income is forecast at "
        f"{_m(f['forecast_op_income'])}, {_m(abs(gap))} {direction} the {_m(f['budget_op_income'])} budget. "
        f"Margin moves from {f['budget_margin']:.1%} to {f['forecast_margin']:.1%}.",
        f"The biggest driver is {f['biggest_driver']} ({_m(f['biggest_driver_amount'])} on operating income). "
        f"Returns contribute {_m(f['bridge']['returns'])}, net flows {_m(f['bridge']['flows'])}, "
        f"and hiring and cost rates {_m(f['bridge']['costs'])}.",
    ]
    if f["forecast_incentive"] < f["budget_incentive"] * 0.9:
        lines.append(
            f"Incentive fees are forecast at {_m(f['forecast_incentive'])} versus {_m(f['budget_incentive'])} "
            "in the budget. These fees only count above the high-water mark, so they swing more than "
            "management fees.")
    lines.append(
        f"Range of outcomes: {_m(f['downside_op_income'])} in the downside case to "
        f"{_m(f['upside_op_income'])} in the upside case. Figures are from a sample-firm model.")
    return " ".join(lines)


def _prompt(facts: dict) -> str:
    return (
        "You are an FP&A analyst at an investment firm. Write a variance commentary of at most 120 words "
        "for senior leaders who are not finance specialists. Use ONLY the figures below (US$ millions). "
        "Say what moved versus budget, the biggest driver, and one risk to watch. Do not invent causes "
        "beyond what the numbers show. Mention that the firm is a sample. No headings, no bullets.\n\n"
        + json.dumps(facts, indent=2, default=float)
    )


def http_post_json(url: str, headers: dict, payload: dict, timeout: int = 20) -> dict:
    req = urllib.request.Request(url, data=json.dumps(payload).encode("utf-8"), headers=headers, method="POST")
    with urllib.request.urlopen(req, timeout=timeout) as resp:
        return json.loads(resp.read().decode("utf-8"))


def get_commentary(outlook: dict, env: Optional[dict] = None,
                   post: Callable[..., dict] = http_post_json) -> dict:
    env = os.environ if env is None else env
    key = env.get("ANTHROPIC_API_KEY", "").strip()
    fallback = template_commentary(outlook)
    if not key:
        return {"source": "template", "text": fallback}
    model = env.get("ANTHROPIC_MODEL", "claude-sonnet-5-5")
    try:
        res = post(ANTHROPIC_URL,
                   {"x-api-key": key, "anthropic-version": "2023-06-01", "content-type": "application/json"},
                   {"model": model, "max_tokens": 400,
                    "messages": [{"role": "user", "content": _prompt(_facts(outlook))}]})
        text = "".join(block.get("text", "") for block in res.get("content", []) if block.get("type") == "text").strip()
        if text:
            return {"source": "claude", "model": model, "text": text}
    except Exception:
        pass
    return {"source": "template", "text": fallback}
