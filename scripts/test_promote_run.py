"""Behavior tests for deterministic staged-state promotion."""

from __future__ import annotations

import json
import importlib.util
import shutil
import subprocess
import sys
import tempfile
import unittest
from datetime import datetime, timedelta, timezone
from pathlib import Path
from unittest import mock


SCRIPT_DIR = Path(__file__).resolve().parent
SOURCE_SYSTEM_ROOT = SCRIPT_DIR.parent
PROMOTER_PATH = SCRIPT_DIR / "promote_run.py"
STATE_FILES = (
    "portfolio.json",
    "candidates.json",
    "budget.json",
    "evidence.json",
    "rating-manifest.json",
    "analyst-ratings.json",
)

RUNTIME_ALLOWED_TOOLS = [
    "get_accounts",
    "get_earnings_calendar",
    "get_earnings_results",
    "get_equity_fundamentals",
    "get_equity_historicals",
    "get_equity_orders",
    "get_equity_positions",
    "get_equity_quotes",
    "get_equity_technical_indicators",
    "get_equity_tradability",
    "get_financials",
    "get_pnl_trade_history",
    "get_portfolio",
    "get_realized_pnl",
    "search",
]
REQUIRED_RECONCILIATION_GETTERS = [
    "get_accounts",
    "get_portfolio",
    "get_equity_positions",
    "get_equity_orders",
    "get_equity_quotes",
    "get_equity_tradability",
]


def inject_runtime_proof(staging_root, run_key, observed_at=None, **fact_overrides):
    state_root = Path(staging_root) / "state"
    evidence_path = state_root / "evidence.json"
    evidence = json.loads(evidence_path.read_text(encoding="utf-8"))
    portfolio = json.loads(
        (state_root / "portfolio.json").read_text(encoding="utf-8")
    )
    budget = json.loads((state_root / "budget.json").read_text(encoding="utf-8"))
    holding_count = len(portfolio["holdings"])
    if observed_at is None:
        observed_at = datetime.now(timezone.utc).isoformat()
    facts = {
        "run_key": run_key,
        "observed_at": observed_at,
        "tool_count": 15,
        "allowed_tools": list(RUNTIME_ALLOWED_TOOLS),
        "mutation_tools_present": [],
        "required_getters": list(REQUIRED_RECONCILIATION_GETTERS),
        "required_getters_succeeded": 6,
        "required_getters_total": 6,
        "position_count": holding_count,
        "quote_count": holding_count,
        "official_close_count": holding_count,
        "tradability_count": holding_count,
        "cash": portfolio["reconciliation"]["cash"],
        "buying_power": portfolio["reconciliation"]["buying_power"],
        "pending_deposits": portfolio["reconciliation"]["pending_deposits"],
        "unsettled_funds": portfolio["reconciliation"]["unsettled_funds"],
        "open_order_count": 0,
        "open_orders_reconciled": True,
        "open_order_reserve": budget["broker"]["open_order_reserve"],
        "open_order_issue": False,
        "mutation_tool_called": False,
    }
    facts.update(fact_overrides)
    evidence["records"].append(
        {
            "id": f"runtime-promotion-proof-{run_key}",
            "source": "Codex runtime catalog and Robinhood read-only reconciliation",
            "retrieval_completed_at": observed_at,
            "effective_date": run_key[:10],
            "status": "VERIFIED",
            "proof_type": "RUNTIME_CATALOG_LIVE_READ",
            "facts": facts,
        }
    )
    evidence_path.write_text(json.dumps(evidence, indent=2), encoding="utf-8")


def make_system_fixture(base, run_key="2026-08-11-am", observed_at=None):
    system_root = Path(base) / "SYSTEM"
    staging_root = system_root / "staging" / "incoming"
    (system_root / "config").mkdir(parents=True)
    (system_root / "state").mkdir()
    (system_root / "RUNS").mkdir()
    (staging_root / "config").mkdir(parents=True)
    (staging_root / "state").mkdir()
    (staging_root / "RUNS").mkdir()
    shutil.copy2(
        SOURCE_SYSTEM_ROOT / "config" / "policy.yaml",
        system_root / "config" / "policy.yaml",
    )
    shutil.copy2(
        SOURCE_SYSTEM_ROOT / "config" / "policy.yaml",
        staging_root / "config" / "policy.yaml",
    )
    for name in STATE_FILES:
        shutil.copy2(SOURCE_SYSTEM_ROOT / "state" / name, system_root / "state" / name)
        shutil.copy2(SOURCE_SYSTEM_ROOT / "state" / name, staging_root / "state" / name)
    for name in ("PORTFOLIO.md", "BENCH.md", "RULES.md"):
        shutil.copy2(SOURCE_SYSTEM_ROOT / name, system_root / name)
    (staging_root / "RUNS" / f"{run_key}.md").write_text(
        f"# {run_key} staged run\n\nNo allocation executed.\n",
        encoding="utf-8",
    )
    inject_runtime_proof(staging_root, run_key, observed_at=observed_at)
    return system_root, staging_root


