#!/usr/bin/env python3
"""Validate and interpret a saved Pangram response without network access.

The report intentionally omits submitted and window text. It checks response
consistency; it does not determine authorship or recommend edits.
"""

from __future__ import annotations

import argparse
import hashlib
import json
import math
import sys
from collections import Counter
from pathlib import Path
from typing import Any


SCHEMA_VERSION = "pangram-audit/v1"
DISCLAIMER = (
    "Detector scores and local provenance are supporting signals, not proof of authorship or misconduct."
)
KNOWN_SHORT_PREDICTIONS = {"ai", "ai-assisted", "human", "mixed"}
KNOWN_CONFIDENCE = {"high", "medium", "low"}


class AuditInputError(ValueError):
    """Raised when a result file cannot be audited."""


def sha256_bytes(data: bytes) -> str:
    return hashlib.sha256(data).hexdigest()


def canonical_label(value: Any) -> str | None:
    if not isinstance(value, str):
        return None
    normalized = value.strip().lower().replace("_", "-").replace(" ", "-")
    while "--" in normalized:
        normalized = normalized.replace("--", "-")
    aliases = {
        "human": "human",
        "human-written": "human",
        "fully-human-written": "human",
        "lightly-ai-assisted": "light",
        "light-ai-assisted": "light",
        "moderately-ai-assisted": "moderate",
        "moderate-ai-assisted": "moderate",
        "ai": "ai",
        "ai-generated": "ai",
        "fully-ai-generated": "ai",
    }
    return aliases.get(normalized)


def band_for_33_score(score: float) -> str | None:
    """Return an unambiguous Pangram 3.3 score band.

    Pangram documents exactly 0.50 only as the boundary between two "between"
    ranges, so no label is asserted for that exact value.
    """

    if score <= 0.25:
        return "human"
    if score < 0.50:
        return "light"
    if score == 0.50:
        return None
    if score < 0.75:
        return "moderate"
    return "ai"


def finite_number(value: Any) -> bool:
    return isinstance(value, (int, float)) and not isinstance(value, bool) and math.isfinite(value)


def add_check(
    checks: list[dict[str, str]], code: str, severity: str, message: str
) -> None:
    checks.append({"code": code, "severity": severity, "message": message})


def unwrap_response(data: Any) -> tuple[dict[str, Any], str]:
    if not isinstance(data, dict):
        raise AuditInputError("The top-level JSON value must be an object.")

    for key in ("result", "output"):
        nested = data.get(key)
        if isinstance(nested, dict):
            merged = dict(nested)
            if "stage" not in merged and isinstance(data.get("stage"), str):
                merged["stage"] = data["stage"]
            if "task_id" not in merged and isinstance(data.get("task_id"), str):
                merged["task_id"] = data["task_id"]
            return merged, f"{key}-wrapper"
    return data, "direct"


def count_words(text: str) -> int:
    return len(text.split())


