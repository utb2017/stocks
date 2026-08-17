"""Deterministic, stdlib-only validators for the stock operating system."""

from __future__ import annotations

import argparse
from datetime import datetime
from decimal import Decimal, InvalidOperation
import hashlib
import json
from pathlib import Path
import re


CANONICAL_ROBINHOOD_RECONCILIATION_GETTERS = [
    "get_accounts",
    "get_portfolio",
    "get_equity_positions",
    "get_equity_orders",
    "get_equity_quotes",
    "get_equity_tradability",
]


def _is_iso8601_timestamp_with_timezone(value):
    if not isinstance(value, str) or not value.strip():
        return False
    normalized = value[:-1] + "+00:00" if value.endswith("Z") else value
    try:
        parsed = datetime.fromisoformat(normalized)
    except ValueError:
        return False
    return parsed.tzinfo is not None and parsed.utcoffset() is not None


def _target_profile_sha256(policy):
    sleeves = policy.get("targets", {}).get("sleeves")
    if not isinstance(sleeves, list):
        return None
    try:
        canonical = json.dumps(
            sleeves,
            ensure_ascii=False,
            sort_keys=True,
            separators=(",", ":"),
        )
    except (TypeError, ValueError):
        return None
    return hashlib.sha256(canonical.encode("utf-8")).hexdigest()


def load_document(path):
    """Load a JSON document or JSON-compatible YAML policy."""

    document_path = Path(path)
    with document_path.open("r", encoding="utf-8") as handle:
        value = json.load(handle)
    if not isinstance(value, dict):
        raise ValueError(f"{document_path} must contain a JSON object")
    return value


