from __future__ import annotations

import argparse
import platform
import sys
from pathlib import Path
from typing import Any

from qsol_import.canonical import canonical_json_bytes, sha256_bytes, sha256_file


PORTABILITY_PROTOCOL = "QSOL-IMPORT/PORTABILITY-RECEIPT/1"
SCHEMA_VERSION = "1.0.0"
SUPPORTED_PYTHON_MIN = (3, 11)
SUPPORTED_PYTHON_MAX = (3, 13)
SUPPORTED_PLATFORMS = ("linux", "darwin", "win32")
BOUNDARIES = (
    "SUPPORTED_ENVIRONMENT != ALL_FUTURE_ENVIRONMENTS",
    "BYTE_IDENTICAL_OUTPUT != FACTUAL_TRUTH",
    "IMPLEMENTATION_CHANGE != SILENT_BASELINE_REFRESH",
    "PLATFORM_PATH != CANONICAL_PATH",
    "LOCALE != CANONICAL_COLLATION",
)


class PortabilityError(ValueError):
    pass


def tree_receipt(root: Path) -> list[dict[str, Any]]:
    if root.is_symlink() or not root.is_dir():
        raise PortabilityError("tree root must be a non-symlink directory")

    files: list[Path] = []
    for entry in root.rglob("*"):
        # Check the entry before filtering by type. A directory symlink is not a
        # file and Path.rglob() does not descend through it, so checking only the
        # selected files would make a symlink-only tree look empty.
        if entry.is_symlink():
            raise PortabilityError(
                f"tree contains a symlink: {entry.relative_to(root).as_posix()}"
            )
        if entry.is_dir():
            continue
        if not entry.is_file():
            raise PortabilityError(
                f"tree contains a non-regular entry: {entry.relative_to(root).as_posix()}"
            )
        files.append(entry)

    rows: list[dict[str, Any]] = []
    for path in sorted(
        files,
        key=lambda item: item.relative_to(root).as_posix().encode("utf-8"),
    ):
        rel = path.relative_to(root).as_posix()
        rows.append(
            {
                "path": rel,
                "sha256": sha256_file(path),
                "size_bytes": path.stat().st_size,
            }
        )
    return rows


def tree_sha256(root: Path) -> str:
    return sha256_bytes(canonical_json_bytes(tree_receipt(root)))


def compare_trees(first: Path, second: Path) -> dict[str, Any]:
    first_rows = tree_receipt(first)
    second_rows = tree_receipt(second)
    first_sha = sha256_bytes(canonical_json_bytes(first_rows))
    second_sha = sha256_bytes(canonical_json_bytes(second_rows))
    body = {
        "protocol": PORTABILITY_PROTOCOL,
        "schema_version": SCHEMA_VERSION,
        "python_implementation": platform.python_implementation(),
        "python_version": (
            f"{sys.version_info.major}.{sys.version_info.minor}.{sys.version_info.micro}"
        ),
        "platform": sys.platform,
        "supported_python_range": "CPython >=3.11,<3.14",
        "supported_platforms": list(SUPPORTED_PLATFORMS),
        "first_tree_sha256": first_sha,
        "second_tree_sha256": second_sha,
        "byte_identical": first_rows == second_rows,
        "canonical_dependencies": [
            "exact input bytes",
            "exact policy bytes",
            "exact implementation bytes",
            "UTF-8 byte ordering",
        ],
        "excluded_dependencies": [
            "wall clock",
            "randomness",
            "network",
            "locale",
            "absolute filesystem path",
        ],
        "boundaries": list(BOUNDARIES),
    }
    return {
        **body,
        "receipt_sha256": sha256_bytes(canonical_json_bytes(body)),
    }


def assert_supported_runtime() -> None:
    if platform.python_implementation() != "CPython":
        raise PortabilityError(
            "only CPython is in the verified portability boundary"
        )
    version = (sys.version_info.major, sys.version_info.minor)
    if not (SUPPORTED_PYTHON_MIN <= version <= SUPPORTED_PYTHON_MAX):
        raise PortabilityError(
            "CPython runtime is outside the verified 3.11-3.13 boundary"
        )
    if sys.platform not in SUPPORTED_PLATFORMS:
        raise PortabilityError(
            "platform is outside the verified Linux/macOS/Windows boundary"
        )


def _parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        description="Compare two QSOL-IMPORT output trees byte-for-byte"
    )
    parser.add_argument("first", type=Path)
    parser.add_argument("second", type=Path)
    return parser


def main() -> int:
    import json

    args = _parser().parse_args()
    assert_supported_runtime()
    receipt = compare_trees(args.first, args.second)
    print(json.dumps(receipt, indent=2, sort_keys=True))
    return 0 if receipt["byte_identical"] else 1


if __name__ == "__main__":
    raise SystemExit(main())
