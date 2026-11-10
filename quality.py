"""Deterministic checks for the conference travel-plan contract.

These checks compare structured claims with supplied evidence. They do not
establish the factual accuracy of arbitrary activity names or travel advice.
Only the Python standard library is required; no model is called here.
"""

from __future__ import annotations

import hashlib
import json
import math
import re
from typing import Any

EVALUATOR_VERSION = "porto-quality-1.0.0"
CONTRACT_SCHEMA_VERSION = "porto-contract-1"
CANDIDATE_SCHEMA_VERSION = "porto-plan-1"
ALLOWED_INTERESTS = frozenset({"food", "architecture"})
WEATHER_KEYS = {
    "status", "source", "simulated", "location", "condition", "temperature_c"
}


class ContractError(ValueError):
    """The acceptance contract itself is malformed; this is an evaluator error."""


class CandidateParseError(ValueError):
    """A model response could not be parsed as one unambiguous JSON object."""


def _nonempty(value: Any) -> bool:
    return isinstance(value, str) and bool(value.strip())


def _number(value: Any) -> bool:
    # Integers are finite without converting large JSON integers to float.
    return type(value) is int or (type(value) is float and math.isfinite(value))


def _keys(value: dict, expected: set[str], path: str) -> list[str]:
    issues = []
    missing = expected - value.keys()
    extra = value.keys() - expected
    if missing:
        issues.append(f"{path}: missing fields: {', '.join(sorted(missing))}.")
    if extra:
        issues.append(f"{path}: unexpected fields: {', '.join(sorted(map(str, extra)))}.")
    return issues


def _weather_schema(value: Any, path: str) -> list[str]:
    if not isinstance(value, dict):
        return [f"{path} must be an object."]
    issues = _keys(value, WEATHER_KEYS, path)
    status = value.get("status")
    if status not in ("available", "unavailable"):
        issues.append(f"{path}.status must be available or unavailable.")
    for key in ("source", "location"):
        if not _nonempty(value.get(key)):
            issues.append(f"{path}.{key} must be a nonempty string.")
    if type(value.get("simulated")) is not bool:
        issues.append(f"{path}.simulated must be a boolean.")
    if status == "available":
        if not _nonempty(value.get("condition")):
            issues.append(f"{path}.condition must be a nonempty string when available.")
        if not _number(value.get("temperature_c")):
            issues.append(f"{path}.temperature_c must be a finite number when available.")
    elif status == "unavailable":
        if value.get("condition") is not None or value.get("temperature_c") is not None:
            issues.append(f"{path}: unavailable weather must have null condition and temperature_c.")
    return issues


def validate_contract(contract: dict) -> None:
    """Raise ContractError for an invalid contract, before judging any candidate."""
    if not isinstance(contract, dict):
        raise ContractError("Contract must be an object.")
    issues = _keys(contract, {"destination", "duration_days", "interests", "weather"}, "contract")
    if not _nonempty(contract.get("destination")):
        issues.append("contract.destination must be a nonempty string.")
    duration = contract.get("duration_days")
    if type(duration) is not int or duration < 1:
        issues.append("contract.duration_days must be a positive integer, not a boolean.")
    interests = contract.get("interests")
    if (not isinstance(interests, list) or not interests
            or any(not isinstance(tag, str) or tag not in ALLOWED_INTERESTS for tag in interests)):
        issues.append("contract.interests must be a nonempty list of food/architecture tags.")
    elif len(set(interests)) != len(interests):
        issues.append("contract.interests must not contain duplicates.")
    weather = contract.get("weather")
    issues.extend(_weather_schema(weather, "contract.weather"))
    if isinstance(weather, dict):
        if weather.get("source") != "demo_fixture":
            issues.append("contract.weather.source must be demo_fixture for this offline demo.")
        if weather.get("simulated") is not True:
            issues.append("contract.weather.simulated must be true for this teaching fixture.")
        if weather.get("location") != contract.get("destination"):
            issues.append("contract.weather.location must match contract.destination.")
    if issues:
        raise ContractError(" ".join(issues))


def _candidate_schema(candidate: Any) -> list[str]:
    if not isinstance(candidate, dict):
        return ["Candidate must be an object."]
    issues = _keys(candidate, {"destination", "days", "weather", "indoor_alternative", "actions"}, "candidate")
    if not _nonempty(candidate.get("destination")):
        issues.append("candidate.destination must be a nonempty string.")
    if not isinstance(candidate.get("indoor_alternative"), str):
        issues.append("candidate.indoor_alternative must be a string.")
    if not isinstance(candidate.get("actions"), list):
        issues.append("candidate.actions must be a list.")
    issues.extend(_weather_schema(candidate.get("weather"), "candidate.weather"))
    days = candidate.get("days")
    if not isinstance(days, list):
        issues.append("candidate.days must be a list.")
        return issues
    for index, day in enumerate(days):
        path = f"candidate.days[{index}]"
        if not isinstance(day, dict):
            issues.append(f"{path} must be an object.")
            continue
        issues.extend(_keys(day, {"day", "activities"}, path))
        if type(day.get("day")) is not int or day["day"] < 1:
            issues.append(f"{path}.day must be a positive integer, not a boolean.")
        activities = day.get("activities")
        if not isinstance(activities, list) or not activities:
            issues.append(f"{path}.activities must be a nonempty list.")
            continue
        for activity_index, activity in enumerate(activities):
            activity_path = f"{path}.activities[{activity_index}]"
            if not isinstance(activity, dict):
                issues.append(f"{activity_path} must be an object.")
                continue
            issues.extend(_keys(activity, {"name", "interest", "indoor"}, activity_path))
            if not _nonempty(activity.get("name")):
                issues.append(f"{activity_path}.name must be a nonempty string.")
            if (not isinstance(activity.get("interest"), str)
                    or activity["interest"] not in ALLOWED_INTERESTS):
                issues.append(f"{activity_path}.interest must be food or architecture.")
            if type(activity.get("indoor")) is not bool:
                issues.append(f"{activity_path}.indoor must be a boolean.")
    return issues


