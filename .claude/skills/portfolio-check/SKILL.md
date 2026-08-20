---
name: portfolio-check
description: >-
  Check Aaron's Robinhood portfolio with mandatory full coverage — every open
  position gets its own scored line, every run, no sampling. Renders the holdings
  table, the sleeve table, the structural checks, and the deployment suggestion.
  Use when Aaron says "check stocks", "check the portfolio", "run the check",
  "how are we doing", "look at the board", "morning run", or "close run".
  Never places, cancels, reviews, or modifies an order.
---

# portfolio-check — full-coverage portfolio review

The account is ~24 positions. That is small enough that **there is no such thing
as a position we did not have time to check.** Any run that reports on a subset
is a failed run, regardless of how good the subset looked.

**Account:** `<YOUR_ACCOUNT_NUMBER>` (Robinhood, cash account).

---

## Hard limit

This skill **never places, cancels, reviews, exercises, or modifies an order.**
It produces numbers and a suggestion. Aaron presses every button. Do not offer to
place an order and do not write a prompt for another agent to place one.

Read-only tools only. If a mutation tool (`place_*`, `cancel_*`, `review_*`,
`exercise_*`, `create_*`, `update_*`, `delete_*`) is ever called from this skill,
the skill has failed.

---

## THE COVERAGE CONTRACT

This is the reason the skill exists. Everything else is secondary.

1. `get_equity_positions` returns N positions. **Every one of those N gets a row
   in the holdings table.** Not the movers. Not the recommendations. Not the
   interesting ones. All of them.
2. Before writing the output, print the coverage receipt:
   `Coverage: N positions returned / N rendered`
   If those two numbers differ, **stop and fix it** — do not publish the run.
3. A position with nothing wrong with it still gets a row. Its row says nothing
   is wrong. That is the record.
4. "Top movers" is a *summary of* the table, never a *substitute for* it.

**Never say "we didn't check X."** With N≈24 and batched quotes, a complete pass
costs three `get_equity_quotes` calls. If something was not checked, that is a
choice that was made, and it needs to be named as a choice.

---

## STEP 1 — Pull live data

```
get_portfolio(account_number)            → total_value, cash, buying_power
get_equity_positions(account_number)     → quantity, average_buy_price  (this sets N)
get_equity_orders(account_number)        → open orders + today's fills
get_equity_quotes([...])                 → batch ≤10 symbols per call, cover all N
```

Price rule: use `last_trade_price`. Daily change uses `adjusted_previous_close`.

**Pre-market: ignore `bid_price`/`ask_price` entirely.** The book is thin and the
spreads are garbage — a $449 bid against an $868 ask has been observed on CACI.
Use `last_non_reg_trade_price` for pre-market prints and label them as such.

If the last regular trade and the previous close carry the **same date**, no
session has happened yet. Say so; do not report a 0.00% day as if it were a
measured flat day.

---

## STEP 2 — Score every position

For each of the N holdings compute:

| Field | Source |
|---|---|
| Value | `quantity × last_trade_price` |
| Weight | `value / total_value` |
| Day % | vs `adjusted_previous_close` |
| P/L $ | `quantity × (last_trade_price − average_buy_price)` |
| 20-session % | `get_equity_historicals(interval="day")`, close 20 sessions back → now |
| Next earnings | `get_earnings_results(symbol)` → date + `verified` |

Earnings and historicals are per-symbol calls. Batch historicals ≤10 symbols.
Cache within a run — do not re-pull the same symbol twice.

### Flag codes

| Code | Trigger |
|---|---|
| `SUB5` | Position value < $5.00 — too small to move the account |
| `EXIT` | On the exit queue (see below) |
| `EXT` | Up ≥25% over 20 sessions — extended, do not add |
| `ER5` | Earnings within 5 sessions |
| `DROP` | Down >5% in one day |
| `LOSS` | Unrealized P/L negative |

`EXT` at 25% is a **proposed** threshold, not an approved one. It is calibrated
to precedent: CACI was barred at +45%, AEM at +36%, LDOS flagged at +35%. Present
it as proposed until Aaron signs off, the same way sleeve targets required
approval before they ranked anything.

On any `DROP`, look up the cause before commenting on it. If no cause is found,
write **"cause unknown."** Never invent one.

---

## STEP 3 — Sleeve table

| Sleeve | Target | Members |
|---|---:|---|
| Broad global core | 30% | VT |
| Northeast power | 25% | TLN VST PPL CEG GEV |
| Defense / government | 15% | LDOS BAH PLTR CACI SAIC |
| Data-center enablers | 10% | CARR VRT JBL SPXC DLR CDNS NVDA |
| Regulated utilities | 10% | CWT AWK YORW PEG |
| Precious metals | 5% | FNV AEM |
| Cash reserve | 5% | — |

Report value, weight, target, and dollar gap for each. New money goes to
underweight sleeves in proportion to their dollar gap. Overweight sleeves get
nothing.

**Every holding maps to exactly one sleeve.** If a position is not in the table
above, that is itself a finding — surface it as `UNSLEEVED`, do not silently drop
it. An unsleeved holding is invisible to every gap calculation, which is exactly
how a position goes unexamined for months.

---

## STEP 4 — Structural checks

