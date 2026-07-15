#!/usr/bin/env python3
"""Evaluate a fixed detector policy on an authorized labeled JSONL dataset.

This script never calls a detector and never optimizes a threshold. A numeric
threshold is used only when the caller supplies it explicitly.
"""

from __future__ import annotations

import argparse
import hashlib
import json
import math
import re
import sys
from collections import defaultdict
from pathlib import Path
from typing import Any, Iterable


SCHEMA_VERSION = "detector-evaluation/v1"
DISCLAIMER = (
    "This evaluation measures a fixed policy on this labeled sample. It does not "
    "prove authorship for an individual document or guarantee performance under "
    "other distributions or future detector versions."
)
Z_95 = 1.959963984540054
MIN_GROUP_SIZE = 30
MIN_GROUP_CLASS_COUNT = 10
MIN_OVERALL_SIZE = 30
MIN_OVERALL_CLASS_COUNT = 10
BLOCKED_GROUP_FIELD_TERMS = {
    "attempt",
    "candidate",
    "iteration",
    "prompt",
    "rewrite",
    "round",
    "variant",
}
ALLOWED_GROUP_FIELDS = {
    "assistance_type",
    "author_group",
    "collection_period",
    "detector_version",
    "domain",
    "genre",
    "generator_family",
    "generator_release_period",
    "input_format",
    "language",
    "length_band",
    "model_version",
    "native_language_status",
    "policy_category",
    "source_group",
    "translation_status",
    "writer_background",
}


class EvaluationInputError(ValueError):
    """Raised when benchmark input or policy is invalid."""


def normalized_label(value: Any) -> str:
    if not isinstance(value, str) or not value.strip():
        raise EvaluationInputError("Labels must be nonempty strings.")
    return value.strip().lower().replace("_", "-").replace(" ", "-")


def parse_label_set(raw: str, option: str) -> set[str]:
    values = {normalized_label(item) for item in raw.split(",") if item.strip()}
    if not values:
        raise EvaluationInputError(f"{option} must include at least one label.")
    return values


def parse_prevalences(raw: str) -> list[float]:
    values: list[float] = []
    for item in raw.split(","):
        item = item.strip()
        if not item:
            continue
        try:
            value = float(item)
        except ValueError as exc:
            raise EvaluationInputError(f"Invalid prevalence {item!r}.") from exc
        if not math.isfinite(value) or not 0.0 < value < 1.0:
            raise EvaluationInputError("Prevalence values must be finite and strictly between 0 and 1.")
        values.append(value)
    if not values:
        raise EvaluationInputError("--prevalence must include at least one value.")
    return sorted(set(values))


def load_jsonl(path: Path) -> tuple[list[dict[str, Any]], bytes]:
    try:
        raw = path.read_bytes()
    except OSError as exc:
        raise EvaluationInputError(str(exc)) from exc
    try:
        text = raw.decode("utf-8")
    except UnicodeDecodeError as exc:
        raise EvaluationInputError(f"Input is not UTF-8: {exc}") from exc

    rows: list[dict[str, Any]] = []
    for line_number, line in enumerate(text.splitlines(), start=1):
        if not line.strip():
            continue
        try:
            value = json.loads(line)
        except json.JSONDecodeError as exc:
            raise EvaluationInputError(f"Line {line_number} is invalid JSON: {exc}") from exc
        if not isinstance(value, dict):
            raise EvaluationInputError(f"Line {line_number} must contain a JSON object.")
        value = dict(value)
        value["__line_number"] = line_number
        rows.append(value)
    return rows, raw


def wilson_interval(successes: int, total: int) -> list[float] | None:
    if total <= 0:
        return None
    proportion = successes / total
    z2 = Z_95 * Z_95
    denominator = 1.0 + z2 / total
    center = (proportion + z2 / (2.0 * total)) / denominator
    margin = (
        Z_95
        * math.sqrt((proportion * (1.0 - proportion) + z2 / (4.0 * total)) / total)
        / denominator
    )
    return [max(0.0, center - margin), min(1.0, center + margin)]


def divide(numerator: int | float, denominator: int | float) -> float | None:
    if denominator == 0:
        return None
    return numerator / denominator


def rate_metric(successes: int, total: int) -> dict[str, Any]:
    return {
        "estimate": divide(successes, total),
        "ci95_wilson": wilson_interval(successes, total),
        "numerator": successes,
        "denominator": total,
    }


def no_interval_metric(value: float | None) -> dict[str, Any]:
    return {"estimate": value, "ci95_wilson": None}