def audit(
    raw: bytes,
    *,
    result_retrieved_at: str | None = None,
    input_format: str | None = None,
    extraction_path: str | None = None,
) -> dict[str, Any]:
    try:
        parsed = json.loads(raw)
    except (UnicodeDecodeError, json.JSONDecodeError) as exc:
        raise AuditInputError(f"Invalid UTF-8 JSON: {exc}") from exc

    result, response_shape = unwrap_response(parsed)
    checks: list[dict[str, str]] = []
    limitations = [
        "Pangram describes 3.2/3.3 resolution as approximately 50 words, not token-level provenance.",
        "Results can change with detector version, domain, language, length, extraction method, and editing history.",
        "Current score bands describe AI involvement; they are not documented probabilities of misconduct.",
        "Highlighted windows must not be treated as instructions for changing a detector score.",
    ]

    stage = result.get("stage")
    if stage is None:
        add_check(
            checks,
            "stage.missing",
            "warning",
            "No task stage is present; this may be an archived or legacy result.",
        )
    elif not isinstance(stage, str):
        add_check(checks, "stage.type", "error", "Task stage must be a string.")
    elif stage != "STAGE_SUCCESS":
        severity = "warning" if stage.startswith("STAGE_") else "error"
        add_check(
            checks,
            "stage.not_success",
            severity,
            f"Task stage is {stage!r}; classification fields may be incomplete.",
        )

    audit_context = {
        "result_retrieved_at": result_retrieved_at,
        "input_format": input_format,
        "extraction_path": extraction_path,
    }
    for field, value in audit_context.items():
        if value is None:
            add_check(
                checks,
                f"context.{field}.missing",
                "info",
                f"{field} was not supplied; record it for a reproducible review packet.",
            )

    version = result.get("version")
    if not isinstance(version, str) or not version.strip():
        add_check(
            checks,
            "version.missing",
            "warning",
            "No model/API version is recorded; score-band and drift comparisons are limited.",
        )
        version_value = None
    else:
        version_value = version.strip()

    prediction_short = result.get("prediction_short")
    if prediction_short not in (None, ""):
        if not isinstance(prediction_short, str):
            add_check(
                checks,
                "prediction_short.type",
                "error",
                "prediction_short must be a string.",
            )
        elif prediction_short.strip().lower() not in KNOWN_SHORT_PREDICTIONS:
            add_check(
                checks,
                "prediction_short.unknown",
                "warning",
                f"Unrecognized short prediction {prediction_short!r}; preserve it as version-specific output.",
            )

    fractions: dict[str, float | None] = {}
    fraction_fields = {
        "ai": "fraction_ai",
        "assisted": "fraction_ai_assisted",
        "human": "fraction_human",
    }
    for short_name, field in fraction_fields.items():
        value = result.get(field)
        if value is None:
            fractions[short_name] = None
            add_check(
                checks,
                f"{field}.missing",
                "warning",
                f"{field} is missing.",
            )
        elif not finite_number(value):
            fractions[short_name] = None
            add_check(
                checks,
                f"{field}.type",
                "error",
                f"{field} must be a finite number.",
            )
        else:
            numeric = float(value)
            fractions[short_name] = numeric
            if not 0.0 <= numeric <= 1.0:
                add_check(
                    checks,
                    f"{field}.range",
                    "error",
                    f"{field} must be between 0 and 1.",
                )

    present_fractions = [value for value in fractions.values() if value is not None]
    if len(present_fractions) == 3 and stage in (None, "STAGE_SUCCESS"):
        total = sum(present_fractions)
        if abs(total - 1.0) > 0.02:
            add_check(
                checks,
                "fractions.sum",
                "error",
                f"Document fractions sum to {total:.6f}, outside the 0.02 audit tolerance around 1.0.",
            )
        elif abs(total - 1.0) > 1e-6:
            add_check(
                checks,
                "fractions.rounding",
                "info",
                f"Document fractions sum to {total:.6f}; the small difference may be rounding.",
            )

    analyzed_text = result.get("text")
    text_available = isinstance(analyzed_text, str)
    if analyzed_text is not None and not text_available:
        add_check(checks, "text.type", "error", "The analyzed text must be a string.")

    word_count = count_words(analyzed_text) if text_available else None
    character_count = len(analyzed_text) if text_available else None
    if word_count is not None and word_count < 50:
        add_check(
            checks,
            "input.short",
            "warning",
            f"The saved input has {word_count} words; Pangram 3.2/3.3 documents a 50-word minimum.",
        )
    if character_count is not None and character_count > 75_000:
        add_check(
            checks,
            "input.long",
            "warning",
            "The saved input exceeds the 75,000-character maximum documented for Pangram 3.1; verify the applicable version limit.",
        )

    windows_value = result.get("windows")
    windows: list[Any]
    if windows_value is None:
        windows = []
        add_check(
            checks,
            "windows.missing",
            "warning",
            "No windows array is present; segment-level consistency cannot be checked.",
        )
    elif not isinstance(windows_value, list):
        windows = []
        add_check(checks, "windows.type", "error", "windows must be an array.")
    else:
        windows = windows_value

    observed_counts = {"ai": 0, "assisted": 0, "human": 0, "unknown": 0}
    confidence_counts: Counter[str] = Counter()
    previous_start: int | None = None
    for index, window in enumerate(windows):
        prefix = f"windows[{index}]"
        if not isinstance(window, dict):
            add_check(checks, f"{prefix}.type", "error", f"{prefix} must be an object.")
            observed_counts["unknown"] += 1
            continue

        label = canonical_label(window.get("label"))
        if label is None:
            observed_counts["unknown"] += 1
            add_check(
                checks,
                f"{prefix}.label",
                "warning",
                f"{prefix} has a missing or unrecognized label.",
            )
        elif label in {"light", "moderate"}:
            observed_counts["assisted"] += 1
        else:
            observed_counts[label] += 1

        score = window.get("ai_assistance_score")
        if not finite_number(score):
            add_check(
                checks,
                f"{prefix}.score",
                "error",
                f"{prefix}.ai_assistance_score must be finite.",
            )
        else:
            numeric_score = float(score)
            if not 0.0 <= numeric_score <= 1.0:
                add_check(
                    checks,
                    f"{prefix}.score_range",
                    "error",
                    f"{prefix}.ai_assistance_score must be between 0 and 1.",
                )
            elif version_value and version_value.startswith("3.3") and label is not None:
                expected = band_for_33_score(numeric_score)
                if expected is not None and expected != label:
                    add_check(
                        checks,
                        f"{prefix}.score_label",
                        "warning",
                        f"{prefix} label does not match the public 3.3 score band; preserve the raw result and verify the exact service version.",
                    )

        confidence = window.get("confidence")
        if confidence is not None:
            if not isinstance(confidence, str) or confidence.strip().lower() not in KNOWN_CONFIDENCE:
                add_check(
                    checks,
                    f"{prefix}.confidence",
                    "warning",
                    f"{prefix} has an unrecognized confidence value.",
                )
            else:
                confidence_counts[confidence.strip().lower()] += 1

        start = window.get("start_index")
        end = window.get("end_index")
        if not isinstance(start, int) or isinstance(start, bool):
            add_check(
                checks,
                f"{prefix}.start_index",
                "error",
                f"{prefix}.start_index must be an integer.",
            )
            start = None
        if not isinstance(end, int) or isinstance(end, bool):
            add_check(
                checks,
                f"{prefix}.end_index",
                "error",
                f"{prefix}.end_index must be an integer.",
            )
            end = None
        if start is not None and end is not None:
            if start < 0 or end < start:
                add_check(
                    checks,
                    f"{prefix}.range",
                    "error",
                    f"{prefix} has an invalid character range.",
                )
            if text_available and end > len(analyzed_text):
                add_check(
                    checks,
                    f"{prefix}.bounds",
                    "error",
                    f"{prefix} extends beyond the saved input text.",
                )
            if previous_start is not None and start < previous_start:
                add_check(
                    checks,
                    f"{prefix}.order",
                    "warning",
                    f"{prefix} starts before the preceding returned window.",
                )
            previous_start = start

            window_text = window.get("text")
            if (
                text_available
                and isinstance(window_text, str)
                and 0 <= start <= end <= len(analyzed_text)
                and analyzed_text[start:end] != window_text
            ):
                add_check(
                    checks,
                    f"{prefix}.text_range",
                    "warning",
                    f"{prefix} text does not match the saved input at its documented offsets.",
                )

        for field in ("word_count", "token_length"):
            value = window.get(field)
            if value is not None and (
                not isinstance(value, int) or isinstance(value, bool) or value < 0
            ):
                add_check(
                    checks,
                    f"{prefix}.{field}",
                    "error",
                    f"{prefix}.{field} must be a nonnegative integer.",
                )

    documented_counts = {
        "ai": result.get("num_ai_segments"),
        "assisted": result.get("num_ai_assisted_segments"),
        "human": result.get("num_human_segments"),
    }
    for category, value in documented_counts.items():
        field = {
            "ai": "num_ai_segments",
            "assisted": "num_ai_assisted_segments",
            "human": "num_human_segments",
        }[category]
        if value is None:
            add_check(checks, f"{field}.missing", "warning", f"{field} is missing.")
        elif not isinstance(value, int) or isinstance(value, bool) or value < 0:
            add_check(
                checks,
                f"{field}.type",
                "error",
                f"{field} must be a nonnegative integer.",
            )
        elif windows_value is not None and observed_counts["unknown"] == 0 and value != observed_counts[category]:
            add_check(
                checks,
                f"{field}.mismatch",
                "warning",
                f"{field} is {value}, while returned window labels imply {observed_counts[category]}.",
            )

    if not checks:
        add_check(
            checks,
            "structure.ok",
            "info",
            "No structural inconsistencies were found in the saved response.",
        )

    error_count = sum(check["severity"] == "error" for check in checks)
    warning_count = sum(check["severity"] == "warning" for check in checks)
    return {
        "schema_version": SCHEMA_VERSION,
        "input": {
            "sha256": sha256_bytes(raw),
            "response_shape": response_shape,
            "model_version": version_value,
            "text_included_in_report": False,
            "saved_text_word_count": word_count,
            "saved_text_character_count": character_count,
        },
        "summary": {
            "stage": stage,
            "headline": result.get("headline") if isinstance(result.get("headline"), str) else None,
            "prediction": result.get("prediction") if isinstance(result.get("prediction"), str) else None,
            "prediction_short": prediction_short if isinstance(prediction_short, str) else None,
            "fractions": fractions,
            "window_count": len(windows),
            "documented_segment_counts": documented_counts,
            "window_aggregates": {
                "label_counts": observed_counts,
                "confidence_counts": dict(sorted(confidence_counts.items())),
                "per_span_details_suppressed": True,
            },
        },
        "audit_context": audit_context,
        "checks": checks,
        "check_totals": {"errors": error_count, "warnings": warning_count},
        "interpretation": {
            "scope": "Saved probabilistic detector output",
            "decision_warning": DISCLAIMER,
        },
        "limitations": limitations,
    }


