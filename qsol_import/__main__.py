from __future__ import annotations

import argparse
import json
from pathlib import Path

from qsol_import.core import import_openai_zip


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(prog="qsol-import", description="Deterministic vendor-neutral context importer")
    parser.add_argument("source", type=Path, help="source export ZIP")
    parser.add_argument("--adapter", choices=["openai"], default="openai")
    parser.add_argument("--profile", default="conversation-first", choices=["conversation-first"])
    parser.add_argument("--policy", type=Path, default=None, help="explicit policy JSON")
    parser.add_argument("--output", type=Path, required=True)
    return parser


def main() -> int:
    args = build_parser().parse_args()
    if args.adapter != "openai":
        raise SystemExit("unsupported adapter")
    policy = args.policy or Path(__file__).resolve().parents[1] / "policies" / "conversation-first.json"
    receipt = import_openai_zip(args.source, args.output, policy)
    print(json.dumps(receipt, indent=2, sort_keys=True))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
