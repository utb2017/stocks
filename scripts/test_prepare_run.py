"""Behavior tests for deterministic daily-budget preparation."""

from __future__ import annotations

import copy
import importlib.util
import json
import subprocess
import sys
import tempfile
import unittest
from pathlib import Path


SCRIPT_DIR = Path(__file__).resolve().parent
PREPARE_PATH = SCRIPT_DIR / "prepare_run.py"


def load_prepare():
    spec = importlib.util.spec_from_file_location("prepare_run", PREPARE_PATH)
    if spec is None or spec.loader is None:
        raise AssertionError("prepare_run.py must be importable")
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def budget_fixture():
    return {
        "schema_version": 1,
        "generated_at": "2026-08-10T22:00:00-07:00",
        "status": "OBSERVE_ONLY",
        "modeled_daily_contribution": "20.00",
        "modeled_start_date": None,
        "modeled_rollover": "0.00",
        "contribution_accrued_for_dates": [],
        "broker": {
            "as_of": "2026-08-11T06:10:00-07:00",
            "cash": "27.00",
            "buying_power": "27.00",
            "pending_deposits": "0.00",
            "unsettled_funds": "0.00",
            "open_order_reserve": "0.00",
        },
        "policy": {
            "targets_approved": False,
            "targets_enabled": False,
            "cash_reserve_floor": None,
            "minimum_allocation": "1.00",
        },
        "deployable_now": "0.00",
        "deployable_reason": "old",
        "planned_allocations": [{"ticker": "VT", "amount_usd": "5.00"}],
        "planned_total": "5.00",
        "ending_cash": "22.00",
        "if_funded_plan": {"ticker": "VT"},
        "notes": [],
    }


def policy_fixture(*, approved):
    return {
        "budget": {"modeled_daily_contribution_usd": 20.0},
        "policy_status": {
            "targets_approved": approved,
            "targets_enabled": approved,
        },
        "targets": {
            "sleeves": [
                {"id": "broad_global_core", "target_pct": 30},
                {"id": "cash_reserve", "target_pct": 5},
            ]
        },
    }


class PrepareBudgetTests(unittest.TestCase):
    def test_open_trading_date_accrues_twenty_exactly_once(self):
        prepare = load_prepare()
        original = budget_fixture()

        first = prepare.prepare_budget(
            original,
            policy_fixture(approved=False),
            portfolio_total="157.00",
            trading_date="2026-08-11",
            market_is_open=True,
            generated_at="2026-08-11T13:10:00Z",
        )
        second = prepare.prepare_budget(
            first,
            policy_fixture(approved=False),
            portfolio_total="157.00",
            trading_date="2026-08-11",
            market_is_open=True,
            generated_at="2026-08-11T20:15:00Z",
        )

        self.assertEqual("20.00", first["modeled_rollover"])
        self.assertEqual("20.00", second["modeled_rollover"])
        self.assertEqual(["2026-08-11"], second["contribution_accrued_for_dates"])
        self.assertEqual("2026-08-11", second["modeled_start_date"])
        self.assertEqual(original, budget_fixture(), "prepare_budget must not mutate its input")

    def test_unapproved_targets_keep_deployable_zero_but_do_not_stop_accrual(self):
        prepare = load_prepare()

        result = prepare.prepare_budget(
            budget_fixture(),
            policy_fixture(approved=False),
            portfolio_total="157.00",
            trading_date="2026-08-11",
            market_is_open=True,
            generated_at="2026-08-11T13:10:00Z",
        )

        self.assertEqual("20.00", result["modeled_rollover"])
        self.assertEqual("0.00", result["deployable_now"])
        self.assertEqual("OBSERVE_ONLY", result["status"])
        self.assertEqual([], result["planned_allocations"])
        self.assertEqual("0.00", result["planned_total"])
        self.assertIsNone(result["if_funded_plan"])

    def test_approved_targets_preserve_five_percent_cash_and_cap_at_modeled_money(self):
        prepare = load_prepare()
        budget = budget_fixture()
        budget["modeled_rollover"] = "15.00"
        budget["contribution_accrued_for_dates"] = ["2026-08-10"]

        result = prepare.prepare_budget(
            budget,
            policy_fixture(approved=True),
            portfolio_total="157.00",
            trading_date="2026-08-11",
            market_is_open=True,
            generated_at="2026-08-11T13:10:00Z",
        )

        self.assertEqual("35.00", result["modeled_rollover"])
        self.assertEqual("7.85", result["policy"]["cash_reserve_floor"])
        self.assertEqual("19.15", result["deployable_now"])
        self.assertEqual("READY_FOR_ALLOCATION", result["status"])

    def test_cash_floor_is_subtracted_from_buying_power_when_buying_power_is_lower(self):
        prepare = load_prepare()
        budget = budget_fixture()
        budget["modeled_rollover"] = "30.00"
        budget["broker"]["cash"] = "100.00"
        budget["broker"]["buying_power"] = "20.00"

        result = prepare.prepare_budget(
            budget,
            policy_fixture(approved=True),
            portfolio_total="100.00",
            trading_date="2026-08-11",
            market_is_open=True,
            generated_at="2026-08-11T13:10:00Z",
        )

        self.assertEqual("5.00", result["policy"]["cash_reserve_floor"])
        self.assertEqual("15.00", result["deployable_now"])

    def test_closed_market_does_not_accrue_and_weekend_cannot_be_attested_open(self):
        prepare = load_prepare()
        closed = prepare.prepare_budget(
            budget_fixture(),
            policy_fixture(approved=False),
            portfolio_total="157.00",
            trading_date="2026-08-15",
            market_is_open=False,
            generated_at="2026-08-15T13:10:00Z",
        )

        self.assertEqual("0.00", closed["modeled_rollover"])
        self.assertEqual([], closed["contribution_accrued_for_dates"])
        with self.assertRaisesRegex(ValueError, "weekend"):
            prepare.prepare_budget(
                budget_fixture(),
                policy_fixture(approved=False),
                portfolio_total="157.00",
                trading_date="2026-08-15",
                market_is_open=True,
                generated_at="2026-08-15T13:10:00Z",
            )


class PrepareRunCliTests(unittest.TestCase):
    def test_cli_writes_prepared_budget_only_to_explicit_output(self):
        with tempfile.TemporaryDirectory() as temp_dir:
            root = Path(temp_dir)
            budget_path = root / "budget.json"
            policy_path = root / "policy.yaml"
            output_path = root / "staging" / "budget.json"
            original = budget_fixture()
            budget_path.write_text(json.dumps(original), encoding="utf-8")
            policy_path.write_text(
                json.dumps(policy_fixture(approved=False)), encoding="utf-8"
            )

            result = subprocess.run(
                [
                    sys.executable,
                    str(PREPARE_PATH),
                    "--budget",
                    str(budget_path),
                    "--policy",
                    str(policy_path),
                    "--output",
                    str(output_path),
                    "--portfolio-total",
                    "157.00",
                    "--trading-date",
                    "2026-08-11",
                    "--market-status",
                    "OPEN",
                    "--generated-at",
                    "2026-08-11T13:10:00Z",
                ],
                check=False,
                capture_output=True,
                text=True,
            )

            prepared = json.loads(output_path.read_text(encoding="utf-8"))
            unchanged = json.loads(budget_path.read_text(encoding="utf-8"))

        self.assertEqual(0, result.returncode, result.stdout + result.stderr)
        self.assertEqual("20.00", prepared["modeled_rollover"])
        self.assertEqual(original, unchanged)
        self.assertIn("PREPARED", result.stdout)


if __name__ == "__main__":
    unittest.main(verbosity=2)