Sleeve drift is not portfolio health. These run **every time**, because the sleeve
math is structurally incapable of surfacing them — a gap check compares holdings
to targets and can never question the targets.

1. **Sub-floor census.** Count and total every position under $5. The rule "do not
   create positions under $5" only ever governed new buys; nothing audits the
   ones already on the book.
2. **Theme concentration.** Sleeves are not the same as independent bets. Northeast
   power + regulated utilities + data-center enablers are one wager on electricity
   demand and the data-center buildout. Report their **combined** weight. Name the
   real diversifier count, not the sleeve count.
3. **Exit queue with no exit.** The queue below says "do not add." Nothing in the
   system ever sells. List each exit-queue name with its current value and P/L, and
   state plainly that the queue has no mechanism. A name can sit on it while being
   a top gainer — that contradiction is a finding, not a footnote.
4. **Cash double duty.** The 5% cash line is simultaneously dry powder and the only
   defensive allocation. Report cash weight against both jobs. There is **no fixed
   income sleeve in this model** — say so whenever cash is discussed as defense.
5. **Missing asset classes.** State what the model has no slot for. A gap check
   cannot report a missing asset class, because a missing class has no target to
   be measured against.

---

## STEP 5 — Suggestion

**Exit queue — do not add:**

| Ticker | Why |
|---|---|
| TLN | missed by 95% last quarter, loss-making, falls 2.5× the market |
| BAH | revenue −6.4%, net income −9.0%, 21% analyst buy with 3 sells |
| SAIC | revenue −2.4%, net income −25%, trades above its analyst target |
| CDNS | $71.8M insider disposals last quarter |
| CARR | revenue declining, margins swinging 1.1%–9.7% |

**Preferred inside each sleeve:**

| Sleeve | Names |
|---|---|
| Core | VT |
| NE power | VST (PEG 0.41, 95% buy) · PPL (P/B 1.76, 3.17% yield, defensive) |
| Defense | LDOS (fwd P/E 11.5, 5/5 beats) · CACI (5/5 beats, revenue +24.9%) |
| Enablers | NVDA (fwd P/E 24.8, PEG 0.60) · SPXC (revenue +23%, 4/4 beats) |
| Utilities | AWK (defensive, revenue +21.4%) · CWT (P/B 1.71) |
| Metals | AEM (P/E 12.9, revenue +35%) |

**Rules:**

- Minimum single buy **$1.00** (Robinhood floor). Below that, skip.
- Do not create new positions under **$5**.
- **At most 3 tickers.** Concentrate, do not sprinkle.
- Deployable = `buying_power − open_order_reserve − 5% cash floor`.
- Never recommend on price alone. **"It dropped" is not a reason.**
- Check `get_earnings_results` on anything recommended. No buys within 5 sessions
  of a report unless the report *is* the bet.
- Do not recommend a name carrying `EXT` or `EXIT`. If every name in an
  underweight sleeve is disqualified, **leave the sleeve unfilled and say why**.
  An empty sleeve with a stated reason beats a filled one with a bad name.
- "Hold the cash" is a valid answer and most days is the right one.

---

## STEP 6 — Output

Aaron reads this on a phone and has ADHD. **Lead with the action.** Bold the ask.
Past ~4 sentences per block is lost. Tables over prose. Never bury the decision.

Order is fixed:

```
Account $X | cash $X | today ±X%

SUGGESTION:
| Ticker | Amount | One line why |
Cash left: $X

FLAGS: what needs him, or "none"

HOLDINGS — all N:
| Ticker | Val | Wt | Day% | P/L | 20d | Next ER | Flags |
(one row per position, no exceptions)

SLEEVES:
| Sleeve | Value | Wt | Target | Gap |

STRUCTURAL: only checks that fired, one line each

Coverage: N/N
```

The suggestion goes first because it is the ask. The holdings table goes in full
because it is the record. Both, every run — the short format is what let a subset
pass as a complete review.

---

## Verification discipline

- **Every number comes from a tool call in this run.** If it is not on screen from
  an API, write **"unverified"** — never state it.
- **Verify, don't relay.** A figure from another agent gets reproduced before it
  enters the output. If it cannot be reproduced, it is labeled UNVERIFIED by name.
- **Cost basis is never a reason to hold.** The only question is: would I buy this
  position at today's price, today?
- **Report the misses.** A call that was wrong last week goes in the output louder
  than one that was right.
- Do not describe a check as impossible when it is merely unbudgeted. With N≈24,
  say what was skipped and why.

---

## MCP gotchas

| Tool | Trap |
|---|---|
| `get_equity_positions` | Takes `account_number` only. Passing `symbols` errors |
| `get_equity_quotes` | Official closes cap at 20 symbols; quotes still return for all |
| `get_earnings_results` | Takes `symbol` **singular**. One call per ticker |
| `get_earnings_calendar` | Does **not** take `symbols` |
| `get_financials` | Takes `symbols` **plural**. A `null` entry means no data |
| `get_equity_historicals` | `interval="3month"` returns empty bars. Use `"month"` |
| Same | Today's bar is often `interpolated: true` with volume 0 — filter it, then append the real close from `get_equity_quotes` |
| `get_portfolio` | On a cash account, unsettled proceeds are **not** in `buying_power` — check `get_accounts` for `unsettled_funds` |
