"""Offline tests for the deterministic portfolio-state validator."""

from __future__ import annotations

import importlib.util
import hashlib
import json
import subprocess
import sys
import tempfile
import unittest
from pathlib import Path


SCRIPT_DIR = Path(__file__).resolve().parent
VALIDATOR_PATH = SCRIPT_DIR / "validate_state.py"
POLICY_PATH = SCRIPT_DIR.parent / "config" / "policy.yaml"
STATE_DIR = SCRIPT_DIR.parent / "state"
PORTFOLIO_PATH = STATE_DIR / "portfolio.json"
CANDIDATES_PATH = STATE_DIR / "candidates.json"
BUDGET_PATH = STATE_DIR / "budget.json"
EVIDENCE_PATH = STATE_DIR / "evidence.json"


def load_validator():
    if not VALIDATOR_PATH.exists():
        raise AssertionError("validate_state.py must exist")
    spec = importlib.util.spec_from_file_location("validate_state", VALIDATOR_PATH)
    if spec is None or spec.loader is None:
        raise AssertionError("validate_state.py must be importable")
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def target_profile_sha256(sleeves):
    canonical = json.dumps(
        sleeves,
        ensure_ascii=False,
        sort_keys=True,
        separators=(",", ":"),
    )
    return hashlib.sha256(canonical.encode("utf-8")).hexdigest()


def valid_policy(*, targets_approved: bool = False, target_weights=None):
    if target_weights is None:
        target_weights = [30, 25, 15, 10, 10, 5, 5]
    policy = {
        "schema_version": 1,
        "policy_status": {
            "architecture_approved": True,
            "targets_approved": targets_approved,
            "targets_enabled": targets_approved,
        },
        "owner_approval": {
            "targets": None,
            "manual_run": None,
        },
        "verdicts": {
            "allowed_actions": ["BUY", "HOLD", "SELL"],
            "allowed_sell_scopes": ["TRIM", "EXIT"],
        },
        "budget": {
            "modeled_daily_contribution_usd": 20,
            "trading_days_only": True,
            "rollover_enabled": True,
            "credit_once_per_trading_date": True,
            "minimum_allocation_usd": 1,
            "broker_buying_power_is_cap": True,
        },
        "targets": {
            "approval_required": True,
            "sum_tolerance_pct": 0.01,
            "sleeves": [
                {"id": f"sleeve_{index}", "target_pct": weight}
                for index, weight in enumerate(target_weights)
            ],
        },
        "candidates": {
            "states": [
                "DISCOVERED",
                "RESEARCHING",
                "WAITING_DATA",
                "WAITING_EVENT",
                "QUALIFIED",
                "WAITING_CASH",
                "PROPOSED",
                "REJECTED",
                "OWNED",
            ],
            "gate_results": ["PASS", "FAIL", "UNKNOWN"],
            "unknown_is_failure": False,
            "unknown_destination": "WAITING_DATA",
            "promotion_requires_all_required_gates_pass": True,
        },
        "correlation": {
            "return_type": "close_to_close",
            "price_adjustment": "split_adjusted",
            "date_alignment": "inner_join",
            "windows": [28, 63, 250],
            "rolling_window": 63,
            "role_rejection_only": True,
            "company_rejection_allowed": False,
        },
        "providers": {
            "robinhood": {"enabled": True, "schedule_eligible": True, "role": "portfolio_source_of_truth"},
            "alpha_vantage": {"enabled": True, "schedule_eligible": True, "role": "research_supplement"},
            "primary_sources": {"enabled": True, "schedule_eligible": True, "role": "thesis_authority"},
            "firecrawl": {"enabled": True, "schedule_eligible": True, "role": "untrusted_primary_document_fetcher"},
            "rating_screenshots": {"enabled": True, "schedule_eligible": False, "role": "secondary_context"},
            "exa": {"enabled": False, "schedule_eligible": False, "role": "source_discovery_fallback"},
            "quiver": {"enabled": False, "schedule_eligible": False, "role": "alternative_data_optional"},
            "stocknews_mcp": {"enabled": False, "schedule_eligible": False, "role": "rejected"},
        },
        "automation": {
            "enabled": False,
            "status": "SAFETY_BLOCK",
            "schedule_registered": False,
            "offline_state_status": "VALID",
            "runtime_tool_isolation_status": "UNVERIFIED",
            "first_manual_run_status": "NOT_RUN",
            "catalog_unavailable_is_safety_block": True,
            "missing_required_getter_is_safety_block": True,
        },
        "safety": {
            "read_only": True,
            "recommendations_only": True,
            "orders_allowed": False,
            "live_mcp_required_for_offline_state_validation": False,
            "runtime_catalog_required_for_completed_live_run": True,
            "robinhood_allowed_tools": [
                "get_accounts",
                "get_portfolio",
                "get_equity_positions",
                "get_equity_orders",
                "get_equity_quotes",
                "get_equity_fundamentals",
                "get_financials",
                "get_earnings_results",
                "get_earnings_calendar",
                "get_equity_historicals",
                "get_equity_tradability",
                "get_equity_technical_indicators",
                "get_pnl_trade_history",
                "get_realized_pnl",
                "search",
            ],
            "robinhood_required_getters": [
                "get_accounts",
                "get_portfolio",
                "get_equity_positions",
                "get_equity_orders",
                "get_equity_quotes",
                "get_equity_tradability",
            ],
            "robinhood_allowed_mutation_tools": [],
        },
    }
    if targets_approved:
        policy["owner_approval"]["targets"] = {
            "approved_at": "2026-08-11T00:00:00-07:00",
            "source": "owner_message",
            "profile_sha256": target_profile_sha256(policy["targets"]["sleeves"]),
        }
    return policy


