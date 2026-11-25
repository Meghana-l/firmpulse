"""Build the downloadable starter workbook:  python scripts/build_excel.py  ->  public/FirmPulse_Model.xlsx"""
import os
import sys

ROOT = os.path.join(os.path.dirname(os.path.abspath(__file__)), "..")
sys.path.insert(0, ROOT)

from lib.engine import Assumptions                    # noqa: E402
from lib.market import get_market                      # noqa: E402
from lib.xlsx_builder import build_workbook           # noqa: E402

if __name__ == "__main__":
    mk = get_market()                                  # live if FRED_API_KEY is set, else sample
    wb = build_workbook(Assumptions(fy=mk["fy"]), mk["monthly_market_returns"], mk["cash_rate"])
    out = os.path.join(ROOT, "public", "FirmPulse_Model.xlsx")
    wb.save(out)
    print(f"Saved {out}  (market data: {mk['source']})")
