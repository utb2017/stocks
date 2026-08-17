"""Validate and atomically promote one staged stock-system run."""

from __future__ import annotations

import argparse
from contextlib import contextmanager
from datetime import date, datetime, timedelta, timezone
from decimal import Decimal, InvalidOperation
import hashlib
import importlib.util
import json
import os
from pathlib import Path
import re
import sys
import tempfile


RUN_KEY_PATTERN = re.compile(r"\A(\d{4}-\d{2}-\d{2})-(am|pm)\Z")
MAX_RUNTIME_PROOF_AGE = timedelta(minutes=30)
MAX_RUNTIME_PROOF_FUTURE_SKEW = timedelta(minutes=5)
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
SECRET_PATTERNS = (
    re.compile(
        rb"\bauthorization\s*:\s*bearer\s+[A-Za-z0-9._~+/=_-]{8,}",
        re.IGNORECASE,
    ),
    re.compile(
        rb"\b(?:api[_-]?key|access[_-]?token|client[_-]?secret)\s*[=:]\s*[\"']?[A-Za-z0-9._~+/=_-]{8,}",
        re.IGNORECASE,
    ),
)


class PromotionError(RuntimeError):
    """A staged bundle cannot be safely promoted."""


def _load_sibling_module(name):
    path = Path(__file__).resolve().parent / f"{name}.py"
    spec = importlib.util.spec_from_file_location(f"stocks_daily_{name}", path)
    if spec is None or spec.loader is None:
        raise PromotionError(f"cannot load required module {path}")
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


VALIDATOR = _load_sibling_module("validate_state")
RENDERER = _load_sibling_module("render_reports")


STAGED_DOCUMENTS = {
    "policy": Path("config/policy.yaml"),
    "portfolio": Path("state/portfolio.json"),
    "candidates": Path("state/candidates.json"),
    "budget": Path("state/budget.json"),
    "evidence": Path("state/evidence.json"),
    "rating-manifest": Path("state/rating-manifest.json"),
    "analyst-ratings": Path("state/analyst-ratings.json"),
}


def validate_run_key(value):
    """Return a canonical run key or raise without resolving a path."""

    match = RUN_KEY_PATTERN.fullmatch(value)
    if match is None:
        raise PromotionError(f"invalid run key: {value!r}")
    try:
        date.fromisoformat(match.group(1))
    except ValueError as exc:
        raise PromotionError(f"invalid run key: {value!r}") from exc
    return value


def _load_staged_document(staging_root, relative_path):
    path = staging_root / relative_path
    if path.is_symlink():
        raise PromotionError(f"staged file must not be a symlink: {relative_path}")
    try:
        return VALIDATOR.load_document(path)
    except (OSError, ValueError, json.JSONDecodeError) as exc:
        raise PromotionError(f"cannot load staged {relative_path}: {exc}") from exc


def validate_staged_bundle(staging_root):
    """Load and fully validate every required staged state document."""

    root = Path(staging_root)
    documents = {
        label: _load_staged_document(root, relative_path)
        for label, relative_path in STAGED_DOCUMENTS.items()
    }
    policy = documents["policy"]
    checks = (
        ("policy", VALIDATOR.validate_policy(policy)),
        (
            "rating-manifest",
            VALIDATOR.validate_rating_manifest(
                documents["rating-manifest"], verify_source_files=True
            ),
        ),
        (
            "analyst-ratings",
            VALIDATOR.validate_analyst_ratings(documents["analyst-ratings"]),
        ),
        ("portfolio", VALIDATOR.validate_portfolio(documents["portfolio"], policy)),
        ("candidates", VALIDATOR.validate_candidates(documents["candidates"], policy)),
        ("budget", VALIDATOR.validate_budget(documents["budget"], policy)),
        ("evidence", VALIDATOR.validate_evidence(documents["evidence"])),
    )
    errors = [f"{label}: {error}" for label, values in checks for error in values]
    if errors:
        raise PromotionError("validation failed: " + "; ".join(errors))
    return documents


def _parse_timezone_aware_timestamp(value, field):
    try:
        normalized = value[:-1] + "+00:00" if value.endswith("Z") else value
        parsed = datetime.fromisoformat(normalized)
        if parsed.tzinfo is None or parsed.utcoffset() is None:
            raise ValueError("timezone is required")
        return parsed.astimezone(timezone.utc)
    except (AttributeError, TypeError, ValueError) as exc:
        raise PromotionError(f"{field} must be a timezone-aware timestamp") from exc


def _is_exact_string_inventory(value, expected):
    return (
        isinstance(value, list)
        and len(value) == len(expected)
        and all(isinstance(item, str) for item in value)
        and set(value) == set(expected)
    )


