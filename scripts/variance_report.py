"""
Monthly variance report, automated.

    python scripts/variance_report.py            # uses live data if FRED_API_KEY is set
    python scripts/variance_report.py --sample   # force sample data

Writes reports/variance_FY<year>.md and prints it. Schedule it with cron or a GitHub Action
to produce the report every month with no manual work.
"""
import argparse
import os
import sys

ROOT = os.path.join(os.path.dirname(os.path.abspath(__file__)), "..")
sys.path.insert(0, ROOT)

from lib.commentary import get_commentary       # noqa: E402
from lib.engine import Assumptions, build_outlook  # noqa: E402
from lib.market import get_market                # noqa: E402


def m(x):
    return f"{x:,.1f}"


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--sample", action="store_true", help="ignore API keys and use sample data")
    args = ap.parse_args()

    mk = get_market(env={} if args.sample else None)
    a = Assumptions(fy=mk["fy"])
    out = build_outlook(a, mk["monthly_market_returns"], mk["cash_rate"])
    b, f, br = out["budget"]["totals"], out["forecast"]["totals"], out["bridge"]
    note = get_commentary(out)

    lines = [
        f"# FY{a.fy} variance report (sample firm)",
        f"*Market data: {mk['source'].upper()} - {mk['note']}*",
        "",
        f"Completed months: {out['completed_months']}",
        "",
        "| $m | Budget | Forecast | Variance |", "|---|---:|---:|---:|",
    ]
    for label, k in (("Total revenue", "revenue"), ("Incentive fees", "incentive_fee"), ("Total costs", "opex"),
                     ("Operating income", "op_income"), ("Ending assets", "end_aum")):
        lines.append(f"| {label} | {m(b[k])} | {m(f[k])} | {m(f[k] - b[k])} |")
    lines += [
        "",
        "## Why operating income moved",
        f"- Market returns: {m(br['returns'])}",
        f"- Net flows: {m(br['flows'])}",
        f"- Hiring and cost rates: {m(br['costs'])}",
        "",
        "## Commentary",
        note["text"],
        f"*(source: {note['source']})*",
    ]
    text = "\n".join(lines)
    os.makedirs(os.path.join(ROOT, "reports"), exist_ok=True)
    path = os.path.join(ROOT, "reports", f"variance_FY{a.fy}.md")
    with open(path, "w", encoding="utf-8") as fh:
        fh.write(text + "\n")
    print(text)
    print(f"\nSaved to {path}")


if __name__ == "__main__":
    main()
