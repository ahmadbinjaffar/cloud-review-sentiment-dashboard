"""Classification metrics used by the experiments.

Textbook definitions (no ML library needed), verified by tests/test_metrics.py:
- precision_c   = TP / (TP + FP),  0 when the denominator is 0
- recall_c      = TP / (TP + FN),  0 when the denominator is 0
- F1_c          = 2 * P * R / (P + R),  0 when P + R is 0
- macro-F1      = unweighted mean of F1 over all classes (zero-support classes count)
- accuracy      = correct / n
"""
from __future__ import annotations

CLASSES = ("positive", "neutral", "negative")


def confusion_matrix(y_true: list[str], y_pred: list[str], classes: tuple = CLASSES) -> list[list[int]]:
    """Rows = true class, columns = predicted class (order follows `classes`)."""
    if len(y_true) != len(y_pred):
        raise ValueError("y_true and y_pred must have the same length")
    index = {c: i for i, c in enumerate(classes)}
    matrix = [[0] * len(classes) for _ in classes]
    for true, pred in zip(y_true, y_pred):
        if true not in index or pred not in index:
            raise ValueError(f"unknown label: true={true!r} pred={pred!r}")
        matrix[index[true]][index[pred]] += 1
    return matrix


def accuracy(y_true: list[str], y_pred: list[str]) -> float:
    if not y_true:
        raise ValueError("empty input")
    if len(y_true) != len(y_pred):
        raise ValueError("y_true and y_pred must have the same length")
    return sum(t == p for t, p in zip(y_true, y_pred)) / len(y_true)


def per_class_scores(y_true: list[str], y_pred: list[str], classes: tuple = CLASSES) -> dict[str, dict]:
    matrix = confusion_matrix(y_true, y_pred, classes)
    out = {}
    for i, cls in enumerate(classes):
        tp = matrix[i][i]
        fp = sum(matrix[r][i] for r in range(len(classes))) - tp
        fn = sum(matrix[i]) - tp
        precision = tp / (tp + fp) if (tp + fp) else 0.0
        recall = tp / (tp + fn) if (tp + fn) else 0.0
        f1 = 2 * precision * recall / (precision + recall) if (precision + recall) else 0.0
        out[cls] = {
            "precision": precision,
            "recall": recall,
            "f1": f1,
            "support": sum(matrix[i]),
        }
    return out


def macro_f1(y_true: list[str], y_pred: list[str], classes: tuple = CLASSES) -> float:
    scores = per_class_scores(y_true, y_pred, classes)
    return sum(s["f1"] for s in scores.values()) / len(scores)


def report(y_true: list[str], y_pred: list[str], classes: tuple = CLASSES) -> dict:
    """Full metrics dict written to CSV/JSON by the experiments."""
    per_class = per_class_scores(y_true, y_pred, classes)
    return {
        "n": len(y_true),
        "accuracy": accuracy(y_true, y_pred),
        "macro_precision": sum(s["precision"] for s in per_class.values()) / len(per_class),
        "macro_recall": sum(s["recall"] for s in per_class.values()) / len(per_class),
        "macro_f1": macro_f1(y_true, y_pred, classes),
        "per_class": per_class,
        "confusion_matrix": confusion_matrix(y_true, y_pred, classes),
        "classes": list(classes),
    }
