import importlib.util
import json
import math
import sys
import unittest
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
SCRIPT = ROOT / ".codex/skills/pangram-audit/scripts/audit_result.py"
SPEC = importlib.util.spec_from_file_location("audit_result", SCRIPT)
audit_result = importlib.util.module_from_spec(SPEC)
assert SPEC and SPEC.loader
sys.modules[SPEC.name] = audit_result
SPEC.loader.exec_module(audit_result)


def sample_result():
    text = " ".join(f"word{i}" for i in range(60))
    first = " ".join(text.split()[:30])
    second_start = len(first) + 1
    second = text[second_start:]
    return {
        "stage": "STAGE_SUCCESS",
        "text": text,
        "version": "3.3.2",
        "headline": "AI Detected",
        "prediction": "A saved product prediction.",
        "prediction_short": "Mixed",
        "fraction_ai": 0.5,
        "fraction_ai_assisted": 0.5,
        "fraction_human": 0.0,
        "num_ai_segments": 1,
        "num_ai_assisted_segments": 1,
        "num_human_segments": 0,
        "windows": [
            {
                "text": first,
                "label": "AI-Generated",
                "ai_assistance_score": 0.85,
                "confidence": "High",
                "start_index": 0,
                "end_index": len(first),
                "word_count": 30,
                "token_length": 40,
            },
            {
                "text": second,
                "label": "Lightly AI-Assisted",
                "ai_assistance_score": 0.4,
                "confidence": "Medium",
                "start_index": second_start,
                "end_index": len(text),
                "word_count": 30,
                "token_length": 40,
            },
        ],
    }


class AuditResultTests(unittest.TestCase):
    def test_valid_current_direct_result(self):
        raw = json.dumps(sample_result()).encode()
        report = audit_result.audit(raw)
        self.assertEqual(report["input"]["response_shape"], "direct")
        self.assertEqual(report["input"]["model_version"], "3.3.2")
        self.assertEqual(report["check_totals"]["errors"], 0)
        self.assertEqual(report["summary"]["window_count"], 2)
        self.assertEqual(
            report["summary"]["window_aggregates"]["label_counts"]["assisted"], 1
        )
        self.assertFalse(
            any(check["code"] == "windows[1].label" for check in report["checks"])
        )

    def test_task_wrapper_is_unwrapped(self):
        result = sample_result()
        stage = result.pop("stage")
        raw = json.dumps({"stage": stage, "task_id": "task-1", "output": result}).encode()
        report = audit_result.audit(raw)
        self.assertEqual(report["input"]["response_shape"], "output-wrapper")
        self.assertEqual(report["summary"]["stage"], "STAGE_SUCCESS")

    def test_nonfinite_score_and_invalid_offset_are_errors(self):
        result = sample_result()
        result["windows"][0]["ai_assistance_score"] = math.nan
        result["windows"][1]["end_index"] = len(result["text"]) + 10
        report = audit_result.audit(json.dumps(result).encode())
        codes = {check["code"] for check in report["checks"]}
        self.assertIn("windows[0].score", codes)
        self.assertIn("windows[1].bounds", codes)
        self.assertGreaterEqual(report["check_totals"]["errors"], 2)

    def test_fraction_mismatch_is_error(self):
        result = sample_result()
        result["fraction_human"] = 0.5
        report = audit_result.audit(json.dumps(result).encode())
        codes = {check["code"] for check in report["checks"]}
        self.assertIn("fractions.sum", codes)

    def test_failed_task_zero_fractions_are_not_treated_as_a_sum_error(self):
        result = {
            "stage": "STAGE_FAILED",
            "text": "",
            "version": "",
            "headline": "preprocessing failed",
            "prediction": "",
            "prediction_short": "",
            "fraction_ai": 0.0,
            "fraction_ai_assisted": 0.0,
            "fraction_human": 0.0,
            "num_ai_segments": 0,
            "num_ai_assisted_segments": 0,
            "num_human_segments": 0,
            "windows": [],
        }
        report = audit_result.audit(json.dumps(result).encode())
        codes = {check["code"] for check in report["checks"]}
        self.assertNotIn("fractions.sum", codes)
        self.assertIn("stage.not_success", codes)

    def test_current_score_label_mismatch_warns_but_exact_half_does_not(self):
        result = sample_result()
        result["windows"][0]["label"] = "Human-Written"
        result["windows"][1]["ai_assistance_score"] = 0.5
        result["num_ai_segments"] = 0
        result["num_ai_assisted_segments"] = 1
        result["num_human_segments"] = 1
        report = audit_result.audit(json.dumps(result).encode())
        score_label_checks = [
            check for check in report["checks"] if check["code"].endswith("score_label")
        ]
        self.assertEqual(len(score_label_checks), 1)
        self.assertEqual(score_label_checks[0]["code"], "windows[0].score_label")

    def test_report_does_not_echo_submitted_or_window_text(self):
        result = sample_result()
        secret = "UNIQUE_PRIVATE_SUBMITTED_TEXT"
        result["text"] += " " + secret
        result["windows"][-1]["end_index"] = len(result["text"])
        result["windows"][-1]["text"] += " " + secret
        report = audit_result.audit(json.dumps(result).encode())
        serialized = json.dumps(report)
        markdown = audit_result.markdown_report(report)
        self.assertNotIn(secret, serialized)
        self.assertNotIn(secret, markdown)
        self.assertNotIn("score_summary", serialized)
        self.assertIn("local provenance", report["interpretation"]["decision_warning"])
        self.assertFalse(report["input"]["text_included_in_report"])

    def test_audit_context_is_recorded(self):
        report = audit_result.audit(
            json.dumps(sample_result()).encode(),
            result_retrieved_at="2026-07-15T14:30:00Z",
            input_format="raw-text",
            extraction_path="async API task",
        )
        self.assertEqual(report["audit_context"]["input_format"], "raw-text")
        self.assertFalse(
            any(check["code"].startswith("context.") for check in report["checks"])
        )

    def test_top_level_must_be_object(self):
        with self.assertRaises(audit_result.AuditInputError):
            audit_result.audit(b"[]")


if __name__ == "__main__":
    unittest.main()
