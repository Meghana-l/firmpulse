# FirmPulse

**A live model of how an alternative asset manager makes and spends money, built the way a hedge fund's
finance team would plan and report on its own firm.**

A firm like D. E. Shaw earns money by managing other people's capital and spends it on researchers, engineers,
data and offices. The people who plan that business need one answer, every month: *how is the year going
against plan, why, and what happens if markets or investor flows change?* FirmPulse answers that, and keeps
the answer current by feeding real market data into the model.

> The firm inside the model is a **sample** firm. It is not D. E. Shaw and says nothing about any real
> company's economics. Not investment advice, not affiliated with any firm.

## How a hedge fund makes money (the part the model captures)

- **Management fee.** A small yearly percentage of assets under management (AUM), earned whatever the
  performance.
- **Incentive (performance) fee.** A share of profits, but only profits above the fund's **high-water mark**
  (its previous peak). After a loss, the fund must win it back before earning this fee again, so this income
  is lumpy and can drop to zero.
- **Costs.** People (the biggest cost), bonus pool tied to revenue, technology and data, offices, other.
- **Operating income.** Revenue minus costs: what the firm itself keeps.

Two things move all of this and the firm only partly controls them: **market returns** and **investor money
flowing in or out**.

## What the model does

| Finance task | What FirmPulse produces |
|---|---|
| **Budget** | The plan for the year: planned return, flows, hiring, pay, tech spend. |
| **Forecast** | Months already finished use real market returns; months still to come use the plan. |
| **Scenarios** | Base, Upside and Downside runs side by side (a shock in the downside). |
| **Variance** | Forecast minus budget, then explained: how much came from market returns, how much from investor flows, how much from hiring and cost rates. |
| **Reporting** | A written commentary on the variance, an Excel workbook, and a monthly markdown report. |

### How the numbers are calculated

Monthly, for twelve months:

```
fund return      = alpha + beta x stock-market return + (1 - beta) x cash rate     (finished months, real data)
                 = planned return, plus scenario change                            (future months)
management fee   = assets x fee / 12
incentive fee    = share of the gain above the high-water mark, settled every 3 months
end assets       = assets after return - fees + net money in/out
revenue          = management fee + incentive fee
costs            = headcount x pay + bonus pool + tech and data + offices + other
operating income = revenue - costs
```

**The variance bridge** swaps plan assumptions for actual ones one group at a time (returns, then flows, then
hiring and cost rates) and records the change in operating income at each step. The steps add up exactly to
the total gap, and the Excel workbook carries a check cell that proves it.

## Data

| Source | Used for |
|---|---|
| FRED (St. Louis Fed) | S&P 500, VIX, 3-month T-bill and 10-year yield. Real returns for completed months. |
| Finnhub (optional) | Latest SPY quote. |
| SEC EDGAR | D. E. Shaw's public 13F filings (see below). |
| Claude (optional) | Plain-English variance commentary built only from the model's numbers. |

When no live key is configured, the app uses a built-in **sample** dataset and shows a **SAMPLE** badge. With
keys it shows **LIVE**.

### The 13F tab: a public window into D. E. Shaw

Every large US manager must file a **Form 13F** each quarter listing the US-listed stocks and options it held on
the last day of the quarter. FirmPulse reads D. E. Shaw's latest two filings, combines the lines by security,
and shows the biggest positions, the biggest changes since the previous quarter, and how concentrated the
portfolio is. It is a partial and delayed view (US-listed long equity and options only, filed up to 45 days after
quarter-end), and the app says so on the page.

## What is in the project

```
api/                  Serverless routes: market, model, commentary, holdings, export
lib/engine.py         The model: AUM -> fees (high-water mark) -> revenue -> costs -> operating income
lib/market.py         FRED and Finnhub data, with a sample fallback
lib/sec13f.py         13F download and parsing from SEC EDGAR
lib/commentary.py     Variance commentary
lib/xlsx_builder.py   Excel workbook where every number is a live formula
public/               The web app (one HTML file) and a starter Excel workbook
scripts/              Monthly variance report, Excel builder
tests/                32 tests, including "Excel gives the same answers as the Python model"
```

## Quality checks

- Fee and high-water-mark logic, the assets identity (end = start + gains - fees + flows, to the cent), and the
  bridge adding up exactly are all tested.
- The Excel workbook is recalculated independently and matches the Python model to 1e-9 across four test
  cases and all scenario sheets.
- Inputs from the browser are clamped to sane ranges; API keys and the SEC contact line stay on the server and
  never appear in a response.
- Live calls to FRED, SEC, Finnhub and Claude are tested against mock responses. Run them with real keys to
  see live data.

## Limits

The firm is a sample, market data is end-of-day, the fund is a single simplified fund, and 13F covers only part
of what a firm like D. E. Shaw holds. Natural next steps: multiple funds, actuals from a ledger instead of
run-rate inputs, approval-controlled assumption changes with an audit trail, and linking headcount to a
people-analytics dataset.
