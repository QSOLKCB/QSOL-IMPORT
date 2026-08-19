from __future__ import annotations

import argparse
import re
import shutil
import tempfile
from dataclasses import dataclass
from pathlib import Path, PurePosixPath
from typing import Any

from qsol_import.canonical import (
    canonical_json_bytes,
    loads_strict,
    sha256_bytes,
    sha256_file,
)


CANDIDATE_PROTOCOL = "QSOL-IMPORT/CANDIDATE-MANIFEST/1"
IMPORT_RECEIPT_PROTOCOL = "QSOL-IMPORT/RECEIPT/1"
CONTEXT_DECISION_PROTOCOL = "QSOL-CONTEXT/IMPORT-DECISION/1"
CONTROL_HANDOFF_PROTOCOL = "QSOL-IMPORT/CONTROL-HANDOFF/1"
CONTROL_PACK_SPEC_PROTOCOL = "qsol-control-restore-pack-spec/1"
THOTH_ROUTE_PROTOCOL = "QSOL-THOTH/ROUTE-DECISION/1"
SCHEMA_VERSION = "1.0.0"

PRIVACY_CLASSES = {"PUBLIC", "INTERNAL", "RESTRICTED"}
RECOVERY_CLASSES = {
    "NEAR_SHELL",
    "MID_SHELL",
    "OUTER_SHELL",
    "RESONANCE_NODE",
    "WIGGLE_ZONE",
}
DECISIONS = {"accepted", "rejected", "partially_accepted"}
DISPOSITIONS = {"accept", "reject"}
MAX_JSON_BYTES = 32 * 1024 * 1024
MAX_ARTIFACTS = 100_000

TOKEN_RE = re.compile(r"^[a-z][a-z0-9_]*$")
CONCAP_RE = re.compile(r"^concap\.[a-z0-9_.-]+/[1-9][0-9]*$")
SHA256_REF_RE = re.compile(r"^sha256:[0-9a-f]{64}$")

CANDIDATE_BOUNDARIES = (
    "PARSED != TRUSTED",
    "NORMALIZED != CANONICAL",
    "IMPORT != FACTUAL_AUTHORITY",
    "IMPORT != ROUTING",
    "CANDIDATE_MANIFEST != CONCAP_EXPORT_SPEC",
)

DECISION_BOUNDARIES = (
    "QSOL_CONTEXT_ACCEPTS != QSOL_IMPORT_ACCEPTS",
    "IMPORT_DECISION != FACTUAL_AUTHORITY",
    "ACCEPTED_CANDIDATE != CONCAP_ROLE",
    "REJECTED != DELETED_SOURCE",
    "DECISION_RECEIPT != SOURCE_BYTES",
    "ROUTING_RECEIPT != IMPORT_DECISION",
)

THOTH_ROUTE_BOUNDARIES = (
    "ROUTING != FACTUAL_AUTHORITY",
    "STYLE_SWITCH != EPISTEMIC_SWITCH",
    "STYLE_SUPPORT != EVIDENCE",
    "CONCAP_ID != CAPSULE_BYTES",
    "ROUTE_DECISION != CAPSULE_AVAILABILITY",
    "SELECTED != LOADED",
    "LOADED != TRUE",
)

HANDOFF_BOUNDARIES = (
    "CONTROL_HANDOFF != CONCAP_EXPORT_SPEC",
    "CONTROL_PACK_SPEC != CONCAP_ROLE_BINDING",
    "STAGED_FOR_PACKING != FACTUAL_AUTHORITY",
    "ACCEPTED_CANDIDATE != CANONICAL_CONTEXT",
    "ROUTING_RECEIPT_IMMUTABLE_DURING_HANDOFF",
    "QSOL_CONTEXT_REMAINS_ACCEPTANCE_AUTHORITY",
)


class HandoffError(ValueError):
    def __init__(self, code: str, message: str):
        super().__init__(message)
        self.code = code


@dataclass(frozen=True)
class CandidateState:
    root: Path
    candidate: dict[str, Any]
    import_receipt: dict[str, Any]
    artifacts: tuple[dict[str, Any], ...]
    import_receipt_bytes_sha256: str


@dataclass(frozen=True)
class DecisionState:
    receipt: dict[str, Any]
    accepted: tuple[dict[str, Any], ...]
    rejected: tuple[dict[str, Any], ...]


@dataclass(frozen=True)
class RouteReceiptState:
    receipt: dict[str, Any]
    file_sha256: str