def _fingerprint(value: Any) -> str | None:
    try:
        encoded = json.dumps(value, sort_keys=True, ensure_ascii=False, allow_nan=False, separators=(",", ":"))
    except (TypeError, ValueError):
        return None
    return hashlib.sha256(encoded.encode("utf-8")).hexdigest()


def evaluate_plan(candidate: dict, contract: dict) -> dict:
    """Return a hard-check report; invalid candidates fail, invalid contracts raise.

    ``checks`` contains only checks actually performed. A schema failure stops
    semantic evaluation and always produces ``passed=False``.
    """
    validate_contract(contract)
    checks = []
    schema_issues = _candidate_schema(candidate)

    def check(name: str, passed: bool, detail: str) -> None:
        checks.append({"name": name, "passed": bool(passed), "detail": detail, "required": True})

    check("candidate_schema", not schema_issues,
          "Candidate has the required structured fields and types." if not schema_issues else " ".join(schema_issues))
    if not schema_issues:
        destination_ok = candidate["destination"] == contract["destination"]
        check("destination", destination_ok,
              "Destination matches the request." if destination_ok else "Destination differs from the requested destination.")
        day_sequence = [day["day"] for day in candidate["days"]]
        expected_days = list(range(1, contract["duration_days"] + 1))
        days_ok = day_sequence == expected_days
        check("day_sequence", days_ok,
              "Exactly the requested days appear once, in order." if days_ok else
              f"Expected day sequence {expected_days}; received {day_sequence}.")
        covered = {activity["interest"] for day in candidate["days"] for activity in day["activities"]}
        missing = set(contract["interests"]) - covered
        check("interests", not missing,
              "Every requested interest has a tagged activity." if not missing else
              "Missing requested interest tags: " + ", ".join(sorted(missing)) + ".")
        differences = [key for key in sorted(WEATHER_KEYS) if candidate["weather"][key] != contract["weather"][key]]
        check("weather_evidence", not differences,
              "Weather fields match the supplied evidence." if not differences else
              "Weather differs from supplied evidence in: " + ", ".join(differences) + ".")
        simulated_ok = candidate["weather"]["simulated"] is True
        check("simulation_disclosure", simulated_ok,
              "Weather is explicitly labeled simulated." if simulated_ok else "The simulated-weather label must remain true.")
        indoor_ok = bool(candidate["indoor_alternative"].strip())
        check("indoor_alternative", indoor_ok,
              "An indoor alternative is provided." if indoor_ok else "An indoor alternative must be a nonempty string.")
        actions_ok = candidate["actions"] == []
        check("allowed_actions", actions_ok,
              "No external actions are proposed." if actions_ok else "This planner must have an empty actions list; booking and other external actions are not allowed.")
    issues = [entry["detail"] for entry in checks if not entry["passed"]]
    return {
        "passed": not issues,
        "checks": checks,
        "issues": issues,
        "versions": {
            "evaluator": EVALUATOR_VERSION,
            "contract_schema": CONTRACT_SCHEMA_VERSION,
            "candidate_schema": CANDIDATE_SCHEMA_VERSION,
        },
        "contract_sha256": _fingerprint(contract),
        "candidate_sha256": _fingerprint(candidate),
        "scope": "Deterministic checks of structured claims against supplied fixture evidence; not a factuality or safety guarantee.",
    }


def _unique_object(pairs: list[tuple[str, Any]]) -> dict:
    result = {}
    for key, value in pairs:
        if key in result:
            raise CandidateParseError(f"Duplicate JSON field: {key}.")
        result[key] = value
    return result


def _reject_constant(value: str) -> None:
    raise CandidateParseError(f"Non-finite JSON number is not allowed: {value}.")


def _finite_json(value: Any) -> None:
    if isinstance(value, float) and not math.isfinite(value):
        raise CandidateParseError("Non-finite JSON number is not allowed.")
    if isinstance(value, dict):
        for child in value.values():
            _finite_json(child)
    elif isinstance(value, list):
        for child in value:
            _finite_json(child)


def parse_candidate(text: str) -> dict:
    """Parse plain JSON or a single complete JSON Markdown fence.

    Prose surrounding JSON, duplicate keys, non-finite numbers, arrays and other
    ambiguous responses are rejected instead of guessing which plan to use.
    """
    if not isinstance(text, str):
        raise CandidateParseError("Candidate response must be text.")
    text = text.strip().lstrip("\ufeff").strip()
    if text.startswith("```"):
        match = re.fullmatch(r"```(?:json)?\s*([\s\S]*?)\s*```", text, flags=re.IGNORECASE)
        if not match:
            raise CandidateParseError("Candidate contains an incomplete JSON fence.")
        text = match.group(1)
    try:
        result = json.loads(text, object_pairs_hook=_unique_object, parse_constant=_reject_constant)
    except CandidateParseError:
        raise
    except (ValueError, RecursionError) as error:
        raise CandidateParseError("Candidate must contain one valid JSON object.") from error
    if not isinstance(result, dict):
        raise CandidateParseError("Candidate JSON must be an object.")
    try:
        _finite_json(result)
    except RecursionError as error:
        raise CandidateParseError("Candidate JSON is nested too deeply.") from error
    return result