def markdown_report(report: dict[str, Any]) -> str:
    summary = report["summary"]
    source = report["input"]
    fractions = summary["fractions"]
    context = report["audit_context"]
    aggregates = summary["window_aggregates"]

    def display(value: Any) -> str:
        return "not recorded" if value is None or value == "" else str(value)

    lines = [
        "# Pangram Saved-Result Audit",
        "",
        f"- Raw response SHA-256: `{source['sha256']}`",
        f"- Response shape: {source['response_shape']}",
        f"- Model/API version: {display(source['model_version'])}",
        f"- Task stage: {display(summary['stage'])}",
        f"- Returned headline: {display(summary['headline'])}",
        f"- Returned short prediction: {display(summary['prediction_short'])}",
        f"- Returned long prediction: {display(summary['prediction'])}",
        f"- Fractions: AI={display(fractions['ai'])}, assisted={display(fractions['assisted'])}, human={display(fractions['human'])}",
        f"- Returned windows: {summary['window_count']}",
        f"- Saved input words: {display(source['saved_text_word_count'])}",
        f"- Saved input characters: {display(source['saved_text_character_count'])}",
        f"- Documented segment counts: {json.dumps(summary['documented_segment_counts'], sort_keys=True)}",
        f"- Aggregate window labels: {json.dumps(aggregates['label_counts'], sort_keys=True)}",
        f"- Aggregate window confidence: {json.dumps(aggregates['confidence_counts'], sort_keys=True)}",
        "- Per-span scores, offsets, and text included in this report: no",
        "- Submitted and window text included in this report: no",
        f"- Result retrieved at: {display(context['result_retrieved_at'])}",
        f"- Input format: {display(context['input_format'])}",
        f"- Extraction path: {display(context['extraction_path'])}",
        "",
        "## Consistency checks",
        "",
    ]
    severity_order = {"error": 0, "warning": 1, "info": 2}
    for check in sorted(report["checks"], key=lambda item: (severity_order[item["severity"]], item["code"])):
        lines.append(f"- **{check['severity'].upper()} — {check['code']}**: {check['message']}")
    lines.extend(["", "## Limitations", ""])
    lines.extend(f"- {item}" for item in report["limitations"])
    lines.extend(["", f"> {DISCLAIMER}", ""])
    return "\n".join(lines)