def _require_runtime_proof(documents, run_key, reference_time=None):
    records = documents.get("evidence", {}).get("records", [])
    matching = [
        record
        for record in records
        if record.get("proof_type") == "RUNTIME_CATALOG_LIVE_READ"
        and record.get("facts", {}).get("run_key") == run_key
    ]
    if not matching:
        raise PromotionError(f"runtime proof is missing for run key {run_key}")
    if len(matching) != 1:
        raise PromotionError(f"runtime proof is ambiguous for run key {run_key}")
    proof = matching[-1]
    if proof.get("status") not in {"VERIFIED", "COMPLETE"}:
        raise PromotionError("runtime proof status must be VERIFIED or COMPLETE")
    if proof.get("effective_date") != run_key[:10]:
        raise PromotionError("runtime proof effective date must match the run key")
    facts = proof.get("facts", {})
    observed_at = facts.get("observed_at")
    observed = _parse_timezone_aware_timestamp(observed_at, "runtime proof observed_at")
    retrieved = _parse_timezone_aware_timestamp(
        proof.get("retrieval_completed_at"),
        "runtime proof retrieval_completed_at",
    )
    if retrieved != observed:
        raise PromotionError(
            "runtime proof retrieval timestamp must equal its observed_at timestamp"
        )
    if reference_time is None:
        reference = datetime.now(timezone.utc)
    elif isinstance(reference_time, datetime):
        if reference_time.tzinfo is None or reference_time.utcoffset() is None:
            raise PromotionError("reference_time must be timezone-aware")
        reference = reference_time.astimezone(timezone.utc)
    else:
        reference = _parse_timezone_aware_timestamp(reference_time, "reference_time")
    if reference - observed > MAX_RUNTIME_PROOF_AGE:
        raise PromotionError("runtime proof is stale (older than 30 minutes)")
    if observed - reference > MAX_RUNTIME_PROOF_FUTURE_SKEW:
        raise PromotionError("runtime proof observed_at is too far in the future")

    tool_count = facts.get("tool_count")
    allowed_tools = facts.get("allowed_tools")
    if tool_count != len(RUNTIME_ALLOWED_TOOLS):
        raise PromotionError("runtime catalog tool_count must be 15")
    if not _is_exact_string_inventory(allowed_tools, RUNTIME_ALLOWED_TOOLS):
        raise PromotionError("runtime catalog inventory must equal the read-only allowlist")
    if facts.get("mutation_tools_present") != []:
        raise PromotionError("runtime catalog contains or does not exclude mutation tools")
    if not _is_exact_string_inventory(
        facts.get("required_getters"), REQUIRED_RECONCILIATION_GETTERS
    ):
        raise PromotionError("runtime proof required getter set is incomplete")
    if not (
        facts.get("required_getters_succeeded") == len(REQUIRED_RECONCILIATION_GETTERS)
        and facts.get("required_getters_total") == len(REQUIRED_RECONCILIATION_GETTERS)
    ):
        raise PromotionError("runtime proof must show all six required getters succeeded")
    if facts.get("mutation_tool_called") is not False:
        raise PromotionError("runtime proof must show no mutation tool was called")

    reconciliation_counts = [
        facts.get(field)
        for field in (
            "position_count",
            "quote_count",
            "official_close_count",
            "tradability_count",
        )
    ]
    if any(
        isinstance(value, bool) or not isinstance(value, int) or value <= 0
        for value in reconciliation_counts
    ) or len(set(reconciliation_counts)) != 1:
        raise PromotionError(
            "runtime position/quote/close/tradability reconciliation counts must match"
        )
    portfolio = documents.get("portfolio", {})
    holdings = portfolio.get("holdings", [])
    staged_holding_count = len(holdings) if isinstance(holdings, list) else -1
    recorded_holding_count = portfolio.get("reconciliation", {}).get("holding_count")
    if (
        staged_holding_count <= 0
        or isinstance(recorded_holding_count, bool)
        or not isinstance(recorded_holding_count, int)
        or recorded_holding_count != staged_holding_count
        or reconciliation_counts[0] != staged_holding_count
    ):
        raise PromotionError(
            "runtime reconciliation counts must equal the staged portfolio holding count"
        )

    portfolio_reconciliation = portfolio.get("reconciliation", {})
    budget_broker = documents.get("budget", {}).get("broker", {})
    for field in ("cash", "buying_power", "pending_deposits", "unsettled_funds"):
        try:
            proof_amount = Decimal(str(facts.get(field)))
            portfolio_amount = Decimal(str(portfolio_reconciliation.get(field)))
            budget_amount = Decimal(str(budget_broker.get(field)))
        except (InvalidOperation, TypeError, ValueError) as exc:
            raise PromotionError(f"runtime {field} must be numeric") from exc
        if not all(
            amount.is_finite()
            for amount in (proof_amount, portfolio_amount, budget_amount)
        ):
            raise PromotionError(f"runtime {field} must be finite")
        if proof_amount != portfolio_amount or proof_amount != budget_amount:
            raise PromotionError(
                f"runtime {field} must match staged portfolio and budget state"
            )

    open_order_count = facts.get("open_order_count")
    if (
        isinstance(open_order_count, bool)
        or not isinstance(open_order_count, int)
        or open_order_count < 0
    ):
        raise PromotionError("runtime open order count must be a nonnegative integer")
    if facts.get("open_orders_reconciled") is not True:
        raise PromotionError("runtime open orders must be reconciled")
    if facts.get("open_order_issue") is not False:
        raise PromotionError("runtime proof reports an open order issue")
    try:
        proof_reserve = Decimal(str(facts.get("open_order_reserve")))
        portfolio_reserve = Decimal(
            str(portfolio_reconciliation.get("open_order_reserve"))
        )
        budget_reserve = Decimal(
            str(documents.get("budget", {}).get("broker", {}).get("open_order_reserve"))
        )
    except (InvalidOperation, TypeError, ValueError) as exc:
        raise PromotionError("open order reserve must be numeric") from exc
    if not all(
        amount.is_finite()
        for amount in (proof_reserve, portfolio_reserve, budget_reserve)
    ) or proof_reserve < 0:
        raise PromotionError("open order reserve must be finite and nonnegative")
    if proof_reserve != budget_reserve or proof_reserve != portfolio_reserve:
        raise PromotionError(
            "runtime open order reserve must match staged portfolio and budget reserve"
        )
    if open_order_count == 0 and proof_reserve != 0:
        raise PromotionError("runtime open order reserve must be zero when no orders are open")
    return proof