def valid_rating_manifest(image_path: Path, sha256: str):
    return {
        "schema_version": 1,
        "generated_at": "2026-08-10T20:30:00-07:00",
        "source_directory": str(image_path.parent),
        "capture_time_basis": "filesystem_modified_time",
        "policy": {
            "evidence_role": "secondary_context",
            "standalone_verdict_allowed": False,
            "stale_after_days": 7,
            "analyst_counts_are_inferred_from_displayed_percentages": True,
            "chart_endpoints_without_visible_labels": "not_extracted",
        },
        "ratings": [
            {
                "ticker": "PEG",
                "source": "Robinhood screenshot",
                "path": str(image_path),
                "sha256": sha256,
                "file_modified_at": "2026-08-10T20:14:52.946793-07:00",
                "displayed_price": 74.56,
                "analyst_count": 26,
                "buy_pct": 35,
                "hold_pct": 65,
                "sell_pct": 0,
                "inferred_buy_count": 9,
                "inferred_hold_count": 17,
                "inferred_sell_count": 0,
                "percentage_sum": 100,
                "extraction_confidence": "HIGH",
            }
        ],
    }


def valid_analyst_ratings():
    return {
        "schema_version": 1,
        "generated_at": "2026-08-10T22:30:00-07:00",
        "policy": {
            "evidence_is_provider_specific": True,
            "merged_consensus_allowed": False,
        },
        "alpha_vantage": {
            "tool": "COMPANY_OVERVIEW",
            "source_url": "https://mcp.alphavantage.co/mcp",
            "retrieval_batches": [
                {
                    "batch_id": "alpha-20260810-01",
                    "started_at": "2026-08-10T22:00:00-07:00",
                    "completed_at": "2026-08-10T22:01:00-07:00",
                    "symbols": ["PEG"],
                }
            ],
            "records": [
                {
                    "ticker": "PEG",
                    "role": "holding",
                    "batch_id": "alpha-20260810-01",
                    "name": "Public Service Enterprise Group Inc",
                    "latest_quarter": "2026-06-30",
                    "analyst_target_price": "87.29",
                    "ratings": {
                        "strong_buy": "1",
                        "buy": "8",
                        "hold": "13",
                        "sell": "0",
                        "strong_sell": "1",
                        "total": 23,
                    },
                    "status": "COMPLETE",
                    "error": None,
                }
            ],
        },
        "cross_provider_comparisons": [
            {
                "ticker": "PEG",
                "robinhood_capture_ref": "rating-manifest.json#PEG",
                "alpha_record_ref": "alpha_vantage.records#PEG",
                "status": "DIFFERS",
                "notes": ["Provider headcounts differ; do not merge."],
            }
        ],
    }


