"""
Excel version of the FirmPulse model, built with openpyxl.

Every number below the inputs is a LIVE FORMULA (nothing is pasted in), so an analyst can
change a blue input and watch the whole workbook move. Tests recalculate this file in
LibreOffice and check it matches the Python engine to the cent.

Colour code (standard financial-modeling convention):
    blue text on yellow  = input you can change
    black text           = formula on the same sheet
    green text           = link pulled from another sheet
"""
from __future__ import annotations

import io
from dataclasses import fields
from typing import List, Optional

from openpyxl import Workbook
from openpyxl.styles import Alignment, Border, Font, PatternFill, Side
from openpyxl.utils import get_column_letter

from .engine import MONTHS, SCENARIOS, Assumptions

NAVY = "1F3A5F"
INPUT_FILL = PatternFill("solid", fgColor="FFF8DC")
HEAD_FILL = PatternFill("solid", fgColor=NAVY)
SUB_FILL = PatternFill("solid", fgColor="E8EEF6")
F_INPUT = Font(name="Calibri", size=11, color="0000FF")
F_CALC = Font(name="Calibri", size=11, color="000000")
F_LINK = Font(name="Calibri", size=11, color="007A33")
F_HEAD = Font(name="Calibri", size=11, bold=True, color="FFFFFF")
F_BOLD = Font(name="Calibri", size=11, bold=True)
F_TITLE = Font(name="Calibri", size=16, bold=True, color=NAVY)
THIN = Side(style="thin", color="B0B7C3")

USD = '#,##0.0;[Red](#,##0.0);"-"'
PCT = '0.0%;[Red]-0.0%;"-"'
PCT2 = '0.00%;[Red]-0.00%;"-"'
NUM = '#,##0.00'

# (key, label, number format, note)
INPUT_GROUPS = [
    ("Fund economics", [
        ("start_aum", "Starting assets under management ($m)", USD, "Money the firm manages on 1 Jan."),
        ("mgmt_fee", "Management fee (per year)", PCT2, "Charged monthly on assets."),
        ("incentive_fee", "Incentive fee (share of profit)", PCT, "Only on profit above the high-water mark."),
        ("crystallize_every", "Incentive fee settled every N months", "0", "3 = quarterly."),
        ("start_index", "Fund unit price at start", NUM, "Index used to track the high-water mark."),
        ("start_hwm", "High-water mark at start", NUM, "Highest unit price already paid on."),
    ]),
    ("Returns", [
        ("budget_return", "Budget: planned return (per year)", PCT, "The plan."),
        ("beta", "Beta: share of the fund that moves with the stock market", "0.00", "0.3 = moves 30% as much as the market."),
        ("alpha_monthly", "Alpha: skill beyond the market (per month)", PCT2, "Assumption, not a promise."),
        ("cash_rate", "Cash / T-bill rate (per year)", PCT2, "Live T-bill rate in the web app."),
    ]),
    ("Money in and out ($m per month)", [
        ("budget_flow", "Budget: net new money per month", USD, "Plan. Negative = redemptions."),
        ("actual_flow", "Actual: net new money per month", USD, "Run-rate seen so far."),
    ]),
    ("People and costs", [
        ("start_headcount", "Starting headcount", "#,##0.0", ""),
        ("budget_hires", "Budget: hires per month", "0.00", ""),
        ("actual_hires", "Actual: hires per month", "0.00", ""),
        ("budget_comp", "Budget: base pay per head per year ($m)", '0.000', ""),
        ("actual_comp", "Actual: base pay per head per year ($m)", '0.000', ""),
        ("budget_tech", "Budget: technology + data per head per year ($m)", '0.000', ""),
        ("actual_tech", "Actual: technology + data per head per year ($m)", '0.000', ""),
        ("occupancy", "Offices per year ($m)", USD, ""),
        ("bonus_pct", "Bonus pool (share of revenue)", PCT, ""),
        ("other_pct", "Other costs (share of revenue)", PCT, ""),
    ]),
]

