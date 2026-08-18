from __future__ import annotations

import hashlib
import shutil
import tempfile
from dataclasses import asdict
from pathlib import Path, PurePosixPath
from typing import Any, BinaryIO

from qsol_import import __version__
from qsol_import.adapter_contract import (
    ADAPTER_PROTOCOL,
    PROVENANCE_PROTOCOL,
    Adapter,
    AdapterError,
    validate_result,
)
from qsol_import.canonical import (
    canonical_json_bytes,
    loads_strict,
    package_implementation_sha256,
    sha256_bytes,
    sha256_file,
    sha256_stream,
)
from qsol_import.classify import classify_file
from qsol_import.documents import DocumentExtractionError, extract_document_text, frozen_extractor_contract
from qsol_import.privacy import scan_files
from qsol_import.source import SourceArchive


def _load_policy(path: Path) -> tuple[dict[str, Any], bytes]:
    raw = path.read_bytes()
    value = loads_strict(raw)
    if not isinstance(value, dict):
        raise ValueError("import policy must be a JSON object")
    return value, raw


def _safe_output_path(root: Path, original: str) -> Path:
    return root.joinpath(*PurePosixPath(original).parts)


def _copy_stream(source: BinaryIO, destination: Path) -> str:
    destination.parent.mkdir(parents=True, exist_ok=True)
    digest = hashlib.sha256()
    with destination.open("wb") as out:
        while chunk := source.read(1024 * 1024):
            digest.update(chunk)
            out.write(chunk)
    return digest.hexdigest()