class PolicyValidationTests(unittest.TestCase):
    def test_unapproved_target_sum_is_not_enforced(self):
        validator = load_validator()
        policy = valid_policy(targets_approved=False, target_weights=[30, 20])

        self.assertEqual([], validator.validate_policy(policy))

    def test_approved_target_sum_must_equal_one_hundred_percent(self):
        validator = load_validator()
        policy = valid_policy(targets_approved=True, target_weights=[30, 20])

        errors = validator.validate_policy(policy)

        self.assertIn("targets.sleeves target_pct must sum to 100 when approved (got 50.0)", errors)

    def test_policy_rejects_any_action_outside_buy_hold_sell(self):
        validator = load_validator()
        policy = valid_policy()
        policy["verdicts"]["allowed_actions"].append("ADD")

        errors = validator.validate_policy(policy)

        self.assertIn("verdicts.allowed_actions must be exactly BUY, HOLD, SELL", errors)

    def test_policy_never_maps_unknown_to_failure_or_rejection(self):
        validator = load_validator()
        policy = valid_policy()
        policy["candidates"]["unknown_is_failure"] = True
        policy["candidates"]["unknown_destination"] = "REJECTED"

        errors = validator.validate_policy(policy)

        self.assertIn("candidates.unknown_is_failure must be false", errors)
        self.assertIn("candidates.unknown_destination must be WAITING_DATA", errors)

    def test_policy_rejects_trading_capability_and_scheduled_fallbacks(self):
        validator = load_validator()
        policy = valid_policy()
        policy["safety"]["read_only"] = False
        policy["safety"]["orders_allowed"] = True
        policy["safety"]["robinhood_allowed_mutation_tools"] = ["place_equity_order"]
        policy["providers"]["exa"]["schedule_eligible"] = True

        errors = validator.validate_policy(policy)

        self.assertIn("safety.read_only must be true", errors)
        self.assertIn("safety.orders_allowed must be false", errors)
        self.assertIn("safety.robinhood_allowed_mutation_tools must be empty", errors)
        self.assertIn("providers.exa.schedule_eligible must be false", errors)

    def test_automation_fails_closed_until_runtime_isolation_and_targets_are_approved(self):
        validator = load_validator()
        policy = valid_policy()
        policy["automation"]["enabled"] = True
        policy["automation"]["schedule_registered"] = True

        errors = validator.validate_policy(policy)

        self.assertIn(
            "automation.enabled requires runtime_tool_isolation_status VERIFIED",
            errors,
        )
        self.assertIn(
            "automation.enabled requires approved and enabled targets",
            errors,
        )
        self.assertIn(
            "automation.enabled requires first_manual_run_status OWNER_REVIEWED",
            errors,
        )

    def test_manual_run_must_be_owner_reviewed_before_automation(self):
        validator = load_validator()
        policy = valid_policy(targets_approved=True)
        policy["automation"].update(
            {
                "enabled": True,
                "status": "ENABLED",
                "schedule_registered": True,
                "runtime_tool_isolation_status": "VERIFIED",
                "first_manual_run_status": "COMPLETE_AWAITING_OWNER_REVIEW",
            }
        )

        errors = validator.validate_policy(policy)

        self.assertIn(
            "automation.enabled requires first_manual_run_status OWNER_REVIEWED",
            errors,
        )
        self.assertIn(
            "automation.enabled requires recorded target and manual-run owner approvals",
            errors,
        )

    def test_missing_catalog_or_required_getter_must_be_a_safety_block(self):
        validator = load_validator()
        policy = valid_policy()
        policy["automation"]["catalog_unavailable_is_safety_block"] = False
        policy["automation"]["missing_required_getter_is_safety_block"] = False

        errors = validator.validate_policy(policy)

        self.assertIn(
            "automation.catalog_unavailable_is_safety_block must be true",
            errors,
        )
        self.assertIn(
            "automation.missing_required_getter_is_safety_block must be true",
            errors,
        )

    def test_required_broker_getters_are_explicit_and_allowed(self):
        validator = load_validator()
        policy = valid_policy()
        del policy["safety"]["robinhood_required_getters"]

        errors = validator.validate_policy(policy)

        self.assertIn("safety.robinhood_required_getters must be a nonempty list", errors)

        policy = valid_policy()
        policy["safety"]["robinhood_required_getters"].append("get_missing_tool")
        errors = validator.validate_policy(policy)

        self.assertIn(
            "safety.robinhood_required_getters must be unique and contained in robinhood_allowed_tools",
            errors,
        )

        policy = valid_policy()
        policy["safety"]["robinhood_required_getters"] = ["search"]
        errors = validator.validate_policy(policy)

        self.assertIn(
            "safety.robinhood_required_getters must equal the six canonical reconciliation getters",
            errors,
        )

    def test_automation_status_and_schedule_registration_cannot_contradict_flags(self):
        validator = load_validator()
        policy = valid_policy()
        policy["automation"]["schedule_registered"] = True

        errors = validator.validate_policy(policy)

        self.assertIn(
            "automation.SAFETY_BLOCK requires enabled false and schedule_registered false",
            errors,
        )

        policy = valid_policy()
        policy["automation"]["status"] = "ENABLED"
        errors = validator.validate_policy(policy)

        self.assertIn(
            "automation.status ENABLED requires automation.enabled true",
            errors,
        )

    def test_registered_schedule_requires_every_activation_prerequisite(self):
        validator = load_validator()
        policy = valid_policy()
        policy["automation"].update(
            {
                "status": "READY",
                "schedule_registered": True,
            }
        )

        errors = validator.validate_policy(policy)

        self.assertIn(
            "automation.schedule_registered requires automation.enabled true",
            errors,
        )
        self.assertIn(
            "automation.schedule_registered requires automation.status ENABLED",
            errors,
        )
        self.assertIn(
            "automation.schedule_registered requires approved and enabled targets",
            errors,
        )
        self.assertIn(
            "automation.schedule_registered requires first_manual_run_status OWNER_REVIEWED",
            errors,
        )

    def test_approved_targets_require_a_recorded_owner_approval(self):
        validator = load_validator()
        policy = valid_policy(targets_approved=True)
        policy["owner_approval"]["targets"] = None

        errors = validator.validate_policy(policy)

        self.assertIn(
            "approved or enabled targets require owner_approval.targets",
            errors,
        )

    def test_target_approval_hash_must_match_the_current_profile(self):
        validator = load_validator()
        policy = valid_policy(targets_approved=True)
        policy["targets"]["sleeves"][0]["target_pct"] = 31
        policy["targets"]["sleeves"][1]["target_pct"] = 24

        errors = validator.validate_policy(policy)

        self.assertIn(
            "owner_approval.targets.profile_sha256 must match targets.sleeves",
            errors,
        )

    def test_target_approval_requires_timestamp_and_owner_message_source(self):
        validator = load_validator()
        policy = valid_policy(targets_approved=True)
        policy["owner_approval"]["targets"].update(
            {
                "approved_at": "yesterday",
                "source": "assistant_inference",
            }
        )

        errors = validator.validate_policy(policy)

        self.assertIn(
            "owner_approval.targets.approved_at must be an ISO-8601 timestamp with timezone",
            errors,
        )
        self.assertIn(
            "owner_approval.targets.source must be owner_message",
            errors,
        )

    def test_owner_reviewed_manual_run_requires_recorded_provenance(self):
        validator = load_validator()
        policy = valid_policy()
        policy["automation"]["first_manual_run_status"] = "OWNER_REVIEWED"

        errors = validator.validate_policy(policy)

        self.assertIn(
            "first_manual_run_status OWNER_REVIEWED requires owner_approval.manual_run",
            errors,
        )

    def test_manual_run_approval_requires_timestamp_source_run_key_and_evidence_id(self):
        validator = load_validator()
        policy = valid_policy()
        policy["automation"]["first_manual_run_status"] = "OWNER_REVIEWED"
        policy["owner_approval"]["manual_run"] = {
            "reviewed_at": "yesterday",
            "source": "assistant_inference",
            "run_key": "latest",
            "evidence_id": "",
        }

        errors = validator.validate_policy(policy)

        self.assertIn(
            "owner_approval.manual_run.reviewed_at must be an ISO-8601 timestamp with timezone",
            errors,
        )
        self.assertIn(
            "owner_approval.manual_run.source must be owner_message",
            errors,
        )
        self.assertIn(
            "owner_approval.manual_run.run_key must match YYYY-MM-DD-am|pm",
            errors,
        )
        self.assertIn(
            "owner_approval.manual_run.evidence_id must be a nonempty string",
            errors,
        )

    def test_enabled_automation_requires_both_recorded_owner_approvals(self):
        validator = load_validator()
        policy = valid_policy(targets_approved=True)
        policy["automation"].update(
            {
                "enabled": True,
                "status": "ENABLED",
                "schedule_registered": True,
                "runtime_tool_isolation_status": "VERIFIED",
                "first_manual_run_status": "OWNER_REVIEWED",
            }
        )

        errors = validator.validate_policy(policy)

        self.assertIn(
            "automation.enabled requires recorded target and manual-run owner approvals",
            errors,
        )

    def test_fully_proven_enabled_automation_policy_passes(self):
        validator = load_validator()
        policy = valid_policy(targets_approved=True)
        policy["owner_approval"]["manual_run"] = {
            "reviewed_at": "2026-08-11T00:15:00-07:00",
            "source": "owner_message",
            "run_key": "2026-08-10-pm",
            "evidence_id": "runtime-live-dry-run-2026-08-10",
        }
        policy["automation"].update(
            {
                "enabled": True,
                "status": "ENABLED",
                "schedule_registered": True,
                "runtime_tool_isolation_status": "VERIFIED",
                "first_manual_run_status": "OWNER_REVIEWED",
            }
        )

        self.assertEqual([], validator.validate_policy(policy))

    def test_direct_owner_authorization_can_enable_read_only_automation_without_fake_run_review(self):
        validator = load_validator()
        policy = valid_policy(targets_approved=True)
        policy["owner_approval"]["automation"] = {
            "authorized_at": "2026-08-11T00:45:00-07:00",
            "source": "owner_message",
            "scope": "recommendations_only",
            "cadence": "11:05_and_13:15_America/Los_Angeles",
        }
        policy["automation"].update(
            {
                "enabled": True,
                "status": "ENABLED",
                "schedule_registered": True,
                "runtime_tool_isolation_status": "VERIFIED",
                "first_manual_run_status": "NOT_RUN",
                "activation_basis": "OWNER_DIRECT_AUTHORIZATION",
            }
        )

        self.assertEqual([], validator.validate_policy(policy))

    def test_direct_owner_authorization_requires_timestamp_source_scope_and_cadence(self):
        validator = load_validator()
        policy = valid_policy(targets_approved=True)
        policy["owner_approval"]["automation"] = {
            "authorized_at": "today",
            "source": "assistant_inference",
            "scope": "trading",
            "cadence": "",
        }
        policy["automation"]["activation_basis"] = "OWNER_DIRECT_AUTHORIZATION"

        errors = validator.validate_policy(policy)

        self.assertIn(
            "owner_approval.automation.authorized_at must be an ISO-8601 timestamp with timezone",
            errors,
        )
        self.assertIn(
            "owner_approval.automation.source must be owner_message",
            errors,
        )
        self.assertIn(
            "owner_approval.automation.scope must be recommendations_only",
            errors,
        )
        self.assertIn(
            "owner_approval.automation.cadence must be a nonempty string",
            errors,
        )

    def test_direct_owner_authorization_cannot_bypass_recommendations_only_safety(self):
        validator = load_validator()
        policy = valid_policy(targets_approved=True)
        policy["owner_approval"]["automation"] = {
            "authorized_at": "2026-08-11T00:45:00-07:00",
            "source": "owner_message",
            "scope": "recommendations_only",
            "cadence": "11:05_and_13:15_America/Los_Angeles",
        }
        policy["automation"].update(
            {
                "enabled": True,
                "status": "ENABLED",
                "schedule_registered": True,
                "runtime_tool_isolation_status": "VERIFIED",
                "first_manual_run_status": "NOT_RUN",
                "activation_basis": "OWNER_DIRECT_AUTHORIZATION",
            }
        )
        policy["safety"]["recommendations_only"] = False

        errors = validator.validate_policy(policy)

        self.assertIn("safety.recommendations_only must be true", errors)

    def test_required_scheduled_sources_remain_eligible_but_do_not_imply_a_schedule(self):
        validator = load_validator()
        policy = valid_policy()
        policy["providers"]["robinhood"]["schedule_eligible"] = False
        policy["providers"]["primary_sources"]["schedule_eligible"] = False

        errors = validator.validate_policy(policy)

        self.assertIn("providers.robinhood.schedule_eligible must be true", errors)
        self.assertIn("providers.primary_sources.schedule_eligible must be true", errors)

    def test_policy_scopes_correlation_to_role_and_gate_results_to_three_states(self):
        validator = load_validator()
        policy = valid_policy()
        policy["candidates"]["gate_results"].append("SKIP")
        policy["correlation"]["role_rejection_only"] = False
        policy["correlation"]["company_rejection_allowed"] = True

        errors = validator.validate_policy(policy)

        self.assertIn("candidates.gate_results must be exactly PASS, FAIL, UNKNOWN", errors)
        self.assertIn("correlation.role_rejection_only must be true", errors)
        self.assertIn("correlation.company_rejection_allowed must be false", errors)

    def test_policy_sets_broker_fractional_floor_to_one_dollar(self):
        validator = load_validator()
        policy = valid_policy()
        policy["budget"]["minimum_allocation_usd"] = 0.99

        errors = validator.validate_policy(policy)

        self.assertIn("budget.minimum_allocation_usd must be 1.00", errors)

    def test_canonical_policy_loads_offline_with_approved_targets_and_enabled_automation(self):
        validator = load_validator()
        self.assertTrue(hasattr(validator, "load_document"), "load_document must exist")

        policy = validator.load_document(POLICY_PATH)

        self.assertEqual([], validator.validate_policy(policy))
        self.assertIs(policy["policy_status"]["targets_approved"], True)
        self.assertIs(policy["policy_status"]["targets_enabled"], True)
        self.assertIs(policy["automation"]["enabled"], True)
        self.assertEqual("ENABLED", policy["automation"]["status"])
        self.assertIs(policy["automation"]["schedule_registered"], True)
        self.assertEqual(2, len(policy["automation"]["registered_schedules"]))
        self.assertIsInstance(policy["owner_approval"]["targets"], dict)
        self.assertIsNone(policy["owner_approval"]["manual_run"])
        self.assertIsInstance(policy["owner_approval"]["automation"], dict)
        self.assertEqual(
            "OWNER_DIRECT_AUTHORIZATION", policy["automation"]["activation_basis"]
        )
        self.assertEqual(
            "VERIFIED", policy["automation"]["runtime_tool_isolation_status"]
        )

    def test_malformed_policy_returns_schema_errors_instead_of_crashing(self):
        validator = load_validator()

        try:
            errors = validator.validate_policy({})
        except Exception as exc:  # pragma: no cover - the assertion is the behavior
            self.fail(f"validator crashed on malformed policy: {exc}")

        self.assertIn("schema_version must be 1", errors)

    def test_unapproved_targets_cannot_be_enabled(self):
        validator = load_validator()
        policy = valid_policy(targets_approved=False)
        policy["policy_status"]["targets_enabled"] = True

        errors = validator.validate_policy(policy)

        self.assertIn("policy_status.targets_enabled requires targets_approved", errors)


