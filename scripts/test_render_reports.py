"""Behavior tests for deterministic Markdown report rendering."""

from __future__ import annotations

import importlib.util
import json
import subprocess
import sys
import tempfile
import unittest
from pathlib import Path


SCRIPT_DIR = Path(__file__).resolve().parent
SYSTEM_ROOT = SCRIPT_DIR.parent
RENDERER_PATH = SCRIPT_DIR / "render_reports.py"


def load_renderer():
    spec = importlib.util.spec_from_file_location("render_reports", RENDERER_PATH)
    if spec is None or spec.loader is None:
        raise AssertionError("render_reports.py must be importable")
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def load_json(name):
    return json.loads((SYSTEM_ROOT / "state" / name).read_text(encoding="utf-8"))


class RenderBehaviorTests(unittest.TestCase):
    def test_negative_money_places_the_sign_before_the_currency_symbol(self):
        renderer = load_renderer()

        self.assertEqual("-$0.04", renderer._money("-0.04"))

    def test_portfolio_report_has_one_row_per_holding_and_only_canonical_actions(self):
        renderer = load_renderer()
        portfolio = load_json("portfolio.json")
        ratings = load_json("analyst-ratings.json")

        report = renderer.render_portfolio(portfolio, ratings)

        rows = [line for line in report.splitlines() if line.startswith("| ")]
        holding_rows = [line for line in rows if any(f"| {item['ticker']} |" in line for item in portfolio["holdings"])]
        self.assertEqual(22, len(holding_rows))
        self.assertNotIn("| ADD |", report)
        self.assertNotIn("| REVIEW |", report)
        self.assertIn("Observe-only", report)
        self.assertIn("Most positions remain low-confidence migration HOLDs", report)
        self.assertNotIn("Every position is HOLD with low confidence", report)

    def test_portfolio_blocks_are_derived_from_current_unverified_evidence(self):
        renderer = load_renderer()
        portfolio = load_json("portfolio.json")
        ratings = load_json("analyst-ratings.json")
        evidence = load_json("evidence.json")
        evidence["unverified_claims"] = [
            {
                "ticker": "TEST",
                "claim": "Fixture-local unresolved claim.",
                "required_sources": ["Fixture primary source"],
            }
        ]

        report = renderer.render_portfolio(portfolio, ratings, evidence)

        self.assertIn("TEST", report)
        self.assertIn("remain unverified", report)
        self.assertNotIn("PEG primary-source claims remain unverified", report)
        self.assertNotIn("CDNS's legacy insider-sale claim", report)

    def test_portfolio_sheet_reflects_active_targets_and_recommendation_only_scope(self):
        renderer = load_renderer()
        portfolio = load_json("portfolio.json")
        ratings = load_json("analyst-ratings.json")
        evidence = load_json("evidence.json")
        budget = load_json("budget.json")
        budget["if_funded_plan"] = {
            "status": "CONDITIONAL_BROKER_CONFIRMATION_REQUIRED",
            "assumed_new_cash": "20.00",
            "assumed_total_cash": "27.00",
            "planned_allocations": [
                {"ticker": "VT", "amount_usd": "15.00", "reason": "largest target gap"}
            ],
            "planned_total": "15.00",
            "ending_cash": "12.00",
        }
        policy = json.loads(
            (SYSTEM_ROOT / "config" / "policy.yaml").read_text(encoding="utf-8")
        )
        policy["policy_status"]["targets_approved"] = True
        policy["policy_status"]["targets_enabled"] = True
        policy["targets"]["status"] = "APPROVED_ENABLED"

        report = renderer.render_portfolio(
            portfolio,
            ratings,
            evidence,
            policy=policy,
            budget=budget,
        )

        self.assertIn("BUY / HOLD / SELL sheet", report)
        self.assertIn("Targets active", report)
        self.assertIn("recommendations only", report)
        self.assertIn("| Sleeve | Value | Weight | Target | Gap |", report)
        self.assertIn("## Money plan", report)
        self.assertIn("Right now", report)
        self.assertIn("| VT | $15.00 | largest target gap |", report)
        self.assertIn("Ending cash if funded: **$12.00**", report)
        self.assertNotIn("targets unapproved", report)
        self.assertNotIn("disabled until Aaron approves", report)

    def test_bench_report_distinguishes_rejected_evidence_from_waiting_data(self):
        renderer = load_renderer()
        candidates = load_json("candidates.json")

        report = renderer.render_bench(candidates)

        self.assertIn("| VT | CORE | WAITING_CASH |", report)
        self.assertIn("| LEU | THEME | WAITING_DATA |", report)
        self.assertIn("| ASPN | DIVERSIFIER | REJECTED |", report)
        self.assertIn("| UEC | THEME | REJECTED |", report)
        self.assertNotIn("ASPN/UEC:** missing broker financial fields", report)
        self.assertNotIn("Ready — in rank order", report)

    def test_bench_report_handles_a_qualified_candidate_waiting_for_cash(self):
        renderer = load_renderer()
        candidates = load_json("candidates.json")
        candidates["candidates"][0]["state"] = "WAITING_CASH"
        for gate in candidates["candidates"][0]["gates"]:
            gate["result"] = "PASS"

        report = renderer.render_bench(candidates)

        self.assertIn("| VT | CORE | WAITING_CASH |", report)
        self.assertIn("confirmed buying power", report)
        self.assertNotIn("No candidate is currently qualified for money", report)

    def test_rules_report_says_targets_are_disabled_and_floor_is_one_dollar(self):
        renderer = load_renderer()
        policy = json.loads((SYSTEM_ROOT / "config" / "policy.yaml").read_text(encoding="utf-8"))
        policy["targets"]["status"] = "PROPOSED_DISABLED"
        policy["policy_status"]["targets_approved"] = False
        policy["policy_status"]["targets_enabled"] = False
        policy["automation"]["enabled"] = False
        policy["automation"]["status"] = "DISABLED"

        report = renderer.render_rules(policy)

        self.assertIn("PROPOSED_DISABLED", report)
        self.assertIn("$1.00", report)
        self.assertIn("UNKNOWN → WAITING_DATA", report)
        self.assertIn("Automation:** disabled", report)
        self.assertIn("DISABLED", report)
        self.assertIn("runtime isolation VERIFIED", report)
        self.assertNotIn("SAFETY_BLOCK", report)
        self.assertNotIn("minimum $5", report)

    def test_rules_report_says_approved_targets_are_enabled(self):
        renderer = load_renderer()
        policy = json.loads(
            (SYSTEM_ROOT / "config" / "policy.yaml").read_text(encoding="utf-8")
        )
        policy["targets"]["status"] = "APPROVED_ENABLED"
        policy["policy_status"]["targets_approved"] = True
        policy["policy_status"]["targets_enabled"] = True
        policy["automation"]["enabled"] = True
        policy["automation"]["status"] = "ENABLED"

        report = renderer.render_rules(policy)

        self.assertIn("Approved targets - enabled", report)
        self.assertIn("Automation:** enabled", report)
        self.assertNotIn("cannot steer an allocation", report)


class RenderCliTests(unittest.TestCase):
    def test_cli_writes_all_three_reports_to_an_explicit_output_directory(self):
        with tempfile.TemporaryDirectory() as temp_dir:
            result = subprocess.run(
                [
                    sys.executable,
                    str(RENDERER_PATH),
                    "--system-root",
                    str(SYSTEM_ROOT),
                    "--output-dir",
                    temp_dir,
                ],
                check=False,
                capture_output=True,
                text=True,
            )
            output = Path(temp_dir)
            rendered = {path.name for path in output.iterdir()}

        self.assertEqual(0, result.returncode, result.stdout + result.stderr)
        self.assertEqual({"PORTFOLIO.md", "BENCH.md", "RULES.md"}, rendered)
        self.assertIn("Rendered 3 reports", result.stdout)


if __name__ == "__main__":
    unittest.main(verbosity=2)