def _write_jsonl(path: Path, records: tuple[dict[str, Any], ...] | list[dict[str, Any]]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("wb") as handle:
        for record in records:
            handle.write(canonical_json_bytes(record))


def _manifest_digest(root: Path, excluded: set[str]) -> str:
    records = []
    for path in sorted(p for p in root.rglob("*") if p.is_file()):
        rel = path.relative_to(root).as_posix()
        if rel in excluded:
            continue
        records.append({"path": rel, "sha256": sha256_file(path), "size_bytes": path.stat().st_size})
    return sha256_bytes(canonical_json_bytes(records))


def _semantic_context(adapter: Adapter, result, path: str, kind: str) -> dict[str, Any]:
    basename = PurePosixPath(path).name
    key = adapter.member_reference_key(path)
    contexts = list(result.attachment_index.get(key, ())) if key is not None else []
    body: dict[str, Any] = {
        "label": f"{kind} export asset: {basename}",
        "label_source": "deterministic_adapter_context",
        "reference_match": "none",
    }
    if contexts:
        first = contexts[0]
        body.update(
            {
                "reference_match": "exact",
                "reference_key": key,
                "reference_count": len(contexts),
                "conversation_id": first.get("conversation_id"),
                "source_message_id": first.get("source_message_id"),
                "source_path": first.get("source_path"),
                "source_index": first.get("source_index"),
                "label": f"{kind} referenced by conversation {first.get('conversation_id')}: {basename}",
            }
        )
    return body


def _write_tombstone(
    handle: BinaryIO,
    *,
    adapter: Adapter,
    path: str,
    size_bytes: int,
    object_sha: str,
    kind: str,
    media_type: str,
    reason: str,
    result,
) -> None:
    handle.write(
        canonical_json_bytes(
            {
                "protocol": "QSOL-IMPORT/TOMBSTONE/1",
                "source_vendor": adapter.source_vendor,
                "original_path": path,
                "original_name": PurePosixPath(path).name,
                "sha256": object_sha,
                "size_bytes": size_bytes,
                "detected_type": media_type,
                "asset_class": kind,
                "decision": "omit_bytes",
                "reason": reason,
                "semantic_context": _semantic_context(adapter, result, path, kind),
            }
        )
    )


def _write_candidate_manifest(
    output_dir: Path,
    *,
    adapter: Adapter,
    source_sha256: str,
    policy: dict[str, Any],
    policy_sha256: str,
    implementation_sha256: str,
) -> dict[str, Any]:
    artifacts = []
    for path in sorted(p for p in output_dir.rglob("*") if p.is_file()):
        rel = path.relative_to(output_dir).as_posix()
        if rel in {"CANDIDATE.json", "IMPORT.json", "SHA256SUMS"}:
            continue
        artifacts.append({"path": rel, "sha256": sha256_file(path), "size_bytes": path.stat().st_size})
    body = {
        "protocol": "QSOL-IMPORT/CANDIDATE-MANIFEST/1",
        "schema_version": "1.0.0",
        "authority": "candidate-only",
        "source_type": adapter.source_type,
        "profile": policy["profile"],
        "input_sha256": source_sha256,
        "policy_sha256": policy_sha256,
        "implementation_sha256": implementation_sha256,
        "concap_roles_assigned": False,
        "import_receipt_path": "IMPORT.json",
        "artifacts": artifacts,
        "boundaries": [
            "PARSED != TRUSTED",
            "NORMALIZED != CANONICAL",
            "IMPORT != FACTUAL_AUTHORITY",
            "IMPORT != ROUTING",
            "CANDIDATE_MANIFEST != CONCAP_EXPORT_SPEC",
            "VENDOR_FORMAT != CANONICAL_FORMAT",
        ],
    }
    manifest = {**body, "candidate_sha256": sha256_bytes(canonical_json_bytes(body))}
    (output_dir / "CANDIDATE.json").write_bytes(canonical_json_bytes(manifest))
    return manifest


def _hash_member(source: SourceArchive, path: str) -> str:
    with source.open_member(path) as handle:
        return sha256_stream(handle)


def _document_disposition(
    *,
    source: SourceArchive,
    path: str,
    output_dir: Path,
    policy: dict[str, Any],
    classification,
    record: dict[str, Any],
    counts: dict[str, int],
    tombstone_out: BinaryIO,
    adapter: Adapter,
    result,
    scan_paths: set[str],
) -> None:
    document_policy = policy["documents"]
    size_bytes = source.size(path)
    contract = frozen_extractor_contract(classification.media_type)
    extract_text = bool(document_policy.get("extract_text", False))
    max_extract_bytes = int(document_policy.get("max_extract_bytes", document_policy["keep_original_under_bytes"]))
    keep_limit = int(document_policy["keep_original_under_bytes"])

    if extract_text and contract is not None and size_bytes <= max_extract_bytes:
        data = source.read_bytes(path, max_extract_bytes)
        record["sha256"] = sha256_bytes(data)
        record["extractor_contract"] = contract
        try:
            extraction = extract_document_text(data, classification.media_type, document_policy)
        except DocumentExtractionError as exc:
            record["extraction_error_code"] = exc.code
        else:
            destination = _safe_output_path(output_dir / "extracted" / "documents", path + ".txt")
            destination.parent.mkdir(parents=True, exist_ok=True)
            destination.write_bytes(extraction.text_bytes)
            rel = destination.relative_to(output_dir).as_posix()
            scan_paths.add(rel)
            record.update(
                {
                    "reason": "document_text_extracted",
                    "extracted_path": rel,
                    "extracted_sha256": sha256_bytes(extraction.text_bytes),
                    "extracted_size_bytes": len(extraction.text_bytes),
                }
            )
            if size_bytes <= keep_limit:
                retained = _safe_output_path(output_dir / "retained", path)
                with source.open_member(path) as handle:
                    _copy_stream(handle, retained)
            return

    if size_bytes <= keep_limit:
        with source.open_member(path) as handle:
            record["sha256"] = _copy_stream(handle, _safe_output_path(output_dir / "retained", path))
        record["decision"] = "keep"
        record["reason"] = "document_retained_no_frozen_extraction"
        counts["extract"] -= 1
        counts["keep"] += 1
        return

    object_sha = _hash_member(source, path)
    record["sha256"] = object_sha
    record["decision"] = "tombstone"
    record["reason"] = "document_over_retention_limit"
    counts["extract"] -= 1
    counts["tombstone"] += 1
    _write_tombstone(
        tombstone_out,
        adapter=adapter,
        path=path,
        size_bytes=size_bytes,
        object_sha=object_sha,
        kind=classification.kind,
        media_type=classification.media_type,
        reason="document_over_retention_limit",
        result=result,
    )


def _build_import(
    source_path: Path,
    *,
    output_dir: Path,
    policy: dict[str, Any],
    policy_sha256: str,
    implementation_sha256: str,
    adapter: Adapter,
    source_sha256: str,
) -> dict[str, Any]:
    for directory in ("conversations", "messages", "provenance", "tombstones", "retained", "extracted", "reports"):
        (output_dir / directory).mkdir(parents=True, exist_ok=True)

    classifications: list[dict[str, Any]] = []
    provenance: list[dict[str, Any]] = []
    counts = {"keep": 0, "extract": 0, "tombstone": 0, "reject": 0}
    scan_paths = {"conversations/conversations.jsonl", "messages/messages.jsonl"}

    with SourceArchive(source_path, policy) as source:
        discovered = adapter.discover(source.members)
        if len(set(discovered)) != len(discovered):
            raise AdapterError("duplicate_discovery", "adapter returned duplicate discovered members")
        known_paths = {member.path for member in source.members}
        if any(path not in known_paths for path in discovered):
            raise AdapterError("unknown_discovery_member", "adapter discovered a member not present in the source")

        adapter_limit = int(
            policy["archive_limits"].get(
                "max_conversation_member_bytes",
                policy["archive_limits"]["max_member_uncompressed_bytes"],
            )
        )
        payloads = {path: source.read_bytes(path, adapter_limit) for path in discovered}
        result = adapter.parse(payloads)
        validate_result(result, adapter.adapter_id)

        _write_jsonl(output_dir / "conversations" / "conversations.jsonl", result.conversations)
        _write_jsonl(output_dir / "messages" / "messages.jsonl", result.messages)

        consumed = set(discovered)
        consumed_hashes = {path: sha256_bytes(payloads[path]) for path in discovered}
        for path in discovered:
            counts["extract"] += 1
            record = {
                "path": path,
                "size_bytes": source.size(path),
                "kind": "adapter_source",
                "media_type": "application/json",
                "decision": "extract",
                "reason": "adapter_normalized",
                "sha256": consumed_hashes[path],
                "adapter_id": adapter.adapter_id,
            }
            classifications.append(record)
            provenance.append(
                {
                    "protocol": PROVENANCE_PROTOCOL,
                    "adapter_protocol": ADAPTER_PROTOCOL,
                    "adapter_id": adapter.adapter_id,
                    "source_vendor": adapter.source_vendor,
                    "source_type": adapter.source_type,
                    "source_path": path,
                    "source_sha256": consumed_hashes[path],
                    "size_bytes": source.size(path),
                    "disposition": "normalized",
                    "reason": "adapter_normalized",
                }
            )

        with (output_dir / "tombstones" / "tombstones.jsonl").open("wb") as tombstone_out:
            for member in source.members:
                path = member.path
                if path in consumed:
                    continue
                head = source.head(path)
                classification = classify_file(path, member.size_bytes, head, policy)
                override = adapter.member_disposition(path)
                decision = override.decision if override is not None else classification.decision
                reason = override.reason if override is not None else classification.reason
                if decision not in counts:
                    raise AdapterError("invalid_member_disposition", f"adapter returned invalid decision {decision!r}")
                counts[decision] += 1
                record = {
                    "path": path,
                    "size_bytes": member.size_bytes,
                    **asdict(classification),
                    "decision": decision,
                    "reason": reason,
                }

                if decision == "keep":
                    destination = _safe_output_path(output_dir / "retained", path)
                    with source.open_member(path) as handle:
                        record["sha256"] = _copy_stream(handle, destination)
                    if classification.kind == "structured_text":
                        scan_paths.add(destination.relative_to(output_dir).as_posix())
                elif decision == "extract":
                    if classification.kind != "document":
                        raise AdapterError("unsupported_extract_kind", f"unsupported extract kind for {path!r}")
                    _document_disposition(
                        source=source,
                        path=path,
                        output_dir=output_dir,
                        policy=policy,
                        classification=classification,
                        record=record,
                        counts=counts,
                        tombstone_out=tombstone_out,
                        adapter=adapter,
                        result=result,
                        scan_paths=scan_paths,
                    )
                elif decision == "tombstone":
                    object_sha = _hash_member(source, path)
                    record["sha256"] = object_sha
                    _write_tombstone(
                        tombstone_out,
                        adapter=adapter,
                        path=path,
                        size_bytes=member.size_bytes,
                        object_sha=object_sha,
                        kind=classification.kind,
                        media_type=classification.media_type,
                        reason=reason,
                        result=result,
                    )
                else:
                    record["sha256"] = _hash_member(source, path)

                classifications.append(record)
                provenance.append(
                    {
                        "protocol": PROVENANCE_PROTOCOL,
                        "adapter_protocol": ADAPTER_PROTOCOL,
                        "adapter_id": adapter.adapter_id,
                        "source_vendor": adapter.source_vendor,
                        "source_type": adapter.source_type,
                        "source_path": path,
                        "source_sha256": record["sha256"],
                        "size_bytes": member.size_bytes,
                        "disposition": record["decision"],
                        "reason": record["reason"],
                    }
                )

    provenance.sort(key=lambda row: row["source_path"].encode("utf-8"))
    _write_jsonl(output_dir / "provenance" / "provenance.jsonl", provenance)
    (output_dir / "reports" / "classifications.json").write_bytes(canonical_json_bytes(classifications))
    privacy = scan_files(output_dir, scan_paths)
    (output_dir / "reports" / "privacy-scan.json").write_bytes(canonical_json_bytes(privacy))

    stats = {
        "protocol": "QSOL-IMPORT/STATISTICS/1",
        "source_type": adapter.source_type,
        "adapter_id": adapter.adapter_id,
        "profile": policy["profile"],
        "conversations": len(result.conversations),
        "messages": len(result.messages),
        "provenance_records": len(provenance),
        "files_seen": sum(counts.values()),
        "files_retained": counts["keep"],
        "files_extracted": counts["extract"],
        "files_tombstoned": counts["tombstone"],
        "files_rejected": counts["reject"],
        "privacy_findings": privacy["finding_occurrences"],
    }
    (output_dir / "reports" / "statistics.json").write_bytes(canonical_json_bytes(stats))
    (output_dir / "reports" / "adapter.json").write_bytes(canonical_json_bytes(adapter.descriptor()))

    candidate = _write_candidate_manifest(
        output_dir,
        adapter=adapter,
        source_sha256=source_sha256,
        policy=policy,
        policy_sha256=policy_sha256,
        implementation_sha256=implementation_sha256,
    )
    output_sha256 = _manifest_digest(output_dir, {"IMPORT.json", "SHA256SUMS"})
    receipt_body = {
        "protocol": "QSOL-IMPORT/RECEIPT/1",
        "schema_version": "1.0.0",
        "implementation_version": __version__,
        "source_type": adapter.source_type,
        "profile": policy["profile"],
        "input_sha256": source_sha256,
        "policy_sha256": policy_sha256,
        "implementation_sha256": implementation_sha256,
        "output_sha256": output_sha256,
        "candidate_sha256": candidate["candidate_sha256"],
        "adapter_id": adapter.adapter_id,
        "conversations": stats["conversations"],
        "messages": stats["messages"],
        "provenance_records": stats["provenance_records"],
        "files_seen": stats["files_seen"],
        "files_retained": stats["files_retained"],
        "files_extracted": stats["files_extracted"],
        "files_tombstoned": stats["files_tombstoned"],
        "files_rejected": stats["files_rejected"],
    }
    receipt = {**receipt_body, "receipt_sha256": sha256_bytes(canonical_json_bytes(receipt_body))}
    (output_dir / "IMPORT.json").write_bytes(canonical_json_bytes(receipt))

    checksums = []
    for path in sorted(p for p in output_dir.rglob("*") if p.is_file()):
        rel = path.relative_to(output_dir).as_posix()
        if rel != "SHA256SUMS":
            checksums.append(f"{sha256_file(path)}  {rel}\n")
    (output_dir / "SHA256SUMS").write_text("".join(checksums), encoding="utf-8", newline="\n")
    return receipt


def _remove_path(path: Path) -> None:
    if path.is_dir():
        shutil.rmtree(path)
    elif path.exists():
        path.unlink()


def _commit_output(staging_dir: Path, output_dir: Path) -> None:
    backup_dir: Path | None = None
    if output_dir.exists():
        backup_dir = Path(tempfile.mkdtemp(prefix=f".{output_dir.name}.previous-", dir=output_dir.parent))
        backup_dir.rmdir()
        output_dir.rename(backup_dir)
    try:
        staging_dir.rename(output_dir)
    except Exception:
        if backup_dir is not None and not output_dir.exists():
            backup_dir.rename(output_dir)
        raise
    else:
        if backup_dir is not None:
            _remove_path(backup_dir)


def import_with_adapter(
    source_path: Path,
    output_dir: Path,
    policy_path: Path,
    adapter: Adapter,
) -> dict[str, Any]:
    policy, policy_raw = _load_policy(policy_path)
    policy_sha256 = sha256_bytes(policy_raw)
    package_root = Path(__file__).resolve().parent
    implementation_sha256 = package_implementation_sha256(package_root)
    source_sha256 = sha256_file(source_path)

    output_dir.parent.mkdir(parents=True, exist_ok=True)
    staging_dir = Path(tempfile.mkdtemp(prefix=f".{output_dir.name}.import-", dir=output_dir.parent))
    try:
        receipt = _build_import(
            source_path,
            output_dir=staging_dir,
            policy=policy,
            policy_sha256=policy_sha256,
            implementation_sha256=implementation_sha256,
            adapter=adapter,
            source_sha256=source_sha256,
        )
        if sha256_file(source_path) != source_sha256:
            raise ValueError("source changed during import")
        _commit_output(staging_dir, output_dir)
        return receipt
    except Exception:
        if staging_dir.exists():
            _remove_path(staging_dir)
        raise