class AllocationValidationTests(unittest.TestCase):
    def test_one_dollar_passes_and_ninety_nine_cents_fails(self):
        validator = load_validator()
        self.assertTrue(hasattr(validator, "validate_allocations"), "validate_allocations must exist")
        allocations = [
            {"ticker": "B", "amount_usd": 1.00},
            {"ticker": "VT", "amount_usd": 0.99},
        ]

        errors = validator.validate_allocations(allocations, minimum_usd=1.00)

        self.assertEqual(["allocations[1].amount_usd must be at least 1.00"], errors)


class HoldingValidationTests(unittest.TestCase):
    def test_each_holding_has_exactly_one_supported_action(self):
        validator = load_validator()
        self.assertTrue(hasattr(validator, "validate_holding_actions"), "validate_holding_actions must exist")
        holdings = [
            {"ticker": "PEG", "action": "HOLD"},
            {"ticker": "SAIC", "action": "ADD"},
            {"ticker": "TLN", "action": ["HOLD", "SELL"]},
        ]

        errors = validator.validate_holding_actions(holdings)

        self.assertEqual(
            [
                "holdings[1].action must be exactly one of BUY, HOLD, SELL",
                "holdings[2].action must be exactly one of BUY, HOLD, SELL",
            ],
            errors,
        )