def confusion(rows: Iterable[dict[str, Any]]) -> dict[str, int]:
    counts = {"tp": 0, "tn": 0, "fp": 0, "fn": 0}
    for row in rows:
        truth_positive = bool(row["__truth_positive"])
        predicted_positive = bool(row["__predicted_positive"])
        if truth_positive and predicted_positive:
            counts["tp"] += 1
        elif truth_positive:
            counts["fn"] += 1
        elif predicted_positive:
            counts["fp"] += 1
        else:
            counts["tn"] += 1
    return counts


def calculate_metrics(counts: dict[str, int]) -> tuple[dict[str, Any], list[str]]:
    tp, tn, fp, fn = counts["tp"], counts["tn"], counts["fp"], counts["fn"]
    n = tp + tn + fp + fn
    positives = tp + fn
    negatives = tn + fp
    predicted_positives = tp + fp
    predicted_negatives = tn + fn
    warnings: list[str] = []

    denominators = {
        "sensitivity/tpr": positives,
        "false_negative_rate/fnr": positives,
        "specificity/tnr": negatives,
        "false_positive_rate/fpr": negatives,
        "precision/ppv": predicted_positives,
        "negative_predictive_value/npv": predicted_negatives,
    }
    for name, value in denominators.items():
        if value == 0:
            warnings.append(f"{name} is undefined because its denominator is zero.")

    sensitivity = divide(tp, positives)
    specificity = divide(tn, negatives)
    f1 = divide(2 * tp, 2 * tp + fp + fn)
    balanced = (
        (sensitivity + specificity) / 2.0
        if sensitivity is not None and specificity is not None
        else None
    )
    metrics = {
        "accuracy": rate_metric(tp + tn, n),
        "sensitivity_tpr": rate_metric(tp, positives),
        "specificity_tnr": rate_metric(tn, negatives),
        "false_positive_rate_fpr": rate_metric(fp, negatives),
        "false_negative_rate_fnr": rate_metric(fn, positives),
        "precision_ppv": rate_metric(tp, predicted_positives),
        "negative_predictive_value_npv": rate_metric(tn, predicted_negatives),
        "f1": no_interval_metric(f1),
        "balanced_accuracy": no_interval_metric(balanced),
    }
    return metrics, warnings


def result_block(rows: list[dict[str, Any]]) -> tuple[dict[str, Any], list[str]]:
    counts = confusion(rows)
    metrics, warnings = calculate_metrics(counts)
    return {
        "n": len(rows),
        "observed_truth_positive_rate": divide(counts["tp"] + counts["fn"], len(rows)),
        "confusion_matrix": counts,
        "metrics": metrics,
    }, warnings


def project_base_rates(
    metrics: dict[str, Any], prevalences: list[float]
) -> tuple[list[dict[str, Any]], list[str]]:
    sensitivity = metrics["sensitivity_tpr"]["estimate"]
    specificity = metrics["specificity_tnr"]["estimate"]
    sensitivity_interval = metrics["sensitivity_tpr"]["ci95_wilson"]
    specificity_interval = metrics["specificity_tnr"]["ci95_wilson"]
    warnings: list[str] = []
    if sensitivity is None or specificity is None:
        warnings.append(
            "Base-rate projections are unavailable because sensitivity or specificity is undefined."
        )
        return [], warnings

    projections: list[dict[str, Any]] = []

    def projected_values(sens: float, spec: float, prevalence: float) -> tuple[float | None, float | None]:
        fpr = 1.0 - spec
        fnr = 1.0 - sens
        ppv_denominator = sens * prevalence + fpr * (1.0 - prevalence)
        npv_denominator = spec * (1.0 - prevalence) + fnr * prevalence
        return (
            divide(sens * prevalence, ppv_denominator),
            divide(spec * (1.0 - prevalence), npv_denominator),
        )

    for prevalence in prevalences:
        ppv, npv = projected_values(sensitivity, specificity, prevalence)
        ppv_range = None
        npv_range = None
        if sensitivity_interval is not None and specificity_interval is not None:
            low_ppv, low_npv = projected_values(
                sensitivity_interval[0], specificity_interval[0], prevalence
            )
            high_ppv, high_npv = projected_values(
                sensitivity_interval[1], specificity_interval[1], prevalence
            )
            ppv_range = [low_ppv, high_ppv]
            npv_range = [low_npv, high_npv]
        projections.append(
            {
                "prevalence": prevalence,
                "projected_ppv": ppv,
                "projected_npv": npv,
                "projected_ppv_range_from_wilson_bounds": ppv_range,
                "projected_npv_range_from_wilson_bounds": npv_range,
            }
        )
    warnings.append(
        "Projected PPV/NPV ranges combine marginal Wilson bounds as sensitivity ranges; they are not joint 95% confidence intervals."
    )
    return projections, warnings


