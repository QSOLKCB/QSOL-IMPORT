from __future__ import annotations

import hashlib
import shutil
import tempfile
import zipfile
from collections import defaultdict
from dataclasses import asdict
from pathlib import Path, PurePosixPath
from typing import Any, BinaryIO

from qsol_import import __version__
from qsol_import.adapters.openai import (
    context_for,
    conversation_file_sort_key,
    finalize_attachment_reference_index,
    is_conversation_file,
    iter_message_records,
    load_conversations,
    semantic_context_for_path,
    update_attachment_reference_index,
)
from qsol_import.archive import UnsafeArchiveError, validate_archive
from qsol_import.canonical import (
    canonical_json_bytes,
    loads_strict,
    package_implementation_sha256,
    sha256_bytes,
    sha256_file,
    sha256_stream,
)
from qsol_import.classify import classify_file


def _load_policy(path: Path) -> tuple[dict[str, Any], bytes]:
    raw = path.read_bytes()
    value = loads_strict(raw)
    if not isinstance(value, dict):
        raise ValueError("import policy must be a JSON object")
    return value, raw


def _copy_stream(source: BinaryIO, destination: Path) -> str:
    destination.parent.mkdir(parents=True, exist_ok=True)
    digest = hashlib.sha256()
    with destination.open("wb") as out:
        while chunk := source.read(1024 * 1024):
            digest.update(chunk)
            out.write(chunk)
    return digest.hexdigest()


def _hash_stream(source: BinaryIO) -> str:
    return sha256_stream(source)


def _safe_output_path(root: Path, original: str) -> Path:
    return root.joinpath(*PurePosixPath(original).parts)


def _manifest_digest(root: Path, excluded: set[str]) -> str:
    records = []
    for path in sorted(p for p in root.rglob("*") if p.is_file()):
        rel = path.relative_to(root).as_posix()
        if rel in excluded:
            continue
        records.append(
            {"path": rel, "sha256": sha256_file(path), "size_bytes": path.stat().st_size}
        )
    return sha256_bytes(canonical_json_bytes(records))


def _write_candidate_manifest(
    output_dir: Path,
    *,
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
        artifacts.append(
            {"path": rel, "sha256": sha256_file(path), "size_bytes": path.stat().st_size}
        )

    body = {
        "protocol": "QSOL-IMPORT/CANDIDATE-MANIFEST/1",
        "schema_version": "1.0.0",
        "authority": "candidate-only",
        "source_type": "openai.export",
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
        ],
    }
    manifest = {
        **body,
        "candidate_sha256": sha256_bytes(canonical_json_bytes(body)),
    }
    (output_dir / "CANDIDATE.json").write_bytes(canonical_json_bytes(manifest))
    return manifest


def _write_tombstone(
    handle: BinaryIO,
    *,
    info: zipfile.ZipInfo,
    object_sha: str,
    classification,
    reason: str,
    refs,
) -> None:
    tombstone = {
        "protocol": "QSOL-IMPORT/TOMBSTONE/1",
        "source_vendor": "openai",
        "original_path": info.filename,
        "original_name": PurePosixPath(info.filename).name,
        "sha256": object_sha,
        "size_bytes": info.file_size,
        "detected_type": classification.media_type,
        "asset_class": classification.kind,
        "decision": "omit_bytes",
        "reason": reason,
        "semantic_context": semantic_context_for_path(
            info.filename,
            classification.kind,
            refs,
        ),
    }
    handle.write(canonical_json_bytes(tombstone))