def _load_object(path: Path, *, max_bytes: int = MAX_JSON_BYTES) -> dict[str, Any]:
    if path.is_symlink() or not path.is_file():
        raise HandoffError(
            "invalid_json_input",
            f"JSON input is missing or a symlink: {path.name}",
        )
    size = path.stat().st_size
    if size > max_bytes:
        raise HandoffError(
            "json_size_limit",
            f"JSON input exceeds {max_bytes} bytes: {path.name}",
        )
    try:
        value = loads_strict(path.read_bytes())
    except (UnicodeDecodeError, ValueError) as exc:
        raise HandoffError(
            "invalid_json",
            f"strict JSON parsing failed: {path.name}",
        ) from exc
    if not isinstance(value, dict):
        raise HandoffError(
            "invalid_json_shape",
            f"JSON input must contain an object: {path.name}",
        )
    return value


def _require_exact_keys(value: dict[str, Any], expected: set[str], where: str) -> None:
    if set(value) != expected:
        raise HandoffError(
            "field_mismatch",
            f"{where} fields mismatch: expected {sorted(expected)!r}, "
            f"found {sorted(value)!r}",
        )


def _canonical_relative_path(value: Any, where: str) -> str:
    if not isinstance(value, str) or not value or "\\" in value or "\x00" in value:
        raise HandoffError(
            "invalid_path",
            f"{where} must be a canonical relative POSIX path",
        )
    if any(ord(ch) < 32 or ord(ch) == 127 for ch in value):
        raise HandoffError("invalid_path", f"{where} contains a control character")
    path = PurePosixPath(value)
    if path.is_absolute() or any(part in {"", ".", ".."} for part in path.parts):
        raise HandoffError(
            "invalid_path",
            f"{where} contains an absolute, dot, or parent segment",
        )
    if path.as_posix() != value:
        raise HandoffError("invalid_path", f"{where} is not canonical POSIX form")
    return value


def _hex_sha256(value: Any, where: str) -> str:
    if (
        not isinstance(value, str)
        or len(value) != 64
        or any(ch not in "0123456789abcdef" for ch in value)
    ):
        raise HandoffError(
            "invalid_sha256",
            f"{where} must be 64 lowercase hexadecimal characters",
        )
    return value


def _sha256_ref(value: Any, where: str) -> str:
    if not isinstance(value, str) or SHA256_REF_RE.fullmatch(value) is None:
        raise HandoffError(
            "invalid_sha256_ref",
            f"{where} must be sha256:<64-lowercase-hex>",
        )
    return value


def _nonnegative_int(value: Any, where: str) -> int:
    if type(value) is not int or value < 0:
        raise HandoffError(
            "invalid_integer",
            f"{where} must be a non-negative integer",
        )
    return value


def _nonempty_string(value: Any, where: str) -> str:
    if not isinstance(value, str) or not value:
        raise HandoffError("invalid_string", f"{where} must be a non-empty string")
    return value


def _validate_unique_strings(value: Any, where: str) -> list[str]:
    if not isinstance(value, list) or any(
        not isinstance(item, str) or not item for item in value
    ):
        raise HandoffError(
            "invalid_string_array",
            f"{where} must be an array of non-empty strings",
        )
    if len(value) != len(set(value)):
        raise HandoffError(
            "duplicate_string",
            f"{where} must contain unique values",
        )
    return list(value)


def _verify_self_hash(value: dict[str, Any], hash_field: str, where: str) -> None:
    expected = _hex_sha256(value.get(hash_field), f"{where}.{hash_field}")
    body = {key: item for key, item in value.items() if key != hash_field}
    actual = sha256_bytes(canonical_json_bytes(body))
    if actual != expected:
        raise HandoffError("self_hash_mismatch", f"{where} self hash mismatch")


def _resolve_artifact(root: Path, relative: str) -> Path:
    root_resolved = root.resolve()
    current = root_resolved
    for part in PurePosixPath(relative).parts:
        current = current / part
        if current.is_symlink():
            raise HandoffError(
                "artifact_symlink",
                f"artifact traverses a symlink: {relative}",
            )
    try:
        current.resolve(strict=False).relative_to(root_resolved)
    except ValueError as exc:
        raise HandoffError(
            "artifact_escape",
            f"artifact escapes candidate root: {relative}",
        ) from exc
    if not current.is_file():
        raise HandoffError(
            "artifact_missing",
            f"candidate artifact is missing: {relative}",
        )
    return current