def group_value(row: dict[str, Any], field: str) -> str:
    group = row.get("group")
    value = group.get(field) if isinstance(group, dict) and field in group else row.get(field)
    if value is None:
        return "<missing>"
    if isinstance(value, (str, int, float, bool)):
        return str(value)
    return json.dumps(value, sort_keys=True, ensure_ascii=False)


def prepare_rows(
    rows: list[dict[str, Any]],
    positive_truth: set[str],
    negative_truth: set[str],
    positive_prediction: set[str] | None,
    negative_prediction: set[str] | None,
    threshold: float | None,
) -> tuple[list[dict[str, Any]], list[str], list[str]]:
    prepared: list[dict[str, Any]] = []
    warnings: list[str] = []
    errors: list[str] = []
    seen_ids: set[str] = set()

    for row in rows:
        line = row["__line_number"]
        sample_id = row.get("id")
        if sample_id is None:
            errors.append(f"Line {line}: id is required.")
            continue
        elif not isinstance(sample_id, (str, int)):
            errors.append(f"Line {line}: id must be a string or integer.")
            continue
        else:
            sample_key = str(sample_id)
            if not sample_key.strip():
                errors.append(f"Line {line}: id must be nonempty.")
                continue
            if sample_key in seen_ids:
                errors.append(f"Line {line}: duplicate id {sample_key!r}.")
                continue
            seen_ids.add(sample_key)

        try:
            truth = normalized_label(row.get("truth"))
        except EvaluationInputError as exc:
            errors.append(f"Line {line}: invalid truth label ({exc}).")
            continue
        if truth not in positive_truth | negative_truth:
            errors.append(
                f"Line {line}: truth label {truth!r} is outside the declared positive and negative truth sets."
            )
            continue

        predicted_positive: bool
        if threshold is not None:
            score = row.get("score")
            if (
                not isinstance(score, (int, float))
                or isinstance(score, bool)
                or not math.isfinite(score)
                or not 0.0 <= float(score) <= 1.0
            ):
                errors.append(f"Line {line}: score must be finite and between 0 and 1.")
                continue
            predicted_positive = float(score) >= threshold
        else:
            try:
                prediction = normalized_label(row.get("prediction"))
            except EvaluationInputError as exc:
                errors.append(f"Line {line}: invalid prediction label ({exc}).")
                continue
            assert positive_prediction is not None
            assert negative_prediction is not None
            if prediction not in positive_prediction | negative_prediction:
                errors.append(
                    f"Line {line}: prediction label {prediction!r} is outside the declared positive and negative prediction sets."
                )
                continue
            predicted_positive = prediction in positive_prediction

        prepared_row = dict(row)
        prepared_row["__id"] = sample_key
        prepared_row["__truth_label"] = truth
        prepared_row["__prediction_label"] = (
            None if threshold is not None else prediction
        )
        prepared_row["__truth_positive"] = truth in positive_truth
        prepared_row["__predicted_positive"] = predicted_positive
        prepared.append(prepared_row)
    return prepared, warnings, errors