def validate_policy(policy):
    """Return deterministic validation errors for a decoded policy object."""

    if not isinstance(policy, dict):
        return ["policy must be an object"]
    errors = []
    if policy.get("schema_version") != 1:
        errors.append("schema_version must be 1")
    actions = policy.get("verdicts", {}).get("allowed_actions")
    if actions != ["BUY", "HOLD", "SELL"]:
        errors.append("verdicts.allowed_actions must be exactly BUY, HOLD, SELL")
    candidates = policy.get("candidates", {})
    if candidates.get("unknown_is_failure") is not False:
        errors.append("candidates.unknown_is_failure must be false")
    if candidates.get("unknown_destination") != "WAITING_DATA":
        errors.append("candidates.unknown_destination must be WAITING_DATA")
    if candidates.get("gate_results") != ["PASS", "FAIL", "UNKNOWN"]:
        errors.append("candidates.gate_results must be exactly PASS, FAIL, UNKNOWN")
    correlation = policy.get("correlation", {})
    if correlation.get("role_rejection_only") is not True:
        errors.append("correlation.role_rejection_only must be true")
    if correlation.get("company_rejection_allowed") is not False:
        errors.append("correlation.company_rejection_allowed must be false")
    minimum_allocation = policy.get("budget", {}).get("minimum_allocation_usd")
    try:
        valid_minimum = Decimal(str(minimum_allocation)) == Decimal("1.00")
    except InvalidOperation:
        valid_minimum = False
    if not valid_minimum:
        errors.append("budget.minimum_allocation_usd must be 1.00")
    safety = policy.get("safety", {})
    if safety.get("read_only") is not True:
        errors.append("safety.read_only must be true")
    if safety.get("recommendations_only") is not True:
        errors.append("safety.recommendations_only must be true")
    if safety.get("orders_allowed") is not False:
        errors.append("safety.orders_allowed must be false")
    if safety.get("robinhood_allowed_mutation_tools") != []:
        errors.append("safety.robinhood_allowed_mutation_tools must be empty")
    allowed_tools = safety.get("robinhood_allowed_tools")
    required_getters = safety.get("robinhood_required_getters")
    if not isinstance(allowed_tools, list) or not allowed_tools:
        errors.append("safety.robinhood_allowed_tools must be a nonempty list")
    if not isinstance(required_getters, list) or not required_getters:
        errors.append("safety.robinhood_required_getters must be a nonempty list")
    elif (
        len(set(required_getters)) != len(required_getters)
        or not isinstance(allowed_tools, list)
        or not set(required_getters).issubset(set(allowed_tools))
    ):
        errors.append(
            "safety.robinhood_required_getters must be unique and contained in robinhood_allowed_tools"
        )
    if (
        isinstance(required_getters, list)
        and required_getters
        and required_getters != CANONICAL_ROBINHOOD_RECONCILIATION_GETTERS
    ):
        errors.append(
            "safety.robinhood_required_getters must equal the six canonical reconciliation getters"
        )
    if safety.get("live_mcp_required_for_offline_state_validation") is not False:
        errors.append("safety.live_mcp_required_for_offline_state_validation must be false")
    if safety.get("runtime_catalog_required_for_completed_live_run") is not True:
        errors.append("safety.runtime_catalog_required_for_completed_live_run must be true")
    providers = policy.get("providers", {})
    if providers.get("robinhood", {}).get("schedule_eligible") is not True:
        errors.append("providers.robinhood.schedule_eligible must be true")
    if providers.get("primary_sources", {}).get("schedule_eligible") is not True:
        errors.append("providers.primary_sources.schedule_eligible must be true")
    if providers.get("exa", {}).get("schedule_eligible") is not False:
        errors.append("providers.exa.schedule_eligible must be false")
    automation = policy.get("automation", {})
    policy_status = policy.get("policy_status", {})
    owner_approval = policy.get("owner_approval")
    if not isinstance(owner_approval, dict):
        errors.append("owner_approval must be an object")
        target_approval = None
        manual_run_approval = None
        automation_approval = None
    else:
        target_approval = owner_approval.get("targets")
        manual_run_approval = owner_approval.get("manual_run")
        automation_approval = owner_approval.get("automation")
        if "targets" not in owner_approval or not (
            target_approval is None or isinstance(target_approval, dict)
        ):
            errors.append("owner_approval.targets must be explicitly null or an object")
            target_approval = None
        if "manual_run" not in owner_approval or not (
            manual_run_approval is None or isinstance(manual_run_approval, dict)
        ):
            errors.append("owner_approval.manual_run must be explicitly null or an object")
            manual_run_approval = None
        if "automation" in owner_approval and not (
            automation_approval is None or isinstance(automation_approval, dict)
        ):
            errors.append("owner_approval.automation must be null or an object")
            automation_approval = None

    if isinstance(target_approval, dict):
        if not _is_iso8601_timestamp_with_timezone(target_approval.get("approved_at")):
            errors.append(
                "owner_approval.targets.approved_at must be an ISO-8601 timestamp with timezone"
            )
        if target_approval.get("source") != "owner_message":
            errors.append("owner_approval.targets.source must be owner_message")
        if target_approval.get("profile_sha256") != _target_profile_sha256(policy):
            errors.append(
                "owner_approval.targets.profile_sha256 must match targets.sleeves"
            )

    if isinstance(manual_run_approval, dict):
        if not _is_iso8601_timestamp_with_timezone(
            manual_run_approval.get("reviewed_at")
        ):
            errors.append(
                "owner_approval.manual_run.reviewed_at must be an ISO-8601 timestamp with timezone"
            )
        if manual_run_approval.get("source") != "owner_message":
            errors.append("owner_approval.manual_run.source must be owner_message")
        run_key = manual_run_approval.get("run_key")
        if not isinstance(run_key, str) or re.fullmatch(
            r"\d{4}-\d{2}-\d{2}-(?:am|pm)", run_key
        ) is None:
            errors.append(
                "owner_approval.manual_run.run_key must match YYYY-MM-DD-am|pm"
            )
        evidence_id = manual_run_approval.get("evidence_id")
        if not isinstance(evidence_id, str) or not evidence_id.strip():
            errors.append(
                "owner_approval.manual_run.evidence_id must be a nonempty string"
            )

    direct_authorization_record_valid = False
    if isinstance(automation_approval, dict):
        direct_authorization_record_valid = True
        if not _is_iso8601_timestamp_with_timezone(
            automation_approval.get("authorized_at")
        ):
            errors.append(
                "owner_approval.automation.authorized_at must be an ISO-8601 timestamp with timezone"
            )
            direct_authorization_record_valid = False
        if automation_approval.get("source") != "owner_message":
            errors.append("owner_approval.automation.source must be owner_message")
            direct_authorization_record_valid = False
        if automation_approval.get("scope") != "recommendations_only":
            errors.append(
                "owner_approval.automation.scope must be recommendations_only"
            )
            direct_authorization_record_valid = False
        cadence = automation_approval.get("cadence")
        if not isinstance(cadence, str) or not cadence.strip():
            errors.append(
                "owner_approval.automation.cadence must be a nonempty string"
            )
            direct_authorization_record_valid = False

    if (
        policy_status.get("targets_approved") is True
        or policy_status.get("targets_enabled") is True
    ) and not isinstance(target_approval, dict):
        errors.append("approved or enabled targets require owner_approval.targets")

    if automation.get("catalog_unavailable_is_safety_block") is not True:
        errors.append("automation.catalog_unavailable_is_safety_block must be true")
    if automation.get("missing_required_getter_is_safety_block") is not True:
        errors.append("automation.missing_required_getter_is_safety_block must be true")
    if automation.get("status") not in {"DISABLED", "SAFETY_BLOCK", "READY", "ENABLED"}:
        errors.append("automation.status must be DISABLED, SAFETY_BLOCK, READY, or ENABLED")
    if automation.get("offline_state_status") not in {"VALID", "INVALID"}:
        errors.append("automation.offline_state_status must be VALID or INVALID")
    if automation.get("runtime_tool_isolation_status") not in {"UNVERIFIED", "FAILED", "VERIFIED"}:
        errors.append(
            "automation.runtime_tool_isolation_status must be UNVERIFIED, FAILED, or VERIFIED"
        )
    if automation.get("first_manual_run_status") not in {
        "NOT_RUN",
        "COMPLETE_AWAITING_OWNER_REVIEW",
        "OWNER_REVIEWED",
    }:
        errors.append(
            "automation.first_manual_run_status must be NOT_RUN, COMPLETE_AWAITING_OWNER_REVIEW, or OWNER_REVIEWED"
        )
    if automation.get("first_manual_run_status") == "OWNER_REVIEWED" and not isinstance(
        manual_run_approval, dict
    ):
        errors.append(
            "first_manual_run_status OWNER_REVIEWED requires owner_approval.manual_run"
        )
    activation_basis = automation.get("activation_basis")
    if activation_basis not in {
        None,
        "MANUAL_RUN_REVIEW",
        "OWNER_DIRECT_AUTHORIZATION",
    }:
        errors.append(
            "automation.activation_basis must be MANUAL_RUN_REVIEW or OWNER_DIRECT_AUTHORIZATION"
        )
    if (
        activation_basis == "OWNER_DIRECT_AUTHORIZATION"
        and not isinstance(automation_approval, dict)
    ):
        errors.append(
            "automation OWNER_DIRECT_AUTHORIZATION requires owner_approval.automation"
        )
    manual_run_authorized = (
        automation.get("first_manual_run_status") == "OWNER_REVIEWED"
        and isinstance(manual_run_approval, dict)
    )
    directly_authorized = (
        activation_basis == "OWNER_DIRECT_AUTHORIZATION"
        and direct_authorization_record_valid
        and safety.get("read_only") is True
        and safety.get("recommendations_only") is True
        and safety.get("orders_allowed") is False
        and safety.get("robinhood_allowed_mutation_tools") == []
    )
    activation_authorized = manual_run_authorized or directly_authorized
    if automation.get("schedule_registered") is True:
        if automation.get("enabled") is not True:
            errors.append(
                "automation.schedule_registered requires automation.enabled true"
            )
        if automation.get("status") != "ENABLED":
            errors.append(
                "automation.schedule_registered requires automation.status ENABLED"
            )
        if not (
            policy_status.get("targets_approved") is True
            and policy_status.get("targets_enabled") is True
        ):
            errors.append(
                "automation.schedule_registered requires approved and enabled targets"
            )
        if not activation_authorized:
            errors.append(
                "automation.schedule_registered requires first_manual_run_status OWNER_REVIEWED"
            )
    if automation.get("status") == "SAFETY_BLOCK" and not (
        automation.get("enabled") is False
        and automation.get("schedule_registered") is False
    ):
        errors.append(
            "automation.SAFETY_BLOCK requires enabled false and schedule_registered false"
        )
    if automation.get("status") == "ENABLED" and automation.get("enabled") is not True:
        errors.append("automation.status ENABLED requires automation.enabled true")
    if automation.get("enabled") is True and automation.get("status") != "ENABLED":
        errors.append("automation.enabled true requires status ENABLED")
    if automation.get("enabled") is True:
        if automation.get("runtime_tool_isolation_status") != "VERIFIED":
            errors.append(
                "automation.enabled requires runtime_tool_isolation_status VERIFIED"
            )
        if not (
            policy.get("policy_status", {}).get("targets_approved") is True
            and policy.get("policy_status", {}).get("targets_enabled") is True
        ):
            errors.append("automation.enabled requires approved and enabled targets")
        if not activation_authorized:
            errors.append(
                "automation.enabled requires first_manual_run_status OWNER_REVIEWED"
            )
        if automation.get("schedule_registered") is not True:
            errors.append("automation.enabled requires schedule_registered true")
        if not (isinstance(target_approval, dict) and activation_authorized):
            errors.append(
                "automation.enabled requires recorded target and manual-run owner approvals"
            )
    status = policy_status
    if status.get("targets_enabled") is True and status.get("targets_approved") is not True:
        errors.append("policy_status.targets_enabled requires targets_approved")
    if status.get("targets_approved"):
        sleeves = policy.get("targets", {}).get("sleeves", [])
        try:
            total = sum(float(sleeve.get("target_pct", 0)) for sleeve in sleeves)
            tolerance = float(policy.get("targets", {}).get("sum_tolerance_pct", 0))
        except (AttributeError, TypeError, ValueError):
            errors.append("targets.sleeves target_pct values must be numeric when approved")
        else:
            if abs(total - 100.0) <= tolerance:
                return errors
            errors.append(
                f"targets.sleeves target_pct must sum to 100 when approved (got {total:.1f})"
            )
    return errors


