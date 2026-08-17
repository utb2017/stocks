# stocks

A live decision record for a small, real brokerage account run as a learning
instrument. It produces **recommendations only** — nothing here places, cancels,
or modifies an order.

Started 2026-08-04 with $2.25.

---

## Read these first

| File | What it is |
|---|---|
| **[RULES.md](RULES.md)** | Verdict logic and the nine gates a name must clear |
| **[PORTFOLIO.md](PORTFOLIO.md)** | Every holding with exactly one action: BUY, HOLD or SELL |
| **[IN-AND-OUT.md](IN-AND-OUT.md)** | Who's headed out, who replaces them. **Nothing exits without a named replacement** |
| **[BENCH.md](BENCH.md)** | Candidates and their state |
| **[PHONE-PROMPT.md](PHONE-PROMPT.md)** | Self-contained prompt for a scheduled mobile agent |
| **[VANTAGE-REPORT-2026-08-13.md](VANTAGE-REPORT-2026-08-13.md)** | Analyst targets, forward P/E, PEG, ROE across the book |
| `RUNS/` | Immutable dated run reports |
| `state/` | Machine-readable state — the source of truth |
| `scripts/` | Validators and renderers |

---

## The rules that actually matter

**Cost basis is never a reason to hold.** The only question is whether you'd buy
the position at today's price today.

**Price is never a sell trigger.** A sell needs a broken thesis: revenue
collapsing, guidance withdrawn, an interim CEO, or the reason you bought being
factually gone.

**Unknown is not failed.** Missing data moves a candidate to `WAITING_DATA`, never
to `REJECTED`. Two names were wrongly rejected for a null API field that a second
provider had all along.

**Correlation rejects a role, not a company.** A name hired to diversify can fail
that job on correlation alone. That says nothing about the business.

**Name the metric the business type runs on before judging it.** Utilities →
operating cash flow. REITs → FFO. Merchant power → contracted cash flow.
Asset-light software → margins and ROE, not book value. Getting this wrong caused
three separate misjudgments, all recorded.

**A correlation is a measurement, not a property.** Always print the window,
return frequency and as-of date. The same pair measured −0.44, −0.14 and +0.08
across three windows in one afternoon.

---

## Sleeve targets

| Sleeve | Target |
|---|---:|
| Broad global core | 30% |
| Northeast power | 25% |
| Defense / government | 15% |
| Data-center enablers | 10% |
| Regulated utilities | 10% |
| Precious metals | 5% |
| Cash reserve | 5% |

Targets steer where new money goes. **They never authorize a trade.**

---

## Setup

The account number is redacted as `<YOUR_ACCOUNT_NUMBER>`. Substitute your own
when using `PHONE-PROMPT.md`.

No API keys, tokens, or credentials are in this repository, and none should ever
be committed. Keys live outside the repo and are read at runtime only.

---

## What this is not

Not advice. Not a track record. A few weeks of decisions on a few hundred dollars
is a log, not evidence — and the log includes the mistakes on purpose, because
those are the part worth keeping.
