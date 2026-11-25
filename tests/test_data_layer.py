import datetime as dt
import json
import os
import sys

sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))

from lib import market, sec13f, commentary
from lib.engine import Assumptions, build_outlook


# ---------- market ----------
def fake_fred_obs():
    # Dec 31 2025 = 100, then month-end closes; includes a holiday '.' and mid-month noise
    pts = [("2025-12-30", "99"), ("2025-12-31", "100"), ("2026-01-15", "101"), ("2026-01-30", "102"),
           ("2026-02-16", "."), ("2026-02-27", "99.96"), ("2026-03-31", "102.0"), ("2026-04-30", "103.0")]
    return [{"date": d, "value": v} for d, v in pts]


def test_monthly_returns_month_end_to_month_end():
    r = market.monthly_returns_for_year(fake_fred_obs(), 2026, dt.date(2026, 4, 10))
    assert len(r) == 3                       # Jan, Feb, Mar are complete; April is not
    assert abs(r[0] - 0.02) < 1e-9           # 102/100 - 1
    assert abs(r[1] - (99.96 / 102 - 1)) < 1e-9
    assert abs(r[2] - (102.0 / 99.96 - 1)) < 1e-9


def test_returns_stop_at_gap():
    obs = [o for o in fake_fred_obs() if not o["date"].startswith("2026-02")]
    r = market.monthly_returns_for_year(obs, 2026, dt.date(2026, 4, 10))
    assert len(r) == 1


def test_no_key_gives_labelled_sample():
    out = market.get_market(env={}, today=dt.date(2026, 5, 3))
    assert out["source"] == "sample" and out["completed_months"] == 4
    assert "SAMPLE" in out["note"]


def test_live_path_with_fake_fetcher_and_key_not_leaked():
    calls = []

    def fake(url, headers=None, timeout=8):
        calls.append(url)
        if "series_id=SP500" in url:
            return {"observations": fake_fred_obs()}
        if "VIXCLS" in url:
            return {"observations": [{"date": "2026-04-29", "value": "16.2"}]}
        if "DTB3" in url:
            return {"observations": [{"date": "2026-04-29", "value": "3.9"}]}
        if "DGS10" in url:
            return {"observations": [{"date": "2026-04-29", "value": "4.4"}]}
        if "finnhub" in url:
            return {"c": 600.5, "dp": 0.4, "t": 1700000000}
        raise AssertionError(url)

    out = market.get_market(env={"FRED_API_KEY": "SECRETKEY", "FINNHUB_API_KEY": "FH"},
                            today=dt.date(2026, 4, 10), fetch=fake)
    assert out["source"] == "live" and out["completed_months"] == 3
    assert abs(out["cash_rate"] - 0.039) < 1e-9 and out["vix"] == 16.2
    assert out["quote"]["price"] == 600.5
    assert "SECRETKEY" not in json.dumps(out)


def test_live_failure_falls_back_without_leaking_key():
    def boom(url, headers=None, timeout=8):
        raise RuntimeError("https://api.stlouisfed.org/?api_key=SECRETKEY exploded")

    out = market.get_market(env={"FRED_API_KEY": "SECRETKEY"}, today=dt.date(2026, 4, 10), fetch=boom)
    assert out["source"] == "sample"
    assert "SECRETKEY" not in json.dumps(out)


def test_january_has_zero_completed_months():
    out = market.get_market(env={}, today=dt.date(2026, 1, 20))
    assert out["completed_months"] == 0 and out["monthly_market_returns"] == []


# ---------- 13F ----------
# FAKE fixture: invented names and numbers, only to test the parser.
FIXTURE_XML = b"""<?xml version="1.0"?>
<informationTable xmlns="http://www.sec.gov/edgar/document/thirteenf/informationtable">
  <infoTable><nameOfIssuer>ALPHA CORP</nameOfIssuer><titleOfClass>COM</titleOfClass><cusip>111111111</cusip>
    <value>6000</value><shrsOrPrnAmt><sshPrnamt>60</sshPrnamt><sshPrnamtType>SH</sshPrnamtType></shrsOrPrnAmt>
    <investmentDiscretion>DFND</investmentDiscretion></infoTable>
  <infoTable><nameOfIssuer>ALPHA CORP</nameOfIssuer><titleOfClass>COM</titleOfClass><cusip>111111111</cusip>
    <value>4000</value><shrsOrPrnAmt><sshPrnamt>40</sshPrnamt><sshPrnamtType>SH</sshPrnamtType></shrsOrPrnAmt></infoTable>
  <infoTable><nameOfIssuer>BETA INC</nameOfIssuer><titleOfClass>COM</titleOfClass><cusip>222222222</cusip>
    <value>3000</value><shrsOrPrnAmt><sshPrnamt>30</sshPrnamt><sshPrnamtType>SH</sshPrnamtType></shrsOrPrnAmt></infoTable>
  <infoTable><nameOfIssuer>BETA INC</nameOfIssuer><titleOfClass>COM</titleOfClass><cusip>222222222</cusip>
    <value>99999</value><shrsOrPrnAmt><sshPrnamt>9</sshPrnamt><sshPrnamtType>SH</sshPrnamtType></shrsOrPrnAmt>
    <putCall>Call</putCall></infoTable>
</informationTable>"""