# Row map for each model sheet
R = dict(month=4, name=5, phase=6, mkt=7, ret=8, flow=9, hire=10, comp=11, tech=12,
         begin=14, gross=15, mfee=16, aumpre=17, idxpre=18, crys=19, hwm0=20, inc=21,
         idxpost=22, hwm1=23, flow2=24, end=25,
         rev_m=27, rev_i=28, rev=29, hc=30, base=31, bonus=32, techc=33, occ=34, other=35,
         opex=36, oi=37, margin=38)
FIRST_COL, LAST_COL, TOT_COL = 3, 14, 15       # C..N months, O total


def _cell(ws, ref, value, font=F_CALC, fmt=None, fill=None, bold=False, align=None):
    c = ws[ref]
    c.value = value
    c.font = Font(name=font.name, size=font.size, color=font.color, bold=bold or font.bold)
    if fmt:
        c.number_format = fmt
    if fill:
        c.fill = fill
    if align:
        c.alignment = Alignment(horizontal=align)
    return c


def _header(ws, row, values, start_col=1):
    for i, v in enumerate(values):
        c = ws.cell(row=row, column=start_col + i, value=v)
        c.font, c.fill = F_HEAD, HEAD_FILL
        c.alignment = Alignment(horizontal="center" if i else "left", vertical="center", wrap_text=True)


