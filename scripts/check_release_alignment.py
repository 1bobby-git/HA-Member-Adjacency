from __future__ import annotations

import json
import os
import re
import sys
from pathlib import Path


MANIFEST_PATH = Path("custom_components/member_adjacency/manifest.json")
VERSION_RE = re.compile(r"^\d+\.\d+\.\d+(?:[-+][0-9A-Za-z.-]+)?$")
TAG_RE = re.compile(r"^v(?P<version>\d+\.\d+\.\d+(?:[-+][0-9A-Za-z.-]+)?)$")


def read_manifest_version(manifest_path: Path = MANIFEST_PATH) -> str | None:
    try:
        with manifest_path.open("r", encoding="utf-8") as manifest_file:
            version = json.load(manifest_file).get("version")
    except (OSError, json.JSONDecodeError):
        return None

    if not isinstance(version, str) or VERSION_RE.fullmatch(version) is None:
        return None
    return version


def _tag_from_environment() -> str | None:
    ref_name = os.environ.get("GITHUB_REF_NAME")
    if ref_name:
        return ref_name

    ref = os.environ.get("GITHUB_REF")
    if ref and ref.startswith("refs/tags/"):
        return ref.removeprefix("refs/tags/")

    return None


def check_release_alignment(manifest_path: Path = MANIFEST_PATH, tag: str | None = None) -> int:
    version = read_manifest_version(manifest_path)
    if version is None:
        return 1

    tag = tag or _tag_from_environment()
    if not tag:
        return 2

    match = TAG_RE.fullmatch(tag)
    if match is None or match.group("version") != version:
        return 1
    return 0


def main() -> int:
    tag = sys.argv[1] if len(sys.argv) > 1 else None
    version = read_manifest_version()
    result = check_release_alignment(tag=tag)
    if result == 1:
        expected = f"v{version}" if version else "v{manifest.version}"
        actual = tag or _tag_from_environment() or "<missing>"
        print(f"Release tag {actual} does not match manifest version {expected}.", file=sys.stderr)
    elif result == 2:
        expected = f"v{version}" if version else "v{manifest.version}"
        print(f"No release tag was provided; expected {expected}.", file=sys.stderr)
    return result


if __name__ == "__main__":
    raise SystemExit(main())