class PortfolioStateValidationTests(unittest.TestCase):
    def test_canonical_portfolio_reconciles_positions_sleeves_and_actions(self):
        validator = load_validator()
        policy = validator.load_document(POLICY_PATH)
        portfolio = validator.load_document(PORTFOLIO_PATH)

        self.assertEqual([], validator.validate_portfolio(portfolio, policy))

    def test_portfolio_detects_a_position_value_that_no_longer_equals_quantity_times_price(self):
        validator = load_validator()
        policy = validator.load_document(POLICY_PATH)
        portfolio = validator.load_document(PORTFOLIO_PATH)
        portfolio["holdings"][0]["market_value"] = "999.00"

        errors = validator.validate_portfolio(portfolio, policy)

        self.assertIn(
            "holdings[0].market_value must equal quantity times price within 0.01",
            errors,
        )

    def test_portfolio_rejects_duplicate_tickers_and_unknown_primary_sleeves(self):
        validator = load_validator()
        policy = validator.load_document(POLICY_PATH)
        portfolio = validator.load_document(PORTFOLIO_PATH)
        portfolio["holdings"][1]["ticker"] = portfolio["holdings"][0]["ticker"]
        portfolio["holdings"][1]["primary_sleeve"] = "invented_sleeve"

        errors = validator.validate_portfolio(portfolio, policy)

        self.assertIn(f"holdings has duplicate ticker {portfolio['holdings'][0]['ticker']}", errors)
        self.assertIn("holdings[1].primary_sleeve is not defined by policy targets", errors)


