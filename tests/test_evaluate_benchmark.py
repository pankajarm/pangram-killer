import importlib.util
import json
import subprocess
import sys
import tempfile
import unittest
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
SCRIPT = ROOT / ".codex/skills/pangram-audit/scripts/evaluate_benchmark.py"
SPEC = importlib.util.spec_from_file_location("evaluate_benchmark", SCRIPT)
evaluate_benchmark = importlib.util.module_from_spec(SPEC)
assert SPEC and SPEC.loader
sys.modules[SPEC.name] = evaluate_benchmark
SPEC.loader.exec_module(evaluate_benchmark)


def run_evaluation(rows, prevalences=None, groups=None):
    raw = "\n".join(json.dumps(row) for row in rows).encode()
    prepared_rows = []
    for line_number, row in enumerate(rows, 1):
        copied = dict(row)
        copied["__line_number"] = line_number
        prepared_rows.append(copied)
    return evaluate_benchmark.evaluate(
        prepared_rows,
        raw,
        {"ai"},
        {"human"},
        {"ai"},
        {"human"},
        None,
        prevalences or [0.01],
        groups or [],
    )


class EvaluateBenchmarkTests(unittest.TestCase):
    def test_perfect_predictions(self):
        rows = [
            {
                "id": f"ai-{index}",
                "truth": "ai",
                "prediction": "ai",
                "model_version": "3.3.2",
            }
            for index in range(20)
        ] + [
            {
                "id": f"human-{index}",
                "truth": "human",
                "prediction": "human",
                "model_version": "3.3.2",
            }
            for index in range(20)
        ]
        report = run_evaluation(rows)
        metrics = report["overall"]["metrics"]
        self.assertEqual(metrics["accuracy"]["estimate"], 1.0)
        self.assertEqual(metrics["sensitivity_tpr"]["estimate"], 1.0)
        self.assertEqual(metrics["specificity_tnr"]["estimate"], 1.0)
        self.assertEqual(metrics["f1"]["estimate"], 1.0)

    def test_tp_tn_fp_fn_fixture(self):
        metrics, warnings = evaluate_benchmark.calculate_metrics(
            {"tp": 1, "tn": 1, "fp": 1, "fn": 1}
        )
        self.assertEqual(warnings, [])
        for name in (
            "accuracy",
            "sensitivity_tpr",
            "specificity_tnr",
            "false_positive_rate_fpr",
            "false_negative_rate_fnr",
            "precision_ppv",
            "negative_predictive_value_npv",
            "f1",
            "balanced_accuracy",
        ):
            self.assertAlmostEqual(metrics[name]["estimate"], 0.5)
        interval = metrics["sensitivity_tpr"]["ci95_wilson"]
        self.assertAlmostEqual(interval[0], 0.094531, places=5)
        self.assertAlmostEqual(interval[1], 0.905469, places=5)

    def test_base_rate_projection(self):
        rows = []
        for index in range(90):
            rows.append({"id": f"tp-{index}", "truth": "ai", "prediction": "ai"})
        for index in range(10):
            rows.append({"id": f"fn-{index}", "truth": "ai", "prediction": "human"})
        rows.append({"id": "fp-0", "truth": "human", "prediction": "ai"})
        for index in range(99):
            rows.append({"id": f"tn-{index}", "truth": "human", "prediction": "human"})
        report = run_evaluation(rows, prevalences=[0.01])
        scenario = report["base_rate_scenarios"][0]
        self.assertAlmostEqual(scenario["projected_ppv"], 0.476190476, places=8)
        self.assertAlmostEqual(scenario["projected_npv"], 0.998980736, places=8)
        self.assertEqual(len(scenario["projected_ppv_range_from_wilson_bounds"]), 2)
        self.assertEqual(len(scenario["projected_npv_range_from_wilson_bounds"]), 2)

    def test_zero_denominator_is_null_with_warning(self):
        metrics, warnings = evaluate_benchmark.calculate_metrics(
            {"tp": 0, "tn": 2, "fp": 0, "fn": 0}
        )
        self.assertIsNone(metrics["sensitivity_tpr"]["estimate"])
        self.assertTrue(any("denominator is zero" in warning for warning in warnings))

    def test_groups_and_version_warnings(self):
        rows = [
            {
                "id": f"ai-{index}",
                "truth": "ai",
                "prediction": "ai",
                "model_version": "3.3.1",
                "group": {"domain": "academic"},
            }
            for index in range(20)
        ] + [
            {
                "id": f"human-{index}",
                "truth": "human",
                "prediction": "human",
                "model_version": "3.3.2",
                "group": {"domain": "news"},
            }
            for index in range(20)
        ]
        report = run_evaluation(rows, groups=["domain"])
        self.assertEqual(set(report["groups"]["domain"]), {"academic", "news"})
        self.assertTrue(any("Multiple model versions" in warning for warning in report["warnings"]))
        self.assertTrue(any("metrics were suppressed" in warning for warning in report["warnings"]))

    def test_duplicate_or_missing_ids_fail_closed(self):
        duplicate_rows = [
            {"id": "same", "truth": "ai", "prediction": "ai", "__line_number": 1},
            {"id": "same", "truth": "human", "prediction": "human", "__line_number": 2},
        ]
        missing_rows = [
            {"truth": "ai", "prediction": "ai", "__line_number": 1}
        ]
        empty_rows = [
            {"id": "  ", "truth": "ai", "prediction": "ai", "__line_number": 1}
        ]
        for rows in (duplicate_rows, missing_rows, empty_rows):
            with self.subTest(rows=rows):
                with self.assertRaises(evaluate_benchmark.EvaluationInputError):
                    evaluate_benchmark.evaluate(
                        rows,
                        b"fixture",
                        {"ai"},
                        {"human"},
                        {"ai"},
                        {"human"},
                        None,
                        [0.01],
                        [],
                    )

    def test_explicit_threshold_uses_score(self):
        rows = [
            {
                "id": f"ai-{index}",
                "truth": "ai",
                "score": 0.75,
                "__line_number": index + 1,
            }
            for index in range(20)
        ] + [
            {
                "id": f"human-{index}",
                "truth": "human",
                "score": 0.74,
                "__line_number": index + 21,
            }
            for index in range(20)
        ]
        report = evaluate_benchmark.evaluate(
            rows,
            b"fixture",
            {"ai"},
            {"human"},
            None,
            None,
            0.75,
            [0.01],
            [],
        )
        self.assertEqual(report["overall"]["confusion_matrix"], {"tp": 20, "tn": 20, "fp": 0, "fn": 0})
        self.assertEqual(report["policy"]["score_threshold"], 0.75)
        self.assertFalse(report["policy"]["threshold_optimization"])

    def test_unknown_labels_fail_closed(self):
        rows = [
            {"id": "typo", "truth": "humna", "prediction": "???", "__line_number": 1}
        ]
        with self.assertRaises(evaluate_benchmark.EvaluationInputError):
            evaluate_benchmark.evaluate(
                rows,
                b"fixture",
                {"ai"},
                {"human"},
                {"ai"},
                {"human"},
                None,
                [0.01],
                [],
            )

    def test_small_group_metrics_are_suppressed(self):
        rows = [
            {
                "id": "a",
                "truth": "ai",
                "prediction": "human",
                "group": {"domain": "tiny"},
            },
            {
                "id": "b",
                "truth": "human",
                "prediction": "human",
                "group": {"domain": "tiny"},
            },
        ] + [
            {
                "id": f"main-ai-{index}",
                "truth": "ai",
                "prediction": "ai",
                "group": {"domain": "main"},
            }
            for index in range(19)
        ] + [
            {
                "id": f"main-human-{index}",
                "truth": "human",
                "prediction": "human",
                "group": {"domain": "main"},
            }
            for index in range(19)
        ]
        report = run_evaluation(rows, groups=["domain"])
        self.assertTrue(report["groups"]["domain"]["tiny"]["metrics_suppressed"])
        self.assertNotIn("metrics", report["groups"]["domain"]["tiny"])

    def test_small_overall_benchmark_is_rejected(self):
        rows = [
            {"id": "a", "truth": "ai", "prediction": "ai"},
            {"id": "b", "truth": "human", "prediction": "human"},
        ]
        with self.assertRaises(evaluate_benchmark.EvaluationInputError):
            run_evaluation(rows)

    def test_optimization_oriented_group_field_is_rejected(self):
        rows = [
            {"id": "a", "truth": "ai", "prediction": "ai", "variant": "one"}
        ]
        with self.assertRaises(evaluate_benchmark.EvaluationInputError):
            run_evaluation(rows, groups=["rewrite_variant"])

    def test_neutral_unapproved_group_field_is_rejected(self):
        rows = [
            {"id": "a", "truth": "ai", "prediction": "ai", "condition": "one"}
        ]
        with self.assertRaises(evaluate_benchmark.EvaluationInputError):
            run_evaluation(rows, groups=["condition"])

    def test_writer_background_is_an_allowed_audit_dimension(self):
        self.assertIn("writer_background", evaluate_benchmark.ALLOWED_GROUP_FIELDS)

    def test_generator_dimensions_are_allowed(self):
        self.assertIn("generator_family", evaluate_benchmark.ALLOWED_GROUP_FIELDS)
        self.assertIn("generator_release_period", evaluate_benchmark.ALLOWED_GROUP_FIELDS)

    def test_prevalence_endpoints_are_rejected(self):
        for value in ("0", "1", "0,0.5", "0.5,1"):
            with self.subTest(value=value):
                with self.assertRaises(evaluate_benchmark.EvaluationInputError):
                    evaluate_benchmark.parse_prevalences(value)

    def test_large_group_includes_base_rate_scenarios(self):
        rows = []
        for index in range(20):
            rows.append(
                {
                    "id": f"ai-{index}",
                    "truth": "ai",
                    "prediction": "ai" if index < 18 else "human",
                    "group": {"domain": "academic"},
                }
            )
        for index in range(20):
            rows.append(
                {
                    "id": f"human-{index}",
                    "truth": "human",
                    "prediction": "human" if index < 19 else "ai",
                    "group": {"domain": "academic"},
                }
            )
        report = run_evaluation(rows, prevalences=[0.01], groups=["domain"])
        group = report["groups"]["domain"]["academic"]
        self.assertFalse(group["metrics_suppressed"])
        self.assertEqual(group["base_rate_scenarios"][0]["prevalence"], 0.01)

    def test_large_total_with_tiny_class_is_suppressed(self):
        rows = [
            {
                "id": f"ai-{index}",
                "truth": "ai",
                "prediction": "ai",
                "group": {"domain": "imbalanced"},
            }
            for index in range(99)
        ]
        rows.append(
            {
                "id": "human-0",
                "truth": "human",
                "prediction": "human",
                "group": {"domain": "imbalanced"},
            }
        )
        rows.extend(
            {
                "id": f"balancer-human-{index}",
                "truth": "human",
                "prediction": "human",
                "group": {"domain": "balancer"},
            }
            for index in range(9)
        )
        report = run_evaluation(rows, groups=["domain"])
        group = report["groups"]["domain"]["imbalanced"]
        self.assertTrue(group["metrics_suppressed"])
        self.assertIn("truth-negative denominator", group["suppression_reason"])

    def test_optimize_threshold_is_not_supported(self):
        with tempfile.TemporaryDirectory() as temporary:
            dataset = Path(temporary) / "data.jsonl"
            dataset.write_text('{"id":"a","truth":"ai","score":0.9}\n', encoding="utf-8")
            completed = subprocess.run(
                [
                    sys.executable,
                    str(SCRIPT),
                    str(dataset),
                    "--positive-truth",
                    "ai",
                    "--threshold",
                    "0.75",
                    "--optimize-threshold",
                ],
                capture_output=True,
                text=True,
            )
            self.assertEqual(completed.returncode, 2)
            self.assertIn("unrecognized arguments", completed.stderr)


if __name__ == "__main__":
    unittest.main()