def _build_import(
    source_handle: BinaryIO,
    *,
    source_sha256: str,
    output_dir: Path,
    policy: dict[str, Any],
    policy_sha256: str,
    implementation_sha256: str,
) -> dict[str, Any]:
    (output_dir / "conversations").mkdir(parents=True)
    (output_dir / "messages").mkdir()
    (output_dir / "tombstones").mkdir()
    (output_dir / "retained").mkdir()
    (output_dir / "reports").mkdir()

    classifications: list[dict[str, Any]] = []
    counts = {"keep": 0, "extract": 0, "tombstone": 0, "reject": 0}
    conversation_count = 0
    message_count = 0
    refs_sets = defaultdict(set)

    source_handle.seek(0)
    with zipfile.ZipFile(source_handle, "r") as zf:
        validate_archive(zf, policy)
        conversation_infos = [
            info
            for info in zf.infolist()
            if not info.is_dir() and is_conversation_file(info.filename)
        ]
        max_conversation_bytes = int(
            policy["archive_limits"].get(
                "max_conversation_member_bytes",
                policy["archive_limits"]["max_member_uncompressed_bytes"],
            )
        )

        with (
            (output_dir / "conversations" / "conversations.jsonl").open("wb") as conversation_out,
            (output_dir / "messages" / "messages.jsonl").open("wb") as message_out,
        ):
            for info in sorted(
                conversation_infos,
                key=lambda item: conversation_file_sort_key(item.filename),
            ):
                if info.file_size > max_conversation_bytes:
                    raise UnsafeArchiveError(
                        f"conversation member too large: {info.filename!r}"
                    )
                with zf.open(info, "r") as handle:
                    data = handle.read()
                object_sha = sha256_bytes(data)
                items = load_conversations(data)
                counts["extract"] += 1
                classifications.append(
                    {
                        "path": info.filename,
                        "size_bytes": info.file_size,
                        "kind": "conversation_json",
                        "media_type": "application/json",
                        "decision": "extract",
                        "reason": "conversation_normalized",
                        "sha256": object_sha,
                    }
                )

                for index, conversation in enumerate(items):
                    ctx = context_for(conversation, info.filename, index)
                    conversation_count += 1
                    conversation_out.write(
                        canonical_json_bytes(
                            {
                                "protocol": "QSOL-IMPORT/OPENAI-CONVERSATION/1",
                                "source_file": info.filename,
                                "source_index": index,
                                "conversation": conversation,
                            }
                        )
                    )
                    update_attachment_reference_index(refs_sets, ctx, conversation)
                    for record in iter_message_records(ctx, conversation):
                        message_out.write(canonical_json_bytes(record))
                        message_count += 1

                del items
                del data

        refs = finalize_attachment_reference_index(refs_sets)

        with (output_dir / "tombstones" / "tombstones.jsonl").open("wb") as tombstone_out:
            for info in sorted(zf.infolist(), key=lambda item: item.filename.encode("utf-8")):
                if info.is_dir() or is_conversation_file(info.filename):
                    continue
                with zf.open(info, "r") as handle:
                    head = handle.read(512)
                classification = classify_file(info.filename, info.file_size, head, policy)
                counts[classification.decision] += 1

                record = {
                    "path": info.filename,
                    "size_bytes": info.file_size,
                    **asdict(classification),
                }

                if classification.decision == "keep":
                    with zf.open(info, "r") as handle:
                        record["sha256"] = _copy_stream(
                            handle,
                            _safe_output_path(output_dir / "retained", info.filename),
                        )
                elif classification.decision == "extract":
                    if classification.kind != "document":
                        raise ValueError(
                            f"unsupported extract policy for {classification.kind}: {info.filename!r}"
                        )
                    limit = int(policy["documents"]["keep_original_under_bytes"])
                    if info.file_size <= limit:
                        with zf.open(info, "r") as handle:
                            record["sha256"] = _copy_stream(
                                handle,
                                _safe_output_path(output_dir / "retained", info.filename),
                            )
                        record["decision"] = "keep"
                        record["reason"] = "document_retained_pending_extractor"
                        counts["extract"] -= 1
                        counts["keep"] += 1
                    else:
                        with zf.open(info, "r") as handle:
                            object_sha = _hash_stream(handle)
                        record["sha256"] = object_sha
                        record["decision"] = "tombstone"
                        record["reason"] = "document_over_retention_limit"
                        counts["extract"] -= 1
                        counts["tombstone"] += 1
                        _write_tombstone(
                            tombstone_out,
                            info=info,
                            object_sha=object_sha,
                            classification=classification,
                            reason="document_over_retention_limit",
                            refs=refs,
                        )
                elif classification.decision == "tombstone":
                    with zf.open(info, "r") as handle:
                        object_sha = _hash_stream(handle)
                    record["sha256"] = object_sha
                    _write_tombstone(
                        tombstone_out,
                        info=info,
                        object_sha=object_sha,
                        classification=classification,
                        reason=classification.reason,
                        refs=refs,
                    )
                else:
                    with zf.open(info, "r") as handle:
                        record["sha256"] = _hash_stream(handle)

                classifications.append(record)

    (output_dir / "reports" / "classifications.json").write_bytes(
        canonical_json_bytes(classifications)
    )

    stats = {
        "protocol": "QSOL-IMPORT/STATISTICS/1",
        "source_type": "openai.export",
        "profile": policy["profile"],
        "conversations": conversation_count,
        "messages": message_count,
        "files_seen": sum(counts.values()),
        "files_retained": counts["keep"],
        "files_extracted": counts["extract"],
        "files_tombstoned": counts["tombstone"],
        "files_rejected": counts["reject"],
    }
    (output_dir / "reports" / "statistics.json").write_bytes(canonical_json_bytes(stats))

    candidate = _write_candidate_manifest(
        output_dir,
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
        "source_type": "openai.export",
        "profile": policy["profile"],
        "input_sha256": source_sha256,
        "policy_sha256": policy_sha256,
        "implementation_sha256": implementation_sha256,
        "output_sha256": output_sha256,
        "candidate_sha256": candidate["candidate_sha256"],
        **{
            key: stats[key]
            for key in (
                "conversations",
                "messages",
                "files_seen",
                "files_retained",
                "files_extracted",
                "files_tombstoned",
                "files_rejected",
            )
        },
    }
    receipt = {
        **receipt_body,
        "receipt_sha256": sha256_bytes(canonical_json_bytes(receipt_body)),
    }
    (output_dir / "IMPORT.json").write_bytes(canonical_json_bytes(receipt))

    checksums = []
    for path in sorted(p for p in output_dir.rglob("*") if p.is_file()):
        rel = path.relative_to(output_dir).as_posix()
        if rel == "SHA256SUMS":
            continue
        checksums.append(f"{sha256_file(path)}  {rel}\n")
    (output_dir / "SHA256SUMS").write_text(
        "".join(checksums),
        encoding="utf-8",
        newline="\n",
    )
    return receipt