def _validate_artifact_rows(
    rows: Any,
    where: str,
) -> tuple[dict[str, Any], ...]:
    if not isinstance(rows, list) or len(rows) > MAX_ARTIFACTS:
        raise HandoffError(
            "invalid_artifacts",
            f"{where} must be an array of at most {MAX_ARTIFACTS} items",
        )
    normalized: list[dict[str, Any]] = []
    seen: set[str] = set()
    previous: bytes | None = None
    for index, row in enumerate(rows):
        if not isinstance(row, dict):
            raise HandoffError(
                "invalid_artifact",
                f"{where}[{index}] must be an object",
            )
        _require_exact_keys(
            row,
            {"path", "sha256", "size_bytes"},
            f"{where}[{index}]",
        )
        path = _canonical_relative_path(row["path"], f"{where}[{index}].path")
        if path in {"CANDIDATE.json", "IMPORT.json", "SHA256SUMS"}:
            raise HandoffError(
                "reserved_artifact_path",
                f"candidate artifact uses reserved path: {path}",
            )
        encoded = path.encode("utf-8")
        if previous is not None and previous >= encoded:
            raise HandoffError(
                "artifact_order",
                f"{where} must be strictly UTF-8 path sorted",
            )
        previous = encoded
        if path in seen:
            raise HandoffError(
                "duplicate_artifact",
                f"duplicate candidate artifact: {path}",
            )
        seen.add(path)
        normalized.append(
            {
                "path": path,
                "sha256": _hex_sha256(
                    row["sha256"],
                    f"{where}[{index}].sha256",
                ),
                "size_bytes": _nonnegative_int(
                    row["size_bytes"],
                    f"{where}[{index}].size_bytes",
                ),
            }
        )
    return tuple(normalized)


def _candidate_file_inventory(root: Path) -> dict[str, Path]:
    files: dict[str, Path] = {}
    for entry in root.rglob("*"):
        rel = entry.relative_to(root).as_posix()
        if entry.is_symlink():
            raise HandoffError(
                "candidate_symlink",
                f"candidate tree contains a symlink: {rel}",
            )
        if entry.is_dir():
            continue
        if not entry.is_file():
            raise HandoffError(
                "candidate_nonregular",
                f"candidate tree contains a non-regular entry: {rel}",
            )
        files[rel] = entry
    return files


def _candidate_output_sha256(
    root: Path,
    artifacts: tuple[dict[str, Any], ...],
) -> str:
    included = ["CANDIDATE.json", *(row["path"] for row in artifacts)]
    records = []
    for relative in sorted(included, key=lambda value: value.encode("utf-8")):
        path = root.joinpath(*PurePosixPath(relative).parts)
        records.append(
            {
                "path": relative,
                "sha256": sha256_file(path),
                "size_bytes": path.stat().st_size,
            }
        )
    return sha256_bytes(canonical_json_bytes(records))


def _validate_import_receipt(
    receipt: dict[str, Any],
    candidate: dict[str, Any],
    root: Path,
    artifacts: tuple[dict[str, Any], ...],
) -> None:
    base_fields = {
        "protocol",
        "schema_version",
        "implementation_version",
        "source_type",
        "profile",
        "input_sha256",
        "policy_sha256",
        "implementation_sha256",
        "output_sha256",
        "candidate_sha256",
        "receipt_sha256",
        "conversations",
        "messages",
        "files_seen",
        "files_retained",
        "files_extracted",
        "files_tombstoned",
        "files_rejected",
    }
    adapter_fields = {"adapter_id", "provenance_records"}
    found = set(receipt)
    if found not in (base_fields, base_fields | adapter_fields):
        raise HandoffError(
            "import_receipt_fields",
            "import receipt fields do not match the frozen receipt contract",
        )
    if (
        receipt["protocol"] != IMPORT_RECEIPT_PROTOCOL
        or receipt["schema_version"] != SCHEMA_VERSION
    ):
        raise HandoffError(
            "import_receipt_protocol",
            "unsupported import receipt protocol/version",
        )

    for field in ("implementation_version", "source_type", "profile"):
        _nonempty_string(receipt[field], f"import receipt.{field}")
    for field in (
        "input_sha256",
        "policy_sha256",
        "implementation_sha256",
        "output_sha256",
        "candidate_sha256",
        "receipt_sha256",
    ):
        _hex_sha256(receipt[field], f"import receipt.{field}")
    for field in (
        "conversations",
        "messages",
        "files_seen",
        "files_retained",
        "files_extracted",
        "files_tombstoned",
        "files_rejected",
    ):
        _nonnegative_int(receipt[field], f"import receipt.{field}")

    if adapter_fields.issubset(receipt):
        _nonempty_string(receipt["adapter_id"], "import receipt.adapter_id")
        _nonnegative_int(
            receipt["provenance_records"],
            "import receipt.provenance_records",
        )

    disposition_total = (
        receipt["files_retained"]
        + receipt["files_extracted"]
        + receipt["files_tombstoned"]
        + receipt["files_rejected"]
    )
    if receipt["files_seen"] != disposition_total:
        raise HandoffError(
            "import_receipt_counter_mismatch",
            "files_seen does not equal the sum of disposition counters",
        )

    _verify_self_hash(receipt, "receipt_sha256", "import receipt")
    for field in (
        "input_sha256",
        "policy_sha256",
        "implementation_sha256",
        "candidate_sha256",
    ):
        if receipt[field] != candidate[field]:
            raise HandoffError(
                "candidate_receipt_mismatch",
                f"candidate/import receipt mismatch: {field}",
            )
    if (
        receipt["source_type"] != candidate["source_type"]
        or receipt["profile"] != candidate["profile"]
    ):
        raise HandoffError(
            "candidate_receipt_mismatch",
            "candidate/import receipt source type or profile mismatch",
        )

    actual_output_sha256 = _candidate_output_sha256(root, artifacts)
    if receipt["output_sha256"] != actual_output_sha256:
        raise HandoffError(
            "output_identity_mismatch",
            "import receipt output_sha256 does not match the verified candidate tree",
        )