def validate_allocations(allocations, *, minimum_usd=1.00):
    """Validate proposed dollar allocations without touching a broker."""

    errors = []
    minimum = Decimal(str(minimum_usd))
    for index, allocation in enumerate(allocations):
        amount = Decimal(str(allocation.get("amount_usd")))
        if amount < minimum:
            errors.append(
                f"allocations[{index}].amount_usd must be at least {minimum:.2f}"
            )
    return errors


def validate_holding_actions(holdings):
    """Require one scalar BUY, HOLD, or SELL action per holding."""

    errors = []
    allowed = {"BUY", "HOLD", "SELL"}
    for index, holding in enumerate(holdings):
        action = holding.get("action")
        if not isinstance(action, str) or action not in allowed:
            errors.append(
                f"holdings[{index}].action must be exactly one of BUY, HOLD, SELL"
            )
    return errors


def _decimal(value, field, errors):
    """Decode a finite decimal field and append a stable error on failure."""

    try:
        result = Decimal(str(value))
    except (InvalidOperation, TypeError, ValueError):
        errors.append(f"{field} must be numeric")
        return None
    if not result.is_finite():
        errors.append(f"{field} must be finite")
        return None
    return result


def validate_portfolio(portfolio, policy):
    """Reconcile holdings, sleeves, actions, and official-close totals offline."""

    if not isinstance(portfolio, dict):
        return ["portfolio must be an object"]
    errors = []
    if portfolio.get("schema_version") != 1:
        errors.append("schema_version must be 1")
    holdings = portfolio.get("holdings")
    if not isinstance(holdings, list) or not holdings:
        return errors + ["holdings must be a non-empty list"]
    errors.extend(validate_holding_actions(holdings))
    allowed_sleeves = {
        sleeve.get("id")
        for sleeve in policy.get("targets", {}).get("sleeves", [])
        if isinstance(sleeve, dict)
    }
    allowed_flags = set(policy.get("verdicts", {}).get("operational_flags", []))
    seen_tickers = set()
    equity_total = Decimal("0")
    sleeve_holding_totals = {}
    for index, holding in enumerate(holdings):
        ticker = holding.get("ticker")
        if ticker in seen_tickers:
            errors.append(f"holdings has duplicate ticker {ticker}")
        seen_tickers.add(ticker)
        sleeve = holding.get("primary_sleeve")
        if sleeve not in allowed_sleeves:
            errors.append(f"holdings[{index}].primary_sleeve is not defined by policy targets")
        for flag in holding.get("flags", []):
            if flag not in allowed_flags:
                errors.append(f"holdings[{index}].flags contains unsupported value {flag}")
        quantity = _decimal(holding.get("quantity"), f"holdings[{index}].quantity", errors)
        price = _decimal(holding.get("price"), f"holdings[{index}].price", errors)
        market_value = _decimal(
            holding.get("market_value"), f"holdings[{index}].market_value", errors
        )
        if quantity is None or price is None or market_value is None:
            continue
        if abs((quantity * price) - market_value) > Decimal("0.01"):
            errors.append(
                f"holdings[{index}].market_value must equal quantity times price within 0.01"
            )
        equity_total += market_value
        sleeve_holding_totals[sleeve] = sleeve_holding_totals.get(sleeve, Decimal("0")) + market_value

    reconciliation = portfolio.get("reconciliation", {})
    expected_equity = _decimal(
        reconciliation.get("official_close_equity_value"),
        "reconciliation.official_close_equity_value",
        errors,
    )
    cash = _decimal(reconciliation.get("cash"), "reconciliation.cash", errors)
    expected_total = _decimal(
        reconciliation.get("official_close_total_value"),
        "reconciliation.official_close_total_value",
        errors,
    )
    if expected_equity is not None and abs(equity_total - expected_equity) > Decimal("0.01"):
        errors.append("holdings market values must reconcile to official_close_equity_value")
    if expected_total is not None and cash is not None:
        if abs((equity_total + cash) - expected_total) > Decimal("0.01"):
            errors.append("equity plus cash must reconcile to official_close_total_value")

    sleeves = portfolio.get("sleeves")
    if not isinstance(sleeves, list) or not sleeves:
        return errors + ["sleeves must be a non-empty list"]
    seen_sleeves = set()
    sleeve_value_total = Decimal("0")
    sleeve_weight_total = Decimal("0")
    for index, sleeve_row in enumerate(sleeves):
        name = sleeve_row.get("name")
        if name in seen_sleeves:
            errors.append(f"sleeves has duplicate name {name}")
        seen_sleeves.add(name)
        if name not in allowed_sleeves:
            errors.append(f"sleeves[{index}].name is not defined by policy targets")
        value = _decimal(sleeve_row.get("value"), f"sleeves[{index}].value", errors)
        weight = _decimal(
            sleeve_row.get("weight_pct"), f"sleeves[{index}].weight_pct", errors
        )
        if value is not None:
            sleeve_value_total += value
            if name == "cash_reserve" and cash is not None:
                expected_sleeve_value = cash
            else:
                expected_sleeve_value = sleeve_holding_totals.get(name, Decimal("0"))
            if abs(value - expected_sleeve_value) > Decimal("0.01"):
                errors.append(f"sleeves[{index}].value does not reconcile to its holdings")
        if weight is not None:
            sleeve_weight_total += weight
    if expected_total is not None and abs(sleeve_value_total - expected_total) > Decimal("0.01"):
        errors.append("sleeve values must reconcile to official_close_total_value")
    if abs(sleeve_weight_total - Decimal("100")) > Decimal("0.01"):
        errors.append("sleeve weights must sum to 100")
    return errors


