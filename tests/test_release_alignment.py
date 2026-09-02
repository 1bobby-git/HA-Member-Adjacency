from __future__ import annotations

import importlib
import json
import os
import subprocess
import sys
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch


release_alignment = importlib.import_module("scripts.check_release_alignment")
REPO_ROOT = Path(__file__).resolve().parents[1]
SCRIPT_PATH = REPO_ROOT / "scripts" / "check_release_alignment.py"
CURRENT_VERSION = "1.6.2"


def run_release_alignment_cli(
    *args: str,
    cwd: Path = REPO_ROOT,
    env: dict[str, str] | None = None,
) -> subprocess.CompletedProcess[str]:
    process_env = os.environ.copy()
    process_env.update(env or {})
    return subprocess.run(
        [sys.executable, str(SCRIPT_PATH), *args],
        cwd=cwd,
        env=process_env,
        text=True,
        stdout=subprocess.PIPE,
        stderr=subprocess.PIPE,
        check=False,
    )


class ReleaseAlignmentTests(unittest.TestCase):
    def test_match_returns_zero(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            manifest = Path(tmp) / "manifest.json"
            manifest.write_text(json.dumps({"version": "1.6.0"}), encoding="utf-8")

            self.assertEqual(0, release_alignment.check_release_alignment(manifest, "v1.6.0"))

    def test_mismatch_returns_one(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            manifest = Path(tmp) / "manifest.json"
            manifest.write_text(json.dumps({"version": "1.6.0"}), encoding="utf-8")

            self.assertEqual(1, release_alignment.check_release_alignment(manifest, "v1.5.2"))

    def test_malformed_tag_returns_one(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            manifest = Path(tmp) / "manifest.json"
            manifest.write_text(json.dumps({"version": "1.6.0"}), encoding="utf-8")

            self.assertEqual(1, release_alignment.check_release_alignment(manifest, "1.6.0"))

    def test_malformed_manifest_returns_one(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            manifest = Path(tmp) / "manifest.json"
            manifest.write_text(json.dumps({"version": 160}), encoding="utf-8")

            with patch.dict(release_alignment.os.environ, {}, clear=True):
                self.assertEqual(1, release_alignment.check_release_alignment(manifest))

    def test_missing_tag_returns_two(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            manifest = Path(tmp) / "manifest.json"
            manifest.write_text(json.dumps({"version": "1.6.0"}), encoding="utf-8")

            with patch.dict(release_alignment.os.environ, {}, clear=True):
                self.assertEqual(2, release_alignment.check_release_alignment(manifest))

    def test_environment_ref_name_is_used_when_tag_argument_is_missing(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            manifest = Path(tmp) / "manifest.json"
            manifest.write_text(json.dumps({"version": "1.6.0"}), encoding="utf-8")

            with patch.dict(release_alignment.os.environ, {"GITHUB_REF_NAME": "v1.6.0"}, clear=True):
                self.assertEqual(0, release_alignment.check_release_alignment(manifest))

    def test_cli_matching_tag_exits_zero(self) -> None:
        result = run_release_alignment_cli(f"v{CURRENT_VERSION}")

        self.assertEqual(0, result.returncode, result.stderr)
        self.assertEqual("", result.stderr)

    def test_cli_matching_tag_exits_zero_outside_repo_cwd(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            result = run_release_alignment_cli(f"v{CURRENT_VERSION}", cwd=Path(tmp))

        self.assertEqual(0, result.returncode, result.stderr)
        self.assertEqual("", result.stderr)

    def test_cli_mismatched_tag_exits_one(self) -> None:
        result = run_release_alignment_cli("v1.5.2")

        self.assertEqual(1, result.returncode)
        self.assertIn(
            f"Release tag v1.5.2 does not match manifest version v{CURRENT_VERSION}.",
            result.stderr,
        )

    def test_cli_malformed_tag_exits_one(self) -> None:
        result = run_release_alignment_cli(CURRENT_VERSION)

        self.assertEqual(1, result.returncode)
        self.assertIn(
            f"Release tag {CURRENT_VERSION} does not match manifest version v{CURRENT_VERSION}.",
            result.stderr,
        )

    def test_cli_missing_tag_exits_two_with_clear_stderr(self) -> None:
        env = {"GITHUB_REF_NAME": "", "GITHUB_REF": ""}

        result = run_release_alignment_cli(env=env)

        self.assertEqual(2, result.returncode)
        self.assertIn(
            f"No release tag was provided; expected v{CURRENT_VERSION}.",
            result.stderr,
        )


if __name__ == "__main__":
    unittest.main()