def run_promoter(system_root, staging_root, run_key):
    return subprocess.run(
        [
            sys.executable,
            str(PROMOTER_PATH),
            "--system-root",
            str(system_root),
            "--staging-dir",
            str(staging_root),
            "--run-key",
            run_key,
        ],
        check=False,
        capture_output=True,
        text=True,
    )


def load_promoter_module():
    spec = importlib.util.spec_from_file_location("promote_run_under_test", PROMOTER_PATH)
    if spec is None or spec.loader is None:
        raise RuntimeError(f"cannot load {PROMOTER_PATH}")
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


class RuntimeProofGateTests(unittest.TestCase):
    def test_missing_run_bound_runtime_proof_fails_before_any_write(self):
        run_key = "2026-08-11-am"
        with tempfile.TemporaryDirectory() as temp_dir:
            system_root, staging_root = make_system_fixture(temp_dir, run_key)
            evidence_path = staging_root / "state" / "evidence.json"
            evidence = json.loads(evidence_path.read_text(encoding="utf-8"))
            evidence["records"] = [
                record
                for record in evidence["records"]
                if record.get("proof_type") != "RUNTIME_CATALOG_LIVE_READ"
            ]
            evidence_path.write_text(json.dumps(evidence), encoding="utf-8")
            canonical_path = system_root / "state" / "portfolio.json"
            canonical_before = canonical_path.read_bytes()
            promoter = load_promoter_module()

            with self.assertRaisesRegex(
                promoter.PromotionError, "runtime proof.*run key"
            ):
                promoter.promote_bundle(system_root, staging_root, run_key)

            self.assertEqual(canonical_before, canonical_path.read_bytes())
            self.assertFalse((system_root / "RUNS" / f"{run_key}.md").exists())

    def test_unparseable_runtime_proof_time_is_rejected(self):
        run_key = "2026-08-11-am"
        with tempfile.TemporaryDirectory() as temp_dir:
            system_root, staging_root = make_system_fixture(
                temp_dir, run_key, observed_at="not-a-timestamp"
            )
            promoter = load_promoter_module()

            with self.assertRaisesRegex(promoter.PromotionError, "observed_at"):
                promoter.promote_bundle(system_root, staging_root, run_key)

            self.assertFalse((system_root / "RUNS" / f"{run_key}.md").exists())

    def test_runtime_proof_older_than_thirty_minutes_is_rejected(self):
        run_key = "2026-08-11-am"
        reference_time = datetime(2026, 8, 11, 16, 0, tzinfo=timezone.utc)
        observed_at = (reference_time - timedelta(minutes=30, seconds=1)).isoformat()
        with tempfile.TemporaryDirectory() as temp_dir:
            system_root, staging_root = make_system_fixture(
                temp_dir, run_key, observed_at=observed_at
            )
            canonical_path = system_root / "state" / "portfolio.json"
            canonical_before = canonical_path.read_bytes()
            promoter = load_promoter_module()

            caught = None
            try:
                promoter.promote_bundle(
                    system_root,
                    staging_root,
                    run_key,
                    reference_time=reference_time,
                )
            except Exception as exc:  # assert the public failure type below
                caught = exc

            self.assertIsInstance(caught, promoter.PromotionError)
            self.assertIn("stale", str(caught).lower())
            self.assertEqual(canonical_before, canonical_path.read_bytes())
            self.assertFalse((system_root / "RUNS" / f"{run_key}.md").exists())

    def test_runtime_proof_too_far_in_the_future_is_rejected(self):
        run_key = "2026-08-11-am"
        reference_time = datetime(2026, 8, 11, 16, 0, tzinfo=timezone.utc)
        observed_at = (reference_time + timedelta(minutes=5, seconds=1)).isoformat()
        with tempfile.TemporaryDirectory() as temp_dir:
            system_root, staging_root = make_system_fixture(
                temp_dir, run_key, observed_at=observed_at
            )
            promoter = load_promoter_module()

            with self.assertRaisesRegex(promoter.PromotionError, "future"):
                promoter.promote_bundle(
                    system_root,
                    staging_root,
                    run_key,
                    reference_time=reference_time,
                )

            self.assertFalse((system_root / "RUNS" / f"{run_key}.md").exists())

    def test_runtime_proof_for_a_different_run_key_is_rejected(self):
        run_key = "2026-08-11-am"
        with tempfile.TemporaryDirectory() as temp_dir:
            system_root, staging_root = make_system_fixture(temp_dir, run_key)
            evidence_path = staging_root / "state" / "evidence.json"
            evidence = json.loads(evidence_path.read_text(encoding="utf-8"))
            proof = next(
                record
                for record in evidence["records"]
                if record.get("proof_type") == "RUNTIME_CATALOG_LIVE_READ"
            )
            proof["facts"]["run_key"] = "2026-08-11-pm"
            evidence_path.write_text(json.dumps(evidence), encoding="utf-8")
            promoter = load_promoter_module()

            with self.assertRaisesRegex(
                promoter.PromotionError, "runtime proof.*run key"
            ):
                promoter.promote_bundle(system_root, staging_root, run_key)

            self.assertFalse((system_root / "RUNS" / f"{run_key}.md").exists())

    def test_runtime_proof_record_metadata_must_match_run_and_observation(self):
        run_key = "2026-08-11-am"
        reference_time = datetime(2026, 8, 11, 16, 0, tzinfo=timezone.utc)
        cases = (
            ("wrong effective date", "effective_date", "2026-08-10", "effective date"),
            (
                "retrieval differs from observation",
                "retrieval_completed_at",
                "2026-08-11T15:00:00+00:00",
                "retrieval",
            ),
        )
        for label, field, value, expected_message in cases:
            with self.subTest(label=label), tempfile.TemporaryDirectory() as temp_dir:
                system_root, staging_root = make_system_fixture(
                    temp_dir,
                    run_key,
                    observed_at=reference_time.isoformat(),
                )
                evidence_path = staging_root / "state" / "evidence.json"
                evidence = json.loads(evidence_path.read_text(encoding="utf-8"))
                proof = next(
                    record
                    for record in evidence["records"]
                    if record.get("proof_type") == "RUNTIME_CATALOG_LIVE_READ"
                )
                proof[field] = value
                evidence_path.write_text(json.dumps(evidence), encoding="utf-8")
                promoter = load_promoter_module()

                with self.assertRaisesRegex(
                    promoter.PromotionError, expected_message
                ):
                    promoter.promote_bundle(
                        system_root,
                        staging_root,
                        run_key,
                        reference_time=reference_time,
                    )

                self.assertFalse(
                    (system_root / "RUNS" / f"{run_key}.md").exists()
                )

    def test_catalog_proof_requires_exact_inventory_and_accepts_reconciled_orders(self):
        run_key = "2026-08-11-am"
        reference_time = datetime(2026, 8, 11, 16, 0, tzinfo=timezone.utc)
        cases = (
            "inventory_reordered",
            "reconciled_open_order",
        )
        for case in cases:
            with self.subTest(case=case), tempfile.TemporaryDirectory() as temp_dir:
                system_root, staging_root = make_system_fixture(
                    temp_dir,
                    run_key,
                    observed_at=reference_time.isoformat(),
                )
                evidence_path = staging_root / "state" / "evidence.json"
                evidence = json.loads(evidence_path.read_text(encoding="utf-8"))
                proof = next(
                    record
                    for record in evidence["records"]
                    if record.get("proof_type") == "RUNTIME_CATALOG_LIVE_READ"
                )
                if case == "inventory_reordered":
                    proof["facts"]["allowed_tools"].reverse()
                    proof["facts"]["required_getters"].reverse()
                else:
                    proof["facts"]["open_order_count"] = 1
                    proof["facts"]["open_order_reserve"] = "2.00"
                    budget_path = staging_root / "state" / "budget.json"
                    budget = json.loads(budget_path.read_text(encoding="utf-8"))
                    budget["broker"]["open_order_reserve"] = "2.00"
                    budget_path.write_text(json.dumps(budget), encoding="utf-8")
                    portfolio_path = staging_root / "state" / "portfolio.json"
                    portfolio = json.loads(
                        portfolio_path.read_text(encoding="utf-8")
                    )
                    portfolio["reconciliation"]["open_order_reserve"] = "2.00"
                    portfolio_path.write_text(
                        json.dumps(portfolio), encoding="utf-8"
                    )
                evidence_path.write_text(json.dumps(evidence), encoding="utf-8")
                promoter = load_promoter_module()

                result = promoter.promote_bundle(
                    system_root,
                    staging_root,
                    run_key,
                    reference_time=reference_time,
                )

                self.assertEqual("PROMOTED", result)
                self.assertTrue((system_root / "RUNS" / f"{run_key}.md").exists())

    def test_unsafe_or_unreconciled_runtime_facts_are_rejected(self):
        run_key = "2026-08-11-am"
        reference_time = datetime(2026, 8, 11, 16, 0, tzinfo=timezone.utc)
        cases = (
            (
                "catalog not proven",
                {"tool_count": 14, "allowed_tools": []},
                "catalog",
            ),
            (
                "catalog names missing despite correct count",
                {"allowed_tools": None},
                "inventory",
            ),
            (
                "mutation tool present",
                {"mutation_tools_present": ["place_equity_order"]},
                "mutation",
            ),
            (
                "wrong required getter set",
                {"required_getters": REQUIRED_RECONCILIATION_GETTERS[:-1]},
                "required getter",
            ),
            (
                "required getter failed",
                {"required_getters_succeeded": 5},
                "required getter",
            ),
            (
                "mutation call made",
                {"mutation_tool_called": True},
                "mutation",
            ),
            (
                "quote count differs",
                {"quote_count": 21},
                "reconciliation",
            ),
            (
                "proof counts agree but not with staged holdings",
                {
                    "position_count": 21,
                    "quote_count": 21,
                    "official_close_count": 21,
                    "tradability_count": 21,
                },
                "staged portfolio",
            ),
            (
                "cash differs from staged state",
                {"cash": "999.00"},
                "cash",
            ),
            (
                "open orders not reconciled",
                {"open_orders_reconciled": False},
                "open order",
            ),
            (
                "open order reserve not accounted",
                {"open_order_count": 1, "open_order_reserve": "2.00"},
                "reserve",
            ),
            (
                "open order issue reported",
                {"open_order_issue": True},
                "open order",
            ),
        )
        for label, fact_overrides, expected_message in cases:
            with self.subTest(label=label), tempfile.TemporaryDirectory() as temp_dir:
                system_root, staging_root = make_system_fixture(
                    temp_dir,
                    run_key,
                    observed_at=reference_time.isoformat(),
                )
                evidence_path = staging_root / "state" / "evidence.json"
                evidence = json.loads(evidence_path.read_text(encoding="utf-8"))
                proof = next(
                    record
                    for record in evidence["records"]
                    if record.get("proof_type") == "RUNTIME_CATALOG_LIVE_READ"
                )
                proof["facts"].update(fact_overrides)
                evidence_path.write_text(json.dumps(evidence), encoding="utf-8")
                canonical_path = system_root / "state" / "portfolio.json"
                canonical_before = canonical_path.read_bytes()
                promoter = load_promoter_module()

                with self.assertRaisesRegex(
                    promoter.PromotionError, expected_message
                ):
                    promoter.promote_bundle(
                        system_root,
                        staging_root,
                        run_key,
                        reference_time=reference_time,
                    )

                self.assertEqual(canonical_before, canonical_path.read_bytes())
                self.assertFalse((system_root / "RUNS" / f"{run_key}.md").exists())