class BudgetStateValidationTests(unittest.TestCase):
    def test_canonical_observe_only_budget_reconciles_without_inventing_the_daily_twenty(self):
        validator = load_validator()
        policy = validator.load_document(POLICY_PATH)
        budget = validator.load_document(BUDGET_PATH)

        self.assertEqual([], validator.validate_budget(budget, policy))

    def test_budget_rejects_allocations_above_deployable_cash_and_wrong_planned_total(self):
        validator = load_validator()
        policy = validator.load_document(POLICY_PATH)
        budget = validator.load_document(BUDGET_PATH)
        budget["deployable_now"] = "2.00"
        budget["planned_allocations"] = [{"ticker": "VT", "amount_usd": "3.00"}]
        budget["planned_total"] = "1.00"

        errors = validator.validate_budget(budget, policy)

        self.assertIn("planned_total must equal the sum of planned_allocations", errors)
        self.assertIn("planned allocations must not exceed deployable_now", errors)


class CandidateStateValidationTests(unittest.TestCase):
    def test_canonical_candidates_keep_unknown_data_out_of_qualified_and_rejected_states(self):
        validator = load_validator()
        policy = validator.load_document(POLICY_PATH)
        candidates = validator.load_document(CANDIDATES_PATH)

        self.assertEqual([], validator.validate_candidates(candidates, policy))

    def test_unknown_gate_requires_waiting_data(self):
        validator = load_validator()
        policy = validator.load_document(POLICY_PATH)
        candidates = validator.load_document(CANDIDATES_PATH)
        candidate_index = next(
            index
            for index, candidate in enumerate(candidates["candidates"])
            if any(gate.get("result") == "UNKNOWN" for gate in candidate["gates"])
        )
        candidates["candidates"][candidate_index]["state"] = "QUALIFIED"

        errors = validator.validate_candidates(candidates, policy)

        self.assertIn(
            f"candidates[{candidate_index}] has UNKNOWN gates and must be WAITING_DATA",
            errors,
        )


