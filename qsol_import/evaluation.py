from __future__ import annotations

import argparse
from pathlib import Path
from typing import Any, Iterable

from qsol_import.canonical import canonical_json_bytes, loads_strict, sha256_bytes, sha256_file
from qsol_import.handoff import verify_candidate_root


EVALUATION_PROTOCOL = "QSOL-IMPORT/EVALUATION/1"
OBLIGATIONS_PROTOCOL = "QSOL-IMPORT/RETENTION-OBLIGATIONS/1"
SCHEMA_VERSION = "1.0.0"
MAX_JSON_BYTES = 32 * 1024 * 1024
MAX_JSONL_BYTES = 512 * 1024 * 1024
MAX_OBLIGATIONS = 100_000

EVALUATION_BOUNDARIES = (
    "BYTE_REDUCTION != CONTEXT_RETENTION",
    "SEMANTIC_COVERAGE != FACTUAL_TRUTH",
    "TOMBSTONED_BYTES != RESTORED_BYTES",
    "UNASSESSED != FAILED",
    "MEASUREMENT != ACCEPTANCE_AUTHORITY",
    "AGGREGATE_SCORE = FORBIDDEN",
)


class EvaluationError(ValueError):
    def __init__(self, code: str, message: str):
        super().__init__(message)
        self.code = code


def _load_object(path: Path, max_bytes: int = MAX_JSON_BYTES) -> dict[str, Any]:
    if path.is_symlink() or not path.is_file():
        raise EvaluationError("invalid_json_input", f"missing or symlink JSON input: {path}")
    if path.stat().st_size > max_bytes:
        raise EvaluationError("json_size_limit", f"JSON input exceeds {max_bytes} bytes: {path}")
    try:
        value = loads_strict(path.read_bytes())
    except (UnicodeDecodeError, ValueError) as exc:
        raise EvaluationError("invalid_json", f"strict JSON parsing failed: {path}") from exc
    if not isinstance(value, dict):
        raise EvaluationError("invalid_json_shape", f"JSON input must contain an object: {path}")
    return value


def _read_jsonl(path: Path) -> list[dict[str, Any]]:
    if not path.is_file() or path.is_symlink():
        return []
    if path.stat().st_size > MAX_JSONL_BYTES:
        raise EvaluationError("jsonl_size_limit", f"JSONL input exceeds {MAX_JSONL_BYTES} bytes: {path}")
    rows: list[dict[str, Any]] = []
    with path.open("rb") as handle:
        for line_number, raw in enumerate(handle, start=1):
            if not raw.strip():
                continue
            try:
                value = loads_strict(raw)
            except (UnicodeDecodeError, ValueError) as exc:
                raise EvaluationError("invalid_jsonl", f"invalid JSONL record at {path}:{line_number}") from exc
            if not isinstance(value, dict):
                raise EvaluationError("invalid_jsonl_shape", f"JSONL record is not an object at {path}:{line_number}")
            rows.append(value)
    return rows


def _ratio(numerator: int, denominator: int) -> dict[str, Any]:
    if denominator == 0:
        return {"numerator": numerator, "denominator": denominator, "basis_points": None, "status": "unassessed"}
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


def _exact_string_list(value: Any, where: str) -> list[str]:
    if not isinstance(value, list) or len(value) > MAX_OBLIGATIONS:
        raise EvaluationError("invalid_obligations", f"{where} must be an array of at most {MAX_OBLIGATIONS} strings")
    if any(not isinstance(item, str) or not item for item in value):
        raise EvaluationError("invalid_obligations", f"{where} contains an invalid string")
    if len(value) != len(set(value)):
        raise EvaluationError("duplicate_obligation", f"{where} contains duplicate values")
    encoded = [item.encode("utf-8") for item in value]
    if encoded != sorted(encoded):
        raise EvaluationError("obligation_order", f"{where} must be UTF-8 sorted")
    return list(value)


def load_obligations(path: Path | None) -> dict[str, Any] | None:
    if path is None:
        return None
    value = _load_object(path)
    expected = {
        "protocol",
        "schema_version",
        "required_conversation_ids",
        "required_message_ids",
        "required_attachment_refs",
        "forbidden_text_fragments",
        "boundaries",
    }
    if set(value) != expected:
        raise EvaluationError("obligation_fields", "retention-obligation fields mismatch")
    if value["protocol"] != OBLIGATIONS_PROTOCOL or value["schema_version"] != SCHEMA_VERSION:
        raise EvaluationError("obligation_protocol", "unsupported retention-obligation protocol/version")
    for field in (
        "required_conversation_ids",
        "required_message_ids",
        "required_attachment_refs",
        "forbidden_text_fragments",
        "boundaries",
    ):
        value[field] = _exact_string_list(value[field], field)
    return value


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


def _iter_strings(value: Any) -> Iterable[str]:
    if isinstance(value, str):
        yield value
    elif isinstance(value, dict):
        for key in sorted(value):
            yield from _iter_strings(value[key])
    elif isinstance(value, list):
        for item in value:
            yield from _iter_strings(item)