def validate_budget(budget, policy):
    """Validate the modeled ledger separately from authoritative broker cash."""

    if not isinstance(budget, dict):
        return ["budget must be an object"]
    errors = []
    if budget.get("schema_version") != 1:
        errors.append("schema_version must be 1")
    contribution = _decimal(
        budget.get("modeled_daily_contribution"), "modeled_daily_contribution", errors
    )
    policy_contribution = _decimal(
        policy.get("budget", {}).get("modeled_daily_contribution_usd"),
        "policy budget contribution",
        errors,
    )
    if contribution is not None and policy_contribution is not None:
        if contribution != policy_contribution:
            errors.append("modeled_daily_contribution must match policy")
    accrued_dates = budget.get("contribution_accrued_for_dates", [])
    if len(accrued_dates) != len(set(accrued_dates)):
        errors.append("contribution_accrued_for_dates must be unique")
    allocations = budget.get("planned_allocations", [])
    minimum = policy.get("budget", {}).get("minimum_allocation_usd", 1)
    errors.extend(validate_allocations(allocations, minimum_usd=minimum))
    allocation_sum = Decimal("0")
    for index, allocation in enumerate(allocations):
        amount = _decimal(
            allocation.get("amount_usd"),
            f"planned_allocations[{index}].amount_usd",
            errors,
        )
        if amount is not None:
            allocation_sum += amount
    planned_total = _decimal(budget.get("planned_total"), "planned_total", errors)
    deployable = _decimal(budget.get("deployable_now"), "deployable_now", errors)
    broker = budget.get("broker", {})
    broker_cash = _decimal(broker.get("cash"), "broker.cash", errors)
    buying_power = _decimal(broker.get("buying_power"), "broker.buying_power", errors)
    reserve = _decimal(broker.get("open_order_reserve"), "broker.open_order_reserve", errors)
    ending_cash = _decimal(budget.get("ending_cash"), "ending_cash", errors)
    if planned_total is not None and planned_total != allocation_sum:
        errors.append("planned_total must equal the sum of planned_allocations")
    if deployable is not None and allocation_sum > deployable:
        errors.append("planned allocations must not exceed deployable_now")
    if deployable is not None and buying_power is not None and reserve is not None:
        if deployable > max(Decimal("0"), buying_power - reserve):
            errors.append("deployable_now must not exceed buying power after open-order reserve")
    if broker_cash is not None and planned_total is not None and ending_cash is not None:
        if ending_cash != broker_cash - planned_total:
            errors.append("ending_cash must equal broker cash minus planned_total")
    return errors


