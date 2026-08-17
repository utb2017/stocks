# Alpha Vantage Overview Report — 2026-08-13

**Source:** Alpha Vantage `OVERVIEW`, all 22 single-name holdings, pulled 2026-08-13.
**Prices:** Robinhood live quotes, same session.

**API note worth keeping:** the endpoint is **`OVERVIEW`**, not `COMPANY_OVERVIEW`.
The published tool list names it `COMPANY_OVERVIEW` — that's the MCP tool name. The
REST function rejects it with *"This API function does not exist."* Cost one failed
sweep to find.

**What this pull added that nothing else had:** analyst target prices, the full
strong-buy/buy/hold/sell/strong-sell breakdown, forward P/E, PEG, ROE, and insider
ownership percentage. None of it is available from the broker.

---

## Upside to analyst target

| Ticker | Price | Target | Upside | % Buy | n | Bears |
|---|---:|---:|---:|---:|---:|---:|
| **VST** | $146.68 | **$221.74** | **+51.2%** | **95%** | 20 | 1 |
| **TLN** | $360.31 | $467.69 | **+29.8%** | 88% | 17 | 0 |
| **SPXC** | $212.67 | $272.00 | **+27.9%** | 92% | 12 | 0 |
| CEG | $278.22 | $349.96 | +25.8% | 87% | 23 | 0 |
| CDNS | $326.40 | $403.67 | +23.7% | 88% | 25 | 0 |
| CARR | $63.50 | $77.82 | +22.6% | 58% | 24 | 0 |
| FNV | $231.02 | $277.17 | +20.0% | 80% | 15 | 0 |
| AEM | $179.83 | $214.98 | +19.5% | 82% | 22 | 1 |
| JBL | $372.51 | $441.44 | +18.5% | 80% | 10 | 0 |
| GEV | $1,058.72 | $1,238.25 | +17.0% | 79% | 38 | 0 |
| PPL | $35.57 | $41.47 | +16.6% | 75% | 16 | 0 |
| PEG | $75.68 | $86.97 | +14.9% | 39% | 23 | 1 |
| DLR | $198.25 | $222.03 | +12.0% | 79% | 33 | 0 |
| BAH | $78.49 | $85.58 | +9.0% | **21%** | 14 | **3** |
| CWT | $50.19 | $54.00 | +7.6% | 100% | 3 | 0 |
| **LDOS** | $142.58 | $153.47 | **+7.6%** | **41%** | 17 | 0 |
| PLTR | $178.54 | $191.68 | +7.4% | 62% | 32 | 2 |
| CACI | $673.02 | $717.43 | +6.6% | 75% | 16 | 0 |
| **AWK** | $136.45 | $140.36 | **+2.9%** | **23%** | 13 | 1 |
| **YORW** | $32.89 | $31.00 | **−5.7%** | 0% | 1 | 0 |
| **SAIC** | $127.35 | $120.00 | **−5.8%** | **18%** | 11 | 1 |

**SAIC and YORW trade above their analyst targets.** The street sees no room left.

---

## Valuation and quality

| Ticker | Fwd P/E | PEG | ROE | Rev growth y/y | Insider % |
|---|---:|---:|---:|---:|---:|
| **VST** | **15.85** | **0.409** | **42.9%** | −5.5% | 0.79% |
| JBL | 21.10 | **0.819** | **65.9%** | +11.8% | 1.19% |
| BAH | 12.63 | 1.093 | **68.6%** | **−4.2%** | 1.21% |
| VRT | 42.02 | 1.271 | 43.9% | +24.1% | 0.27% |
| PPL | 17.95 | 1.359 | 8.6% | +4.2% | 0.17% |
| SPXC | 25.84 | 1.436 | 14.7% | **+22.9%** | **3.06%** |
| CARR | 22.88 | 1.504 | 9.0% | +3.9% | **4.76%** |
| GEV | 35.84 | 1.719 | **82.6%** | +21.9% | 0.13% |
| CWT | 19.08 | 2.218 | 7.7% | +16.5% | 0.65% |
| PLTR | **112.36** | 2.414 | 38.1% | **+92.8%** | 3.49% |
| **LDOS** | **11.51** | 2.457 | 27.8% | +7.2% | 0.56% |
| AWK | 22.32 | 2.627 | 10.1% | +6.2% | 0.12% |
| CDNS | 40.98 | 3.006 | 23.2% | +24.2% | 0.29% |
| SAIC | **10.00** | 3.670 | 27.7% | +1.5% | 0.72% |
| PEG | 17.04 | 3.705 | 11.8% | **−8.9%** | 0.13% |
| CEG | 22.94 | 3.742 | 15.1% | +23.0% | 0.33% |
| YORW | 25.45 | 4.095 | 9.0% | +22.5% | 1.04% |
| FNV | 29.33 | 11.81 | 19.0% | **+77.7%** | 0.62% |
| DLR | 78.12 | 13.85 | 2.9% | +29.9% | 0.01% |
| AEM | 15.38 | 28.15 | 23.0% | +35.0% | 0.07% |
| CACI | 17.89 | 514.23 | 12.8% | +17.6% | 1.08% |
| TLN | 14.56 | n/a | **−12.8%** | **+111.2%** | 1.37% |

---

## Findings

### 1. VST is the strongest set of numbers in the book

**PEG 0.409** — the only holding under 1.0 by a wide margin, meaning the growth is
cheaper than the multiple. Paired with **forward P/E 15.85**, **ROE 42.9%**,
**95% buy across 20 analysts**, and **+51.2%** to target.

**Against it:** quarterly revenue **−5.5%** (merchant power is lumpy), and
down-capture **2.29** — it falls more than twice as hard as the market on down days.
Best value-and-growth profile owned; worst behavior in a drawdown.

### 2. The street disagrees with the LDOS thesis — record it

Claude has argued LDOS is the best name in the book: **forward P/E 11.51** (cheapest
owned), **ROE 27.8%**, 5-for-5 earnings beats, revenue +11.2% over two years,
down-capture **0.61**.

**Analyst consensus is 41% buy across 17, with only +7.6% to target.**

Both are true. The disagreement is on record so it can be scored later. Precedent
cuts both ways: the same consensus was 3-buy / 8-hold on BAH while it beat by 20%+
three straight quarters — and BAH's revenue was shrinking the whole time.

### 3. BAH confirmed as the weakest holding

**21% buy, 3 bears — worst rating owned.** Revenue **−4.2% y/y**. ROE 68.6% is high
but that is leverage on a shrinking base, not a growing business. Exit-queue status
in `IN-AND-OUT.md` stands.

### 4. PLTR is expensive even on forward earnings

**Forward P/E 112.36** — roughly 3× the next most expensive holding. Revenue growth
**+92.8%** is real and extraordinary. Both facts hold at once.

### 5. AWK was bought with the street against it

Purchased 2026-08-13 at $136.45. **23% buy, 1 bear, +2.9% to target.**

Bought for **down-capture −0.57** — it rises when the market falls — not for upside.
That reasoning is intact, but the weak consensus should be visible in the record
rather than buried.

---

## Not verified

- Analyst counts here are **Alpha Vantage's sample only**. They differ from the
  Robinhood app's ratings screen. The two are never blended.
- Target prices are provider aggregates with no stated date. They lag events — the
  Wall Street Zen upgrade on SBS was dated three days before its earnings miss.
- PEG is unusable where earnings growth is near zero or negative (CACI 514, AEM 28,
  DLR 13.85, FNV 11.81 are artifacts, not signals).
