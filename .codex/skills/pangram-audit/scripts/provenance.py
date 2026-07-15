#!/usr/bin/env python3
"""Create and verify a local, hash-chained drafting provenance manifest.

The manifest stores file hashes and metadata, never document content. It is
tamper-evident supporting evidence, not a trusted timestamp or proof of authorship.
"""

from __future__ import annotations

import argparse
import hashlib
import json
import os
import subprocess
import sys
import tempfile
from datetime import datetime, timezone
from pathlib import Path
from typing import Any


SCHEMA_VERSION = "draft-provenance/v1"
DISCLAIMER = (
    "This locally generated manifest is tamper-evident supporting evidence, not an "
    "independently trusted timestamp or proof of authorship. A person controlling "
    "the project can rebuild the manifest; publish the head hash externally for "
    "stronger timestamp evidence."
)
AI_USE_LEVELS = ("none", "limited", "substantial", "unknown")


class ProvenanceError(ValueError):
    """Raised for invalid manifest operations."""


def utc_now() -> str:
    return datetime.now(timezone.utc).isoformat(timespec="seconds").replace("+00:00", "Z")


def sha256_bytes(data: bytes) -> str:
    return hashlib.sha256(data).hexdigest()


def file_digest(path: Path) -> tuple[str, int]:
    digest = hashlib.sha256()
    size = 0
    try:
        with path.open("rb") as handle:
            while True:
                chunk = handle.read(1024 * 1024)
                if not chunk:
                    break
                digest.update(chunk)
                size += len(chunk)
    except OSError as exc:
        raise ProvenanceError(str(exc)) from exc
    return digest.hexdigest(), size


def canonical_event(event: dict[str, Any]) -> bytes:
    unhashed = {key: value for key, value in event.items() if key != "event_sha256"}
    return json.dumps(
        unhashed, sort_keys=True, separators=(",", ":"), ensure_ascii=False
    ).encode("utf-8")


def event_digest(event: dict[str, Any]) -> str:
    return sha256_bytes(canonical_event(event))


def manifest_boundary(manifest_path: Path) -> Path:
    return manifest_path.resolve().parent


def relative_project_path(manifest_path: Path, file_path: Path) -> tuple[Path, str]:
    boundary = manifest_boundary(manifest_path)
    resolved = file_path.resolve()
    try:
        relative = resolved.relative_to(boundary)
    except ValueError as exc:
        raise ProvenanceError(
            f"File {resolved} is outside the manifest project boundary {boundary}."
        ) from exc
    if resolved == manifest_path.resolve():
        raise ProvenanceError("The manifest cannot snapshot itself.")
    return resolved, relative.as_posix()


def read_manifest(path: Path) -> dict[str, Any]:
    try:
        value = json.loads(path.read_text(encoding="utf-8"))
    except OSError as exc:
        raise ProvenanceError(str(exc)) from exc
    except json.JSONDecodeError as exc:
        raise ProvenanceError(f"Manifest is invalid JSON: {exc}") from exc
    if not isinstance(value, dict):
        raise ProvenanceError("Manifest root must be a JSON object.")
    return value


