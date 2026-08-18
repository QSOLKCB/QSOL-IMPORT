from __future__ import annotations

import argparse
import tempfile
from importlib import resources
from pathlib import Path
from typing import Any

from qsol_import.canonical import canonical_json_bytes, sha256_bytes, sha256_file
from qsol_import.core import import_openai_zip


def _tree_receipt(root: Path) -> list[dict[str, Any]]:
    return [
        {
            "path": path.relative_to(root).as_posix(),
            "sha256": sha256_file(path),
            "size_bytes": path.stat().st_size,
        }
        for path in sorted(p for p in root.rglob("*") if p.is_file())
    ]


def validate_openai_snapshots(sources: list[Path], policy_path: Path) -> dict[str, Any]:
    if len(sources) < 2:
        raise ValueError("real-snapshot validation requires at least two export ZIPs")

    snapshots = []
    for source in sources:
        with tempfile.TemporaryDirectory(prefix="qsol-import-validation-") as tmp:
            root = Path(tmp)
            receipt_a = import_openai_zip(source, root / "a", policy_path)
            receipt_b = import_openai_zip(source, root / "b", policy_path)
            tree_a = _tree_receipt(root / "a")
            tree_b = _tree_receipt(root / "b")
            if tree_a != tree_b:
                raise ValueError(f"non-deterministic repeated import for input {receipt_a['input_sha256']}")
            if receipt_a != receipt_b:
                raise ValueError(f"non-deterministic receipt for input {receipt_a['input_sha256']}")

            snapshots.append(
                {
                    "input_sha256": receipt_a["input_sha256"],
                    "output_sha256": receipt_a["output_sha256"],
                    "candidate_sha256": receipt_a["candidate_sha256"],
                    "conversations": receipt_a["conversations"],
                    "messages": receipt_a["messages"],
                    "files_seen": receipt_a["files_seen"],
                    "repeat_byte_identical": True,
                    "tree_sha256": sha256_bytes(canonical_json_bytes(tree_a)),
                }
            )

    body = {
        "protocol": "QSOL-IMPORT/OPENAI-SNAPSHOT-VALIDATION/1",
        "schema_version": "1.0.0",
        "snapshot_count": len(snapshots),
        "snapshots": snapshots,
        "source_paths_emitted": False,
        "source_bytes_persisted": False,
    }
    return {
        **body,
        "validation_sha256": sha256_bytes(canonical_json_bytes(body)),
    }


def _parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        description="Validate QSOL-IMPORT against two or more local OpenAI export snapshots without persisting source bytes",
    )
    parser.add_argument("sources", nargs="+", type=Path)
    parser.add_argument("--policy", type=Path, default=None)
    parser.add_argument("--output", type=Path, default=None, help="optional validation receipt path")
    return parser


def main() -> int:
    args = _parser().parse_args()
    if len(args.sources) < 2:
        raise SystemExit("provide at least two export ZIP snapshots")

    if args.policy is not None:
        report = validate_openai_snapshots(args.sources, args.policy)
    else:
        policy_resource = resources.files("qsol_import.policies").joinpath("conversation-first.json")
        with resources.as_file(policy_resource) as policy_path:
            report = validate_openai_snapshots(args.sources, policy_path)

    encoded = canonical_json_bytes(report)
    if args.output is not None:
        args.output.write_bytes(encoded)
    else:
        import sys

        sys.stdout.buffer.write(encoded)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
