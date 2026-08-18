from __future__ import annotations

import hashlib
import json
from pathlib import Path
from typing import Any, BinaryIO


class DuplicateKeyError(ValueError):
    pass


def _reject_duplicate_pairs(pairs: list[tuple[str, Any]]) -> dict[str, Any]:
    out: dict[str, Any] = {}
    for key, value in pairs:
        if key in out:
            raise DuplicateKeyError(f"duplicate JSON object member: {key!r}")
        out[key] = value
    return out


def _reject_constant(value: str) -> Any:
    raise ValueError(f"non-finite JSON constant rejected: {value}")


def loads_strict(data: str | bytes) -> Any:
    return json.loads(
        data,
        object_pairs_hook=_reject_duplicate_pairs,
        parse_constant=_reject_constant,
    )


def canonical_json_bytes(value: Any) -> bytes:
    return (
        json.dumps(
            value,
            ensure_ascii=False,
            sort_keys=True,
            separators=(",", ":"),
            allow_nan=False,
        )
        + "\n"
    ).encode("utf-8")


def sha256_bytes(data: bytes) -> str:
    return hashlib.sha256(data).hexdigest()


def sha256_stream(handle: BinaryIO, chunk_size: int = 1024 * 1024) -> str:
    digest = hashlib.sha256()
    while chunk := handle.read(chunk_size):
        digest.update(chunk)
    return digest.hexdigest()


def sha256_file(path: Path, chunk_size: int = 1024 * 1024) -> str:
    with path.open("rb") as handle:
        return sha256_stream(handle, chunk_size)


def package_implementation_sha256(package_root: Path) -> str:
    digest = hashlib.sha256()
    for path in sorted(p for p in package_root.rglob("*.py") if p.is_file()):
        rel = path.relative_to(package_root).as_posix().encode("utf-8")
        data = path.read_bytes()
        digest.update(len(rel).to_bytes(8, "big"))
        digest.update(rel)
        digest.update(len(data).to_bytes(8, "big"))
        digest.update(data)
    return digest.hexdigest()