def validate_candidates(document, policy):
    """Enforce lifecycle, role-scoped failures, and UNKNOWN-to-WAITING_DATA."""

    if not isinstance(document, dict):
        return ["candidates document must be an object"]
    errors = []
    if document.get("schema_version") != 1:
        errors.append("schema_version must be 1")
    candidates = document.get("candidates")
    if not isinstance(candidates, list):
        return errors + ["candidates must be a list"]
    policy_candidates = policy.get("candidates", {})
    allowed_states = set(policy_candidates.get("states", []))
    allowed_results = set(policy_candidates.get("gate_results", []))
    allowed_sleeves = {
        sleeve.get("id")
        for sleeve in policy.get("targets", {}).get("sleeves", [])
        if isinstance(sleeve, dict)
    }
    seen = set()
    for index, candidate in enumerate(candidates):
        ticker = candidate.get("ticker")
        if ticker in seen:
            errors.append(f"candidates has duplicate ticker {ticker}")
        seen.add(ticker)
        state = candidate.get("state")
        if state not in allowed_states:
            errors.append(f"candidates[{index}].state is not allowed by policy")
        sleeve = candidate.get("primary_sleeve")
        if sleeve is not None and sleeve not in allowed_sleeves:
            errors.append(f"candidates[{index}].primary_sleeve is not defined by policy targets")
        gates = candidate.get("gates", [])
        results = [gate.get("result") for gate in gates if isinstance(gate, dict)]
        for result in results:
            if result not in allowed_results:
                errors.append(f"candidates[{index}] has unsupported gate result {result}")
        if "UNKNOWN" in results and state != "WAITING_DATA":
            errors.append(f"candidates[{index}] has UNKNOWN gates and must be WAITING_DATA")
        if state in {"QUALIFIED", "WAITING_CASH", "PROPOSED"} and any(
            result != "PASS" for result in results
        ):
            errors.append(f"candidates[{index}] cannot be {state} unless all gates PASS")
        if state == "REJECTED" and "UNKNOWN" in results:
            errors.append(f"candidates[{index}] cannot be REJECTED from UNKNOWN data")
    max_scouts = document.get("daily_full_scout_limit")
    if max_scouts != policy_candidates.get("maximum_full_scouts_per_trading_day"):
        errors.append("daily_full_scout_limit must match policy")
    completed_dates = document.get("scout_completed_for_dates", [])
    if len(completed_dates) != len(set(completed_dates)):
        errors.append("scout_completed_for_dates must be unique")
    return errors


