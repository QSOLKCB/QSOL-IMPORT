from __future__ import annotations

import argparse
from collections import Counter
from pathlib import Path, PurePosixPath
from typing import Any

from qsol_import.canonical import (
    canonical_json_bytes,
    loads_strict,
    sha256_bytes,
    sha256_file,
)
from qsol_import.handoff import CandidateState, HandoffError, verify_candidate_root


EVALUATION_PROTOCOL = "QSOL-IMPORT/EVALUATION/1"
OBLIGATIONS_PROTOCOL = "QSOL-IMPORT/RETENTION-OBLIGATIONS/1"
OBLIGATIONS_AUTHORITY = "measurement-obligations-only"
SCHEMA_VERSION = "1.0.0"
MAX_JSON_BYTES = 32 * 1024 * 1024
MAX_JSONL_BYTES = 512 * 1024 * 1024
MAX_OBLIGATIONS = 100_000
MAX_FORBIDDEN_FRAGMENTS = 256
MAX_OBLIGATION_STRING_BYTES = 16 * 1024
SCAN_CHUNK_BYTES = 64 * 1024

OBLIGATION_BOUNDARIES = (
    "ABSENT_OBLIGATION != ABSENT_CONTEXT",
    "OBLIGATION_SET != SOURCE_EVIDENCE",
    "RETENTION_OBLIGATION != FACTUAL_AUTHORITY",
)

EVALUATION_BOUNDARIES = (
    "BYTE_REDUCTION != CONTEXT_RETENTION",
    "SEMANTIC_COVERAGE != FACTUAL_TRUTH",
    "TOMBSTONED_BYTES != RESTORED_BYTES",
    "UNASSESSED != FAILED",
    "MEASUREMENT != ACCEPTANCE_AUTHORITY",
    "AGGREGATE_SCORE = FORBIDDEN",
)

CLASSIFICATION_DECISIONS = {"keep", "extract", "tombstone", "reject"}


class EvaluationError(ValueError):
    def __init__(self, code: str, message: str):
        super().__init__(message)
        self.code = code


def _load_object(path: Path, max_bytes: int = MAX_JSON_BYTES) -> dict[str, Any]:
    if path.is_symlink() or not path.is_file():
        raise EvaluationError(
            "invalid_json_input",
            f"missing or symlink JSON input: {path}",
        )
    if path.stat().st_size > max_bytes:
        raise EvaluationError(
            "json_size_limit",
            f"JSON input exceeds {max_bytes} bytes: {path}",
        )
    try:
        value = loads_strict(path.read_bytes())
    except (UnicodeDecodeError, ValueError) as exc:
        raise EvaluationError(
            "invalid_json",
            f"strict JSON parsing failed: {path}",
        ) from exc
    if not isinstance(value, dict):
        raise EvaluationError(
            "invalid_json_shape",
            f"JSON input must contain an object: {path}",
        )
    return value


def _hex_sha256(value: Any, where: str) -> str:
    if (
        not isinstance(value, str)
        or len(value) != 64
        or any(ch not in "0123456789abcdef" for ch in value)
    ):
        raise EvaluationError(
            "invalid_sha256",
            f"{where} must be 64 lowercase hexadecimal characters",
        )
    return value


def _verify_self_hash(value: dict[str, Any], hash_field: str, where: str) -> None:
    expected = _hex_sha256(value.get(hash_field), f"{where}.{hash_field}")
    body = {key: item for key, item in value.items() if key != hash_field}
    actual = sha256_bytes(canonical_json_bytes(body))
    if actual != expected:
        raise EvaluationError(
            "self_hash_mismatch",
            f"{where} self hash mismatch",
        )


def _candidate_artifact_path(
    candidate: CandidateState,
    relative: str,
) -> Path:
    artifact = next(
        (row for row in candidate.artifacts if row["path"] == relative),
        None,
    )
    if artifact is None:
        raise EvaluationError(
            "candidate_artifact_missing",
            f"evaluation input is not listed in CANDIDATE.json: {relative}",
        )
    path = candidate.root.joinpath(*PurePosixPath(relative).parts)
    # verify_candidate_root() has already checked this exact path, size, hash,
    # symlink boundary, and the complete candidate file set.
    return path