class EvidenceStateValidationTests(unittest.TestCase):
    def test_canonical_evidence_has_unique_ids_and_explicit_timestamp_status(self):
        validator = load_validator()
        evidence = validator.load_document(EVIDENCE_PATH)

        self.assertEqual([], validator.validate_evidence(evidence))

    def test_missing_retrieval_time_requires_an_explicit_status(self):
        validator = load_validator()
        evidence = validator.load_document(EVIDENCE_PATH)
        record = next(item for item in evidence["records"] if item["retrieval_completed_at"] is None)
        del record["retrieval_time_status"]

        errors = validator.validate_evidence(evidence)

        self.assertIn(
            f"evidence record {record['id']} needs retrieval_completed_at or retrieval_time_status",
            errors,
        )


class RatingManifestValidationTests(unittest.TestCase):
    def test_manifest_detects_changed_source_image(self):
        validator = load_validator()
        self.assertTrue(hasattr(validator, "validate_rating_manifest"), "validate_rating_manifest must exist")
        with tempfile.TemporaryDirectory() as temp_dir:
            image_path = Path(temp_dir) / "PEG Rating.jpeg"
            image_path.write_bytes(b"rating-image-v1")
            digest = hashlib.sha256(image_path.read_bytes()).hexdigest()
            manifest = valid_rating_manifest(image_path, digest)

            self.assertEqual([], validator.validate_rating_manifest(manifest, verify_source_files=True))

            image_path.write_bytes(b"rating-image-v2")
            errors = validator.validate_rating_manifest(manifest, verify_source_files=True)

        self.assertEqual(["ratings[0].sha256 does not match source file"], errors)

    def test_manifest_rejects_inconsistent_rating_percentages(self):
        validator = load_validator()
        with tempfile.TemporaryDirectory() as temp_dir:
            image_path = Path(temp_dir) / "PEG Rating.jpeg"
            image_path.write_bytes(b"rating-image")
            digest = hashlib.sha256(image_path.read_bytes()).hexdigest()
            manifest = valid_rating_manifest(image_path, digest)
            manifest["ratings"][0]["buy_pct"] = 34

            errors = validator.validate_rating_manifest(manifest, verify_source_files=False)

        self.assertIn("ratings[0] percentages must sum to 100 (got 99)", errors)

    def test_manifest_requires_the_versioned_top_level_schema(self):
        validator = load_validator()

        errors = validator.validate_rating_manifest({}, verify_source_files=False)

        self.assertIn("schema_version must be 1", errors)
        self.assertIn("ratings must be a non-empty list", errors)

    def test_manifest_rejects_duplicate_tickers(self):
        validator = load_validator()
        with tempfile.TemporaryDirectory() as temp_dir:
            image_path = Path(temp_dir) / "PEG Rating.jpeg"
            image_path.write_bytes(b"rating-image")
            digest = hashlib.sha256(image_path.read_bytes()).hexdigest()
            manifest = valid_rating_manifest(image_path, digest)
            manifest["ratings"].append(json.loads(json.dumps(manifest["ratings"][0])))

            errors = validator.validate_rating_manifest(manifest, verify_source_files=False)

        self.assertIn("ratings has duplicate ticker PEG", errors)