def build_workbook(a: Assumptions, market_returns: Optional[List[float]] = None,
                   cash_rate: Optional[float] = None) -> Workbook:
    market_returns = list(market_returns or [])[:12]
    wb = Workbook()

    # ------------------------------------------------------------ README
    ws = wb.active
    ws.title = "README"
    ws["A1"].value, ws["A1"].font = "FirmPulse: firm-economics model (sample firm)", F_TITLE
    lines = [
        "What this is: a monthly model of an asset manager's own finances: assets -> fees -> revenue -> costs -> operating income.",
        "The firm in this workbook is a SAMPLE. The numbers say nothing about any real company.",
        "",
        "How to use it",
        "1. Change blue cells on 'Assumptions' and the market returns on 'Market'. Everything else recalculates.",
        "2. 'Budget' is the plan. 'Fcst_Base' is the latest best guess after real months are in.",
        "3. 'Variance' compares them and explains the gap with a bridge (returns, flows, cost rates).",
        "4. 'Scenarios' compares Base, Upside and Downside.",
        "5. The 'Step1' and 'Step2' sheets are working sheets for the bridge: they swap plan drivers for real ones one group at a time.",
        "",
        "Colour code: blue on yellow = input. black = formula. green = link from another sheet.",
        "Units: US$ millions unless stated.",
    ]
    for i, t in enumerate(lines, start=3):
        ws.cell(row=i, column=1, value=t).font = F_BOLD if t in ("How to use it",) else F_CALC
    ws.column_dimensions["A"].width = 130

    # ------------------------------------------------------------ Assumptions
    wa = wb.create_sheet("Assumptions")
    wa["A1"].value, wa["A1"].font = "Assumptions", F_TITLE
    _header(wa, 3, ["Input", "Value", "Note"])
    ref = {}                      # key -> absolute reference
    row = 4
    for group, items in INPUT_GROUPS:
        c = wa.cell(row=row, column=1, value=group)
        c.font, c.fill = F_BOLD, SUB_FILL
        wa.cell(row=row, column=2).fill = SUB_FILL
        wa.cell(row=row, column=3).fill = SUB_FILL
        row += 1
        for key, label, fmt, note in items:
            wa.cell(row=row, column=1, value=label).font = F_CALC
            _cell(wa, f"B{row}", getattr(a, key), F_INPUT, fmt, INPUT_FILL)
            wa.cell(row=row, column=3, value=note).font = Font(name="Calibri", size=10, italic=True, color="666666")
            ref[key] = f"Assumptions!$B${row}"
            row += 1
    # cash rate may be overridden by live data
    if cash_rate is not None:
        wa[ref["cash_rate"].split("!")[1].replace("$", "")].value = cash_rate

    row += 1
    wa.cell(row=row, column=1, value="Completed months (counted from the Market sheet)").font = F_CALC
    _cell(wa, f"B{row}", "=COUNT(Market!$C$5:$C$16)", F_LINK, "0")
    ref["n"] = f"Assumptions!$B${row}"
    row += 1
    wa.cell(row=row, column=1, value="Fiscal year").font = F_CALC
    _cell(wa, f"B{row}", a.fy, F_INPUT, "0", INPUT_FILL)
    row += 2

    wa.cell(row=row, column=1, value="Scenarios (apply to months that have not happened yet)").font = F_BOLD
    row += 1
    _header(wa, row, ["Scenario", "Return change (per year, added)", "Flow multiplier (x run-rate)", "One-off shock (first open month)"])
    wa.row_dimensions[row].height = 32
    scen_row = {}
    for key in ("base", "upside", "downside"):
        row += 1
        sc = SCENARIOS[key]
        wa.cell(row=row, column=1, value=sc.name).font = F_CALC
        _cell(wa, f"B{row}", sc.return_adj, F_INPUT, PCT, INPUT_FILL)
        _cell(wa, f"C{row}", sc.flow_mult, F_INPUT, "0.00", INPUT_FILL)
        _cell(wa, f"D{row}", sc.shock, F_INPUT, PCT, INPUT_FILL)
        scen_row[key] = row
    wa.column_dimensions["A"].width = 58
    wa.column_dimensions["B"].width = 20
    wa.column_dimensions["C"].width = 34
    wa.column_dimensions["D"].width = 30

    # ------------------------------------------------------------ Market
    wm = wb.create_sheet("Market")
    wm["A1"].value, wm["A1"].font = "Market returns (stock market, month-end to month-end)", F_TITLE
    wm["A2"].value = "Paste real monthly returns for finished months only. Leave future months blank."
    wm["A2"].font = Font(name="Calibri", size=10, italic=True, color="666666")
    _header(wm, 4, ["Month #", "Month", "Market return", "Status"])
    for i in range(12):
        r = 5 + i
        wm.cell(row=r, column=1, value=i + 1).font = F_CALC
        wm.cell(row=r, column=2, value=MONTHS[i]).font = F_CALC
        _cell(wm, f"C{r}", market_returns[i] if i < len(market_returns) else None, F_INPUT, PCT2, INPUT_FILL)
        _cell(wm, f"D{r}", f'=IF(A{r}<={ref["n"]},"Actual","Forecast")', F_CALC)
    for col, w in zip("ABCD", (10, 10, 16, 12)):
        wm.column_dimensions[col].width = w

    # ------------------------------------------------------------ Model sheets
    def model_sheet(name, title, desc, ret_basis, flow_basis, cost_basis, scen):
        ws = wb.create_sheet(name)
        ws["A1"].value, ws["A1"].font = title, F_TITLE
        ws["A2"].value = desc
        ws["A2"].font = Font(name="Calibri", size=10, italic=True, color="666666")
        sr = scen_row[scen] if scen else None
        adj = f"Assumptions!$B${sr}" if sr else None
        mult = f"Assumptions!$C${sr}" if sr else None
        shock = f"Assumptions!$D${sr}" if sr else None
        n = ref["n"]

        labels = {
            "month": "Month #", "name": "Month", "phase": "Phase", "mkt": "Stock market return",
            "ret": "Fund return (gross)", "flow": "Net new money ($m)", "hire": "Hires",
            "comp": "Base pay per head per year ($m)", "tech": "Tech + data per head per year ($m)",
            "begin": "Assets at start of month", "gross": "Assets after investment return",
            "mfee": "Management fee", "aumpre": "Assets before incentive fee",
            "idxpre": "Fund unit price before incentive fee", "crys": "Incentive fee settled this month? (1 = yes)",
            "hwm0": "High-water mark at start of month", "inc": "Incentive fee",
            "idxpost": "Fund unit price after incentive fee", "hwm1": "High-water mark at end of month",
            "flow2": "Net new money", "end": "Assets at end of month",
            "rev_m": "Management fees", "rev_i": "Incentive fees", "rev": "TOTAL REVENUE",
            "hc": "Headcount (end of month)", "base": "Base compensation", "bonus": "Bonus pool",
            "techc": "Technology and data", "occ": "Offices", "other": "Other costs",
            "opex": "TOTAL COSTS", "oi": "OPERATING INCOME", "margin": "Operating margin",
        }
        for k, lab in labels.items():
            c = ws.cell(row=R[k], column=1, value=lab)
            c.font = F_BOLD if k in ("rev", "opex", "oi", "end", "name", "month", "phase") else F_CALC
        ws.cell(row=13, column=1, value="FUND AND FEES").font = F_BOLD
        ws.cell(row=26, column=1, value="REVENUE AND COSTS").font = F_BOLD
        ws.cell(row=3, column=1, value="DRIVERS").font = F_BOLD
        for rr in (3, 13, 26):
            for cc in range(1, TOT_COL + 1):
                ws.cell(row=rr, column=cc).fill = SUB_FILL

        for ci in range(FIRST_COL, LAST_COL + 1):
            L = get_column_letter(ci)
            P = get_column_letter(ci - 1)
            first = ci == FIRST_COL
            m = ci - FIRST_COL + 1
            _cell(ws, f"{L}{R['month']}", m, F_CALC, "0", align="center")
            ws[f"{L}{R['month']}"].font = F_HEAD
            ws[f"{L}{R['month']}"].fill = HEAD_FILL
            _cell(ws, f"{L}{R['name']}", MONTHS[m - 1], F_HEAD, fill=HEAD_FILL, align="center")
            if scen is None:      # the Budget sheet is pure plan
                _cell(ws, f"{L}{R['phase']}", "Plan", F_CALC, align="center")
            else:
                _cell(ws, f"{L}{R['phase']}", f'=IF({L}${R["month"]}<={n},"Actual","Forecast")', F_LINK, align="center")

            # market return (only used by forecast sheets)
            if ret_basis == "forecast":
                _cell(ws, f"{L}{R['mkt']}", f"=INDEX(Market!$C$5:$C$16,{L}${R['month']})", F_LINK, PCT2)
            mr_b = f"((1+{ref['budget_return']})^(1/12)-1)"
            if ret_basis == "budget":
                f_ret = f"={mr_b}"
            else:
                f_ret = (f"=IF({L}${R['month']}<={n},"
                         f"{ref['alpha_monthly']}+{ref['beta']}*{L}{R['mkt']}+(1-{ref['beta']})*{ref['cash_rate']}/12,"
                         f"{mr_b}+{adj}/12+IF({L}${R['month']}={n}+1,{shock},0))")
            _cell(ws, f"{L}{R['ret']}", f_ret, F_LINK, PCT2)

            if flow_basis == "budget":
                f_flow = f"={ref['budget_flow']}"
            else:
                f_flow = f"=IF({L}${R['month']}<={n},{ref['actual_flow']},{ref['actual_flow']}*{mult})"
            _cell(ws, f"{L}{R['flow']}", f_flow, F_LINK, USD)

            kind = "budget" if cost_basis == "budget" else "actual"
            _cell(ws, f"{L}{R['hire']}", f"={ref[kind + '_hires']}", F_LINK, "0.00")
            _cell(ws, f"{L}{R['comp']}", f"={ref[kind + '_comp']}", F_LINK, "0.000")
            _cell(ws, f"{L}{R['tech']}", f"={ref[kind + '_tech']}", F_LINK, "0.000")

            # fund and fees
            _cell(ws, f"{L}{R['begin']}", f"={ref['start_aum']}" if first else f"={P}{R['end']}", F_LINK if first else F_CALC, USD)
            _cell(ws, f"{L}{R['gross']}", f"={L}{R['begin']}*(1+{L}{R['ret']})", F_CALC, USD)
            _cell(ws, f"{L}{R['mfee']}", f"={L}{R['gross']}*{ref['mgmt_fee']}/12", F_CALC, USD)
            _cell(ws, f"{L}{R['aumpre']}", f"={L}{R['gross']}-{L}{R['mfee']}", F_CALC, USD)
            prev_idx = ref["start_index"] if first else f"{P}{R['idxpost']}"
            _cell(ws, f"{L}{R['idxpre']}", f"={prev_idx}*(1+{L}{R['ret']})*(1-{ref['mgmt_fee']}/12)", F_CALC, NUM)
            _cell(ws, f"{L}{R['crys']}", f"=IF(MOD({L}${R['month']},{ref['crystallize_every']})=0,1,0)", F_CALC, "0", align="center")
            _cell(ws, f"{L}{R['hwm0']}", f"={ref['start_hwm']}" if first else f"={P}{R['hwm1']}", F_LINK if first else F_CALC, NUM)
            _cell(ws, f"{L}{R['inc']}",
                  f"=IF(AND({L}{R['crys']}=1,{L}{R['idxpre']}>{L}{R['hwm0']},{L}{R['aumpre']}>0),"
                  f"{ref['incentive_fee']}*({L}{R['idxpre']}-{L}{R['hwm0']})/{L}{R['idxpre']}*{L}{R['aumpre']},0)", F_CALC, USD)
            _cell(ws, f"{L}{R['idxpost']}",
                  f"=IF({L}{R['aumpre']}>0,{L}{R['idxpre']}*(1-{L}{R['inc']}/{L}{R['aumpre']}),{L}{R['idxpre']})", F_CALC, NUM)
            _cell(ws, f"{L}{R['hwm1']}", f"=IF({L}{R['crys']}=1,MAX({L}{R['hwm0']},{L}{R['idxpost']}),{L}{R['hwm0']})", F_CALC, NUM)
            _cell(ws, f"{L}{R['flow2']}", f"={L}{R['flow']}", F_CALC, USD)
            _cell(ws, f"{L}{R['end']}", f"={L}{R['aumpre']}-{L}{R['inc']}+{L}{R['flow2']}", F_CALC, USD, bold=True)

            # revenue and costs
            _cell(ws, f"{L}{R['rev_m']}", f"={L}{R['mfee']}", F_CALC, USD)
            _cell(ws, f"{L}{R['rev_i']}", f"={L}{R['inc']}", F_CALC, USD)
            _cell(ws, f"{L}{R['rev']}", f"={L}{R['rev_m']}+{L}{R['rev_i']}", F_CALC, USD, bold=True)
            _cell(ws, f"{L}{R['hc']}", f"={ref['start_headcount']}+{L}{R['hire']}" if first else f"={P}{R['hc']}+{L}{R['hire']}", F_CALC, "#,##0.0")
            _cell(ws, f"{L}{R['base']}", f"={L}{R['hc']}*{L}{R['comp']}/12", F_CALC, USD)
            _cell(ws, f"{L}{R['bonus']}", f"={ref['bonus_pct']}*{L}{R['rev']}", F_CALC, USD)
            _cell(ws, f"{L}{R['techc']}", f"={L}{R['hc']}*{L}{R['tech']}/12", F_CALC, USD)
            _cell(ws, f"{L}{R['occ']}", f"={ref['occupancy']}/12", F_CALC, USD)
            _cell(ws, f"{L}{R['other']}", f"={ref['other_pct']}*{L}{R['rev']}", F_CALC, USD)
            _cell(ws, f"{L}{R['opex']}", f"=SUM({L}{R['base']}:{L}{R['other']})", F_CALC, USD, bold=True)
            _cell(ws, f"{L}{R['oi']}", f"={L}{R['rev']}-{L}{R['opex']}", F_CALC, USD, bold=True)
            _cell(ws, f"{L}{R['margin']}", f"=IF({L}{R['rev']}>0,{L}{R['oi']}/{L}{R['rev']},0)", F_CALC, PCT)

        # full-year column
        T = get_column_letter(TOT_COL)
        _cell(ws, f"{T}{R['month']}", "FY", F_HEAD, fill=HEAD_FILL, align="center")
        first_l, last_l = get_column_letter(FIRST_COL), get_column_letter(LAST_COL)
        for k in ("flow", "hire", "mfee", "inc", "flow2", "rev_m", "rev_i", "rev",
                  "base", "bonus", "techc", "occ", "other", "opex", "oi"):
            fmt = "0.00" if k == "hire" else USD
            _cell(ws, f"{T}{R[k]}", f"=SUM({first_l}{R[k]}:{last_l}{R[k]})", F_CALC, fmt, bold=True)
        _cell(ws, f"{T}{R['end']}", f"={last_l}{R['end']}", F_CALC, USD, bold=True)
        _cell(ws, f"{T}{R['hc']}", f"={last_l}{R['hc']}", F_CALC, "#,##0.0", bold=True)
        _cell(ws, f"{T}{R['hwm1']}", f"={last_l}{R['hwm1']}", F_CALC, NUM, bold=True)
        _cell(ws, f"{T}{R['margin']}", f"=IF({T}{R['rev']}>0,{T}{R['oi']}/{T}{R['rev']},0)", F_CALC, PCT, bold=True)

        ws.column_dimensions["A"].width = 44
        ws.column_dimensions["B"].width = 2
        for ci in range(FIRST_COL, TOT_COL + 1):
            ws.column_dimensions[get_column_letter(ci)].width = 11
        ws.freeze_panes = "C7"
        for cc in range(1, TOT_COL + 1):
            top = ws.cell(row=R["oi"], column=cc)
            top.border = Border(top=THIN)
        return ws

    model_sheet("Budget", "Budget (the plan)", "Plan drivers only: planned return, planned flows, planned hiring and cost rates.",
                "budget", "budget", "budget", None)
    model_sheet("Step1_Returns", "Bridge step 1: real returns, plan for everything else",
                "Working sheet: only returns are swapped from plan to actual/forecast.", "forecast", "budget", "budget", "base")
    model_sheet("Step2_Flows", "Bridge step 2: + real money in/out",
                "Working sheet: returns and flows swapped; hiring and cost rates still plan.", "forecast", "forecast", "budget", "base")
    model_sheet("Fcst_Base", "Forecast: Base case", "Real months in, plan returns for the rest, run-rate flows, actual hiring and cost rates.",
                "forecast", "forecast", "actual", "base")
    model_sheet("Fcst_Upside", "Forecast: Upside case", "Same as Base, but the rest of the year goes better.",
                "forecast", "forecast", "actual", "upside")
    model_sheet("Fcst_Downside", "Forecast: Downside case", "Same as Base, but a market shock hits, then money leaves.",
                "forecast", "forecast", "actual", "downside")

    T = get_column_letter(TOT_COL)

    # ------------------------------------------------------------ Variance
    wv = wb.create_sheet("Variance")
    wv["A1"].value, wv["A1"].font = "Variance: Budget vs Base forecast", F_TITLE
    _header(wv, 3, ["Line ($m)", "Budget", "Forecast", "Variance ($m)", "Variance (%)", "Good or bad?"])
    lines = [("Management fees", "rev_m", "rev"), ("Incentive fees", "rev_i", "rev"), ("Total revenue", "rev", "rev"),
             ("Base compensation", "base", "cost"), ("Bonus pool", "bonus", "cost"), ("Technology and data", "techc", "cost"),
             ("Offices", "occ", "cost"), ("Other costs", "other", "cost"), ("Total costs", "opex", "cost"),
             ("Operating income", "oi", "rev"), ("Ending assets", "end", "rev")]
    r = 4
    for label, key, kind in lines:
        bold = key in ("rev", "opex", "oi")
        wv.cell(row=r, column=1, value=label).font = F_BOLD if bold else F_CALC
        _cell(wv, f"B{r}", f"=Budget!{T}{R[key]}", F_LINK, USD, bold=bold)
        _cell(wv, f"C{r}", f"=Fcst_Base!{T}{R[key]}", F_LINK, USD, bold=bold)
        _cell(wv, f"D{r}", f"=C{r}-B{r}", F_CALC, USD, bold=bold)
        _cell(wv, f"E{r}", f"=IF(B{r}=0,0,D{r}/ABS(B{r}))", F_CALC, PCT)
        good = f'=IF(D{r}>=0,"Good","Bad")' if kind == "rev" else f'=IF(D{r}<=0,"Good","Bad")'
        _cell(wv, f"F{r}", good, F_CALC, align="center")
        r += 1
    wv.cell(row=r, column=1, value="Operating margin").font = F_CALC
    _cell(wv, f"B{r}", f"=Budget!{T}{R['margin']}", F_LINK, PCT)
    _cell(wv, f"C{r}", f"=Fcst_Base!{T}{R['margin']}", F_LINK, PCT)
    _cell(wv, f"D{r}", f"=C{r}-B{r}", F_CALC, PCT)
    _cell(wv, f"F{r}", f'=IF(D{r}>=0,"Good","Bad")', F_CALC, align="center")
    var_last = r

    r += 2
    wv.cell(row=r, column=1, value="Why did operating income move? (bridge)").font = F_BOLD
    r += 1
    bridge_start = r
    wv.cell(row=r, column=1, value="Budget operating income").font = F_CALC
    _cell(wv, f"B{r}", f"=Budget!{T}{R['oi']}", F_LINK, USD)
    r += 1
    for label, a_sheet, b_sheet in (("Market and returns", "Step1_Returns", "Budget"),
                                    ("Net flows (money in and out)", "Step2_Flows", "Step1_Returns"),
                                    ("Hiring and cost rates", "Fcst_Base", "Step2_Flows")):
        wv.cell(row=r, column=1, value=label).font = F_CALC
        _cell(wv, f"B{r}", f"={a_sheet}!{T}{R['oi']}-{b_sheet}!{T}{R['oi']}", F_LINK, USD)
        r += 1
    wv.cell(row=r, column=1, value="Forecast operating income").font = F_BOLD
    _cell(wv, f"B{r}", f"=Fcst_Base!{T}{R['oi']}", F_LINK, USD, bold=True)
    r += 1
    wv.cell(row=r, column=1, value="Check (should be 0)").font = Font(name="Calibri", size=10, italic=True, color="666666")
    _cell(wv, f"B{r}", f"=SUM(B{bridge_start}:B{r - 2})-B{r - 1}", F_CALC, '0.0000')
    wv.column_dimensions["A"].width = 38
    for col in "BCDEF":
        wv.column_dimensions[col].width = 16
    BRIDGE = {"budget": bridge_start, "returns": bridge_start + 1, "flows": bridge_start + 2,
              "costs": bridge_start + 3, "forecast": bridge_start + 4}

    # ------------------------------------------------------------ Scenarios
    wsn = wb.create_sheet("Scenarios")
    wsn["A1"].value, wsn["A1"].font = "Scenarios: what if the rest of the year goes differently?", F_TITLE
    _header(wsn, 3, ["$m", "Budget", "Base", "Upside", "Downside"])
    sc_lines = [("Ending assets", "end"), ("Total revenue", "rev"), ("Incentive fees", "rev_i"),
                ("Total costs", "opex"), ("Operating income", "oi"), ("Operating margin", "margin")]
    r = 4
    for label, key in sc_lines:
        wsn.cell(row=r, column=1, value=label).font = F_BOLD if key == "oi" else F_CALC
        fmt = PCT if key == "margin" else USD
        for col, sheet in zip("BCDE", ("Budget", "Fcst_Base", "Fcst_Upside", "Fcst_Downside")):
            _cell(wsn, f"{col}{r}", f"={sheet}!{T}{R[key]}", F_LINK, fmt, bold=(key == "oi"))
        r += 1
    wsn.cell(row=r, column=1, value="Operating income vs budget").font = F_CALC
    for col in "CDE":
        _cell(wsn, f"{col}{r}", f"={col}8-$B$8", F_CALC, USD)
    wsn.column_dimensions["A"].width = 30
    for col in "BCDE":
        wsn.column_dimensions[col].width = 16

    order = ["README", "Assumptions", "Market", "Variance", "Scenarios", "Budget", "Step1_Returns",
             "Step2_Flows", "Fcst_Base", "Fcst_Upside", "Fcst_Downside"]
    wb._sheets = [wb[name] for name in order]
    wb.active = 0
    wb.calculation.fullCalcOnLoad = True
    wb._firmpulse_refs = {"bridge": BRIDGE, "var_last": var_last}   # used by tests
    return wb


def workbook_bytes(a: Assumptions, market_returns=None, cash_rate=None) -> bytes:
    buf = io.BytesIO()
    build_workbook(a, market_returns, cash_rate).save(buf)
    return buf.getvalue()
