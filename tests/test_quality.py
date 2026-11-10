"""Offline acceptance and CLI regression tests; standard library only."""

from copy import deepcopy
import json
from pathlib import Path
import subprocess
import sys
import tempfile
import unittest

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

from quality import CandidateParseError, ContractError, evaluate_plan, parse_candidate


def fixture(name):
    return json.loads((ROOT / "fixtures" / name).read_text(encoding="utf-8"))


class QualityTests(unittest.TestCase):
    def setUp(self):
        self.contract = fixture("contract.json")
        self.good = fixture("good-plan.json")

    def assert_fails(self, candidate, name):
        result = evaluate_plan(candidate, self.contract)
        self.assertFalse(result["passed"])
        self.assertTrue(any(check["name"] == name and not check["passed"] for check in result["checks"]))
        self.assertTrue(result["issues"])
        return result

    def test_good_plan_passes_all_required_checks(self):
        result = evaluate_plan(self.good, self.contract)
        self.assertTrue(result["passed"])
        self.assertEqual(result["issues"], [])
        self.assertEqual(len(result["checks"]), 8)
        self.assertTrue(all(check["required"] and check["passed"] for check in result["checks"]))
        self.assertEqual(len(result["candidate_sha256"]), 64)
        self.assertIn("evaluator", result["versions"])

    def test_bad_fixture_exposes_independent_hard_failures(self):
        result = evaluate_plan(fixture("bad-plan.json"), self.contract)
        failed = {check["name"] for check in result["checks"] if not check["passed"]}
        self.assertEqual(failed, {"day_sequence", "interests", "weather_evidence", "simulation_disclosure", "indoor_alternative", "allowed_actions"})

    def test_day_sequence_checks_actual_duration_order_and_duplicates(self):
        for sequence in ([1, 2], [1, 2, 2], [1, 3, 2], [1, 2, 3, 4]):
            with self.subTest(sequence=sequence):
                candidate = deepcopy(self.good)
                candidate["days"] = [dict(deepcopy(self.good["days"][0]), day=number) for number in sequence]
                self.assert_fails(candidate, "day_sequence")

    def test_boolean_is_not_a_day_number(self):
        self.good["days"][0]["day"] = True
        self.assert_fails(self.good, "candidate_schema")

    def test_requested_interests_need_activity_tags(self):
        for day in self.good["days"]:
            for activity in day["activities"]:
                activity["interest"] = "food"
        self.assert_fails(self.good, "interests")

    def test_weather_fields_must_match_actual_evidence(self):
        changes = {"source": "invented", "location": "Lisbon", "condition": "sunny", "temperature_c": 28}
        for field, value in changes.items():
            with self.subTest(field=field):
                candidate = deepcopy(self.good)
                candidate["weather"][field] = value
                self.assert_fails(candidate, "weather_evidence")

    def test_unavailable_weather_cannot_be_replaced_with_a_forecast(self):
        unavailable = fixture("contract-unavailable.json")
        result = evaluate_plan(self.good, unavailable)
        self.assertFalse(result["passed"])
        self.good["weather"] = deepcopy(unavailable["weather"])
        self.assertTrue(evaluate_plan(self.good, unavailable)["passed"])
        self.good["weather"]["condition"] = "sunny"
        self.assertFalse(evaluate_plan(self.good, unavailable)["passed"])

    def test_candidate_schema_rejects_wrong_types_missing_extra_and_empty_day(self):
        invalid = [None, [], {}, dict(self.good, unexpected=True)]
        candidate = deepcopy(self.good); candidate["days"][0]["activities"] = []; invalid.append(candidate)
        candidate = deepcopy(self.good); candidate["days"][0]["activities"][0]["indoor"] = 1; invalid.append(candidate)
        candidate = deepcopy(self.good); candidate["weather"]["temperature_c"] = True; invalid.append(candidate)
        candidate = deepcopy(self.good); candidate["weather"]["temperature_c"] = float("nan"); invalid.append(candidate)
        for candidate in invalid:
            with self.subTest(candidate=candidate):
                self.assert_fails(candidate, "candidate_schema")

    def test_simulation_flag_indoor_alternative_and_actions_are_hard(self):
        for field, value, check in [("indoor_alternative", "   ", "indoor_alternative"), ("actions", ["book"], "allowed_actions")]:
            candidate = dict(self.good, **{field: value})
            self.assert_fails(candidate, check)
        self.good["weather"]["simulated"] = False
        self.assert_fails(self.good, "simulation_disclosure")

    def test_malformed_contract_raises_instead_of_judging_candidate(self):
        for change in ({"duration_days": True}, {"interests": ["food", "food"]}, {"interests": ["other"]}):
            with self.subTest(change=change), self.assertRaises(ContractError):
                evaluate_plan(self.good, dict(self.contract, **change))
        unavailable = fixture("contract-unavailable.json")
        unavailable["weather"]["temperature_c"] = 18
        with self.assertRaises(ContractError):
            evaluate_plan(self.good, unavailable)

    def test_parse_plain_and_fenced_json(self):
        encoded = json.dumps(self.good)
        for text in (encoded, "\ufeff " + encoded, "```json\n" + encoded + "\n```", "```\n" + encoded + "\n```"):
            self.assertEqual(parse_candidate(text), self.good)

    def test_parse_rejects_ambiguous_json_and_nonfinite_numbers(self):
        for text in ('[]', '{"x":1,"x":2}', '{"x":NaN}', '{"x":1e999}', '{} {}', 'Here is the plan: {}', '```json\n{}'):
            with self.subTest(text=text), self.assertRaises(CandidateParseError):
                parse_candidate(text)


