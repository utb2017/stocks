"""Prepare the modeled daily contribution ledger without touching a broker."""

from __future__ import annotations

import argparse
import copy
from datetime import date
from decimal import Decimal, ROUND_HALF_UP
import json
from pathlib import Path
import tempfile


CENT = Decimal("0.01")


def _money(value):
    return Decimal(str(value)).quantize(CENT, rounding=ROUND_HALF_UP)


def _money_text(value):
    return f"{_money(value):.2f}"


def _cash_target_pct(policy):
    for sleeve in policy.get("targets", {}).get("sleeves", []):
        if sleeve.get("id") == "cash_reserve":
            return Decimal(str(sleeve.get("target_pct")))
    raise ValueError("policy targets must define cash_reserve")


def prepare_budget(
    budget,
    policy,
    *,
    portfolio_total,
    trading_date,
    market_is_open,
    generated_at,
):
    """Return a fresh, allocation-neutral budget for one attested market date."""

    market_date = date.fromisoformat(trading_date)
    if market_is_open and market_date.weekday() >= 5:
        raise ValueError("a weekend cannot be attested as an open trading date")

    result = copy.deepcopy(budget)
    daily = _money(result["modeled_daily_contribution"])
    policy_daily = _money(policy["budget"]["modeled_daily_contribution_usd"])
    if daily != policy_daily:
        raise ValueError("budget contribution must match policy")

    accrued = list(result.get("contribution_accrued_for_dates", []))
    rollover = _money(result.get("modeled_rollover", "0.00"))
    if market_is_open and trading_date not in accrued:
        accrued.append(trading_date)
        accrued.sort()
        rollover += daily
        if result.get("modeled_start_date") is None:
            result["modeled_start_date"] = trading_date

    approved = (
        policy.get("policy_status", {}).get("targets_approved") is True
        and policy.get("policy_status", {}).get("targets_enabled") is True
    )
    broker = result["broker"]
    broker_cash = _money(broker["cash"])
    buying_power = _money(broker["buying_power"])
    open_order_reserve = _money(broker["open_order_reserve"])

    if approved:
        cash_floor = _money(
            _money(portfolio_total) * _cash_target_pct(policy) / Decimal("100")
        )
        cash_available = max(
            Decimal("0.00"), broker_cash - cash_floor - open_order_reserve
        )
        buying_power_available = max(
            Decimal("0.00"), buying_power - open_order_reserve - cash_floor
        )
        deployable = min(rollover, cash_available, buying_power_available)
        status = "READY_FOR_ALLOCATION"
        reason = (
            "Capped by modeled rollover, confirmed buying power, open-order reserve, "
            "and the approved cash floor."
        )
    else:
        cash_floor = None
        deployable = Decimal("0.00")
        status = "OBSERVE_ONLY"
        reason = "Targets are unapproved or disabled; contribution accrual continues but allocation is blocked."

    result["generated_at"] = generated_at
    result["status"] = status
    result["modeled_rollover"] = _money_text(rollover)
    result["contribution_accrued_for_dates"] = accrued
    result["policy"] = {
        "targets_approved": approved,
        "targets_enabled": approved,
        "cash_reserve_floor": None if cash_floor is None else _money_text(cash_floor),
        "minimum_allocation": _money_text(
            policy.get("budget", {}).get("minimum_allocation_usd", "1.00")
        ),
    }
    result["deployable_now"] = _money_text(deployable)
    result["deployable_reason"] = reason
    result["planned_allocations"] = []
    result["planned_total"] = "0.00"
    result["ending_cash"] = _money_text(broker_cash)
    result["if_funded_plan"] = None
    return result


def _load(path):
    with Path(path).open("r", encoding="utf-8") as handle:
        value = json.load(handle)
    if not isinstance(value, dict):
        raise ValueError(f"{path} must contain a JSON object")
    return value


def _atomic_json_write(path, value):
    target = Path(path)
    target.parent.mkdir(parents=True, exist_ok=True)
    with tempfile.NamedTemporaryFile(
        mode="w", encoding="utf-8", newline="\n", delete=False, dir=target.parent
    ) as handle:
        json.dump(value, handle, indent=2)
        handle.write("\n")
        temporary = Path(handle.name)
    temporary.replace(target)


def main(argv=None):
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--budget", type=Path, required=True)
    parser.add_argument("--policy", type=Path, required=True)
    parser.add_argument("--output", type=Path, required=True)
    parser.add_argument("--portfolio-total", required=True)
    parser.add_argument("--trading-date", required=True)
    parser.add_argument("--market-status", choices=["OPEN", "CLOSED"], required=True)
    parser.add_argument("--generated-at", required=True)
    args = parser.parse_args(argv)

    prepared = prepare_budget(
        _load(args.budget),
        _load(args.policy),
        portfolio_total=args.portfolio_total,
        trading_date=args.trading_date,
        market_is_open=args.market_status == "OPEN",
        generated_at=args.generated_at,
    )
    _atomic_json_write(args.output, prepared)
    print(f"PREPARED {args.trading_date} {args.market_status} -> {args.output}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