def _read_candidate_jsonl(
    candidate: CandidateState,
    relative: str,
) -> list[dict[str, Any]]:
    path = _candidate_artifact_path(candidate, relative)
    if path.stat().st_size > MAX_JSONL_BYTES:
        raise EvaluationError(
            "jsonl_size_limit",
            f"JSONL input exceeds {MAX_JSONL_BYTES} bytes: {relative}",
        )
    rows: list[dict[str, Any]] = []
    with path.open("rb") as handle:
        for line_number, raw in enumerate(handle, start=1):
            if not raw.strip():
                continue
            try:
                value = loads_strict(raw)
            except (UnicodeDecodeError, ValueError) as exc:
                raise EvaluationError(
                    "invalid_jsonl",
                    f"invalid JSONL record at {relative}:{line_number}",
                ) from exc
            if not isinstance(value, dict):
                raise EvaluationError(
                    "invalid_jsonl_shape",
                    f"JSONL record is not an object at {relative}:{line_number}",
                )
            rows.append(value)
    return rows


def _ratio(numerator: int, denominator: int) -> dict[str, Any]:
    if denominator == 0:
        return {
            "numerator": numerator,
            "denominator": denominator,
            "basis_points": None,
            "status": "unassessed",
        }
    return {
        "numerator": numerator,
        "denominator": denominator,
        "basis_points": (numerator * 10_000) // denominator,
        "status": "measured",
    }


def _reduction(original: int, emitted: int) -> dict[str, Any]:
    if original == 0:
        return {
            "original_bytes": original,
            "emitted_bytes": emitted,
            "reduction_bytes": None,
            "reduction_basis_points": None,
            "status": "unassessed",
        }
    return {
        "original_bytes": original,
        "emitted_bytes": emitted,
        "reduction_bytes": original - emitted,
        "reduction_basis_points": ((original - emitted) * 10_000) // original,
        "status": "measured",
    }


def _exact_string_list(
    value: Any,
    where: str,
    *,
    max_items: int = MAX_OBLIGATIONS,
) -> list[str]:
    if not isinstance(value, list) or len(value) > max_items:
        raise EvaluationError(
            "invalid_obligations",
            f"{where} must be an array of at most {max_items} strings",
        )
    if any(not isinstance(item, str) or not item for item in value):
        raise EvaluationError(
            "invalid_obligations",
            f"{where} contains an invalid string",
        )
    if any(
        len(item.encode("utf-8")) > MAX_OBLIGATION_STRING_BYTES
        for item in value
    ):
        raise EvaluationError(
            "obligation_string_limit",
            f"{where} contains a string exceeding the UTF-8 byte limit",
        )
    if len(value) != len(set(value)):
        raise EvaluationError(
            "duplicate_obligation",
            f"{where} contains duplicate values",
        )
    encoded = [item.encode("utf-8") for item in value]
    if encoded != sorted(encoded):
        raise EvaluationError(
            "obligation_order",
            f"{where} must be UTF-8 sorted",
        )
    return list(value)


def load_obligations(path: Path | None) -> dict[str, Any] | None:
    if path is None:
        return None
    value = _load_object(path)
    expected = {
        "protocol",
        "schema_version",
        "authority",
        "required_conversation_ids",
        "required_message_ids",
        "required_attachment_refs",
        "forbidden_text_fragments",
        "boundaries",
        "obligations_sha256",
    }
    if set(value) != expected:
        raise EvaluationError(
            "obligation_fields",
            "retention-obligation fields mismatch",
        )
    if (
        value["protocol"] != OBLIGATIONS_PROTOCOL
        or value["schema_version"] != SCHEMA_VERSION
    ):
        raise EvaluationError(
            "obligation_protocol",
            "unsupported retention-obligation protocol/version",
        )
    if value["authority"] != OBLIGATIONS_AUTHORITY:
        raise EvaluationError(
            "obligation_authority",
            "retention obligations have an invalid authority declaration",
        )
    _verify_self_hash(value, "obligations_sha256", "retention obligations")

    value["required_conversation_ids"] = _exact_string_list(
        value["required_conversation_ids"],
        "required_conversation_ids",
    )
    value["required_message_ids"] = _exact_string_list(
        value["required_message_ids"],
        "required_message_ids",
    )
    value["required_attachment_refs"] = _exact_string_list(
        value["required_attachment_refs"],
        "required_attachment_refs",
    )
    value["forbidden_text_fragments"] = _exact_string_list(
        value["forbidden_text_fragments"],
        "forbidden_text_fragments",
        max_items=MAX_FORBIDDEN_FRAGMENTS,
    )
    value["boundaries"] = _exact_string_list(
        value["boundaries"],
        "boundaries",
    )
    for boundary in OBLIGATION_BOUNDARIES:
        if boundary not in value["boundaries"]:
            raise EvaluationError(
                "obligation_boundary_missing",
                f"retention obligations are missing boundary: {boundary}",
            )
    return value


