# The Rules — verdict logic for the daily system

**Every rule here was paid for.** Each one traces to a specific mistake in
`LESSONS.md`, `AUDIT-2026-08-10.md` or `DECISION-LOG.md`. Don't soften one
without writing down what changed.

---

## 0. The money assumption

**$20 arrives each trading day.** ~$100/week, ~$430/month.

| Constraint | Source |
|---|---|
| Fractional minimum is **$1.00** | Settled 2026-08-06, got it wrong twice first |
| Dollar-amount orders are **market-only, regular hours** | Same |
| Limit orders are **whole shares only** | Aaron's screenshot, 2026-08-06 |
| Cash account — proceeds settle **T+1** | Sells don't fund same-day buys |

**$20 ÷ 22 positions = $0.91 each — below the minimum.** The system therefore
*cannot* spread the daily money. It must concentrate.

> **Deployment rule: the daily $20 goes to at most 3 tickers, minimum $5 each.**

---

## 1. Verdicts

Exactly one per holding, every run. Default is HOLD.

### SELL — any single trigger fires

| # | Trigger | Paid for by |
|---|---|---|
| S1 | Revenue down 2+ consecutive quarters with no disclosed cause | ERII (−57%) |
| S2 | Guidance withdrawn, or suspended and not reinstated | ERII |
| S3 | CEO is interim, or departed with no named permanent successor | ERII |
| S4 | The specific reason we bought it is factually gone | ERII |
| S5 | We discover it isn't the business we thought it was | HUBB, GOLD≠B |

### TRIM — reduce, do not exit

| # | Trigger |
|---|---|
| T1 | One ticker exceeds **12%** of account value |
| T2 | One sleeve exceeds **40%** of account value |

### BUY — needs money *and* a bench slot

Ranked by, in order:
1. Passes all 9 gates (§2)
2. Lowest correlation to the two large sleeves
3. Furthest below its target weight

### HOLD — everything else

> **Cost basis is never a reason to hold.** The only question is:
> *would I buy this position, at today's price, today?*
> If no — it's a SELL or TRIM, regardless of what we paid.

---

## 2. The 9 gates — a scout must pass ALL of them

**Default is REJECT.** A candidate that can't clear a gate does not go on the
bench; it goes to the rejected list *with the gate number that killed it*.

| # | Gate | Killed |
|---|---|---|
| G1 | Ticker resolves to the company we mean | GOLD ≠ Barrick |
| G2 | `description` read; the business is what we think | ERII, HUBB, NUAI, WTTR |
| G3 | **P/E and P/B pulled together** — neither alone | 7 positions above 13× book |
| G4 | Employee count sane for the market cap | NNE: 62 people, $1.07B |
| G5 | Profitable — or a **written** exception naming the risk | TLN (P/E −79.74) |
| G6 | **Permanent CEO** — the data will *not* catch interim; verify externally | ERII |
| G7 | Revenue trend visible in `get_financials` | ASPN, UEC — no data = no buy |
| G8 | Correlation at 28 / 63 / 250 sessions **+ rolling 63** | PEG −0.50 → +0.08 |
| G9 | No earnings inside 5 sessions — unless the buy *is* the earnings bet | ERII |

### G8 in detail — the correlation rule

A correlation is **a measurement, not a property.** Always record window,
return frequency and as-of date. Nested windows (28/63/250) are *not*
independent observations — the rolling-window pass rate is the real test.

> Report: `% of 188 rolling 63-session windows above 0.30`.
> Above ~70% = correlated, kill it. Below ~30% = genuinely separate.

---

## 3. The two sleeves

Measured 2026-08-10 over 250 sessions through 2026-08-07:

| Sleeve | Members | Weight |
|---|---|---|
| **Defense / gov** | LDOS, BAH, PLTR, CACI, SAIC | **37.1%** |
| **NE power** | TLN, VST, PPL, CEG, GEV | 19.7% |

**Cross-sleeve correlation: −0.009 value-weighted, +0.039 equal-weighted.**
188 rolling 63-session windows all fell between −0.255 and +0.285, median +0.066.

This supports diversification *between their traded risks*. It does **not**
prove causal independence and does **not** predict future correlation.

---

## 4. Scouting cadence

**One new ticker per day. Rejection is the expected outcome.**

If nothing clears all 9 gates, the log records the rejection and the day's $20
goes to the existing bench or stays cash. A day with no new name is a normal
day, not a failed one — the killed list is the strongest evidence in this
notebook.

---

## 5. What the system may NOT do

- **It never places, cancels or modifies an order.** It produces a chart; Aaron
  presses the button.
- It never records a claim it did not verify. Unverified goes in the
  **UNVERIFIED** block, by name.
- It never writes a conclusion from one observation into a shared file.
