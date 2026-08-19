from __future__ import annotations

from pathlib import Path
from typing import Any

from qsol_import.ark_cleanroom import EXTERNAL_EXECUTION_BOUNDARIES
from qsol_import.canonical import canonical_json_bytes, sha256_bytes, sha256_file
from qsol_import.evaluation import OBLIGATION_BOUNDARIES
from qsol_import.handoff import DECISION_BOUNDARIES, THOTH_ROUTE_BOUNDARIES


def _tree_output_sha256(
    root: Path,
    artifacts: list[dict[str, Any]],
) -> str:
    paths = ["CANDIDATE.json", *(row["path"] for row in artifacts)]
    rows = []
    for relative in sorted(paths, key=lambda value: value.encode("utf-8")):
        path = root / relative
        rows.append(
            {
                "path": relative,
                "sha256": sha256_file(path),
                "size_bytes": path.stat().st_size,
            }
        )
    return sha256_bytes(canonical_json_bytes(rows))


def _write_checksums(root: Path) -> None:
    rows = []
    files = [path for path in root.rglob("*") if path.is_file()]
    for path in sorted(
        files,
        key=lambda item: item.relative_to(root).as_posix().encode("utf-8"),
    ):
        relative = path.relative_to(root).as_posix()
        if relative != "SHA256SUMS":
            rows.append(f"{sha256_file(path)}  {relative}\n")
    (root / "SHA256SUMS").write_text(
        "".join(rows),
        encoding="utf-8",
        newline="\n",
    )


def build_candidate(
    root: Path,
    artifacts: dict[str, bytes],
    *,
    input_sha256: str = "1" * 64,
    source_type: str = "synthetic.test",
    profile: str = "conversation-first/1",
    conversations: int = 1,
    messages: int = 1,
    receipt_counts: dict[str, int] | None = None,
    adapter_id: str | None = None,
    provenance_records: int | None = None,
) -> dict[str, Any]:
    root.mkdir(parents=True, exist_ok=True)
    for relative, data in artifacts.items():
        path = root / relative
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_bytes(data)

    artifact_rows = [
        {
            "path": relative,
            "sha256": sha256_file(root / relative),
            "size_bytes": len(data),
        }
        for relative, data in sorted(
            artifacts.items(),
            key=lambda item: item[0].encode("utf-8"),
        )
    ]
    candidate_body = {
        "protocol": "QSOL-IMPORT/CANDIDATE-MANIFEST/1",
        "schema_version": "1.0.0",
        "authority": "candidate-only",
        "source_type": source_type,
        "profile": profile,
        "input_sha256": input_sha256,
        "policy_sha256": "2" * 64,
        "implementation_sha256": "3" * 64,
        "concap_roles_assigned": False,
        "import_receipt_path": "IMPORT.json",
        "artifacts": artifact_rows,
        "boundaries": [
            "PARSED != TRUSTED",
            "NORMALIZED != CANONICAL",
            "IMPORT != FACTUAL_AUTHORITY",
            "IMPORT != ROUTING",
            "CANDIDATE_MANIFEST != CONCAP_EXPORT_SPEC",
        ],
    }
    candidate = {
        **candidate_body,
        "candidate_sha256": sha256_bytes(canonical_json_bytes(candidate_body)),
    }
    (root / "CANDIDATE.json").write_bytes(canonical_json_bytes(candidate))

    counts = receipt_counts or {
        "files_seen": len(artifact_rows),
        "files_retained": len(artifact_rows),
        "files_extracted": 0,
        "files_tombstoned": 0,
        "files_rejected": 0,
    }
    receipt_body: dict[str, Any] = {
        "protocol": "QSOL-IMPORT/RECEIPT/1",
        "schema_version": "1.0.0",
        "implementation_version": "test",
        "source_type": source_type,
        "profile": profile,
        "input_sha256": candidate["input_sha256"],
        "policy_sha256": candidate["policy_sha256"],
        "implementation_sha256": candidate["implementation_sha256"],
        "output_sha256": _tree_output_sha256(root, artifact_rows),
        "candidate_sha256": candidate["candidate_sha256"],
        "conversations": conversations,
        "messages": messages,
        **counts,
    }
    if adapter_id is not None or provenance_records is not None:
        if adapter_id is None or provenance_records is None:
            raise ValueError("adapter_id and provenance_records must be supplied together")
        receipt_body["adapter_id"] = adapter_id
        receipt_body["provenance_records"] = provenance_records
    receipt = {
        **receipt_body,
        "receipt_sha256": sha256_bytes(canonical_json_bytes(receipt_body)),
    }
    (root / "IMPORT.json").write_bytes(canonical_json_bytes(receipt))
    _write_checksums(root)
    return candidate