def write_output(content: str, output: Path | None) -> None:
    if output is None:
        print(content)
    else:
        output.write_text(content, encoding="utf-8")


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        description="Audit a saved Pangram JSON response without sending text anywhere."
    )
    parser.add_argument("result", type=Path, help="Path to saved Pangram JSON")
    parser.add_argument(
        "--format", choices=("json", "markdown"), default="json", help="Report format"
    )
    parser.add_argument("--output", type=Path, help="Write report to this file")
    parser.add_argument(
        "--result-retrieved-at",
        help="Recorded retrieval date/time for the saved result",
    )
    parser.add_argument(
        "--input-format",
        help="Submitted format, such as raw-text, docx, pdf, or rtf",
    )
    parser.add_argument(
        "--extraction-path",
        help="How text reached Pangram, such as API raw text or website PDF upload",
    )
    return parser


def main(argv: list[str] | None = None) -> int:
    args = build_parser().parse_args(argv)
    try:
        raw = args.result.read_bytes()
        report = audit(
            raw,
            result_retrieved_at=args.result_retrieved_at,
            input_format=args.input_format,
            extraction_path=args.extraction_path,
        )
        if args.format == "json":
            content = json.dumps(report, indent=2, sort_keys=True, ensure_ascii=False)
        else:
            content = markdown_report(report)
        write_output(content, args.output)
        return 3 if report["check_totals"]["errors"] else 0
    except (OSError, AuditInputError) as exc:
        print(f"error: {exc}", file=sys.stderr)
        return 2


if __name__ == "__main__":
    raise SystemExit(main())