def _canonical_source_path(value: Any, where: str) -> str:
    if (
        not isinstance(value, str)
        or not value
        or "\\" in value
        or "\x00" in value
        or any(ord(ch) < 32 or ord(ch) == 127 for ch in value)
    ):
        raise EvaluationError(
            "classification_path",
            f"{where} must be a canonical relative POSIX path",
        )
    path = PurePosixPath(value)
    if path.is_absolute() or any(part in {"", ".", ".."} for part in path.parts):
        raise EvaluationError(
            "classification_path",
            f"{where} contains an invalid path segment",
        )
    if path.as_posix() != value:
        raise EvaluationError(
            "classification_path",
            f"{where} is not canonical POSIX form",
        )
    return value


def _load_classifications(candidate: CandidateState) -> list[dict[str, Any]]:
    path = _candidate_artifact_path(
        candidate,
        "reports/classifications.json",
    )
    if path.stat().st_size > MAX_JSON_BYTES:
        raise EvaluationError(
            "classification_size_limit",
            "classification report exceeds limit",
        )
    try:
        rows = loads_strict(path.read_bytes())
    except (UnicodeDecodeError, ValueError) as exc:
        raise EvaluationError(
            "classification_invalid",
            "classification report is not strict JSON",
        ) from exc
    if (
        not isinstance(rows, list)
        or len(rows) > MAX_OBLIGATIONS
        or any(not isinstance(row, dict) for row in rows)
    ):
        raise EvaluationError(
            "classification_shape",
            "classification report must be a bounded array of objects",
        )

    normalized: list[dict[str, Any]] = []
    seen_paths: set[str] = set()
    counts: Counter[str] = Counter()
    for index, row in enumerate(rows):
        source_path = _canonical_source_path(
            row.get("path"),
            f"classifications[{index}].path",
        )
        if source_path in seen_paths:
            raise EvaluationError(
                "classification_duplicate_path",
                f"duplicate classification path: {source_path}",
            )
        seen_paths.add(source_path)
        size = row.get("size_bytes")
        if type(size) is not int or size < 0:
            raise EvaluationError(
                "classification_size",
                f"classifications[{index}].size_bytes must be non-negative",
            )
        decision = row.get("decision")
        if decision not in CLASSIFICATION_DECISIONS:
            raise EvaluationError(
                "classification_decision",
                f"classifications[{index}].decision is invalid",
            )
        counts[decision] += 1
        normalized.append(dict(row))

    receipt = candidate.import_receipt
    if len(normalized) != receipt["files_seen"]:
        raise EvaluationError(
            "classification_count_mismatch",
            "classification row count disagrees with IMPORT.json files_seen",
        )
    expected_counts = {
        "keep": receipt["files_retained"],
        "extract": receipt["files_extracted"],
        "tombstone": receipt["files_tombstoned"],
        "reject": receipt["files_rejected"],
    }
    for decision, expected in expected_counts.items():
        if counts[decision] != expected:
            raise EvaluationError(
                "classification_count_mismatch",
                f"classification {decision} count disagrees with IMPORT.json",
            )
    return normalized


def _conversation_id(row: dict[str, Any]) -> str | None:
    for key in ("source_conversation_id", "conversation_id"):
        value = row.get(key)
        if isinstance(value, str) and value:
            return value
    conversation = row.get("conversation")
    if isinstance(conversation, dict):
        for key in ("id", "conversation_id"):
            value = conversation.get(key)
            if value is not None:
                return str(value)
    return None


def _message_id(row: dict[str, Any]) -> str | None:
    value = row.get("source_message_id")
    if value is not None:
        return str(value)
    message = row.get("message")
    if isinstance(message, dict) and message.get("id") is not None:
        return str(message["id"])
    return None


