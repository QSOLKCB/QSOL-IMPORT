from __future__ import annotations

import argparse
import json
from importlib import resources
from pathlib import Path

from qsol_import.adapter_pipeline import import_with_adapter
from qsol_import.adapters.registry import adapter_names, get_adapter
from qsol_import.core import import_openai_zip


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        prog="qsol-import",
        description="Deterministic vendor-neutral context importer",
    )
    parser.add_argument("source", type=Path, help="source export ZIP/TAR/JSON/JSONL")
    parser.add_argument(
        "--adapter",
        choices=("openai",) + adapter_names(),
        default="openai",
    )
    parser.add_argument(
        "--profile",
        default="conversation-first",
        choices=["conversation-first"],
    )
    parser.add_argument("--policy", type=Path, default=None, help="explicit policy JSON")
    parser.add_argument("--output", type=Path, required=True)
    return parser


def _run(args: argparse.Namespace, policy_path: Path) -> dict:
    if args.adapter == "openai":
        return import_openai_zip(args.source, args.output, policy_path)
    return import_with_adapter(
        args.source,
        args.output,
        policy_path,
        get_adapter(args.adapter),
    )


def main() -> int:
    args = build_parser().parse_args()
    if args.policy is not None:
        receipt = _run(args, args.policy)
    else:
        policy_resource = resources.files("qsol_import.policies").joinpath(
            "conversation-first.json"
        )
        with resources.as_file(policy_resource) as policy_path:
            receipt = _run(args, policy_path)

    print(json.dumps(receipt, indent=2, sort_keys=True))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
