"""Small, deterministic prompt-injection fixtures for the Porto demos.

These rules illustrate detection and pre-agent enforcement. They are not a
general injection defense, a calibrated probability model, or tool
authorization. Benign and malicious content can both be misclassified. Keep
tool permissions and argument validation independent of this module.

No SDK, environment, network, or logging configuration is needed. Input text
is neither logged nor included in the returned decision.
"""

from __future__ import annotations

import math
import re
import unicodedata
from numbers import Real

POLICY_VERSION = "porto-security-v1"
DEFAULT_BLOCK_THRESHOLD = 0.7

# Rule order also defines the stable ordering of returned category names.
# Scores express policy severity for this demonstration, not probabilities.
_RULES: tuple[tuple[str, float, tuple[re.Pattern[str], ...]], ...] = (
    (
        "instruction_override",
        0.85,
        (
            re.compile(
                r"\b(?:ignore|disregard|forget|override|bypass)\s+"
                r"(?:(?:all|any|the|your|our|my|previous|prior|earlier|original|"
                r"system|developer|safety|security|travel[- ]only|above|existing|"
                r"budget|and)\s+){0,6}"
                r"(?:instructions?|rules?|constraints?|polic(?:y|ies)|guardrails?|restrictions?)\b"
            ),
            re.compile(
                r"\b(?:you are now|pretend to be|act as)\s+"
                r"(?:an?\s+)?(?:unrestricted|unfiltered|unconstrained)\b"
            ),
        ),
    ),
    (
        "system_prompt_reveal",
        0.95,
        (
            re.compile(
                r"\b(?:reveal|show|print|repeat|expose|disclose|give|tell)\b"
                r".{0,80}?\b(?:system|developer|internal)\s+"
                r"(?:prompt|instructions?|message|configuration)\b"
            ),
        ),
    ),
    (
        "exfiltration",
        0.95,
        (
            re.compile(
                r"\b(?:send|post|upload|transmit|exfiltrate|leak|forward)\b"
                r".{0,100}?\b(?:api\s*keys?|access\s*tokens?|secrets?|"
                r"credentials?|(?:private|internal)\s+configuration|"
                r"environment\s+variables?|system\s+prompt)\b"
            ),
        ),
    ),
    (
        "tool_instruction_override",
        0.9,
        (
            re.compile(
                r"\b(?:tool\s+(?:output|response|result)|weather\s+(?:report|result)|"
                r"retrieved\s+(?:document|content))\b.{0,140}?"
                r"\b(?:ignore|disregard|override|bypass)\s+"
                r"(?:(?:all|the|your|previous|prior|system|developer|existing)\s+){0,4}"
                r"(?:instructions?|rules?|constraints?|polic(?:y|ies))\b"
            ),
            re.compile(
                r"\b(?:tool\s+(?:output|response|result)|weather\s+(?:report|result)|"
                r"retrieved\s+(?:document|content))\b.{0,100}?"
                r"\b(?:call|fetch|visit|open)\s+(?:(?:this|the)\s+)?"
                r"(?:url\b|https?://)"
            ),
        ),
    ),
)


def _unit_interval(value: float, name: str) -> float:
    """Reject invalid policy inputs instead of silently weakening enforcement."""
    if isinstance(value, bool) or not isinstance(value, Real):
        raise ValueError(f"{name} must be a finite number between 0 and 1")
    number = float(value)
    if not math.isfinite(number) or not 0.0 <= number <= 1.0:
        raise ValueError(f"{name} must be a finite number between 0 and 1")
    return number


def should_block(score: float, threshold: float = DEFAULT_BLOCK_THRESHOLD) -> bool:
    """Block inclusively at the threshold.

    Both inputs must be real, finite numbers in [0, 1]. Booleans, strings,
    NaN, infinity, and out-of-range inputs raise ValueError. A caller should
    treat such an error as an unavailable/invalid decision, never as approval.
    """
    return _unit_interval(score, "score") >= _unit_interval(threshold, "threshold")


def detect_prompt_injection(text: str) -> dict:
    """Return a deterministic teaching decision for a string.

    Normalization is NFKC, case folding, then whitespace collapsing. It does
    not decode arbitrary encodings or cover general multilingual, indirect,
    semantic, or obfuscated attacks. Empty/benign unmatched text scores 0.
    Rule scores use their maximum, clamped to [0, 1], so the decision does
    not depend on how many times a phrase is repeated. Non-string input
    raises TypeError; request validation should run before this function.
    """
    if not isinstance(text, str):
        raise TypeError("text must be a string")
    normalized = " ".join(unicodedata.normalize("NFKC", text).casefold().split())
    patterns: list[str] = []
    score = 0.0
    for category, rule_score, expressions in _RULES:
        if any(expression.search(normalized) for expression in expressions):
            patterns.append(category)
            score = max(score, rule_score)
    score = max(0.0, min(1.0, score))
    return {
        "risk_score": score,
        "patterns": patterns,
        "policy_version": POLICY_VERSION,
        "blocked": should_block(score),
    }
