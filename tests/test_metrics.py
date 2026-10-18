"""Unit tests for the experiment metrics (guards every number the experiments report)."""
from __future__ import annotations

import math

import pytest

from experiments.metrics import (
    accuracy,
    confusion_matrix,
    macro_f1,
    per_class_scores,
    report,
)


def test_perfect_predictions_score_one():
    y = ["positive", "negative", "neutral", "positive"]
    assert accuracy(y, y) == 1.0
    assert macro_f1(y, y) == 1.0
    matrix = confusion_matrix(y, y)
    assert matrix == [[2, 0, 0], [0, 1, 0], [0, 0, 1]]  # positive row first


def test_known_small_example():
    y_true = ["positive", "positive", "negative", "negative"]
    y_pred = ["positive", "negative", "negative", "negative"]
    assert accuracy(y_true, y_pred) == 0.75
    scores = per_class_scores(y_true, y_pred, classes=("positive", "negative"))
    assert scores["positive"]["precision"] == 1.0
    assert scores["positive"]["recall"] == 0.5
    assert scores["negative"]["precision"] == pytest.approx(2 / 3)
    assert scores["negative"]["recall"] == 1.0


def test_macro_f1_value_explicit():
    y_true = ["positive", "positive", "negative", "negative"]
    y_pred = ["positive", "negative", "negative", "negative"]
    # F1(pos) = 2*1*0.5/1.5 = 2/3, F1(neg) = 2*(2/3)*1/(5/3) = 0.8
    assert macro_f1(y_true, y_pred, classes=("positive", "negative")) == pytest.approx((2 / 3 + 0.8) / 2)


def test_zero_support_class_counts_as_zero_in_macro():
    y_true = ["positive", "positive"]
    y_pred = ["positive", "positive"]
    scores = per_class_scores(y_true, y_pred)  # neutral + negative never appear
    assert scores["neutral"]["f1"] == 0.0
    assert scores["neutral"]["support"] == 0
    assert macro_f1(y_true, y_pred) == pytest.approx((1.0 + 0.0 + 0.0) / 3)


def test_never_predicted_class_gets_zero_precision_not_error():
    scores = per_class_scores(["negative"], ["positive"])
    assert scores["negative"]["precision"] == 0.0
    assert scores["negative"]["recall"] == 0.0
    assert scores["negative"]["f1"] == 0.0


def test_length_mismatch_raises():
    with pytest.raises(ValueError):
        accuracy(["positive"], [])
    with pytest.raises(ValueError):
        confusion_matrix(["positive"], [])


def test_unknown_label_raises():
    with pytest.raises(ValueError):
        confusion_matrix(["happy"], ["positive"])


def test_report_shape_and_consistency():
    y_true = ["positive", "neutral", "negative", "positive"]
    y_pred = ["positive", "neutral", "neutral", "negative"]
    result = report(y_true, y_pred)
    assert result["n"] == 4
    assert 0.0 <= result["accuracy"] <= 1.0
    assert 0.0 <= result["macro_f1"] <= 1.0
    assert len(result["confusion_matrix"]) == 3
    assert sum(sum(row) for row in result["confusion_matrix"]) == 4
    assert result["classes"] == ["positive", "neutral", "negative"]
    assert math.isclose(result["macro_f1"], sum(s["f1"] for s in result["per_class"].values()) / 3)
