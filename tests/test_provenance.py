import importlib.util
import sys
import tempfile
import unittest
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
SCRIPT = ROOT / ".codex/skills/pangram-audit/scripts/provenance.py"
SPEC = importlib.util.spec_from_file_location("provenance", SCRIPT)
provenance = importlib.util.module_from_spec(SPEC)
assert SPEC and SPEC.loader
sys.modules[SPEC.name] = provenance
SPEC.loader.exec_module(provenance)


class ProvenanceTests(unittest.TestCase):
    def test_unchanged_snapshot_verifies_and_content_is_not_stored(self):
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary)
            manifest_path = root / "provenance.json"
            draft = root / "draft.md"
            secret = "Private draft body that must not enter the manifest"
            draft.write_text(secret, encoding="utf-8")
            provenance.initialize(manifest_path)
            provenance.snapshot(manifest_path, draft, "First draft")
            manifest = provenance.read_manifest(manifest_path)
            report = provenance.verify_manifest(manifest_path, manifest)
            self.assertTrue(report["verification_passed"])
            self.assertTrue(report["chain_integrity_valid"])
            self.assertFalse(report["authorship_verified"])
            self.assertFalse(report["trusted_timestamp"])
            self.assertTrue(report["checked_files"][0]["matches_latest_snapshot"])
            self.assertNotIn(secret, manifest_path.read_text(encoding="utf-8"))

    def test_file_mutation_fails_verification(self):
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary)
            manifest_path = root / "provenance.json"
            draft = root / "draft.md"
            draft.write_text("version one", encoding="utf-8")
            provenance.initialize(manifest_path)
            provenance.snapshot(manifest_path, draft, None)
            draft.write_text("version two", encoding="utf-8")
            report = provenance.verify_manifest(
                manifest_path, provenance.read_manifest(manifest_path)
            )
            self.assertFalse(report["verification_passed"])
            self.assertTrue(report["chain_integrity_valid"])
            self.assertFalse(report["current_files_match_latest_snapshots"])
            self.assertTrue(any("does not match" in error for error in report["errors"]))

    def test_event_mutation_breaks_chain(self):
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary)
            manifest_path = root / "provenance.json"
            draft = root / "draft.md"
            draft.write_text("draft", encoding="utf-8")
            provenance.initialize(manifest_path)
            provenance.snapshot(manifest_path, draft, "Original note")
            manifest = provenance.read_manifest(manifest_path)
            manifest["events"][1]["note"] = "Changed note"
            report = provenance.verify_manifest(manifest_path, manifest, check_files=False)
            self.assertFalse(report["chain_integrity_valid"])
            self.assertTrue(any("hash does not match" in error for error in report["errors"]))

    def test_event_deletion_breaks_head_or_chain(self):
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary)
            manifest_path = root / "provenance.json"
            draft = root / "draft.md"
            draft.write_text("draft", encoding="utf-8")
            provenance.initialize(manifest_path)
            provenance.snapshot(manifest_path, draft, "Snapshot")
            provenance.declare(manifest_path, "limited", "AI was used for spell checking.")
            manifest = provenance.read_manifest(manifest_path)
            del manifest["events"][1]
            report = provenance.verify_manifest(manifest_path, manifest, check_files=False)
            self.assertFalse(report["chain_integrity_valid"])
            self.assertGreater(len(report["errors"]), 0)

    def test_path_outside_project_boundary_is_rejected(self):
        with tempfile.TemporaryDirectory() as temporary, tempfile.TemporaryDirectory() as outside:
            root = Path(temporary)
            manifest_path = root / "provenance.json"
            outside_file = Path(outside) / "outside.md"
            outside_file.write_text("outside", encoding="utf-8")
            provenance.initialize(manifest_path)
            with self.assertRaises(provenance.ProvenanceError):
                provenance.snapshot(manifest_path, outside_file, None)

    def test_declaration_is_hash_chained(self):
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary)
            manifest_path = root / "provenance.json"
            provenance.initialize(manifest_path)
            event = provenance.declare(
                manifest_path,
                "substantial",
                "AI produced an early outline; I verified and rewrote the final analysis.",
            )
            self.assertEqual(event["type"], "ai_use_declaration")
            self.assertEqual(event["sequence"], 1)
            report = provenance.verify_manifest(
                manifest_path, provenance.read_manifest(manifest_path)
            )
            self.assertTrue(report["verification_passed"])
            self.assertIn("not an independently trusted timestamp", report["decision_warning"])


if __name__ == "__main__":
    unittest.main()
