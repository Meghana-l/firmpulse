"""Recalculate the generated workbook in LibreOffice and compare with the Python engine."""
import math
import os
import shutil
import subprocess
import sys
import tempfile

import pytest
from openpyxl import load_workbook

sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))

from lib.engine import Assumptions, build_outlook
from lib.xlsx_builder import R, TOT_COL, build_workbook
from openpyxl.utils import get_column_letter

pytestmark = pytest.mark.skipif(shutil.which("soffice") is None, reason="LibreOffice not installed")
T = get_column_letter(TOT_COL)


def recalc(wb):
    d = tempfile.mkdtemp()
    src = os.path.join(d, "in.xlsx")
    wb.save(src)
    out = os.path.join(d, "out")
    os.mkdir(out)
    subprocess.run(["soffice", "--headless", "--calc", "--convert-to", "xlsx", "--outdir", out, src],
                   check=True, capture_output=True, timeout=120)
    return load_workbook(os.path.join(out, "in.xlsx"), data_only=True)


CASES = [
    ([0.012, -0.018, 0.021, 0.008, 0.015, -0.006, 0.019, 0.004, -0.011, 0.017], Assumptions()),
    ([0.01, 0.02], Assumptions(actual_flow=-40.0, beta=0.6, incentive_fee=0.25)),
    ([], Assumptions()),
    ([0.011] * 12, Assumptions(crystallize_every=6, start_hwm=103.0)),
]


@pytest.mark.parametrize("market,a", CASES)
def test_excel_matches_engine(market, a):
    cash = 0.039
    wb = recalc(build_workbook(a, market, cash))
    out = build_outlook(a, market, cash)

    def ws_total(sheet, key):
        return wb[sheet][f"{T}{R[key]}"].value

    pairs = {
        "Budget": out["budget"]["totals"],
        "Fcst_Base": out["scenarios"]["base"],
        "Fcst_Upside": out["scenarios"]["upside"],
        "Fcst_Downside": out["scenarios"]["downside"],
    }
    for sheet, tot in pairs.items():
        for key, tkey in (("rev", "revenue"), ("inc", "incentive_fee"), ("opex", "opex"),
                          ("oi", "op_income"), ("end", "end_aum")):
            got = ws_total(sheet, key)
            assert got is not None, (sheet, key)
            assert math.isclose(got, tot[tkey], rel_tol=1e-9, abs_tol=1e-6), (sheet, key, got, tot[tkey])

    # bridge on the Variance sheet equals the engine's bridge
    refs = wb["Variance"]
    labels = {refs.cell(row=r, column=1).value: refs.cell(row=r, column=2).value for r in range(1, 40)}
    br = out["bridge"]
    assert math.isclose(labels["Budget operating income"], br["budget"], abs_tol=1e-6)
    assert math.isclose(labels["Market and returns"], br["returns"], abs_tol=1e-6)
    assert math.isclose(labels["Net flows (money in and out)"], br["flows"], abs_tol=1e-6)
    assert math.isclose(labels["Hiring and cost rates"], br["costs"], abs_tol=1e-6)
    assert math.isclose(labels["Forecast operating income"], br["forecast"], abs_tol=1e-6)
    assert abs(labels["Check (should be 0)"]) < 1e-6


def test_no_formula_errors_anywhere():
    a = Assumptions()
    wb = recalc(build_workbook(a, [0.01, -0.02, 0.015], 0.04))
    for ws in wb.worksheets:
        for row in ws.iter_rows():
            for c in row:
                if isinstance(c.value, str) and c.value.startswith("#"):
                    raise AssertionError(f"{ws.title}!{c.coordinate} = {c.value}")
