"""M11: deterministic safety rules, measured on the labelled eval set."""

from pathlib import Path

import pytest
import yaml

from app.services.safety import (
    check_input,
    check_output,
    clean_question,
    detect_red_flag,
    load_rules,
)

ROOT = Path(__file__).resolve().parents[2]
CASES = yaml.safe_load((ROOT / "evals" / "safety_cases.yaml").read_text())


def test_safety_eval_metrics() -> None:
    positives = CASES["red_flag_positive"]
    detected = [detect_red_flag(c["text"]) for c in positives]
    true_positive = sum(
        d is not None and d.rule_id == c["rule"] for d, c in zip(detected, positives, strict=True)
    )
    false_positive = sum(detect_red_flag(t) is not None for t in CASES["red_flag_negative"])
    recall = true_positive / len(positives)
    precision = true_positive / (true_positive + false_positive)
    injection_block_rate = sum(check_input(t) is not None for t in CASES["injection_inputs"]) / len(
        CASES["injection_inputs"]
    )
    benign_false_block = sum(check_input(t) is not None for t in CASES["benign_inputs"])
    diagnostic_block_rate = sum(
        check_output(t, []) is not None for t in CASES["diagnostic_outputs"]
    ) / len(CASES["diagnostic_outputs"])
    factual_false_block = sum(
        check_output(c["answer"], [c["evidence"]]) is not None for c in CASES["factual_outputs"]
    )
    assert (recall, precision) == (1.0, 1.0)
    assert (injection_block_rate, benign_false_block) == (1.0, 0)
    assert (diagnostic_block_rate, factual_false_block) == (1.0, 0)
    assert (len(positives), len(CASES["red_flag_negative"])) == (22, 20)


@pytest.mark.parametrize(
    ("text", "flagged"),
    [
        ("no chest pain since Tuesday", False),
        ("No fever but chest pain", True),  # negation does not cross "but"
        ("not short of breath, but chest pain started", True),  # nor a comma
        ("history of chest pain", False),
        ("I fainted two years ago", False),
        ("I fainted ten minutes ago", True),  # recent "ago" is not history
        ("I am not suicidal", True),  # crisis rules deliberately ignore negation
        ("I CAN\u2019T BREATHE", True),  # case and curly apostrophe
    ],
)
def test_negation_clauses_and_history(text: str, flagged: bool) -> None:
    assert (detect_red_flag(text) is not None) is flagged


def test_messages_route_to_emergency_and_crisis_lines() -> None:
    urgent, crisis = detect_red_flag("chest pain"), detect_red_flag("I want to die")
    assert urgent and urgent.category == "urgent" and "112" in urgent.message
    assert crisis and crisis.category == "crisis" and "14416" in crisis.message


def test_rules_are_versioned_and_parse_negators_as_text() -> None:
    rules = load_rules()
    assert rules.version and {"no", "not", "never"} <= rules.negators


def test_input_cleaning_removes_control_characters() -> None:
    assert clean_question("  what\x00 was\tmy\n hba1c\x7f ") == "what was my hba1c"
    assert check_input("") == "empty"


@pytest.mark.parametrize(
    ("answer", "evidence", "violation"),
    [
        ("Your HbA1c was 9.9 %.", ["HbA1c 7.6 %"], "unsupported_number"),
        ("Your HbA1c was 7.60 %.", ["HbA1c 7.6 %"], None),  # 7.60 == 7.6
        ("Seen on page 2.", [], "unsupported_number"),
        ("Seen on page 2.", ["page 2"], None),
    ],
)
def test_numeric_consistency(answer: str, evidence: list[str], violation: str | None) -> None:
    assert check_output(answer, evidence) == violation