def validate_evidence(document):
    """Require source identity, unique evidence IDs, and explicit time provenance."""

    if not isinstance(document, dict):
        return ["evidence must be an object"]
    errors = []
    if document.get("schema_version") != 1:
        errors.append("schema_version must be 1")
    records = document.get("records")
    if not isinstance(records, list):
        return errors + ["records must be a list"]
    seen = set()
    for index, record in enumerate(records):
        evidence_id = record.get("id")
        if evidence_id in seen:
            errors.append(f"evidence has duplicate id {evidence_id}")
        seen.add(evidence_id)
        if not record.get("source"):
            errors.append(f"evidence records[{index}].source is required")
        if not record.get("retrieval_completed_at") and not record.get(
            "retrieval_time_status"
        ):
            errors.append(
                f"evidence record {evidence_id} needs retrieval_completed_at or retrieval_time_status"
            )
    for conflict in document.get("provider_conflicts", []):
        if conflict.get("resolution") not in {"DISPLAY_SEPARATELY", "NOT_COMPARABLE"}:
            errors.append("provider conflict resolution must not merge consensus")
    return errors


def validate_rating_manifest(manifest, *, verify_source_files=True):
    """Validate dated screenshot evidence and optionally re-hash each source."""

    if not isinstance(manifest, dict):
        return ["rating manifest must be an object"]
    errors = []
    if manifest.get("schema_version") != 1:
        errors.append("schema_version must be 1")
    ratings_value = manifest.get("ratings")
    if not isinstance(ratings_value, list) or not ratings_value:
        errors.append("ratings must be a non-empty list")
        ratings_value = []
    seen_tickers = set()
    for index, rating in enumerate(ratings_value):
        ticker = rating.get("ticker")
        if ticker in seen_tickers:
            errors.append(f"ratings has duplicate ticker {ticker}")
        seen_tickers.add(ticker)
        percentage_total = sum(
            rating.get(field, 0) for field in ("buy_pct", "hold_pct", "sell_pct")
        )
        if percentage_total != 100:
            errors.append(
                f"ratings[{index}] percentages must sum to 100 (got {percentage_total})"
            )
        if verify_source_files:
            source_path = Path(rating.get("path", ""))
            if not source_path.is_file():
                errors.append(f"ratings[{index}].path does not exist")
                continue
            actual = hashlib.sha256(source_path.read_bytes()).hexdigest()
            if actual != rating.get("sha256"):
                errors.append(f"ratings[{index}].sha256 does not match source file")
    return errors