def verify_candidate_root(root: Path) -> CandidateState:
    if root.is_symlink() or not root.is_dir():
        raise HandoffError(
            "invalid_candidate_root",
            "candidate root must be a non-symlink directory",
        )
    candidate_path = root / "CANDIDATE.json"
    import_path = root / "IMPORT.json"
    candidate = _load_object(candidate_path)
    receipt = _load_object(import_path)

    _require_exact_keys(
        candidate,
        {
            "protocol",
            "schema_version",
            "authority",
            "source_type",
            "profile",
            "input_sha256",
            "policy_sha256",
            "implementation_sha256",
            "concap_roles_assigned",
            "import_receipt_path",
            "artifacts",
            "boundaries",
            "candidate_sha256",
        },
        "candidate manifest",
    )
    if (
        candidate["protocol"] != CANDIDATE_PROTOCOL
        or candidate["schema_version"] != SCHEMA_VERSION
    ):
        raise HandoffError(
            "candidate_protocol",
            "unsupported candidate manifest protocol/version",
        )
    if (
        candidate["authority"] != "candidate-only"
        or candidate["concap_roles_assigned"] is not False
    ):
        raise HandoffError(
            "candidate_authority",
            "candidate manifest attempted authority or CONCAP-role escalation",
        )
    if candidate["import_receipt_path"] != "IMPORT.json":
        raise HandoffError(
            "candidate_receipt_path",
            "candidate import receipt path must be IMPORT.json",
        )
    _nonempty_string(candidate["source_type"], "candidate.source_type")
    _nonempty_string(candidate["profile"], "candidate.profile")
    for field in (
        "input_sha256",
        "policy_sha256",
        "implementation_sha256",
        "candidate_sha256",
    ):
        _hex_sha256(candidate[field], f"candidate.{field}")
    boundaries = _validate_unique_strings(
        candidate["boundaries"],
        "candidate.boundaries",
    )
    for boundary in CANDIDATE_BOUNDARIES:
        if boundary not in boundaries:
            raise HandoffError(
                "candidate_boundary_missing",
                f"candidate manifest missing boundary: {boundary}",
            )
    _verify_self_hash(candidate, "candidate_sha256", "candidate manifest")
    artifacts = _validate_artifact_rows(
        candidate["artifacts"],
        "candidate.artifacts",
    )

    inventory = _candidate_file_inventory(root)
    expected_files = {
        "CANDIDATE.json",
        "IMPORT.json",
        "SHA256SUMS",
        *(row["path"] for row in artifacts),
    }
    actual_files = set(inventory)
    if actual_files != expected_files:
        missing = sorted(expected_files - actual_files)
        unexpected = sorted(actual_files - expected_files)
        raise HandoffError(
            "candidate_tree_mismatch",
            f"candidate file set mismatch: missing={missing!r}, "
            f"unexpected={unexpected!r}",
        )

    for artifact in artifacts:
        path = _resolve_artifact(root, artifact["path"])
        if path.stat().st_size != artifact["size_bytes"]:
            raise HandoffError(
                "artifact_size_mismatch",
                f"candidate artifact size mismatch: {artifact['path']}",
            )
        if sha256_file(path) != artifact["sha256"]:
            raise HandoffError(
                "artifact_hash_mismatch",
                f"candidate artifact hash mismatch: {artifact['path']}",
            )

    _validate_import_receipt(receipt, candidate, root, artifacts)

    return CandidateState(
        root=root,
        candidate=candidate,
        import_receipt=receipt,
        artifacts=artifacts,
        import_receipt_bytes_sha256=sha256_file(import_path),
    )