FIXTURE_PRIOR = FIXTURE_XML.replace(b"<value>6000</value>", b"<value>1000</value>")


def test_parse_and_summarize_combines_lines_and_separates_options():
    s = sec13f.summarize(sec13f.parse_infotable(FIXTURE_XML))
    assert s["n_equity_positions"] == 2
    assert s["total_equity_value"] == 13000          # 6000+4000+3000, options excluded
    assert s["top"][0]["issuer"] == "ALPHA CORP" and s["top"][0]["value"] == 10000
    assert s["option_lines"] == 1
    assert abs(s["top10_share"] - 1.0) < 1e-9


def test_thousands_multiplier():
    rows = sec13f.parse_infotable(FIXTURE_XML, value_in_thousands=True)
    assert rows[0]["value"] == 6_000_000


def test_movers():
    a = sec13f.summarize(sec13f.parse_infotable(FIXTURE_XML))
    b = sec13f.summarize(sec13f.parse_infotable(FIXTURE_PRIOR))
    m = sec13f.movers(a, b)
    assert m["largest_increases"][0]["issuer"] == "ALPHA CORP"
    assert m["largest_increases"][0]["change"] == 5000


def test_get_13f_end_to_end_with_fake_sec():
    subs = {"filings": {"recent": {
        "form": ["8-K", "13F-HR", "13F-HR"],
        "accessionNumber": ["0000000000-26-000001", "0000000000-26-000002", "0000000000-26-000003"],
        "reportDate": ["", "2026-09-30", "2026-06-30"],
        "filingDate": ["2026-11-01", "2026-11-14", "2026-08-14"]}}}

    def fake(url, ua):
        assert "FirmPulse" in ua or "me@example.com" in ua
        if url.endswith("CIK0001009207.json"):
            return json.dumps(subs).encode()
        if url.endswith("index.json"):
            return json.dumps({"directory": {"item": [{"name": "primary_doc.xml"}, {"name": "infotable.xml"}]}}).encode()
        if "000000000026000002" in url:
            return FIXTURE_XML
        return FIXTURE_PRIOR

    out = sec13f.get_13f(env={"SEC_USER_AGENT": "me@example.com"}, getter=fake)
    assert out["ok"] and out["latest"]["report_date"] == "2026-09-30"
    assert out["movers"]["largest_increases"][0]["change"] == 5000
    assert "partial" in out["caveat"]


def test_get_13f_failure_is_graceful():
    def boom(url, ua):
        raise OSError("blocked")
    out = sec13f.get_13f(env={}, getter=boom)
    assert out["ok"] is False and "SEC EDGAR" in out["error"]


# ---------- commentary ----------
def test_template_commentary_mentions_numbers_and_illustrative():
    o = build_outlook(Assumptions(), [0.012, -0.018, 0.021, 0.008, 0.015])
    t = commentary.template_commentary(o)
    assert "operating income" in t and "sample" in t


def test_claude_path_uses_server_built_prompt_only():
    o = build_outlook(Assumptions(), [0.01, 0.02])
    seen = {}

    def fake_post(url, headers, payload, timeout=20):
        seen.update(url=url, headers=headers, payload=payload)
        return {"content": [{"type": "text", "text": "Short note."}]}

    out = commentary.get_commentary(o, env={"ANTHROPIC_API_KEY": "k"}, post=fake_post)
    assert out["source"] == "claude" and out["text"] == "Short note."
    assert "budget_op_income" in seen["payload"]["messages"][0]["content"]


def test_claude_failure_falls_back_to_template():
    o = build_outlook(Assumptions(), [0.01])

    def boom(*a, **k):
        raise OSError("down")

    out = commentary.get_commentary(o, env={"ANTHROPIC_API_KEY": "k"}, post=boom)
    assert out["source"] == "template"


def test_sec_contact_line_never_reaches_the_response():
    secret = "Private Name private.person@example.org"
    seen = []

    def boom(url, ua, timeout=15):
        seen.append(ua)
        raise OSError("down")

    out = sec13f.get_13f(env={"SEC_USER_AGENT": secret}, getter=boom)
    assert seen == [secret]                      # sent to the SEC only
    assert secret not in str(out) and "private.person" not in str(out)