def validate_analyst_ratings(evidence):
    """Validate provider-specific Alpha Vantage analyst evidence offline."""

    if not isinstance(evidence, dict):
        return ["analyst ratings evidence must be an object"]
    errors = []
    if evidence.get("schema_version") != 1:
        errors.append("schema_version must be 1")
    alpha_value = evidence.get("alpha_vantage")
    if not isinstance(alpha_value, dict):
        errors.append("alpha_vantage must be an object")
        alpha_value = {}
    comparisons_value = evidence.get("cross_provider_comparisons")
    if not isinstance(comparisons_value, list):
        errors.append("cross_provider_comparisons must be a list")
        comparisons_value = []
    banned_fields = {
        "merged_consensus",
        "merged_ratings",
        "combined_consensus",
        "consensus_blend",
    }

    def walk(value, path="$."):
        if isinstance(value, dict):
            for key, child in value.items():
                child_path = f"{path}{key}"
                if key in banned_fields:
                    errors.append(f"merged consensus field is prohibited at {child_path}")
                walk(child, f"{child_path}.")
        elif isinstance(value, list):
            for list_index, child in enumerate(value):
                walk(child, f"{path}[{list_index}].")

    walk(evidence)
    fields = ("strong_buy", "buy", "hold", "sell", "strong_sell")
    alpha_vantage = alpha_value
    batch_ids = {
        batch.get("batch_id")
        for batch in alpha_vantage.get("retrieval_batches", [])
        if isinstance(batch, dict)
    }
    records = alpha_vantage.get("records", [])
    seen_tickers = set()
    for index, record in enumerate(records):
        ticker = record.get("ticker")
        if ticker in seen_tickers:
            errors.append(f"alpha_vantage.records has duplicate ticker {ticker}")
        seen_tickers.add(ticker)
        if record.get("batch_id") not in batch_ids:
            errors.append(
                f"alpha_vantage.records[{index}].batch_id must reference a retrieval batch"
            )
        if record.get("role") not in {"holding", "candidate"}:
            errors.append(
                f"alpha_vantage.records[{index}].role must be holding or candidate"
            )
        if record.get("status") not in {"COMPLETE", "MISSING"}:
            errors.append(
                f"alpha_vantage.records[{index}].status must be COMPLETE or MISSING"
            )
        ratings = record.get("ratings", {})
        source_values = [ratings.get(field) for field in fields]
        if all(isinstance(value, str) and value.isdigit() for value in source_values):
            expected_total = sum(int(value) for value in source_values)
            if ratings.get("total") != expected_total:
                errors.append(
                    f"alpha_vantage.records[{index}].ratings.total must equal {expected_total}"
                )
        elif "-" in source_values and ratings.get("total") is not None:
            errors.append(
                f"alpha_vantage.records[{index}].ratings.total must be null when any source count is '-'"
            )
    allowed_comparison_states = {"MATCH", "DIFFERS", "NOT_COMPARABLE"}
    for index, comparison in enumerate(comparisons_value):
        if comparison.get("status") not in allowed_comparison_states:
            errors.append(
                f"cross_provider_comparisons[{index}].status must be MATCH, DIFFERS, or NOT_COMPARABLE"
            )
    return errors