def _attachment_refs(messages: list[dict[str, Any]], tombstones: list[dict[str, Any]]) -> set[str]:
    refs: set[str] = set()
    for row in messages:
        values = row.get("attachment_refs")
        if isinstance(values, list):
            refs.update(item for item in values if isinstance(item, str) and item)
    for row in tombstones:
        context = row.get("semantic_context")
        if not isinstance(context, dict):
            continue
        key = context.get("reference_key")
        if isinstance(key, str) and key:
            refs.add(key)
        keys = context.get("reference_keys")
        if isinstance(keys, list):
            refs.update(item for item in keys if isinstance(item, str) and item)
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


def evaluate_import(
    source_path: Path,
    output_root: Path,
    obligations_path: Path | None = None,
) -> dict[str, Any]:
    candidate = verify_candidate_root(output_root)
    obligations = load_obligations(obligations_path)
    classification_path = output_root / "reports" / "classifications.json"
    if not classification_path.is_file() or classification_path.is_symlink():
        raise EvaluationError("classification_missing", "reports/classifications.json is required")
    if classification_path.stat().st_size > MAX_JSON_BYTES:
        raise EvaluationError("classification_size_limit", "classification report exceeds limit")
    try:
        classification_rows = loads_strict(classification_path.read_bytes())
    except (UnicodeDecodeError, ValueError) as exc:
        raise EvaluationError("classification_invalid", "classification report is not strict JSON") from exc
    if not isinstance(classification_rows, list) or any(not isinstance(row, dict) for row in classification_rows):
        raise EvaluationError("classification_shape", "classification report must be an array of objects")

    conversations = _read_jsonl(output_root / "conversations" / "conversations.jsonl")
    messages = _read_jsonl(output_root / "messages" / "messages.jsonl")
    tombstones = _read_jsonl(output_root / "tombstones" / "tombstones.jsonl")

    source_archive_bytes = source_path.stat().st_size
    source_member_bytes = sum(
        row.get("size_bytes", 0)
        for row in classification_rows
        if type(row.get("size_bytes")) is int and row["size_bytes"] >= 0
    )
    candidate_artifact_bytes = sum(row["size_bytes"] for row in candidate.artifacts)
    verbatim_carried_bytes = sum(
        row["size_bytes"] for row in candidate.artifacts if row["path"].startswith("retained/")
    )
    normalized_conversation_bytes = sum(
        row["size_bytes"] for row in candidate.artifacts if row["path"].startswith("conversations/")
    )
    normalized_message_bytes = sum(
        row["size_bytes"] for row in candidate.artifacts if row["path"].startswith("messages/")
    )
    extracted_text_bytes = sum(
        row["size_bytes"] for row in candidate.artifacts if row["path"].startswith("extracted/")
    )
    tombstoned_source_bytes = sum(
        row.get("size_bytes", 0)
        for row in classification_rows
        if row.get("decision") == "tombstone" and type(row.get("size_bytes")) is int
    )
    rejected_source_bytes = sum(
        row.get("size_bytes", 0)
        for row in classification_rows
        if row.get("decision") == "reject" and type(row.get("size_bytes")) is int
    )

    conversation_ids = {value for row in conversations if (value := _conversation_id(row)) is not None}
    message_ids = {value for row in messages if (value := _message_id(row)) is not None}
    attachment_refs = _attachment_refs(messages, tombstones)
    normalized_text = "\n".join(_iter_strings(conversations + messages + tombstones))

    if obligations is None:
        semantic = {
            "status": "unassessed",
            "conversation_retention": _coverage([], conversation_ids),
            "message_retention": _coverage([], message_ids),
            "attachment_reference_retention": _coverage([], attachment_refs),
            "negative_space": {"status": "unassessed", "forbidden_fragments_found": []},
        }
        obligations_sha256 = None
    else:
        forbidden_found = [
            fragment for fragment in obligations["forbidden_text_fragments"] if fragment in normalized_text
        ]
        conversation_coverage = _coverage(obligations["required_conversation_ids"], conversation_ids)
        message_coverage = _coverage(obligations["required_message_ids"], message_ids)
        attachment_coverage = _coverage(obligations["required_attachment_refs"], attachment_refs)
        component_statuses = [
            conversation_coverage["status"],
            message_coverage["status"],
            attachment_coverage["status"],
            "pass" if not forbidden_found else "fail",
        ]
        semantic = {
            "status": "fail" if "fail" in component_statuses else "pass",
            "conversation_retention": conversation_coverage,
            "message_retention": message_coverage,
            "attachment_reference_retention": attachment_coverage,
            "negative_space": {
                "status": "pass" if not forbidden_found else "fail",
                "forbidden_fragments_found": forbidden_found,
            },
        }
        obligations_sha256 = sha256_file(obligations_path) if obligations_path is not None else None

    body = {
        "protocol": EVALUATION_PROTOCOL,
        "schema_version": SCHEMA_VERSION,
        "authority": "measurement-only",
        "source_sha256": sha256_file(source_path),
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
            "archive_to_candidate": _reduction(source_archive_bytes, candidate_artifact_bytes),
            "member_bytes_to_verbatim_carried": _reduction(source_member_bytes, verbatim_carried_bytes),
        },
        "semantic_retention": semantic,
        "aggregate_score_emitted": False,
        "boundaries": list(EVALUATION_BOUNDARIES),
    }
    return {**body, "evaluation_sha256": sha256_bytes(canonical_json_bytes(body))}


def _parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description="Measure QSOL-IMPORT byte reduction and explicit semantic-retention obligations")
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