def atomic_write(path: Path, value: dict[str, Any]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    content = json.dumps(value, indent=2, sort_keys=True, ensure_ascii=False) + "\n"
    try:
        descriptor, temporary_name = tempfile.mkstemp(
            prefix=f".{path.name}.", suffix=".tmp", dir=str(path.parent)
        )
        with os.fdopen(descriptor, "w", encoding="utf-8") as handle:
            handle.write(content)
            handle.flush()
            os.fsync(handle.fileno())
        os.replace(temporary_name, path)
    except OSError as exc:
        try:
            if "temporary_name" in locals():
                Path(temporary_name).unlink(missing_ok=True)
        except OSError:
            pass
        raise ProvenanceError(str(exc)) from exc


def add_event(manifest: dict[str, Any], event_type: str, payload: dict[str, Any]) -> dict[str, Any]:
    events = manifest.get("events")
    if not isinstance(events, list):
        raise ProvenanceError("Manifest events must be an array.")
    previous_hash = events[-1].get("event_sha256") if events else None
    event = {
        "sequence": len(events),
        "type": event_type,
        "recorded_at_utc": utc_now(),
        "previous_event_sha256": previous_hash,
        **payload,
    }
    event["event_sha256"] = event_digest(event)
    events.append(event)
    manifest["head_event_sha256"] = event["event_sha256"]
    return event


def git_commit(boundary: Path) -> str | None:
    try:
        completed = subprocess.run(
            ["git", "-C", str(boundary), "rev-parse", "--verify", "HEAD"],
            check=False,
            capture_output=True,
            text=True,
            timeout=5,
        )
    except (OSError, subprocess.SubprocessError):
        return None
    value = completed.stdout.strip()
    return value if completed.returncode == 0 and len(value) == 40 else None


def initialize(path: Path) -> dict[str, Any]:
    if path.exists():
        raise ProvenanceError(f"Manifest already exists: {path}")
    manifest: dict[str, Any] = {
        "schema_version": SCHEMA_VERSION,
        "project_boundary": ".",
        "created_at_utc": utc_now(),
        "disclaimer": DISCLAIMER,
        "events": [],
        "head_event_sha256": None,
    }
    add_event(manifest, "manifest_initialized", {"schema_version": SCHEMA_VERSION})
    atomic_write(path, manifest)
    return manifest


def snapshot(path: Path, file_path: Path, note: str | None) -> dict[str, Any]:
    manifest = read_manifest(path)
    check = verify_manifest(path, manifest, check_files=False)
    if not check["chain_integrity_valid"]:
        raise ProvenanceError("Refusing to append to an invalid manifest: " + "; ".join(check["errors"]))
    resolved, relative = relative_project_path(path, file_path)
    if not resolved.is_file():
        raise ProvenanceError(f"Snapshot target is not a regular file: {resolved}")
    digest, size = file_digest(resolved)
    payload: dict[str, Any] = {
        "path": relative,
        "file_sha256": digest,
        "byte_size": size,
    }
    if note:
        payload["note"] = note
    commit = git_commit(manifest_boundary(path))
    if commit:
        payload["git_commit"] = commit
    event = add_event(manifest, "file_snapshot", payload)
    atomic_write(path, manifest)
    return event


def declare(path: Path, ai_use: str, statement: str) -> dict[str, Any]:
    manifest = read_manifest(path)
    check = verify_manifest(path, manifest, check_files=False)
    if not check["chain_integrity_valid"]:
        raise ProvenanceError("Refusing to append to an invalid manifest: " + "; ".join(check["errors"]))
    statement = statement.strip()
    if not statement:
        raise ProvenanceError("The disclosure statement must be nonempty.")
    event = add_event(
        manifest,
        "ai_use_declaration",
        {"ai_use": ai_use, "statement": statement},
    )
    atomic_write(path, manifest)
    return event


def verify_manifest(
    path: Path, manifest: dict[str, Any], *, check_files: bool = True
) -> dict[str, Any]:
    chain_errors: list[str] = []
    file_errors: list[str] = []
    warnings: list[str] = []
    if manifest.get("schema_version") != SCHEMA_VERSION:
        chain_errors.append(
            f"Unsupported schema_version {manifest.get('schema_version')!r}; expected {SCHEMA_VERSION!r}."
        )
    if manifest.get("project_boundary") != ".":
        chain_errors.append("project_boundary must be '.'.")
    events = manifest.get("events")
    if not isinstance(events, list) or not events:
        chain_errors.append("events must be a nonempty array.")
        events = []

    previous_hash: str | None = None
    latest_snapshots: dict[str, dict[str, Any]] = {}
    for index, event in enumerate(events):
        if not isinstance(event, dict):
            chain_errors.append(f"Event {index} is not an object.")
            previous_hash = None
            continue
        if event.get("sequence") != index:
            chain_errors.append(f"Event {index} has an invalid sequence value.")
        if event.get("previous_event_sha256") != previous_hash:
            chain_errors.append(f"Event {index} does not link to the preceding event hash.")
        stored_hash = event.get("event_sha256")
        calculated_hash = event_digest(event)
        if stored_hash != calculated_hash:
            chain_errors.append(f"Event {index} hash does not match its content.")
        previous_hash = stored_hash if isinstance(stored_hash, str) else None
        if event.get("type") == "file_snapshot" and isinstance(event.get("path"), str):
            latest_snapshots[event["path"]] = event

    if manifest.get("head_event_sha256") != previous_hash:
        chain_errors.append("head_event_sha256 does not match the final event.")

    checked_files: list[dict[str, Any]] = []
    if check_files:
        boundary = manifest_boundary(path)
        for relative, event in sorted(latest_snapshots.items()):
            candidate = (boundary / relative).resolve()
            try:
                candidate.relative_to(boundary)
            except ValueError:
                file_errors.append(f"Snapshot path escapes the project boundary: {relative}")
                continue
            if not candidate.is_file():
                file_errors.append(f"Latest snapshotted file is missing: {relative}")
                checked_files.append({"path": relative, "matches_latest_snapshot": False})
                continue
            digest, size = file_digest(candidate)
            matches = digest == event.get("file_sha256") and size == event.get("byte_size")
            if not matches:
                file_errors.append(f"Current file does not match its latest snapshot: {relative}")
            checked_files.append(
                {
                    "path": relative,
                    "matches_latest_snapshot": matches,
                    "current_sha256": digest,
                    "current_byte_size": size,
                }
            )

    if not latest_snapshots:
        warnings.append("The manifest contains no file snapshots.")
    warnings.append(
        "Only the latest snapshot of each current file can be compared without storing historical file content."
    )
    warnings.append(
        "A locally recomputed chain cannot prevent a person controlling the project from rebuilding its history."
    )
    errors = chain_errors + file_errors
    return {
        "schema_version": "draft-provenance-verification/v1",
        "verification_passed": not errors,
        "chain_integrity_valid": not chain_errors,
        "current_files_match_latest_snapshots": not file_errors,
        "authorship_verified": False,
        "trusted_timestamp": False,
        "declaration_source": "self_asserted",
        "manifest": str(path),
        "event_count": len(events),
        "head_event_sha256": manifest.get("head_event_sha256"),
        "checked_files": checked_files,
        "errors": errors,
        "warnings": warnings,
        "decision_warning": DISCLAIMER,
    }


def print_json(value: dict[str, Any]) -> None:
    print(json.dumps(value, indent=2, sort_keys=True, ensure_ascii=False))


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        description="Create or verify a local drafting-provenance manifest."
    )
    subparsers = parser.add_subparsers(dest="command", required=True)

    init_parser = subparsers.add_parser("init", help="Create a new manifest")
    init_parser.add_argument("--manifest", type=Path, required=True)

    snapshot_parser = subparsers.add_parser("snapshot", help="Record a file hash")
    snapshot_parser.add_argument("--manifest", type=Path, required=True)
    snapshot_parser.add_argument("--file", type=Path, required=True)
    snapshot_parser.add_argument("--note")

    declare_parser = subparsers.add_parser("declare", help="Record a truthful AI-use disclosure")
    declare_parser.add_argument("--manifest", type=Path, required=True)
    declare_parser.add_argument("--ai-use", choices=AI_USE_LEVELS, required=True)
    declare_parser.add_argument("--statement", required=True)

    verify_parser = subparsers.add_parser("verify", help="Verify the chain and current files")
    verify_parser.add_argument("--manifest", type=Path, required=True)
    return parser


def main(argv: list[str] | None = None) -> int:
    args = build_parser().parse_args(argv)
    try:
        manifest_path = args.manifest.resolve()
        if args.command == "init":
            value = initialize(manifest_path)
            print_json(
                {
                    "created": str(manifest_path),
                    "head_event_sha256": value["head_event_sha256"],
                    "decision_warning": DISCLAIMER,
                }
            )
            return 0
        if args.command == "snapshot":
            event = snapshot(manifest_path, args.file, args.note)
            print_json({"recorded_event": event, "decision_warning": DISCLAIMER})
            return 0
        if args.command == "declare":
            event = declare(manifest_path, args.ai_use, args.statement)
            print_json({"recorded_event": event, "decision_warning": DISCLAIMER})
            return 0

        manifest = read_manifest(manifest_path)
        report = verify_manifest(manifest_path, manifest)
        print_json(report)
        return 0 if report["verification_passed"] else 3
    except ProvenanceError as exc:
        print(f"error: {exc}", file=sys.stderr)
        return 2


if __name__ == "__main__":
    raise SystemExit(main())