def verify_context_decision(
    candidate: CandidateState,
    decision_path: Path,
) -> DecisionState:
    decision = _load_object(decision_path)
    _require_exact_keys(
        decision,
        {
            "protocol",
            "schema_version",
            "issuer",
            "authority",
            "candidate_sha256",
            "import_receipt_sha256",
            "decision",
            "review_policy",
            "review_policy_sha256",
            "artifacts",
            "concap_roles_assigned",
            "boundaries",
            "decision_sha256",
        },
        "context decision",
    )
    if (
        decision["protocol"] != CONTEXT_DECISION_PROTOCOL
        or decision["schema_version"] != SCHEMA_VERSION
    ):
        raise HandoffError(
            "decision_protocol",
            "unsupported QSOL-CONTEXT decision protocol/version",
        )
    if (
        decision["issuer"] != "QSOL-CONTEXT"
        or decision["authority"] != "context-acceptance-only"
    ):
        raise HandoffError(
            "decision_authority",
            "decision issuer/authority mismatch",
        )
    if decision["concap_roles_assigned"] is not False:
        raise HandoffError(
            "decision_role_escalation",
            "import decision must not assign CONCAP roles",
        )
    if decision["candidate_sha256"] != candidate.candidate["candidate_sha256"]:
        raise HandoffError(
            "decision_candidate_mismatch",
            "decision references a different candidate",
        )
    if decision["import_receipt_sha256"] != candidate.import_receipt_bytes_sha256:
        raise HandoffError(
            "decision_import_receipt_mismatch",
            "decision references different IMPORT.json bytes",
        )
    if decision["decision"] not in DECISIONS:
        raise HandoffError(
            "decision_value",
            "unsupported context decision value",
        )
    _nonempty_string(decision["review_policy"], "decision.review_policy")
    _hex_sha256(
        decision["review_policy_sha256"],
        "decision.review_policy_sha256",
    )
    boundaries = _validate_unique_strings(
        decision["boundaries"],
        "decision.boundaries",
    )
    for boundary in DECISION_BOUNDARIES:
        if boundary not in boundaries:
            raise HandoffError(
                "decision_boundary_missing",
                f"context decision missing boundary: {boundary}",
            )
    _verify_self_hash(decision, "decision_sha256", "context decision")

    rows = decision["artifacts"]
    if not isinstance(rows, list) or len(rows) != len(candidate.artifacts):
        raise HandoffError(
            "decision_artifact_coverage",
            "decision must cover every candidate artifact exactly once",
        )
    candidate_by_path = {row["path"]: row for row in candidate.artifacts}
    normalized: list[dict[str, Any]] = []
    seen: set[str] = set()
    previous: bytes | None = None
    for index, row in enumerate(rows):
        if not isinstance(row, dict):
            raise HandoffError(
                "decision_artifact",
                f"decision.artifacts[{index}] must be an object",
            )
        _require_exact_keys(
            row,
            {"path", "sha256", "size_bytes", "disposition", "reason"},
            f"decision.artifacts[{index}]",
        )
        path = _canonical_relative_path(
            row["path"],
            f"decision.artifacts[{index}].path",
        )
        encoded = path.encode("utf-8")
        if previous is not None and previous >= encoded:
            raise HandoffError(
                "decision_artifact_order",
                "decision artifacts must be strictly UTF-8 path sorted",
            )
        previous = encoded
        if path in seen or path not in candidate_by_path:
            raise HandoffError(
                "decision_artifact_coverage",
                f"unknown or duplicate decision artifact: {path}",
            )
        seen.add(path)
        candidate_row = candidate_by_path[path]
        if (
            row["sha256"] != candidate_row["sha256"]
            or row["size_bytes"] != candidate_row["size_bytes"]
        ):
            raise HandoffError(
                "decision_artifact_identity",
                f"decision artifact identity mismatch: {path}",
            )
        if row["disposition"] not in DISPOSITIONS:
            raise HandoffError(
                "decision_disposition",
                f"invalid artifact disposition: {path}",
            )
        _nonempty_string(row["reason"], f"decision artifact reason: {path}")
        normalized.append(dict(row))

    accepted = tuple(
        row for row in normalized if row["disposition"] == "accept"
    )
    rejected = tuple(
        row for row in normalized if row["disposition"] == "reject"
    )
    expected_decision = (
        "accepted"
        if accepted and not rejected
        else "rejected"
        if rejected and not accepted
        else "partially_accepted"
        if accepted and rejected
        else None
    )
    if expected_decision is None or decision["decision"] != expected_decision:
        raise HandoffError(
            "decision_summary_mismatch",
            "decision summary disagrees with artifact dispositions",
        )
    return DecisionState(decision, accepted, rejected)