def render_staged_reports(documents):
    """Render all generated views from the already validated staged documents."""

    return {
        "PORTFOLIO.md": RENDERER.render_portfolio(
            documents["portfolio"],
            documents["analyst-ratings"],
            documents["evidence"],
        ),
        "BENCH.md": RENDERER.render_bench(documents["candidates"]),
        "RULES.md": RENDERER.render_rules(documents["policy"]),
    }


def _payload_digest(payload, run_input):
    digest = hashlib.sha256()
    for relative_path in sorted(payload):
        content = payload[relative_path]
        digest.update(relative_path.encode("utf-8"))
        digest.update(b"\0")
        digest.update(str(len(content)).encode("ascii"))
        digest.update(b"\0")
        digest.update(content)
    digest.update(b"RUN-INPUT\0")
    digest.update(str(len(run_input)).encode("ascii"))
    digest.update(b"\0")
    digest.update(run_input)
    return digest.hexdigest()


def _reject_secret_patterns(payload, run_input):
    items = list(payload.items()) + [("staged run", run_input)]
    for label, content in items:
        if any(pattern.search(content) for pattern in SECRET_PATTERNS):
            raise PromotionError(f"secret pattern detected in {label}")


def _read_run_input(staging_root, run_key):
    relative_path = Path("RUNS") / f"{run_key}.md"
    path = staging_root / relative_path
    if path.is_symlink():
        raise PromotionError(f"staged file must not be a symlink: {relative_path}")
    try:
        content = path.read_bytes()
        content.decode("utf-8")
    except (OSError, UnicodeDecodeError) as exc:
        raise PromotionError(f"cannot load staged {relative_path}: {exc}") from exc
    if b"promotion-sha256:" in content:
        raise PromotionError("staged run must not contain a promotion digest")
    return content


def _build_payload(staging_root, documents, run_key):
    payload = {
        str(relative_path).replace("\\", "/"): (staging_root / relative_path).read_bytes()
        for relative_path in STAGED_DOCUMENTS.values()
    }
    for name, report in render_staged_reports(documents).items():
        payload[name] = report.encode("utf-8")
    run_input = _read_run_input(staging_root, run_key)
    _reject_secret_patterns(payload, run_input)
    digest = _payload_digest(payload, run_input)
    run_content = run_input.rstrip(b"\n") + (
        f"\n\n<!-- promotion-sha256: {digest} -->\n".encode("ascii")
    )
    payload[f"RUNS/{run_key}.md"] = run_content
    return payload


def _write_prepared_file(directory, content, prefix):
    with tempfile.NamedTemporaryFile(
        delete=False, dir=directory, prefix=prefix
    ) as handle:
        handle.write(content)
        handle.flush()
        os.fsync(handle.fileno())
        return Path(handle.name)


