from __future__ import annotations

import importlib
import json
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch


release_alignment = importlib.import_module("scripts.check_release_alignment")


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


if __name__ == "__main__":
    unittest.main()