class PromoteRunCliTests(unittest.TestCase):
    def test_cli_rejects_a_run_key_that_can_escape_runs_directory(self):
        result = subprocess.run(
            [
                sys.executable,
                str(PROMOTER_PATH),
                "--run-key",
                "../escape",
            ],
            check=False,
            capture_output=True,
            text=True,
        )

        self.assertNotEqual(0, result.returncode)
        self.assertIn("invalid run key", result.stderr.lower())

    def test_invalid_staged_bundle_does_not_change_canonical_state(self):
        run_key = "2026-08-11-am"
        with tempfile.TemporaryDirectory() as temp_dir:
            system_root, staging_root = make_system_fixture(temp_dir, run_key)
            canonical_path = system_root / "state" / "portfolio.json"
            original = canonical_path.read_bytes()
            staged_path = staging_root / "state" / "portfolio.json"
            staged = json.loads(staged_path.read_text(encoding="utf-8"))
            staged["holdings"][0]["action"] = "ADD"
            staged_path.write_text(json.dumps(staged), encoding="utf-8")

            result = subprocess.run(
                [
                    sys.executable,
                    str(PROMOTER_PATH),
                    "--system-root",
                    str(system_root),
                    "--staging-dir",
                    str(staging_root),
                    "--run-key",
                    run_key,
                ],
                check=False,
                capture_output=True,
                text=True,
            )

            self.assertNotEqual(0, result.returncode)
            self.assertIn("validation failed", result.stderr.lower())
            self.assertEqual(original, canonical_path.read_bytes())
            self.assertFalse((system_root / "RUNS" / f"{run_key}.md").exists())

    def test_valid_bundle_promotes_state_and_renders_reports_from_staging(self):
        run_key = "2026-08-11-am"
        with tempfile.TemporaryDirectory() as temp_dir:
            system_root, staging_root = make_system_fixture(temp_dir, run_key)
            staged_path = staging_root / "state" / "portfolio.json"
            staged = json.loads(staged_path.read_text(encoding="utf-8"))
            ticker = staged["holdings"][0]["ticker"]
            staged["holdings"][0]["action"] = "BUY"
            staged_path.write_text(json.dumps(staged), encoding="utf-8")
            staged_evidence_path = staging_root / "state" / "evidence.json"
            staged_evidence = json.loads(
                staged_evidence_path.read_text(encoding="utf-8")
            )
            staged_evidence["unverified_claims"] = [
                {
                    "ticker": "FIXTURE",
                    "claim": "fixture-local report marker",
                    "required_sources": ["fixture source"],
                }
            ]
            staged_evidence_path.write_text(
                json.dumps(staged_evidence), encoding="utf-8"
            )

            result = subprocess.run(
                [
                    sys.executable,
                    str(PROMOTER_PATH),
                    "--system-root",
                    str(system_root),
                    "--staging-dir",
                    str(staging_root),
                    "--run-key",
                    run_key,
                ],
                check=False,
                capture_output=True,
                text=True,
            )

            canonical = json.loads(
                (system_root / "state" / "portfolio.json").read_text(encoding="utf-8")
            )
            portfolio_report = (system_root / "PORTFOLIO.md").read_text(encoding="utf-8")
            run_report = (system_root / "RUNS" / f"{run_key}.md").read_text(
                encoding="utf-8"
            ) if (system_root / "RUNS" / f"{run_key}.md").exists() else ""

            self.assertEqual(0, result.returncode, result.stdout + result.stderr)
            self.assertIn(f"PROMOTED {run_key}", result.stdout)
            self.assertEqual("BUY", canonical["holdings"][0]["action"])
            self.assertIn(f"| {ticker} | BUY |", portfolio_report)
            self.assertIn(
                "FIXTURE primary-source claims remain unverified", portfolio_report
            )
            self.assertIn(f"# {run_key} staged run", run_report)
            self.assertIn("promotion-sha256:", run_report)

    def test_identical_duplicate_run_is_a_noop(self):
        run_key = "2026-08-11-am"
        with tempfile.TemporaryDirectory() as temp_dir:
            system_root, staging_root = make_system_fixture(temp_dir, run_key)
            first = run_promoter(system_root, staging_root, run_key)
            self.assertEqual(0, first.returncode, first.stdout + first.stderr)
            report_path = system_root / "PORTFOLIO.md"
            report_path.write_text("newer canonical report\n", encoding="utf-8")

            duplicate = run_promoter(system_root, staging_root, run_key)

            self.assertEqual(0, duplicate.returncode, duplicate.stdout + duplicate.stderr)
            self.assertIn(f"IDEMPOTENT {run_key}", duplicate.stdout)
            self.assertEqual("newer canonical report\n", report_path.read_text(encoding="utf-8"))

    def test_conflicting_duplicate_run_fails_without_changing_canonical_files(self):
        run_key = "2026-08-11-am"
        with tempfile.TemporaryDirectory() as temp_dir:
            system_root, staging_root = make_system_fixture(temp_dir, run_key)
            first = run_promoter(system_root, staging_root, run_key)
            self.assertEqual(0, first.returncode, first.stdout + first.stderr)
            canonical_path = system_root / "state" / "portfolio.json"
            run_path = system_root / "RUNS" / f"{run_key}.md"
            canonical_before = canonical_path.read_bytes()
            run_before = run_path.read_bytes()
            staged_path = staging_root / "state" / "portfolio.json"
            staged = json.loads(staged_path.read_text(encoding="utf-8"))
            staged["holdings"][0]["action"] = "BUY"
            staged_path.write_text(json.dumps(staged), encoding="utf-8")

            duplicate = run_promoter(system_root, staging_root, run_key)

            self.assertNotEqual(0, duplicate.returncode)
            self.assertIn("conflicting duplicate run", duplicate.stderr.lower())
            self.assertEqual(canonical_before, canonical_path.read_bytes())
            self.assertEqual(run_before, run_path.read_bytes())

    def test_existing_lock_blocks_promotion_before_canonical_changes(self):
        run_key = "2026-08-11-am"
        with tempfile.TemporaryDirectory() as temp_dir:
            system_root, staging_root = make_system_fixture(temp_dir, run_key)
            canonical_path = system_root / "state" / "portfolio.json"
            canonical_before = canonical_path.read_bytes()
            lock_path = system_root / "staging" / ".promote.lock"
            lock_path.write_text("other process\n", encoding="utf-8")

            result = run_promoter(system_root, staging_root, run_key)

            self.assertNotEqual(0, result.returncode)
            self.assertIn("promotion lock is held", result.stderr.lower())
            self.assertEqual(canonical_before, canonical_path.read_bytes())
            self.assertTrue(lock_path.exists())
            self.assertFalse((system_root / "RUNS" / f"{run_key}.md").exists())

    def test_secret_bearing_staged_run_is_rejected_before_canonical_changes(self):
        run_key = "2026-08-11-am"
        with tempfile.TemporaryDirectory() as temp_dir:
            system_root, staging_root = make_system_fixture(temp_dir, run_key)
            canonical_path = system_root / "state" / "portfolio.json"
            canonical_before = canonical_path.read_bytes()
            staged_run = staging_root / "RUNS" / f"{run_key}.md"
            staged_run.write_text(
                "# staged\n\nAuthorization: Bearer fake_token_for_detection_123456\n",
                encoding="utf-8",
            )

            result = run_promoter(system_root, staging_root, run_key)

            self.assertNotEqual(0, result.returncode)
            self.assertIn("secret pattern", result.stderr.lower())
            self.assertEqual(canonical_before, canonical_path.read_bytes())
            self.assertFalse((system_root / "RUNS" / f"{run_key}.md").exists())

    def test_mid_transaction_failure_restores_every_canonical_file(self):
        run_key = "2026-08-11-am"
        with tempfile.TemporaryDirectory() as temp_dir:
            system_root, staging_root = make_system_fixture(temp_dir, run_key)
            staged_path = staging_root / "state" / "portfolio.json"
            staged = json.loads(staged_path.read_text(encoding="utf-8"))
            staged["holdings"][0]["action"] = "BUY"
            staged_path.write_text(json.dumps(staged), encoding="utf-8")
            canonical_paths = (
                [system_root / "config" / "policy.yaml"]
                + [system_root / "state" / name for name in STATE_FILES]
                + [system_root / name for name in ("PORTFOLIO.md", "BENCH.md", "RULES.md")]
            )
            before = {path: path.read_bytes() for path in canonical_paths}
            promoter = load_promoter_module()
            real_replace = promoter.os.replace
            replace_count = 0

            def fail_third_replace(source, destination):
                nonlocal replace_count
                replace_count += 1
                if replace_count == 3:
                    raise OSError("injected replace failure")
                return real_replace(source, destination)

            caught = None
            with mock.patch.object(promoter.os, "replace", side_effect=fail_third_replace):
                try:
                    promoter.promote_bundle(system_root, staging_root, run_key)
                except Exception as exc:  # inspect both type and filesystem outcome
                    caught = exc

            self.assertIsNotNone(caught)
            for path, original in before.items():
                self.assertEqual(original, path.read_bytes(), str(path))
            self.assertIsInstance(caught, promoter.PromotionError)
            self.assertIn("transaction failed", str(caught).lower())
            self.assertFalse((system_root / "RUNS" / f"{run_key}.md").exists())
            self.assertFalse((system_root / "staging" / ".promote.lock").exists())


if __name__ == "__main__":
    unittest.main(verbosity=2)