class AnalystRatingsValidationTests(unittest.TestCase):
    def test_numeric_rating_counts_must_equal_total(self):
        validator = load_validator()
        self.assertTrue(hasattr(validator, "validate_analyst_ratings"), "validate_analyst_ratings must exist")
        evidence = valid_analyst_ratings()

        self.assertEqual([], validator.validate_analyst_ratings(evidence))

        evidence["alpha_vantage"]["records"][0]["ratings"]["total"] = 24
        errors = validator.validate_analyst_ratings(evidence)

        self.assertIn("alpha_vantage.records[0].ratings.total must equal 23", errors)

    def test_missing_source_values_require_null_total_not_zero(self):
        validator = load_validator()
        evidence = valid_analyst_ratings()
        record = evidence["alpha_vantage"]["records"][0]
        for field in ("strong_buy", "buy", "hold", "sell", "strong_sell"):
            record["ratings"][field] = "-"
        record["ratings"]["total"] = None
        record["status"] = "MISSING"
        record["error"] = "ratings unavailable"

        self.assertEqual([], validator.validate_analyst_ratings(evidence))

        record["ratings"]["total"] = 0
        errors = validator.validate_analyst_ratings(evidence)

        self.assertIn("alpha_vantage.records[0].ratings.total must be null when any source count is '-'", errors)

    def test_duplicate_alpha_vantage_tickers_are_rejected(self):
        validator = load_validator()
        evidence = valid_analyst_ratings()
        duplicate = json.loads(json.dumps(evidence["alpha_vantage"]["records"][0]))
        evidence["alpha_vantage"]["records"].append(duplicate)

        errors = validator.validate_analyst_ratings(evidence)

        self.assertIn("alpha_vantage.records has duplicate ticker PEG", errors)

    def test_cross_provider_values_cannot_be_merged_into_consensus(self):
        validator = load_validator()
        evidence = valid_analyst_ratings()
        evidence["merged_consensus"] = {"PEG": {"buy_pct": 50}}

        errors = validator.validate_analyst_ratings(evidence)

        self.assertIn("merged consensus field is prohibited at $.merged_consensus", errors)

    def test_records_require_known_batch_and_enumerated_source_states(self):
        validator = load_validator()
        evidence = valid_analyst_ratings()
        record = evidence["alpha_vantage"]["records"][0]
        record["batch_id"] = "missing-batch"
        record["role"] = "watch"
        record["status"] = "UNKNOWN"
        comparison = evidence["cross_provider_comparisons"][0]
        comparison["status"] = "MERGED"

        errors = validator.validate_analyst_ratings(evidence)

        self.assertIn("alpha_vantage.records[0].batch_id must reference a retrieval batch", errors)
        self.assertIn("alpha_vantage.records[0].role must be holding or candidate", errors)
        self.assertIn("alpha_vantage.records[0].status must be COMPLETE or MISSING", errors)
        self.assertIn("cross_provider_comparisons[0].status must be MATCH, DIFFERS, or NOT_COMPARABLE", errors)

    def test_analyst_evidence_requires_the_versioned_top_level_schema(self):
        validator = load_validator()

        errors = validator.validate_analyst_ratings({})

        self.assertIn("schema_version must be 1", errors)
        self.assertIn("alpha_vantage must be an object", errors)
        self.assertIn("cross_provider_comparisons must be a list", errors)


class CommandLineValidationTests(unittest.TestCase):
    def test_cli_validates_all_three_documents_without_live_mcp(self):
        with tempfile.TemporaryDirectory() as temp_dir:
            root = Path(temp_dir)
            image_path = root / "PEG Rating.jpeg"
            image_path.write_bytes(b"rating-image")
            digest = hashlib.sha256(image_path.read_bytes()).hexdigest()
            documents = {
                "policy.yaml": valid_policy(),
                "rating-manifest.json": valid_rating_manifest(image_path, digest),
                "analyst-ratings.json": valid_analyst_ratings(),
            }
            for filename, document in documents.items():
                (root / filename).write_text(json.dumps(document), encoding="utf-8")

            result = subprocess.run(
                [
                    sys.executable,
                    str(VALIDATOR_PATH),
                    "--policy",
                    str(root / "policy.yaml"),
                    "--rating-manifest",
                    str(root / "rating-manifest.json"),
                    "--analyst-ratings",
                    str(root / "analyst-ratings.json"),
                    "--skip-source-file-check",
                ],
                check=False,
                capture_output=True,
                text=True,
            )

        self.assertEqual(0, result.returncode, result.stdout + result.stderr)
        self.assertIn("VALIDATION PASSED", result.stdout)

    def test_cli_validates_the_complete_canonical_state_bundle(self):
        result = subprocess.run(
            [
                sys.executable,
                str(VALIDATOR_PATH),
                "--policy",
                str(POLICY_PATH),
                "--rating-manifest",
                str(STATE_DIR / "rating-manifest.json"),
                "--analyst-ratings",
                str(STATE_DIR / "analyst-ratings.json"),
                "--portfolio",
                str(PORTFOLIO_PATH),
                "--candidates",
                str(CANDIDATES_PATH),
                "--budget",
                str(BUDGET_PATH),
                "--evidence",
                str(EVIDENCE_PATH),
            ],
            check=False,
            capture_output=True,
            text=True,
        )

        self.assertEqual(0, result.returncode, result.stdout + result.stderr)
        self.assertIn(
            "VALIDATION PASSED (policy, rating-manifest, analyst-ratings, portfolio, candidates, budget, evidence)",
            result.stdout,
        )


if __name__ == "__main__":
    unittest.main(verbosity=2)