def build_decision(
    candidate_root: Path,
    path: Path,
    dispositions: dict[str, str],
) -> dict[str, Any]:
    import json

    candidate = json.loads((candidate_root / "CANDIDATE.json").read_text())
    rows = []
    for artifact in candidate["artifacts"]:
        disposition = dispositions[artifact["path"]]
        rows.append(
            {
                **artifact,
                "disposition": disposition,
                "reason": (
                    "approved by deterministic fixture"
                    if disposition == "accept"
                    else "rejected by deterministic fixture"
                ),
            }
        )
    accepted = sum(row["disposition"] == "accept" for row in rows)
    rejected = sum(row["disposition"] == "reject" for row in rows)
    summary = (
        "accepted"
        if accepted and not rejected
        else "rejected"
        if rejected and not accepted
        else "partially_accepted"
    )
    body = {
        "protocol": "QSOL-CONTEXT/IMPORT-DECISION/1",
        "schema_version": "1.0.0",
        "issuer": "QSOL-CONTEXT",
        "authority": "context-acceptance-only",
        "candidate_sha256": candidate["candidate_sha256"],
        "import_receipt_sha256": sha256_file(candidate_root / "IMPORT.json"),
        "decision": summary,
        "review_policy": "qsol-context-import-review/test",
        "review_policy_sha256": "5" * 64,
        "artifacts": rows,
        "concap_roles_assigned": False,
        "boundaries": list(DECISION_BOUNDARIES),
    }
    decision = {
        **body,
        "decision_sha256": sha256_bytes(canonical_json_bytes(body)),
    }
    path.write_bytes(canonical_json_bytes(decision))
    return decision


def build_thoth_route_receipt(path: Path) -> dict[str, Any]:
    body = {
        "protocol": "QSOL-THOTH/ROUTE-DECISION/1",
        "canonical_intent": "general",
        "style": "neutral",
        "concaps": [
            "concap.identity.core/1",
            "concap.workstyle.engineering/1",
        ],
        "request_sha256": "sha256:" + "6" * 64,
        "configuration_sha256": "sha256:" + "7" * 64,
        "implementation_sha256": "sha256:" + "8" * 64,
        "boundaries": list(THOTH_ROUTE_BOUNDARIES),
    }
    receipt = {
        **body,
        "decision_sha256": "sha256:" + sha256_bytes(canonical_json_bytes(body)),
    }
    path.write_bytes(canonical_json_bytes(receipt))
    return receipt


def build_obligations(
    path: Path,
    *,
    required_conversation_ids: list[str] | None = None,
    required_message_ids: list[str] | None = None,
    required_attachment_refs: list[str] | None = None,
    forbidden_text_fragments: list[str] | None = None,
    extra_boundaries: list[str] | None = None,
) -> dict[str, Any]:
    def ordered(values: list[str] | None) -> list[str]:
        return sorted(values or [], key=lambda value: value.encode("utf-8"))

    boundaries = ordered(
        [*OBLIGATION_BOUNDARIES, *(extra_boundaries or [])]
    )
    body = {
        "protocol": "QSOL-IMPORT/RETENTION-OBLIGATIONS/1",
        "schema_version": "1.0.0",
        "authority": "measurement-obligations-only",
        "required_conversation_ids": ordered(required_conversation_ids),
        "required_message_ids": ordered(required_message_ids),
        "required_attachment_refs": ordered(required_attachment_refs),
        "forbidden_text_fragments": ordered(forbidden_text_fragments),
        "boundaries": boundaries,
    }
    receipt = {
        **body,
        "obligations_sha256": sha256_bytes(canonical_json_bytes(body)),
    }
    path.write_bytes(canonical_json_bytes(receipt))
    return receipt


def build_external_execution_receipt(
    path: Path,
    observation_path: Path,
    *,
    ark_trial_id: str,
) -> dict[str, Any]:
    body = {
        "protocol": "QSOL-IMPORT/EXTERNAL-EXECUTION-RECEIPT/1",
        "schema_version": "1.0.0",
        "authority": "external-execution-observation-only",
        "record_class": "externally-observed-clean-room",
        "observation_sha256": sha256_file(observation_path),
        "ark_trial_id": ark_trial_id,
        "execution_id": "fixture-execution-1",
        "executor": "deterministic-test-operator",
        "environment": "fresh-no-memory-fixture-environment",
        "outcome": "completed",
        "boundaries": list(EXTERNAL_EXECUTION_BOUNDARIES),
    }
    receipt = {
        **body,
        "receipt_sha256": sha256_bytes(canonical_json_bytes(body)),
    }
    path.write_bytes(canonical_json_bytes(receipt))
    return receipt
