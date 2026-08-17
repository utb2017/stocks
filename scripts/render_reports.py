"""Render deterministic Markdown views from validated structured stock state."""

from __future__ import annotations

import argparse
from decimal import Decimal
import json
from pathlib import Path
import tempfile


def _money(value):
    amount = Decimal(str(value))
    prefix = "-" if amount < 0 else ""
    return f"{prefix}${abs(amount):,.2f}"


def _cell(value):
    return str(value).replace("|", "\\|").replace("\n", " ")


def render_portfolio(portfolio, analyst_ratings, evidence=None, *, policy=None, budget=None):
    """Return the human portfolio view without changing any recommendation."""

    targets_active = bool(
        policy
        and policy.get("policy_status", {}).get("targets_approved") is True
        and policy.get("policy_status", {}).get("targets_enabled") is True
    )
    target_by_sleeve = {
        sleeve["id"]: Decimal(str(sleeve["target_pct"]))
        for sleeve in (policy or {}).get("targets", {}).get("sleeves", [])
    }
    records = {
        item["ticker"]: item
        for item in analyst_ratings.get("alpha_vantage", {}).get("records", [])
    }
    reconciliation = portfolio["reconciliation"]
    lines = [
        "# Portfolio - BUY / HOLD / SELL sheet" if targets_active else "# Portfolio — observe-only seed",
        "",
        f"**As of:** {portfolio['market_date']} official SIP close  ",
        (
            "**State:** Targets active · recommendations only · no trades  "
            if targets_active
            else "**State:** Observe-only · targets unapproved · no allocation authorized  "
        ),
        f"**Account value at close:** {_money(reconciliation['official_close_total_value'])} · "
        f"cash {_money(reconciliation['cash'])} · P/L {_money(reconciliation['unrealized_pnl'])}",
        "",
        "> Most positions remain low-confidence migration HOLDs. Sourced exceptions "
        "are labeled separately; preserving a position is not a blanket endorsement.",
        "",
        "## Sleeve snapshot",
        "",
        (
            "| Sleeve | Value | Weight | Target | Gap |"
            if targets_active
            else "| Sleeve | Value | Weight |"
        ),
        (
            "|---|---:|---:|---:|---:|"
            if targets_active
            else "|---|---:|---:|"
        ),
    ]
    for sleeve in portfolio["sleeves"]:
        if targets_active:
            target = target_by_sleeve[sleeve["name"]]
            gap = target - Decimal(str(sleeve["weight_pct"]))
            lines.append(
                f"| {_cell(sleeve['name'])} | {_money(sleeve['value'])} | "
                f"{sleeve['weight_pct']:.1f}% | {target:.1f}% | {gap:+.1f} pts |"
            )
        else:
            lines.append(
                f"| {_cell(sleeve['name'])} | {_money(sleeve['value'])} | {sleeve['weight_pct']:.1f}% |"
            )
    lines.extend(
        [
            "",
            "## Holdings",
            "",
            "| Ticker | Action | Sleeve | Value | Weight | P/L | Flags | Alpha ratings |",
            "|---|---|---|---:|---:|---:|---|---|",
        ]
    )
    for holding in portfolio["holdings"]:
        record = records.get(holding["ticker"])
        if not record or record.get("status") != "COMPLETE":
            rating_text = "missing"
        else:
            ratings = record["ratings"]
            grouped_buy = int(ratings["strong_buy"]) + int(ratings["buy"])
            grouped_sell = int(ratings["sell"]) + int(ratings["strong_sell"])
            rating_text = (
                f"{grouped_buy}/{ratings['hold']}/{grouped_sell} "
                f"(n={ratings['total']})"
            )
        flags = ", ".join(holding.get("flags", [])) or "—"
        lines.append(
            f"| {holding['ticker']} | {holding['action']} | {_cell(holding['primary_sleeve'])} | "
            f"{_money(holding['market_value'])} | {holding['weight_pct']:.1f}% | "
            f"{_money(holding['unrealized_pnl'])} | {_cell(flags)} | {rating_text} |"
        )
    if budget:
        lines.extend(
            [
                "",
                "## Money plan",
                "",
                f"**Right now:** {_money(budget['broker']['buying_power'])} buying power · "
                f"{_money(budget['deployable_now'])} deployable",
            ]
        )
        if_funded = budget.get("if_funded_plan")
        if isinstance(if_funded, dict):
            lines.extend(
                [
                    "",
                    f"**If the expected {_money(if_funded['assumed_new_cash'])} is confirmed after 11:00:**",
                    "",
                    "| Ticker | Amount | Why |",
                    "|---|---:|---|",
                ]
            )
            for allocation in if_funded.get("planned_allocations", []):
                lines.append(
                    f"| {allocation['ticker']} | {_money(allocation['amount_usd'])} | "
                    f"{_cell(allocation['reason'])} |"
                )
            lines.extend(
                [
                    "",
                    f"Ending cash if funded: **{_money(if_funded['ending_cash'])}**",
                ]
            )
    unverified_tickers = sorted(
        {
            claim.get("ticker")
            for claim in (evidence or {}).get("unverified_claims", [])
            if claim.get("ticker")
        }
    )
    lines.extend(["", "## Current blocks", ""])
    if targets_active:
        lines.append("- Sleeve targets are active for ranking recommendations; they never authorize trades.")
    else:
        lines.append("- Proposed sleeve targets are disabled until Aaron approves them.")
    if unverified_tickers:
        lines.append(
            f"- {', '.join(unverified_tickers)} primary-source claims remain unverified."
        )
    lines.append("- FNV is locked for its 2026-08-11 after-close report.")
    if budget:
        lines.append(
            f"- Broker buying power is {_money(budget['broker']['buying_power'])}; "
            f"current deployable recommendation capacity is {_money(budget['deployable_now'])}."
        )
    else:
        lines.append(
            "- The modeled $20 ledger has not started; real buying power is $7 and deployable-now is $0 in observe-only mode."
        )
    lines.append("")
    return "\n".join(lines)