def main(argv=None):
    """Validate canonical files locally; never call an MCP or network service."""

    system_root = Path(__file__).resolve().parent.parent
    default_policy = system_root / "config" / "policy.yaml"
    default_rating_manifest = system_root / "state" / "rating-manifest.json"
    default_analyst_ratings = system_root / "state" / "analyst-ratings.json"
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--policy", type=Path, default=default_policy)
    parser.add_argument(
        "--rating-manifest",
        type=Path,
        default=default_rating_manifest,
    )
    parser.add_argument(
        "--analyst-ratings",
        type=Path,
        default=default_analyst_ratings,
    )
    parser.add_argument("--portfolio", type=Path)
    parser.add_argument("--candidates", type=Path)
    parser.add_argument("--budget", type=Path)
    parser.add_argument("--evidence", type=Path)
    parser.add_argument(
        "--skip-source-file-check",
        action="store_true",
        help="Validate screenshot metadata without re-hashing source images.",
    )
    args = parser.parse_args(argv)

    try:
        policy_document = load_document(args.policy)
    except (OSError, ValueError, json.JSONDecodeError) as exc:
        policy_document = {}
        all_errors = [f"policy: cannot load {args.policy}: {exc}"]
    else:
        all_errors = [f"policy: {error}" for error in validate_policy(policy_document)]
    labels = ["policy"]

    checks = [
        (
            "rating-manifest",
            args.rating_manifest,
            lambda value: validate_rating_manifest(
                value, verify_source_files=not args.skip_source_file_check
            ),
        ),
        ("analyst-ratings", args.analyst_ratings, validate_analyst_ratings),
    ]
    include_structured_state = any(
        path is not None
        for path in (args.portfolio, args.candidates, args.budget, args.evidence)
    ) or (
        args.policy == default_policy
        and args.rating_manifest == default_rating_manifest
        and args.analyst_ratings == default_analyst_ratings
    )
    if include_structured_state:
        checks.extend(
            [
                (
                    "portfolio",
                    args.portfolio or system_root / "state" / "portfolio.json",
                    lambda value: validate_portfolio(value, policy_document),
                ),
                (
                    "candidates",
                    args.candidates or system_root / "state" / "candidates.json",
                    lambda value: validate_candidates(value, policy_document),
                ),
                (
                    "budget",
                    args.budget or system_root / "state" / "budget.json",
                    lambda value: validate_budget(value, policy_document),
                ),
                (
                    "evidence",
                    args.evidence or system_root / "state" / "evidence.json",
                    validate_evidence,
                ),
            ]
        )
    for label, path, validator in checks:
        labels.append(label)
        try:
            document = load_document(path)
        except (OSError, ValueError, json.JSONDecodeError) as exc:
            all_errors.append(f"{label}: cannot load {path}: {exc}")
            continue
        for error in validator(document):
            all_errors.append(f"{label}: {error}")

    if all_errors:
        for error in all_errors:
            print(f"ERROR {error}")
        print(f"VALIDATION FAILED ({len(all_errors)} error(s))")
        return 1
    print(f"VALIDATION PASSED ({', '.join(labels)})")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
