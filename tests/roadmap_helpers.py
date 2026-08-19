from __future__ import annotations

from pathlib import Path
from typing import Any

from qsol_import.canonical import canonical_json_bytes, sha256_bytes, sha256_file
from qsol_import.handoff import DECISION_BOUNDARIES


def build_candidate(root: Path, artifacts: dict[str, bytes]) -> dict[str, Any]:
    root.mkdir(parents=True, exist_ok=True)
    for relative, data in artifacts.items():
        path = root / relative
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_bytes(data)

    rows = [
        {"path": relative, "sha256": sha256_file(root / relative), "size_bytes": len(data)}
        for relative, data in sorted(artifacts.items(), key=lambda item: item[0].encode("utf-8"))
    ]
    candidate_body = {
        "protocol": "QSOL-IMPORT/CANDIDATE-MANIFEST/1",
        "schema_version": "1.0.0",
        "authority": "candidate-only",
        "source_type": "synthetic.test",
        "profile": "conversation-first/1",
        "input_sha256": "1" * 64,
        "policy_sha256": "2" * 64,
        "implementation_sha256": "3" * 64,
        "concap_roles_assigned": False,
        "import_receipt_path": "IMPORT.json",
        "artifacts": rows,
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

    receipt_body = {
        "protocol": "QSOL-IMPORT/RECEIPT/1",
        "schema_version": "1.0.0",
        "implementation_version": "test",
        "source_type": candidate["source_type"],
        "profile": candidate["profile"],
        "input_sha256": candidate["input_sha256"],
        "policy_sha256": candidate["policy_sha256"],
        "implementation_sha256": candidate["implementation_sha256"],
        "output_sha256": "4" * 64,
        "candidate_sha256": candidate["candidate_sha256"],
        "conversations": 1,
        "messages": 1,
        "files_seen": len(rows),
        "files_retained": len(rows),
        "files_extracted": 0,
        "files_tombstoned": 0,
        "files_rejected": 0,
    }
    receipt = {
        **receipt_body,
        "receipt_sha256": sha256_bytes(canonical_json_bytes(receipt_body)),
    }
    (root / "IMPORT.json").write_bytes(canonical_json_bytes(receipt))
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
                "reason": "approved by deterministic fixture" if disposition == "accept" else "rejected by deterministic fixture",
            }
        )
    accepted = sum(row["disposition"] == "accept" for row in rows)
    rejected = sum(row["disposition"] == "reject" for row in rows)
    summary = "accepted" if accepted and not rejected else "rejected" if rejected and not accepted else "partially_accepted"
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
    decision = {**body, "decision_sha256": sha256_bytes(canonical_json_bytes(body))}
    path.write_bytes(canonical_json_bytes(decision))
    return decision
