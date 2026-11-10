"""Offline fixture gate: 0 passes, 1 fails quality, 2 means invalid input/error."""

from __future__ import annotations

import argparse
from datetime import datetime, timezone
import hashlib
import json
import os
from pathlib import Path
import platform
import sys
import tempfile

from quality import (
    CANDIDATE_SCHEMA_VERSION, CONTRACT_SCHEMA_VERSION, EVALUATOR_VERSION,
    CandidateParseError, ContractError, evaluate_plan, parse_candidate,
)


def _read_object(path: Path, label: str) -> tuple[dict, str]:
    try:
        raw = path.read_bytes()
        value = parse_candidate(raw.decode("utf-8-sig"))
    except (OSError, UnicodeError, CandidateParseError) as error:
        raise ValueError(f"{label} file could not be read as a JSON object: {error}") from error
    return value, hashlib.sha256(raw).hexdigest()


def _atomic_report(path: Path, report: dict) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    temporary = None
    try:
        with tempfile.NamedTemporaryFile(mode="w", encoding="utf-8", dir=path.parent,
                                         prefix=".quality-report-", suffix=".tmp", delete=False) as stream:
            temporary = Path(stream.name)
            json.dump(report, stream, ensure_ascii=False, indent=2, allow_nan=False)
            stream.write("\n")
            stream.flush()
            os.fsync(stream.fileno())
        os.replace(temporary, path)
        temporary = None
    finally:
        if temporary is not None:
            temporary.unlink(missing_ok=True)


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--candidate", type=Path, required=True, help="Candidate plan JSON or fenced JSON text.")
    parser.add_argument("--contract", type=Path, required=True, help="Versioned acceptance contract JSON.")
    parser.add_argument("--report", type=Path, help="Write the complete report atomically; failure to write exits 2.")
    args = parser.parse_args(argv)
    provenance = {
        "evaluated_at": datetime.now(timezone.utc).isoformat(),
        "candidate_file": str(args.candidate),
        "contract_file": str(args.contract),
        "python_version": platform.python_version(),
    }
    try:
        contract, provenance["contract_file_sha256"] = _read_object(args.contract, "Contract")
        candidate, provenance["candidate_file_sha256"] = _read_object(args.candidate, "Candidate")
        report = evaluate_plan(candidate, contract)
        exit_code = 0 if report["passed"] else 1
        report.update(status="passed" if exit_code == 0 else "failed", exit_code=exit_code)
    except (ValueError, ContractError) as error:
        exit_code = 2
        report = {
            "passed": False, "status": "error", "exit_code": 2,
            "checks": [], "issues": [str(error)], "error": str(error),
        }
    except Exception as error:
        exit_code = 2
        report = {
            "passed": False, "status": "error", "exit_code": 2,
            "checks": [], "issues": ["Evaluation could not complete."],
            "error": f"Evaluation could not complete ({type(error).__name__}).",
        }
    report["provenance"] = provenance
    report.setdefault("versions", {
        "evaluator": EVALUATOR_VERSION,
        "contract_schema": CONTRACT_SCHEMA_VERSION,
        "candidate_schema": CANDIDATE_SCHEMA_VERSION,
    })
    if args.report is not None:
        try:
            _atomic_report(args.report, report)
        except (OSError, ValueError) as error:
            print(f"ERROR: Required report could not be written: {error}", file=sys.stderr)
            return 2
    print(report["status"].upper())
    for issue in report["issues"]:
        print(f"- {issue}")
    return exit_code


if __name__ == "__main__":
    raise SystemExit(main())