def _attachment_refs(
    messages: list[dict[str, Any]],
    tombstones: list[dict[str, Any]],
) -> set[str]:
    refs: set[str] = set()
    for row in messages:
        values = row.get("attachment_refs")
        if isinstance(values, list):
            refs.update(
                item for item in values if isinstance(item, str) and item
            )
    for row in tombstones:
        context = row.get("semantic_context")
        if not isinstance(context, dict):
            continue
        key = context.get("reference_key")
        if isinstance(key, str) and key:
            refs.add(key)
        keys = context.get("reference_keys")
        if isinstance(keys, list):
            refs.update(
                item for item in keys if isinstance(item, str) and item
            )
    return refs


def _coverage(required: list[str], observed: set[str]) -> dict[str, Any]:
    if not required:
        return {
            "status": "unassessed",
            "required": [],
            "covered": [],
            "missing": [],
            "coverage": _ratio(0, 0),
        }
    covered = [item for item in required if item in observed]
    missing = [item for item in required if item not in observed]
    return {
        "status": "pass" if not missing else "fail",
        "required": required,
        "covered": covered,
        "missing": missing,
        "coverage": _ratio(len(covered), len(required)),
    }


def _scan_forbidden_fragments(
    candidate: CandidateState,
    fragments: list[str],
) -> list[str]:
    if not fragments:
        return []
    patterns = {fragment: fragment.encode("utf-8") for fragment in fragments}
    unresolved = dict(patterns)
    found: set[str] = set()
    max_pattern_bytes = max(len(pattern) for pattern in patterns.values())
    overlap = max_pattern_bytes - 1

    for artifact in candidate.artifacts:
        path = candidate.root.joinpath(*PurePosixPath(artifact["path"]).parts)
        tail = b""
        try:
            with path.open("rb") as handle:
                while chunk := handle.read(SCAN_CHUNK_BYTES):
                    window = tail + chunk
                    for fragment, pattern in list(unresolved.items()):
                        if pattern in window:
                            found.add(fragment)
                            del unresolved[fragment]
                    if not unresolved:
                        return [item for item in fragments if item in found]
                    tail = window[-overlap:] if overlap else b""
        except OSError as exc:
            raise EvaluationError(
                "artifact_scan_error",
                f"cannot scan verified candidate artifact: {artifact['path']}",
            ) from exc
    return [item for item in fragments if item in found]