class GateCliTests(unittest.TestCase):
    def run_gate(self, candidate, report, contract=None):
        return subprocess.run(
            [sys.executable, str(ROOT / "release_gate.py"), "--candidate", str(candidate),
             "--contract", str(contract or ROOT / "fixtures/contract.json"), "--report", str(report)],
            cwd=ROOT, text=True, capture_output=True, timeout=10,
        )

    def test_good_exit_zero_and_bad_exit_one_with_reports(self):
        with tempfile.TemporaryDirectory() as directory:
            for name, expected in (("good-plan.json", 0), ("bad-plan.json", 1)):
                report = Path(directory) / (name + ".report.json")
                process = self.run_gate(ROOT / "fixtures" / name, report)
                self.assertEqual(process.returncode, expected, process.stderr)
                result = json.loads(report.read_text())
                self.assertEqual(result["passed"], expected == 0)
                self.assertEqual(result["exit_code"], expected)
                self.assertTrue(result["checks"])
                self.assertIn("candidate_file_sha256", result["provenance"])
                self.assertIn("versions", result)
            self.assertEqual(list(Path(directory).glob(".quality-report-*.tmp")), [])

    def test_missing_candidate_and_malformed_json_exit_two_not_pass(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            invalid = root / "invalid.json"; invalid.write_text("not json")
            for candidate in (root / "missing.json", invalid):
                process = self.run_gate(candidate, root / "report.json")
                self.assertEqual(process.returncode, 2)
                result = json.loads((root / "report.json").read_text())
                self.assertFalse(result["passed"])
                self.assertEqual(result["status"], "error")
                self.assertIn("evaluator", result["versions"])

    def test_invalid_candidate_schema_is_quality_failure(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            candidate = root / "wrong.json"; candidate.write_text('{}')
            process = self.run_gate(candidate, root / "report.json")
            self.assertEqual(process.returncode, 1)

    def test_malformed_contract_and_unwritable_report_exit_two(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            contract = root / "contract.json"; contract.write_text('{}')
            process = self.run_gate(ROOT / "fixtures/good-plan.json", root / "error.json", contract)
            self.assertEqual(process.returncode, 2)
            # Replacing a directory with a report must never produce a passing exit.
            process = self.run_gate(ROOT / "fixtures/good-plan.json", root)
            self.assertEqual(process.returncode, 2)
            self.assertIn("report could not be written", process.stderr)


if __name__ == "__main__":
    unittest.main()