def verify_thoth_route_receipt(path: Path) -> RouteReceiptState:
    receipt = _load_object(path)
    _require_exact_keys(
        receipt,
        {
            "protocol",
            "canonical_intent",
            "style",
            "concaps",
            "request_sha256",
            "configuration_sha256",
            "implementation_sha256",
            "boundaries",
            "decision_sha256",
        },
        "THOTH route receipt",
    )
    if receipt["protocol"] != THOTH_ROUTE_PROTOCOL:
        raise HandoffError(
            "routing_receipt_protocol",
            "unsupported THOTH route receipt protocol",
        )
    if (
        not isinstance(receipt["canonical_intent"], str)
        or TOKEN_RE.fullmatch(receipt["canonical_intent"]) is None
    ):
        raise HandoffError(
            "routing_receipt_intent",
            "THOTH canonical_intent is invalid",
        )
    if (
        not isinstance(receipt["style"], str)
        or TOKEN_RE.fullmatch(receipt["style"]) is None
    ):
        raise HandoffError(
            "routing_receipt_style",
            "THOTH style is invalid",
        )
    concaps = receipt["concaps"]
    if (
        not isinstance(concaps, list)
        or not concaps
        or len(concaps) != len(set(concaps))
        or any(
            not isinstance(item, str) or CONCAP_RE.fullmatch(item) is None
            for item in concaps
        )
    ):
        raise HandoffError(
            "routing_receipt_concaps",
            "THOTH concaps must be a non-empty unique role-id array",
        )
    for field in (
        "request_sha256",
        "configuration_sha256",
        "implementation_sha256",
        "decision_sha256",
    ):
        _sha256_ref(receipt[field], f"THOTH route receipt.{field}")
    boundaries = _validate_unique_strings(
        receipt["boundaries"],
        "THOTH route receipt.boundaries",
    )
    for boundary in THOTH_ROUTE_BOUNDARIES:
        if boundary not in boundaries:
            raise HandoffError(
                "routing_receipt_boundary_missing",
                f"THOTH route receipt missing boundary: {boundary}",
            )
    body = {
        key: value
        for key, value in receipt.items()
        if key != "decision_sha256"
    }
    actual_decision_sha256 = "sha256:" + sha256_bytes(
        canonical_json_bytes(body)
    )
    if receipt["decision_sha256"] != actual_decision_sha256:
        raise HandoffError(
            "routing_receipt_self_hash",
            "THOTH route decision self-receipt mismatch",
        )
    return RouteReceiptState(receipt=receipt, file_sha256=sha256_file(path))


def _copy_file(source: Path, destination: Path) -> None:
    destination.parent.mkdir(parents=True, exist_ok=True)
    with source.open("rb") as src, destination.open("wb") as dst:
        shutil.copyfileobj(src, dst, length=1024 * 1024)


def _write_checksums(root: Path) -> None:
    rows: list[str] = []
    files = [item for item in root.rglob("*") if item.is_file()]
    for path in sorted(
        files,
        key=lambda item: item.relative_to(root).as_posix().encode("utf-8"),
    ):
        rel = path.relative_to(root).as_posix()
        if rel != "SHA256SUMS":
            rows.append(f"{sha256_file(path)}  {rel}\n")
    (root / "SHA256SUMS").write_text(
        "".join(rows),
        encoding="utf-8",
        newline="\n",
    )


def _remove_path(path: Path) -> None:
    if path.is_symlink() or path.is_file():
        path.unlink()
    elif path.is_dir():
        shutil.rmtree(path)


def _commit_directory(staging: Path, output: Path) -> None:
    backup: Path | None = None
    if output.exists():
        backup = Path(
            tempfile.mkdtemp(
                prefix=f".{output.name}.previous-",
                dir=output.parent,
            )
        )
        backup.rmdir()
        output.rename(backup)
    try:
        staging.rename(output)
    except Exception:
        if backup is not None and not output.exists():
            backup.rename(output)
        raise
    else:
        if backup is not None:
            _remove_path(backup)


def _is_relative_to(path: Path, root: Path) -> bool:
    try:
        path.relative_to(root)
    except ValueError:
        return False
    return True


def _paths_overlap(first: Path, second: Path) -> bool:
    return _is_relative_to(first, second) or _is_relative_to(second, first)


