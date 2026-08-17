---
name: stocks-daily
description: >-
  Run Aaron's twice-daily portfolio review against the live Robinhood MCP.
  Regenerates the verdict table for every holding (BUY/SELL/HOLD/TRIM), scouts
  one new ticker through the 9 gates, and produces the $20 deployment chart.
  Use when Aaron says "run the daily", "morning run", "close run", "scout",
  "update the table", or asks what to do with today's money. Never places orders.
---

# stocks-daily â€” the portfolio operating loop

Aaron runs a live Robinhood account as a **learning instrument**. The written
record is the asset, not the returns. This skill produces the record.

**Canonical files** (read them, don't re-derive their contents):

| File | What |
|---|---|
| `C:\Users\aaron\Desktop\Stocks\SYSTEM\RULES.md` | Verdict logic + the 9 gates. **Read first, every run.** |
| `C:\Users\aaron\Desktop\Stocks\SYSTEM\PORTFOLIO.md` | Live verdict table â€” you regenerate this |
| `C:\Users\aaron\Desktop\Stocks\SYSTEM\BENCH.md` | Cleared candidates + rejected list â€” you append |
| `C:\Users\aaron\Desktop\Stocks\SYSTEM\RUNS\<date>-<am\|pm>.md` | This run's log â€” you create |
| `..\LESSONS.md`, `..\DECISION-LOG.md`, `..\AUDIT-2026-08-10.md` | History. Don't contradict without evidence |

**Account:** `<YOUR_ACCOUNT_NUMBER>` (Robinhood Agentic cash). MCP server `<ROBINHOOD_MCP_SERVER_ID>`.

---

## Hard limit

**This skill never places, cancels, reviews or modifies an order.** It produces
a chart with dollar amounts. Aaron presses the button. Do not offer to place
one, and do not write a prompt for another agent to place one.

---

## AM run â€” before the open

1. `get_portfolio(account_number)` â†’ value, cash, buying power
2. `get_equity_positions(account_number)` â†’ shares + `average_buy_price`
3. `get_equity_quotes([...])` â†’ current prices
4. For any holding that reported since the last run: `get_earnings_results(symbol)`
5. Re-score every holding against Â§1 of `RULES.md`
6. Write `RUNS\<date>-am.md`: what changed overnight, verdict flips, today's plan

**AM does not deploy money.** Dollar-based orders are market-only during regular
hours; the morning is for the plan, not the execution.

## PM run â€” ~30 minutes before the close

1. Repeat 1â€“3 above
2. Regenerate `PORTFOLIO.md` in full
3. Run the day's scout (below)
4. Produce the **$20 chart** â€” at most 3 tickers, minimum $5 each
5. Write `RUNS\<date>-pm.md`

---

## The daily scout

**Scout one new ticker. Expect to reject it.**

Run all 9 gates from `RULES.md`. Default is REJECT â€” a candidate that cannot
clear a gate goes to the rejected table in `BENCH.md` **with the gate number**,
not onto the bench.

A day that benches nothing is a normal day. The rejected list is the strongest
evidence in this notebook precisely because it costs nothing and proves the
process ran.

Minimum tool calls for a scout:

```
get_equity_fundamentals(symbols=["X"])   â†’ G1 G2 G3 G4 G6(name only)
get_financials(symbols=["X"])            â†’ G5 G7   â† null result = REJECT on G7
get_earnings_results(symbol="X")         â†’ G9
get_equity_historicals([X, GEV, LDOS, SPY], interval="day") â†’ G8
```

**G6 cannot be cleared from the MCP.** The `ceo` field shows a name whether or
not that person is interim. Verify permanence with WebSearch/WebFetch or mark
the gate FAILED.

---

## Correlation procedure (gate G8)

Report **28 / 63 / 250 sessions AND the rolling-63 pass rate.** Nested windows
are not independent observations; the rolling rate is the real test.

> Above 0.30 in **>70%** of windows â†’ correlated, reject.
> Below **30%** â†’ genuinely separate.

Reference: PEG measured âˆ’0.442 / âˆ’0.143 / **+0.084** across those three windows â€”
same pair, opposite sign. Always print the window and as-of date.

### Working PowerShell

```powershell
# NOTE: never name a function `R` â€” it collides with the Invoke-History alias.
function Get-Rets($a){ $r=@(); for($i=1;$i -lt $a.Count;$i++){ $r += (($a[$i]-$a[$i-1])/$a[$i-1]) }; ,$r }
function Get-Corr($x,$y){ $n=$x.Count
  $mx=($x|Measure-Object -Average).Average; $my=($y|Measure-Object -Average).Average
  $nu=0;$dx=0;$dy=0; for($i=0;$i -lt $n;$i++){$a=$x[$i]-$mx;$b=$y[$i]-$my;$nu+=$a*$b;$dx+=$a*$a;$dy+=$b*$b}
  [math]::Round($nu/[math]::Sqrt($dx*$dy),3) }
```

Sleeve correlation â€” weight each member by **current position value**, sum to a
sleeve daily return, then correlate the two sleeve series.

---

## MCP gotchas â€” each of these cost a failed call

| Tool | Trap |
|---|---|
| `get_equity_positions` | Takes **`account_number`** only. Passing `symbols` errors |
| `get_equity_quotes` | Official closes cap at **20 symbols**; quotes still return for all |
| `get_earnings_results` | Takes **`symbol`** (singular). No `limit`, no `statement` |
| `get_financials` | Takes **`symbols`** (plural array). A **`null`** entry = no data â†’ fails G7 |
| `get_equity_historicals` | `interval="3month"` returns an **empty** bars array. Use `"month"` |
| `get_equity_historicals` | >4 symbols Ã— 1 year overflows â†’ auto-saved to a file. Parse it in PowerShell, don't Read it |
| Same | Today's bar often comes back **`interpolated: true`, volume 0**. Filter those out, then append the real close from `get_equity_quotes` |
| `get_earnings_calendar` | Does **not** take `symbols` |

---

## Output shape â€” keep it short

Aaron has ADHD. **Lead with the answer in one line. Bold the ask.** Past roughly
four sentences per block is lost. Use tables. Never bury the decision.

Every run ends with exactly this:

```
### Today's $20
| Ticker | Amount | Why |
|---|---|---|
| ... | $X | one line |

Cash left: $X
```

If the honest answer is "nothing today, hold the cash," **say that.** Not
deploying is a valid outcome and should appear in the log as one.

---

## Discipline

- **Cost basis is never a reason to hold.** Ask only: would I buy this position
  at today's price, today?
- **Verify, don't relay.** If another agent supplied a number, reproduce it
  before it enters a file. If you can't, it goes under **UNVERIFIED** by name.
- **Never write a conclusion from one observation into a shared file.** These
  files are read by other sessions.
- **Report the misses.** A verdict that was wrong last week goes in the log
  louder than one that was right.