def render_bench(document):
    """Return active candidate states without inventing a ready queue."""

    ready_states = {"QUALIFIED", "WAITING_CASH", "PROPOSED"}
    has_ready_candidate = any(
        candidate.get("state") in ready_states
        for candidate in document.get("candidates", [])
    )
    lines = [
        "# Candidate bench — migration state",
        "",
        (
            "Qualified candidates remain recommendations only and wait for confirmed buying power."
            if has_ready_candidate
            else "No candidate is currently qualified for money. UNKNOWN data remains WAITING_DATA."
        ),
        "",
        "| Ticker | Role | State | Primary blocker |",
        "|---|---|---|---|",
    ]
    for candidate in document["candidates"]:
        blocker = candidate.get("blockers", ["—"])[0]
        lines.append(
            f"| {candidate['ticker']} | {candidate['intended_role']} | {candidate['state']} | {_cell(blocker)} |"
        )
    states = {
        candidate["ticker"]: candidate.get("state")
        for candidate in document.get("candidates", [])
    }
    lines.append("")
    lines.append("- **B:** wait for FNV's report; it is a correlated metals theme, not diversification.")
    lines.append("- **LEU:** verify CEO permanence and primary financial evidence; sleeve assignment is unresolved.")
    if states.get("VT") == "WAITING_CASH":
        lines.append("- **VT:** ETF gates passed; wait for confirmed buying power and the funded-pass ranking.")
    else:
        lines.append("- **VT:** complete the ETF-specific primary-source path before it can seed the core.")
    lines.extend(
        [
            "- **ASPN:** rejected for the current diversifier role after primary filings showed weak revenue trajectory, compressed gross margin, and continuing GAAP losses.",
            "- **UEC:** rejected for the current theme allocation role until recurring production-sales revenue and financial sustainability emerge.",
            "- At most one ticker receives a full scout per trading day; accepting none is normal.",
            "",
        ]
    )
    return "\n".join(lines)


def render_rules(policy):
    """Return a compact, generated policy summary."""

    targets = policy["targets"]
    budget = policy["budget"]
    automation = policy["automation"]
    targets_enabled = bool(
        policy.get("policy_status", {}).get("targets_approved") is True
        and policy.get("policy_status", {}).get("targets_enabled") is True
    )
    lines = [
        "# Operating rules — generated summary",
        "",
        f"**Target status:** {targets['status']}  ",
        "**Broker access:** read-only policy configured; live runtime must pass capability isolation  ",
        f"**Automation:** {'enabled' if automation['enabled'] else 'disabled'} · "
        f"{automation['status']} · runtime isolation {automation['runtime_tool_isolation_status']}  ",
        f"**Modeled contribution:** {_money(budget['modeled_daily_contribution_usd'])} per verified trading day, credited once and rolled forward  ",
        f"**Fractional allocation floor:** {_money(budget['minimum_allocation_usd'])}",
        "",
        "## Non-negotiable state rules",
        "",
        "- Every live holding has exactly one action: BUY, HOLD, or SELL.",
        "- Flags never replace the action.",
        "- UNKNOWN → WAITING_DATA; it never means failed or rejected.",
        "- Correlation may reject a proposed role, not the company.",
        "- Ratings, targets, momentum, cost basis, and one correlation window cannot independently set a general verdict.",
        "- Real buying power caps every plan; modeled money never makes unavailable cash spendable.",
        "- The system never places, reviews, cancels, modifies, or exercises an order.",
        "",
        "## Approved targets - enabled" if targets_enabled else "## Proposed targets — disabled",
        "",
        "| Sleeve | Target |",
        "|---|---:|",
    ]
    for sleeve in targets["sleeves"]:
        lines.append(f"| {_cell(sleeve['name'])} | {sleeve['target_pct']}% |")
    lines.append("")
    if targets_enabled:
        lines.append("These percentages steer recommendation ranking only; they never authorize trades.")
    else:
        lines.append("These percentages cannot steer an allocation until both approval flags are true and validation passes.")
    lines.append("")
    return "\n".join(lines)


def _load(path):
    return json.loads(path.read_text(encoding="utf-8"))


def _atomic_write(path, content):
    path.parent.mkdir(parents=True, exist_ok=True)
    with tempfile.NamedTemporaryFile(
        mode="w", encoding="utf-8", newline="\n", delete=False, dir=path.parent
    ) as handle:
        handle.write(content)
        temp_path = Path(handle.name)
    temp_path.replace(path)


def main(argv=None):
    parser = argparse.ArgumentParser(description=__doc__)
    default_root = Path(__file__).resolve().parent.parent
    parser.add_argument("--system-root", type=Path, default=default_root)
    parser.add_argument("--output-dir", type=Path)
    args = parser.parse_args(argv)
    root = args.system_root
    output = args.output_dir or root
    portfolio = _load(root / "state" / "portfolio.json")
    candidates = _load(root / "state" / "candidates.json")
    ratings = _load(root / "state" / "analyst-ratings.json")
    evidence = _load(root / "state" / "evidence.json")
    budget = _load(root / "state" / "budget.json")
    policy = _load(root / "config" / "policy.yaml")
    reports = {
        "PORTFOLIO.md": render_portfolio(
            portfolio,
            ratings,
            evidence,
            policy=policy,
            budget=budget,
        ),
        "BENCH.md": render_bench(candidates),
        "RULES.md": render_rules(policy),
    }
    for name, content in reports.items():
        _atomic_write(output / name, content)
    print("Rendered 3 reports")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
