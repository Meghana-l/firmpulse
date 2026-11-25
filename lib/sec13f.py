"""
D. E. Shaw's PUBLIC 13F filings (SEC EDGAR).

What a 13F is: every large US investment manager must file a quarterly report listing the
US-listed stocks (and options on them) it held at quarter-end. It is public, free, and
arrives up to ~45 days after the quarter ends.

What it is NOT: the firm's whole portfolio. It leaves out non-US securities, bonds, most
derivatives, private investments, and short positions. Read it as a partial, delayed lens.

SEC rules: send a real User-Agent with a contact email (set SEC_USER_AGENT) and stay
under 10 requests/second. We make about 6 requests per refresh.
"""
from __future__ import annotations

import json
import os
import urllib.request
import xml.etree.ElementTree as ET
from concurrent.futures import ThreadPoolExecutor
from typing import Callable, Dict, List, Optional

DESHAW_CIK = "0001009207"   # filer shown on the 13F-HR filings for D. E. Shaw & Co., Inc.


def _ua(env) -> str:
    return env.get("SEC_USER_AGENT", "").strip() or "FirmPulse-demo set-SEC_USER_AGENT@example.com"


def sec_get(url: str, ua: str, timeout: int = 15) -> bytes:
    req = urllib.request.Request(url, headers={"User-Agent": ua, "Accept-Encoding": "identity"})
    with urllib.request.urlopen(req, timeout=timeout) as resp:
        return resp.read()


def _local(tag: str) -> str:
    return tag.rsplit("}", 1)[-1]


def parse_infotable(xml_bytes: bytes, value_in_thousands: bool = False) -> List[dict]:
    """Parse a 13F information table into plain dicts."""
    mult = 1000.0 if value_in_thousands else 1.0
    out = []
    root = ET.fromstring(xml_bytes)
    for node in root.iter():
        if _local(node.tag) != "infoTable":
            continue
        rec = {"issuer": "", "cusip": "", "value": 0.0, "shares": 0.0, "put_call": "", "class": ""}
        for ch in node.iter():
            name = _local(ch.tag)
            text = (ch.text or "").strip()
            if name == "nameOfIssuer":
                rec["issuer"] = text
            elif name == "cusip":
                rec["cusip"] = text
            elif name == "titleOfClass":
                rec["class"] = text
            elif name == "value":
                try:
                    rec["value"] = float(text) * mult
                except ValueError:
                    pass
            elif name == "sshPrnamt":
                try:
                    rec["shares"] = float(text)
                except ValueError:
                    pass
            elif name == "putCall":
                rec["put_call"] = text
        out.append(rec)
    return out


def summarize(positions: List[dict], top_n: int = 15) -> dict:
    """Equity (non-option) lines combined by CUSIP. Option lines counted separately."""
    equities: Dict[str, dict] = {}
    option_lines, option_value = 0, 0.0
    for p in positions:
        if p["put_call"]:
            option_lines += 1
            option_value += p["value"]
            continue
        cur = equities.setdefault(p["cusip"], {"issuer": p["issuer"], "cusip": p["cusip"],
                                               "value": 0.0, "shares": 0.0})
        cur["value"] += p["value"]
        cur["shares"] += p["shares"]
    ranked = sorted(equities.values(), key=lambda x: x["value"], reverse=True)
    total = sum(x["value"] for x in ranked)
    top10 = sum(x["value"] for x in ranked[:10])
    return {
        "total_equity_value": total,
        "n_equity_positions": len(ranked),
        "top10_share": (top10 / total) if total else 0.0,
        "option_lines": option_lines,
        "option_value_notional_reported": option_value,
        "top": [{**x, "weight": (x["value"] / total) if total else 0.0} for x in ranked[:top_n]],
        "_by_cusip": equities,
    }


def movers(latest: dict, prior: dict, n: int = 8) -> dict:
    """Biggest changes in reported value between two quarters (equities only)."""
    a, b = latest["_by_cusip"], prior["_by_cusip"]
    deltas = []
    for cusip in set(a) | set(b):
        va = a.get(cusip, {}).get("value", 0.0)
        vb = b.get(cusip, {}).get("value", 0.0)
        name = (a.get(cusip) or b.get(cusip))["issuer"]
        deltas.append({"issuer": name, "cusip": cusip, "latest": va, "prior": vb, "change": va - vb})
    deltas.sort(key=lambda x: x["change"])
    return {"largest_increases": list(reversed(deltas[-n:])), "largest_decreases": deltas[:n]}


def list_13f_filings(submissions: dict, limit: int = 2) -> List[dict]:
    recent = submissions.get("filings", {}).get("recent", {})
    forms = recent.get("form", [])
    out = []
    for i, form in enumerate(forms):
        if form == "13F-HR":
            out.append({"accession": recent["accessionNumber"][i],
                        "report_date": recent["reportDate"][i],
                        "filing_date": recent["filingDate"][i]})
        if len(out) == limit:
            break
    return out


def pick_infotable_name(index_json: dict) -> Optional[str]:
    names = [it.get("name", "") for it in index_json.get("directory", {}).get("item", [])]
    for n in names:
        if "infotable" in n.lower() and n.lower().endswith(".xml"):
            return n
    for n in names:
        if n.lower().endswith(".xml") and "primary_doc" not in n.lower():
            return n
    return None


def get_13f(env: Optional[dict] = None, getter: Callable[[str, str], bytes] = sec_get) -> dict:
    env = os.environ if env is None else env
    ua = _ua(env)
    cik_int = str(int(DESHAW_CIK))
    try:
        subs = json.loads(getter(f"https://data.sec.gov/submissions/CIK{DESHAW_CIK}.json", ua))
        filings = list_13f_filings(subs, 2)
        if not filings:
            return {"ok": False, "error": "No 13F-HR filings found."}

        def load(f: dict) -> dict:
            acc = f["accession"].replace("-", "")
            base = f"https://www.sec.gov/Archives/edgar/data/{cik_int}/{acc}"
            idx = json.loads(getter(base + "/index.json", ua))
            name = pick_infotable_name(idx)
            if not name:
                raise ValueError("information table not found")
            xml = getter(f"{base}/{name}", ua)
            # SEC switched 13F values from thousands to whole dollars for periods after Jan 2023.
            in_thousands = f["filing_date"] < "2023-01-03"
            return summarize(parse_infotable(xml, value_in_thousands=in_thousands))

        with ThreadPoolExecutor(max_workers=2) as pool:
            summaries = list(pool.map(load, filings))
    except Exception as exc:
        return {"ok": False, "error": f"Could not reach SEC EDGAR right now ({type(exc).__name__})."}

    latest = summaries[0]
    result = {
        "ok": True,
        "filer": "D. E. Shaw & Co., Inc.",
        "latest": {"report_date": filings[0]["report_date"], "filing_date": filings[0]["filing_date"],
                   **{k: v for k, v in latest.items() if not k.startswith("_")}},
        "prior": None,
        "movers": None,
        "caveat": ("13F lists only US-listed equities and options reported at quarter-end, up to 45 days "
                   "late. It is a partial lens on a firm whose strategies span many other assets."),
    }
    if len(summaries) == 2:
        prior = summaries[1]
        result["prior"] = {"report_date": filings[1]["report_date"],
                           "total_equity_value": prior["total_equity_value"],
                           "n_equity_positions": prior["n_equity_positions"]}
        result["movers"] = movers(latest, prior)
    return result