def _validate_output_destination(
    output_dir: Path,
    *,
    candidate_root: Path,
    decision_path: Path,
    route_path: Path | None,
) -> None:
    output_resolved = output_dir.resolve(strict=False)
    inputs = {
        "candidate root": candidate_root.resolve(),
        "context decision": decision_path.resolve(),
    }
    if route_path is not None:
        inputs["THOTH route receipt"] = route_path.resolve()
    for label, input_resolved in inputs.items():
        if _paths_overlap(output_resolved, input_resolved):
            raise HandoffError(
                "output_overlap",
                f"handoff output overlaps the {label}",
            )
    if output_dir.exists() and (
        output_dir.is_symlink() or not output_dir.is_dir()
    ):
        raise HandoffError(
            "output_type",
            "handoff output must be absent or an existing non-symlink directory",
        )


def stage_control_handoff(
    candidate_root: Path,
    decision_path: Path,
    output_dir: Path,
    *,
    privacy_class: str = "RESTRICTED",
    recovery_class: str = "OUTER_SHELL",
    capsule: str = "qsol-import-accepted.dat",
    thoth_route_receipt: Path | None = None,
) -> dict[str, Any]:
    if privacy_class not in PRIVACY_CLASSES:
        raise HandoffError("privacy_class", "unsupported privacy class")
    if recovery_class not in RECOVERY_CLASSES:
        raise HandoffError(
            "recovery_class",
            "unsupported CONTROL recovery class",
        )
    if (
        not isinstance(capsule, str)
        or not capsule.endswith(".dat")
        or "/" in capsule
        or "\\" in capsule
        or len(capsule) > 256
    ):
        raise HandoffError(
            "capsule_name",
            "capsule must be a plain .dat filename",
        )

    candidate = verify_candidate_root(candidate_root)
    decision = verify_context_decision(candidate, decision_path)
    route_state = (
        verify_thoth_route_receipt(thoth_route_receipt)
        if thoth_route_receipt is not None
        else None
    )
    _validate_output_destination(
        output_dir,
        candidate_root=candidate_root,
        decision_path=decision_path,
        route_path=thoth_route_receipt,
    )

    output_dir.parent.mkdir(parents=True, exist_ok=True)
    staging = Path(
        tempfile.mkdtemp(
            prefix=f".{output_dir.name}.handoff-",
            dir=output_dir.parent,
        )
    )
    try:
        _copy_file(
            candidate_root / "CANDIDATE.json",
            staging / "review" / "CANDIDATE.json",
        )
        _copy_file(
            candidate_root / "IMPORT.json",
            staging / "review" / "IMPORT.json",
        )
        _copy_file(
            decision_path,
            staging / "review" / "CONTEXT-DECISION.json",
        )

        accepted_entries: list[dict[str, Any]] = []
        for row in decision.accepted:
            source = _resolve_artifact(candidate_root, row["path"])
            destination_rel = f"accepted/{row['path']}"
            destination = staging.joinpath(
                *PurePosixPath(destination_rel).parts
            )
            _copy_file(source, destination)
            accepted_entries.append(
                {
                    "logical_path": (
                        f"import-candidate/artifacts/{row['path']}"
                    ),
                    "source_path": destination_rel,
                    "kind": "qsol-import-candidate-artifact",
                    "privacy_class": privacy_class,
                    "recovery_class": recovery_class,
                    "source_ref": (
                        "QSOL-CONTEXT:IMPORT-DECISION:"
                        f"{decision.receipt['decision_sha256']}#{row['path']}"
                    ),
                }
            )

        pack_spec_path: str | None = None
        pack_spec_sha256: str | None = None
        if decision.accepted:
            metadata_entries = [
                {
                    "logical_path": "import-candidate/review/CANDIDATE.json",
                    "source_path": "review/CANDIDATE.json",
                    "kind": "qsol-import-candidate-manifest",
                    "privacy_class": privacy_class,
                    "recovery_class": recovery_class,
                    "source_ref": (
                        "QSOL-IMPORT:CANDIDATE:"
                        f"{candidate.candidate['candidate_sha256']}"
                    ),
                },
                {
                    "logical_path": "import-candidate/review/IMPORT.json",
                    "source_path": "review/IMPORT.json",
                    "kind": "qsol-import-receipt",
                    "privacy_class": privacy_class,
                    "recovery_class": recovery_class,
                    "source_ref": (
                        "QSOL-IMPORT:RECEIPT:"
                        f"{candidate.import_receipt['receipt_sha256']}"
                    ),
                },
                {
                    "logical_path": (
                        "import-candidate/review/CONTEXT-DECISION.json"
                    ),
                    "source_path": "review/CONTEXT-DECISION.json",
                    "kind": "qsol-context-import-decision",
                    "privacy_class": privacy_class,
                    "recovery_class": recovery_class,
                    "source_ref": (
                        "QSOL-CONTEXT:IMPORT-DECISION:"
                        f"{decision.receipt['decision_sha256']}"
                    ),
                },
            ]
            entries = sorted(
                metadata_entries + accepted_entries,
                key=lambda row: row["logical_path"].encode("utf-8"),
            )
            pack_spec = {
                "protocol": CONTROL_PACK_SPEC_PROTOCOL,
                "capsule": capsule,
                "recovery_class": recovery_class,
                "entries": entries,
            }
            pack_spec_path = "CONTROL-PACK.spec.json"
            (staging / pack_spec_path).write_bytes(
                canonical_json_bytes(pack_spec)
            )
            pack_spec_sha256 = sha256_file(staging / pack_spec_path)

        route_after = (
            sha256_file(thoth_route_receipt)
            if thoth_route_receipt is not None
            else None
        )
        if route_state is not None and route_state.file_sha256 != route_after:
            raise HandoffError(
                "routing_receipt_mutated",
                "THOTH route receipt changed during handoff staging",
            )

        accepted_summary = [
            {
                "path": row["path"],
                "sha256": row["sha256"],
                "size_bytes": row["size_bytes"],
            }
            for row in decision.accepted
        ]
        rejected_summary = [
            {
                "path": row["path"],
                "sha256": row["sha256"],
                "size_bytes": row["size_bytes"],
                "reason": row["reason"],
            }
            for row in decision.rejected
        ]
        body = {
            "protocol": CONTROL_HANDOFF_PROTOCOL,
            "schema_version": SCHEMA_VERSION,
            "authority": "staging-only",
            "candidate_sha256": candidate.candidate["candidate_sha256"],
            "context_decision_sha256": decision.receipt["decision_sha256"],
            "decision": decision.receipt["decision"],
            "accepted_artifacts": accepted_summary,
            "rejected_artifacts": rejected_summary,
            "control_pack_spec_path": pack_spec_path,
            "control_pack_spec_sha256": pack_spec_sha256,
            "concap_roles_assigned": False,
            "thoth_route_receipt": (
                None
                if route_state is None
                else {
                    "protocol": route_state.receipt["protocol"],
                    "decision_sha256": route_state.receipt["decision_sha256"],
                    "file_sha256_before": route_state.file_sha256,
                    "file_sha256_after": route_after,
                    "unchanged": True,
                }
            ),
            "boundaries": list(HANDOFF_BOUNDARIES),
        }
        handoff = {
            **body,
            "handoff_sha256": sha256_bytes(canonical_json_bytes(body)),
        }
        (staging / "HANDOFF.json").write_bytes(
            canonical_json_bytes(handoff)
        )
        _write_checksums(staging)
        _commit_directory(staging, output_dir)
        return handoff
    except Exception:
        if staging.exists():
            _remove_path(staging)
        raise