def _install_payload_transactionally(system_root, payload, run_relative, run_key):
    """Install a complete payload or restore every pre-promotion byte."""

    system = Path(system_root)
    run_path = system / Path(run_relative)
    mutable_items = [
        (relative_path, payload[relative_path])
        for relative_path in sorted(payload)
        if relative_path != run_relative
    ]
    originals = {}
    for relative_path, _content in mutable_items:
        target = system / Path(relative_path)
        try:
            originals[target] = target.read_bytes()
        except FileNotFoundError:
            originals[target] = None
        except OSError as exc:
            raise PromotionError(f"cannot snapshot {relative_path}: {exc}") from exc

    transaction_parent = system / "staging"
    transaction_parent.mkdir(parents=True, exist_ok=True)
    with tempfile.TemporaryDirectory(
        prefix=".promote-", dir=transaction_parent
    ) as transaction_dir_name:
        transaction_dir = Path(transaction_dir_name)
        prepared = []
        try:
            for index, (relative_path, content) in enumerate(mutable_items):
                prepared_path = _write_prepared_file(
                    transaction_dir, content, f"payload-{index:02d}-"
                )
                prepared.append((relative_path, prepared_path))
        except OSError as exc:
            raise PromotionError(f"cannot prepare promotion transaction: {exc}") from exc

        replaced = []
        run_created = False
        try:
            for relative_path, prepared_path in prepared:
                target = system / Path(relative_path)
                target.parent.mkdir(parents=True, exist_ok=True)
                os.replace(prepared_path, target)
                replaced.append(target)
            run_path.parent.mkdir(parents=True, exist_ok=True)
            try:
                run_handle = run_path.open("xb")
            except FileExistsError as exc:
                raise PromotionError(f"run already exists: {run_key}") from exc
            run_created = True
            with run_handle:
                run_handle.write(payload[run_relative])
                run_handle.flush()
                os.fsync(run_handle.fileno())
        except Exception as exc:
            rollback_errors = []
            if run_created:
                try:
                    run_path.unlink()
                except FileNotFoundError:
                    pass
                except OSError as rollback_exc:
                    rollback_errors.append(f"remove {run_relative}: {rollback_exc}")
            for target in reversed(replaced):
                original = originals[target]
                try:
                    if original is None:
                        target.unlink(missing_ok=True)
                    else:
                        rollback_path = _write_prepared_file(
                            transaction_dir, original, "rollback-"
                        )
                        os.replace(rollback_path, target)
                except OSError as rollback_exc:
                    rollback_errors.append(f"restore {target}: {rollback_exc}")
            if rollback_errors:
                detail = "; ".join(rollback_errors)
                raise PromotionError(
                    f"promotion transaction failed: {exc}; rollback failed: {detail}"
                ) from exc
            raise PromotionError(f"promotion transaction failed: {exc}") from exc


@contextmanager
def _promotion_lock(system_root):
    lock_path = Path(system_root) / "staging" / ".promote.lock"
    lock_path.parent.mkdir(parents=True, exist_ok=True)
    try:
        descriptor = os.open(lock_path, os.O_CREAT | os.O_EXCL | os.O_WRONLY, 0o600)
    except FileExistsError as exc:
        raise PromotionError(f"promotion lock is held: {lock_path}") from exc
    try:
        with os.fdopen(descriptor, "w", encoding="ascii", newline="\n") as handle:
            handle.write(f"pid={os.getpid()}\n")
        yield
    finally:
        try:
            lock_path.unlink()
        except FileNotFoundError:
            pass


def promote_bundle(system_root, staging_root, run_key, *, reference_time=None):
    """Promote a validated staged bundle and return PROMOTED."""

    key = validate_run_key(run_key)
    system = Path(system_root)
    staging = Path(staging_root)
    with _promotion_lock(system):
        documents = validate_staged_bundle(staging)
        _require_runtime_proof(documents, key, reference_time=reference_time)
        payload = _build_payload(staging, documents, key)
        run_relative = f"RUNS/{key}.md"
        run_path = system / Path(run_relative)
        if run_path.exists():
            try:
                existing_run = run_path.read_bytes()
            except OSError as exc:
                raise PromotionError(f"cannot read existing run {key}: {exc}") from exc
            if existing_run == payload[run_relative]:
                return "IDEMPOTENT"
            raise PromotionError(f"conflicting duplicate run: {key}")
        _install_payload_transactionally(system, payload, run_relative, key)
        return "PROMOTED"


def main(argv=None):
    parser = argparse.ArgumentParser(description=__doc__)
    default_root = Path(__file__).resolve().parent.parent
    parser.add_argument("--system-root", type=Path, default=default_root)
    parser.add_argument("--staging-dir", type=Path)
    parser.add_argument("--run-key", required=True)
    args = parser.parse_args(argv)
    try:
        staging_root = args.staging_dir or args.system_root / "staging"
        result = promote_bundle(args.system_root, staging_root, args.run_key)
    except PromotionError as exc:
        print(f"PROMOTION FAILED: {exc}", file=sys.stderr)
        return 2
    print(f"{result} {args.run_key}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