def evaluate(
    rows: list[dict[str, Any]],
    raw: bytes,
    positive_truth: set[str],
    negative_truth: set[str],
    positive_prediction: set[str] | None,
    negative_prediction: set[str] | None,
    threshold: float | None,
    prevalences: list[float],
    group_fields: list[str],
) -> dict[str, Any]:
    if positive_truth & negative_truth:
        raise EvaluationInputError("Positive and negative truth labels must be disjoint.")
    if threshold is None:
        if positive_prediction is None or negative_prediction is None:
            raise EvaluationInputError(
                "Categorical evaluation requires positive and negative prediction labels."
            )
        if positive_prediction & negative_prediction:
            raise EvaluationInputError(
                "Positive and negative prediction labels must be disjoint."
            )
    for field in group_fields:
        if field not in ALLOWED_GROUP_FIELDS:
            raise EvaluationInputError(
                f"Unsupported group field {field!r}; use a documented audit dimension."
            )
        tokens = set(filter(None, re.split(r"[^a-z0-9]+", field.lower())))
        blocked_tokens = sorted(tokens & BLOCKED_GROUP_FIELD_TERMS)
        if blocked_tokens:
            raise EvaluationInputError(
                f"Group field {field!r} contains an optimization-oriented token and is not supported."
            )
    prepared, warnings, errors = prepare_rows(
        rows,
        positive_truth,
        negative_truth,
        positive_prediction,
        negative_prediction,
        threshold,
    )
    if errors:
        raise EvaluationInputError("\n".join(errors))
    if not prepared:
        raise EvaluationInputError("No evaluable rows were found.")

    minimum_counts = confusion(prepared)
    minimum_positives = minimum_counts["tp"] + minimum_counts["fn"]
    minimum_negatives = minimum_counts["tn"] + minimum_counts["fp"]
    if (
        len(prepared) < MIN_OVERALL_SIZE
        or minimum_positives < MIN_OVERALL_CLASS_COUNT
        or minimum_negatives < MIN_OVERALL_CLASS_COUNT
    ):
        raise EvaluationInputError(
            "Benchmark is too small for aggregate reporting: require at least "
            f"{MIN_OVERALL_SIZE} rows and {MIN_OVERALL_CLASS_COUNT} examples in each truth class "
            f"(observed n={len(prepared)}, truth-positive={minimum_positives}, truth-negative={minimum_negatives})."
        )

    versions = sorted(
        {
            str(row["model_version"])
            for row in prepared
            if row.get("model_version") not in (None, "")
        }
    )
    missing_version_count = sum(row.get("model_version") in (None, "") for row in prepared)
    if missing_version_count:
        warnings.append(f"{missing_version_count} row(s) do not record model_version.")
    if len(versions) > 1:
        warnings.append(
            "Multiple model versions are mixed in one evaluation: " + ", ".join(versions)
        )

    overall, overall_warnings = result_block(prepared)
    warnings.extend(overall_warnings)
    projections, projection_warnings = project_base_rates(overall["metrics"], prevalences)
    warnings.extend(projection_warnings)
    overall_counts = overall["confusion_matrix"]
    overall_positives = overall_counts["tp"] + overall_counts["fn"]
    overall_negatives = overall_counts["tn"] + overall_counts["fp"]
    if overall_positives < 30 or overall_negatives < 30:
        warnings.append(
            "At least one overall class-specific denominator is below 30; interpret its interval and rate cautiously."
        )

    groups: dict[str, dict[str, Any]] = {}
    for field in group_fields:
        buckets: dict[str, list[dict[str, Any]]] = defaultdict(list)
        for row in prepared:
            buckets[group_value(row, field)].append(row)
        field_results: dict[str, Any] = {}
        for value in sorted(buckets):
            group_rows = buckets[value]
            group_counts = confusion(group_rows)
            group_positives = group_counts["tp"] + group_counts["fn"]
            group_negatives = group_counts["tn"] + group_counts["fp"]
            if (
                len(group_rows) < MIN_GROUP_SIZE
                or group_positives < MIN_GROUP_CLASS_COUNT
                or group_negatives < MIN_GROUP_CLASS_COUNT
            ):
                reasons = []
                if len(group_rows) < MIN_GROUP_SIZE:
                    reasons.append(f"total n is below {MIN_GROUP_SIZE}")
                if group_positives < MIN_GROUP_CLASS_COUNT:
                    reasons.append(
                        f"truth-positive denominator is below {MIN_GROUP_CLASS_COUNT}"
                    )
                if group_negatives < MIN_GROUP_CLASS_COUNT:
                    reasons.append(
                        f"truth-negative denominator is below {MIN_GROUP_CLASS_COUNT}"
                    )
                field_results[value] = {
                    "n": len(group_rows),
                    "truth_positive_count": group_positives,
                    "truth_negative_count": group_negatives,
                    "metrics_suppressed": True,
                    "suppression_reason": "; ".join(reasons),
                }
                warnings.append(
                    f"Group {field}={value} metrics were suppressed: {'; '.join(reasons)}."
                )
                continue
            block, block_warnings = result_block(group_rows)
            group_projections, group_projection_warnings = project_base_rates(
                block["metrics"], prevalences
            )
            block["base_rate_scenarios"] = group_projections
            block["metrics_suppressed"] = False
            field_results[value] = block
            warnings.extend(f"Group {field}={value}: {item}" for item in block_warnings)
            warnings.extend(
                f"Group {field}={value}: {item}" for item in group_projection_warnings
            )
        groups[field] = field_results

    warnings.append(
        "Base-rate projections assume sensitivity and specificity remain stable in deployment."
    )
    warnings.append(
        "Wilson intervals assume independent rows; correlated passages or windows require author/source-level clustered resampling."
    )
    return {
        "schema_version": SCHEMA_VERSION,
        "dataset": {
            "sha256": hashlib.sha256(raw).hexdigest(),
            "rows": len(prepared),
            "model_versions": versions,
            "missing_model_version_rows": missing_version_count,
            "observed_truth_labels": sorted(
                {str(row["__truth_label"]) for row in prepared}
            ),
            "observed_prediction_labels": (
                sorted(
                    {
                        str(row["__prediction_label"])
                        for row in prepared
                        if row["__prediction_label"] is not None
                    }
                )
                if threshold is None
                else None
            ),
        },
        "policy": {
            "positive_truth_labels": sorted(positive_truth),
            "negative_truth_labels": sorted(negative_truth),
            "positive_prediction_labels": (
                sorted(positive_prediction) if positive_prediction is not None else None
            ),
            "negative_prediction_labels": (
                sorted(negative_prediction) if negative_prediction is not None else None
            ),
            "score_threshold": threshold,
            "threshold_optimization": False,
        },
        "overall": overall,
        "groups": groups,
        "base_rate_scenarios": projections,
        "warnings": sorted(set(warnings)),
        "interpretation": {
            "scope": "Fixed detector policy on an authorized labeled sample",
            "decision_warning": DISCLAIMER,
        },
    }


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        description="Evaluate fixed AI-detector predictions on labeled JSONL."
    )
    parser.add_argument("dataset", type=Path, help="Labeled JSONL file")
    parser.add_argument(
        "--positive-truth",
        required=True,
        help="Comma-separated truth labels treated as positive",
    )
    parser.add_argument(
        "--negative-truth",
        default="human",
        help="Comma-separated truth labels treated as negative (default: human)",
    )
    mode = parser.add_mutually_exclusive_group(required=True)
    mode.add_argument(
        "--positive-prediction",
        help="Comma-separated returned labels treated as positive",
    )
    mode.add_argument(
        "--threshold",
        type=float,
        help="Fixed score threshold; rows must contain score",
    )
    parser.add_argument(
        "--negative-prediction",
        default="human",
        help="Comma-separated returned labels treated as negative for categorical evaluation (default: human)",
    )
    parser.add_argument(
        "--prevalence",
        default="0.001,0.01,0.05,0.10,0.50",
        help="Comma-separated deployment prevalence scenarios",
    )
    parser.add_argument(
        "--group-field",
        action="append",
        default=[],
        choices=sorted(ALLOWED_GROUP_FIELDS),
        help="Group field to evaluate; repeat for multiple fields",
    )
    parser.add_argument("--output", type=Path, help="Write JSON report to this file")
    return parser


