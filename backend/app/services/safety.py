"""Deterministic safety layer (M11). No LLM, no network.

- `detect_red_flag`: urgent-symptom rules on the patient's own message, with negation,
  clause boundaries and history markers.
- `check_input`: prompt-injection / role-change attempts in the question.
- `check_output`: no-diagnosis/no-treatment/no-prediction phrasing and numeric consistency
  (every number in an answer must appear in the evidence it was given).
Callers log rule IDs only, never the text that matched.
"""

import re
from dataclasses import dataclass
from decimal import Decimal, InvalidOperation
from functools import lru_cache
from importlib import resources
from typing import Any

import yaml

INPUT_BLOCKED_ANSWER = "I can only answer questions about your own medical records."
OUTPUT_BLOCKED_ANSWER = (
    "I couldn't give a reliable answer from your records. I can share what your records say, "
    "but I can't diagnose, predict or recommend treatment; please discuss this with your doctor."
)
_TOKEN = re.compile(r"[a-z0-9']+|[,;.!?]")
_NUMBER = re.compile(r"(?<![\w.])\d+(?:\.\d+)?")
_CONTROL = re.compile(r"[\x00-\x08\x0b\x0c\x0e-\x1f\x7f]")
_PUNCTUATION_BREAKS = {",", ";", ".", "!", "?"}


@dataclass(frozen=True)
class RedFlagRule:
    id: str
    category: str
    phrases: tuple[tuple[str, ...], ...]
    ignore_negation: bool


@dataclass(frozen=True)
class SafetyRules:
    version: str
    negation_window: int
    negators: frozenset[str]
    clause_breakers: frozenset[str]
    history_before: tuple[tuple[str, ...], ...]
    history_after: tuple[tuple[str, ...], ...]
    messages: dict[str, str]
    red_flags: tuple[RedFlagRule, ...]
    input_injection: tuple[tuple[str, re.Pattern[str]], ...]
    diagnostic_output: tuple[tuple[str, re.Pattern[str]], ...]


@dataclass(frozen=True)
class RedFlag:
    rule_id: str
    category: str
    message: str


def _tokens(text: str) -> list[str]:
    return _TOKEN.findall(text.lower().replace("\u2019", "'"))  # curly apostrophe


def _phrase(text: str) -> tuple[str, ...]:
    return tuple(_tokens(text))


@lru_cache
def load_rules() -> SafetyRules:
    data: dict[str, Any] = yaml.safe_load(
        resources.files("app.data").joinpath("safety_rules.yaml").read_text(encoding="utf-8")
    )
    compile_ = lambda items: tuple((i["id"], re.compile(i["pattern"], re.I)) for i in items)  # noqa: E731
    return SafetyRules(
        version=str(data["version"]),
        negation_window=int(data["negation_window"]),
        negators=frozenset(str(n) for n in data["negators"]),
        clause_breakers=frozenset(str(b) for b in data["clause_breakers"]),
        history_before=tuple(_phrase(p) for p in data["history_before"]),
        history_after=tuple(_phrase(p) for p in data["history_after"]),
        messages={k: " ".join(v.split()) for k, v in data["messages"].items()},
        red_flags=tuple(
            RedFlagRule(
                id=r["id"],
                category=r["category"],
                phrases=tuple(_phrase(p) for p in r["phrases"]),
                ignore_negation=bool(r.get("ignore_negation", False)),
            )
            for r in data["red_flags"]
        ),
        input_injection=compile_(data["input_injection"]),
        diagnostic_output=compile_(data["diagnostic_output"]),
    )


def _contains(window: list[str], phrases: tuple[tuple[str, ...], ...]) -> bool:
    return any(
        window[i : i + len(p)] == list(p) for p in phrases for i in range(len(window) - len(p) + 1)
    )


def _clause_before(tokens: list[str], start: int, rules: SafetyRules) -> list[str]:
    window: list[str] = []
    for token in reversed(tokens[max(0, start - rules.negation_window) : start]):
        if token in _PUNCTUATION_BREAKS or token in rules.clause_breakers:
            break
        window.insert(0, token)
    return window


def _clause_after(tokens: list[str], end: int, rules: SafetyRules) -> list[str]:
    window: list[str] = []
    for token in tokens[end : end + rules.negation_window]:
        if token in _PUNCTUATION_BREAKS or token in rules.clause_breakers:
            break
        window.append(token)
    return window


def detect_red_flag(text: str) -> RedFlag | None:
    rules = load_rules()
    tokens = _tokens(text)
    for rule in rules.red_flags:
        for phrase in rule.phrases:
            for start in range(len(tokens) - len(phrase) + 1):
                if tuple(tokens[start : start + len(phrase)]) != phrase:
                    continue
                before = _clause_before(tokens, start, rules)
                after = _clause_after(tokens, start + len(phrase), rules)
                if not rule.ignore_negation:
                    if rules.negators & set(before):
                        continue  # "no chest pain", "denies shortness of breath"
                    if _contains(before, rules.history_before) or _contains(
                        after, rules.history_after
                    ):
                        continue  # "history of chest pain", "fainted two years ago"
                return RedFlag(rule.id, rule.category, rules.messages[rule.category])
    return None


def clean_question(text: str) -> str:
    """Input validation: drop control characters and collapse whitespace."""
    return " ".join(_CONTROL.sub(" ", text).split())


def check_input(text: str) -> str | None:
    """Return the id of the injection rule the question matches, or None."""
    if not text:
        return "empty"
    return next((rule_id for rule_id, p in load_rules().input_injection if p.search(text)), None)


def _numbers(text: str) -> set[str]:
    normalized: set[str] = set()
    for match in _NUMBER.findall(text):
        try:
            value = Decimal(match).normalize()
        except InvalidOperation:
            continue
        normalized.add(format(value, "f"))
    return normalized


def check_output(answer: str, evidence_texts: list[str], question: str = "") -> str | None:
    """Return a violation id, or None if the answer may be shown."""
    for rule_id, pattern in load_rules().diagnostic_output:
        if pattern.search(answer):
            return rule_id
    allowed = _numbers(question)
    for text in evidence_texts:
        allowed |= _numbers(text)
    if _numbers(answer) - allowed:
        return "unsupported_number"
    return None