def _remove_path(path: Path) -> None:
    if path.is_dir():
        shutil.rmtree(path)
    elif path.exists():
        path.unlink()


def _commit_output(staging_dir: Path, output_dir: Path) -> None:
    backup_dir: Path | None = None
    if output_dir.exists():
        backup_dir = Path(
            tempfile.mkdtemp(
                prefix=f".{output_dir.name}.previous-",
                dir=output_dir.parent,
            )
        )
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


def import_openai_zip(
    source_zip: Path,
    output_dir: Path,
    policy_path: Path,
) -> dict[str, Any]:
    policy, policy_raw = _load_policy(policy_path)
    policy_sha256 = sha256_bytes(policy_raw)
    package_root = Path(__file__).resolve().parent
    implementation_sha256 = package_implementation_sha256(package_root)

    output_dir.parent.mkdir(parents=True, exist_ok=True)
    staging_dir = Path(
        tempfile.mkdtemp(
            prefix=f".{output_dir.name}.import-",
            dir=output_dir.parent,
        )
    )

    try:
        with source_zip.open("rb") as source_handle:
            source_sha256 = sha256_stream(source_handle)
            source_handle.seek(0)
            receipt = _build_import(
                source_handle,
                source_sha256=source_sha256,
                output_dir=staging_dir,
                policy=policy,
                policy_sha256=policy_sha256,
                implementation_sha256=implementation_sha256,
            )
            source_handle.seek(0)
            if sha256_stream(source_handle) != source_sha256:
                raise ValueError("source ZIP changed during import")
        _commit_output(staging_dir, output_dir)
        return receipt
    except Exception:
        if staging_dir.exists():
            _remove_path(staging_dir)
        raise