def main(argv: list[str] | None = None) -> int:
    parser = build_parser()
    args = parser.parse_args(argv)
    try:
        if args.threshold is not None and (
            not math.isfinite(args.threshold) or not 0.0 <= args.threshold <= 1.0
        ):
            raise EvaluationInputError("--threshold must be finite and between 0 and 1.")
        positive_truth = parse_label_set(args.positive_truth, "--positive-truth")
        negative_truth = parse_label_set(args.negative_truth, "--negative-truth")
        positive_prediction = (
            parse_label_set(args.positive_prediction, "--positive-prediction")
            if args.positive_prediction is not None
            else None
        )
        negative_prediction = (
            parse_label_set(args.negative_prediction, "--negative-prediction")
            if args.positive_prediction is not None
            else None
        )
        prevalences = parse_prevalences(args.prevalence)
        group_fields = []
        for field in args.group_field:
            if not field or not field.strip():
                raise EvaluationInputError("--group-field values must be nonempty.")
            group_fields.append(field.strip())
        rows, raw = load_jsonl(args.dataset)
        if not rows:
            print("error: no evaluable rows", file=sys.stderr)
            return 4
        report = evaluate(
            rows,
            raw,
            positive_truth,
            negative_truth,
            positive_prediction,
            negative_prediction,
            args.threshold,
            prevalences,
            group_fields,
        )
        content = json.dumps(report, indent=2, sort_keys=True, ensure_ascii=False)
        if args.output is None:
            print(content)
        else:
            args.output.write_text(content, encoding="utf-8")
        return 0
    except EvaluationInputError as exc:
        if str(exc) == "No evaluable rows were found.":
            print(f"error: {exc}", file=sys.stderr)
            return 4
        print(f"error: {exc}", file=sys.stderr)
        return 2
    except OSError as exc:
        print(f"error: {exc}", file=sys.stderr)
        return 2


if __name__ == "__main__":
    raise SystemExit(main())