def _parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        description=(
            "Verify QSOL-CONTEXT import decisions and stage "
            "CONTROL-compatible handoffs"
        )
    )
    sub = parser.add_subparsers(dest="command", required=True)

    verify = sub.add_parser("verify")
    verify.add_argument("candidate_root", type=Path)
    verify.add_argument("decision", type=Path)

    stage = sub.add_parser("stage")
    stage.add_argument("candidate_root", type=Path)
    stage.add_argument("decision", type=Path)
    stage.add_argument("--output", type=Path, required=True)
    stage.add_argument(
        "--privacy-class",
        choices=sorted(PRIVACY_CLASSES),
        default="RESTRICTED",
    )
    stage.add_argument(
        "--recovery-class",
        choices=sorted(RECOVERY_CLASSES),
        default="OUTER_SHELL",
    )
    stage.add_argument("--capsule", default="qsol-import-accepted.dat")
    stage.add_argument("--thoth-route-receipt", type=Path, default=None)
    return parser


def main() -> int:
    import json

    args = _parser().parse_args()
    if args.command == "verify":
        candidate = verify_candidate_root(args.candidate_root)
        decision = verify_context_decision(candidate, args.decision)
        result = {
            "protocol": "QSOL-IMPORT/CONTEXT-DECISION-VERIFICATION/1",
            "candidate_sha256": candidate.candidate["candidate_sha256"],
            "decision_sha256": decision.receipt["decision_sha256"],
            "decision": decision.receipt["decision"],
            "accepted_artifacts": len(decision.accepted),
            "rejected_artifacts": len(decision.rejected),
            "verified": True,
        }
    else:
        result = stage_control_handoff(
            args.candidate_root,
            args.decision,
            args.output,
            privacy_class=args.privacy_class,
            recovery_class=args.recovery_class,
            capsule=args.capsule,
            thoth_route_receipt=args.thoth_route_receipt,
        )
    print(json.dumps(result, indent=2, sort_keys=True))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