def evaluate_import(
    source_path: Path,
    output_root: Path,
    obligations_path: Path | None = None,
) -> dict[str, Any]:
    if source_path.is_symlink() or not source_path.is_file():
        raise EvaluationError(
            "source_input",
            "evaluation source must be a non-symlink regular file",
        )
    try:
        candidate = verify_candidate_root(output_root)
    except HandoffError as exc:
        raise EvaluationError(
            "candidate_invalid",
            f"candidate verification failed: {exc}",
        ) from exc

    source_sha256 = sha256_file(source_path)
    if source_sha256 != candidate.candidate["input_sha256"]:
        raise EvaluationError(
            "source_candidate_mismatch",
            "evaluation source bytes do not match candidate input_sha256",
        )

    obligations = load_obligations(obligations_path)
    classification_rows = _load_classifications(candidate)
    conversations = _read_candidate_jsonl(
        candidate,
        "conversations/conversations.jsonl",
    )
    messages = _read_candidate_jsonl(
        candidate,
        "messages/messages.jsonl",
    )
    tombstones = _read_candidate_jsonl(
        candidate,
        "tombstones/tombstones.jsonl",
    )

    source_archive_bytes = source_path.stat().st_size
    source_member_bytes = sum(row["size_bytes"] for row in classification_rows)
    candidate_artifact_bytes = sum(
        row["size_bytes"] for row in candidate.artifacts
    )
    verbatim_carried_bytes = sum(
        row["size_bytes"]
        for row in candidate.artifacts
        if row["path"].startswith("retained/")
    )
    normalized_conversation_bytes = sum(
        row["size_bytes"]
        for row in candidate.artifacts
        if row["path"].startswith("conversations/")
    )
    normalized_message_bytes = sum(
        row["size_bytes"]
        for row in candidate.artifacts
        if row["path"].startswith("messages/")
    )
    extracted_text_bytes = sum(
        row["size_bytes"]
        for row in candidate.artifacts
        if row["path"].startswith("extracted/")
    )
    tombstoned_source_bytes = sum(
        row["size_bytes"]
        for row in classification_rows
        if row["decision"] == "tombstone"
    )
    rejected_source_bytes = sum(
        row["size_bytes"]
        for row in classification_rows
        if row["decision"] == "reject"
    )

    conversation_ids = {
        value
        for row in conversations
        if (value := _conversation_id(row)) is not None
    }
    message_ids = {
        value
        for row in messages
        if (value := _message_id(row)) is not None
    }
    attachment_refs = _attachment_refs(messages, tombstones)

    if obligations is None:
        semantic = {
            "status": "unassessed",
            "conversation_retention": _coverage([], conversation_ids),
            "message_retention": _coverage([], message_ids),
            "attachment_reference_retention": _coverage([], attachment_refs),
            "negative_space": {
                "status": "unassessed",
                "forbidden_fragments_found": [],
            },
        }
        obligations_sha256 = None
    else:
        forbidden_fragments = obligations["forbidden_text_fragments"]
        forbidden_found = _scan_forbidden_fragments(
            candidate,
            forbidden_fragments,
        )
        conversation_coverage = _coverage(
            obligations["required_conversation_ids"],
            conversation_ids,
        )
        message_coverage = _coverage(
            obligations["required_message_ids"],
            message_ids,
        )
        attachment_coverage = _coverage(
            obligations["required_attachment_refs"],
            attachment_refs,
        )
        negative_status = (
            "unassessed"
            if not forbidden_fragments
            else "pass"
            if not forbidden_found
            else "fail"
        )
        component_statuses = [
            conversation_coverage["status"],
            message_coverage["status"],
            attachment_coverage["status"],
            negative_status,
        ]
        overall_status = (
            "fail"
            if "fail" in component_statuses
            else "pass"
            if "pass" in component_statuses
            else "unassessed"
        )
        semantic = {
            "status": overall_status,
            "conversation_retention": conversation_coverage,
            "message_retention": message_coverage,
            "attachment_reference_retention": attachment_coverage,
            "negative_space": {
                "status": negative_status,
                "forbidden_fragments_found": forbidden_found,
            },
        }
        obligations_sha256 = (
            sha256_file(obligations_path)
            if obligations_path is not None
            else None
        )

    body = {
        "protocol": EVALUATION_PROTOCOL,
        "schema_version": SCHEMA_VERSION,
        "authority": "measurement-only",
        "source_sha256": source_sha256,
        "candidate_sha256": candidate.candidate["candidate_sha256"],
        "obligations_sha256": obligations_sha256,
        "byte_metrics": {
            "source_archive_bytes": source_archive_bytes,
            "source_member_uncompressed_bytes": source_member_bytes,
            "candidate_artifact_bytes": candidate_artifact_bytes,
            "verbatim_carried_bytes": verbatim_carried_bytes,
            "normalized_conversation_bytes": normalized_conversation_bytes,
            "normalized_message_bytes": normalized_message_bytes,
            "extracted_text_bytes": extracted_text_bytes,
            "tombstoned_source_bytes": tombstoned_source_bytes,
            "rejected_source_bytes": rejected_source_bytes,
            "archive_to_candidate": _reduction(
                source_archive_bytes,
                candidate_artifact_bytes,
            ),
            "member_bytes_to_verbatim_carried": _reduction(
                source_member_bytes,
                verbatim_carried_bytes,
            ),
        },
        "semantic_retention": semantic,
        "aggregate_score_emitted": False,
        "boundaries": list(EVALUATION_BOUNDARIES),
    }
    return {
        **body,
        "evaluation_sha256": sha256_bytes(canonical_json_bytes(body)),
    }


def _parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        description=(
            "Measure QSOL-IMPORT byte reduction and explicit "
            "semantic-retention obligations"
        )
    )
    parser.add_argument("source", type=Path)
    parser.add_argument("output_root", type=Path)
    parser.add_argument("--obligations", type=Path, default=None)
    parser.add_argument("--output", type=Path, default=None)
    return parser


def main() -> int:
    args = _parser().parse_args()
    report = evaluate_import(args.source, args.output_root, args.obligations)
    encoded = canonical_json_bytes(report)
    if args.output is None:
        import sys

        sys.stdout.buffer.write(encoded)
    else:
        args.output.parent.mkdir(parents=True, exist_ok=True)
        args.output.write_bytes(encoded)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
