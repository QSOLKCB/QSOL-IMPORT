from __future__ import annotations

import hashlib
import shutil
import zipfile
from dataclasses import asdict
from pathlib import Path, PurePosixPath
from typing import Any

from qsol_import import __version__
from qsol_import.adapters.openai import (
    build_attachment_reference_index,
    context_for,
    conversation_file_sort_key,
    is_conversation_file,
    iter_message_records,
    load_conversations,
    semantic_context_for_path,
)
from qsol_import.archive import validate_archive
from qsol_import.canonical import (
    canonical_json_bytes,
    loads_strict,
    package_implementation_sha256,
    sha256_bytes,
    sha256_file,
)
from qsol_import.classify import classify_file


def _load_policy(path: Path) -> tuple[dict[str, Any], bytes]:
    raw = path.read_bytes()
    value = loads_strict(raw)
    if not isinstance(value, dict):
        raise ValueError("import policy must be a JSON object")
    return value, raw


def _copy_stream(source, destination: Path) -> str:
    destination.parent.mkdir(parents=True, exist_ok=True)
    digest = hashlib.sha256()
    with destination.open("wb") as out:
        while chunk := source.read(1024 * 1024):
            digest.update(chunk)
            out.write(chunk)
    return digest.hexdigest()


def _hash_stream(source) -> str:
    digest = hashlib.sha256()
    while chunk := source.read(1024 * 1024):
        digest.update(chunk)
    return digest.hexdigest()


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


def import_openai_zip(
    source_zip: Path,
    output_dir: Path,
    policy_path: Path,
) -> dict[str, Any]:
    policy, policy_raw = _load_policy(policy_path)
    source_sha256 = sha256_file(source_zip)
    policy_sha256 = sha256_bytes(policy_raw)
    package_root = Path(__file__).resolve().parent
    implementation_sha256 = package_implementation_sha256(package_root)

    if output_dir.exists():
        shutil.rmtree(output_dir)
    (output_dir / "conversations").mkdir(parents=True)
    (output_dir / "messages").mkdir()
    (output_dir / "tombstones").mkdir()
    (output_dir / "retained").mkdir()
    (output_dir / "reports").mkdir()

    conversations: list[tuple[Any, dict[str, Any]]] = []
    conversation_lines: list[bytes] = []
    message_lines: list[bytes] = []

    with zipfile.ZipFile(source_zip, "r") as zf:
        validate_archive(zf, policy)
        conversation_infos = [
            info
            for info in zf.infolist()
            if not info.is_dir() and is_conversation_file(info.filename)
        ]
        for info in sorted(
            conversation_infos,
            key=lambda i: conversation_file_sort_key(i.filename),
        ):
            with zf.open(info, "r") as handle:
                items = load_conversations(handle.read())
            for index, conversation in enumerate(items):
                ctx = context_for(conversation, info.filename, index)
                conversations.append((ctx, conversation))
                wrapper = {
                    "protocol": "QSOL-IMPORT/OPENAI-CONVERSATION/1",
                    "source_file": info.filename,
                    "source_index": index,
                    "conversation": conversation,
                }
                conversation_lines.append(canonical_json_bytes(wrapper))
                message_lines.extend(
                    canonical_json_bytes(record)
                    for record in iter_message_records(ctx, conversation)
                )

        refs = build_attachment_reference_index(conversations)
        classifications = []
        tombstones = []
        counts = {"keep": 0, "extract": 0, "tombstone": 0, "reject": 0}

        for info in sorted(zf.infolist(), key=lambda i: i.filename.encode("utf-8")):
            if info.is_dir() or is_conversation_file(info.filename):
                continue
            with zf.open(info, "r") as handle:
                head = handle.read(64)
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
                    tombstones.append(
                        {
                            "protocol": "QSOL-IMPORT/TOMBSTONE/1",
                            "source_vendor": "openai",
                            "original_path": info.filename,
                            "original_name": PurePosixPath(info.filename).name,
                            "sha256": object_sha,
                            "size_bytes": info.file_size,
                            "detected_type": classification.media_type,
                            "asset_class": classification.kind,
                            "decision": "omit_bytes",
                            "reason": "document_over_retention_limit",
                            "semantic_context": semantic_context_for_path(
                                info.filename,
                                classification.kind,
                                refs,
                            ),
                        }
                    )
            elif classification.decision == "tombstone":
                with zf.open(info, "r") as handle:
                    object_sha = _hash_stream(handle)
                record["sha256"] = object_sha
                tombstones.append(
                    {
                        "protocol": "QSOL-IMPORT/TOMBSTONE/1",
                        "source_vendor": "openai",
                        "original_path": info.filename,
                        "original_name": PurePosixPath(info.filename).name,
                        "sha256": object_sha,
                        "size_bytes": info.file_size,
                        "detected_type": classification.media_type,
                        "asset_class": classification.kind,
                        "decision": "omit_bytes",
                        "reason": classification.reason,
                        "semantic_context": semantic_context_for_path(
                            info.filename,
                            classification.kind,
                            refs,
                        ),
                    }
                )
            else:
                with zf.open(info, "r") as handle:
                    record["sha256"] = _hash_stream(handle)

            classifications.append(record)

    (output_dir / "conversations" / "conversations.jsonl").write_bytes(
        b"".join(conversation_lines)
    )
    (output_dir / "messages" / "messages.jsonl").write_bytes(b"".join(message_lines))
    (output_dir / "tombstones" / "tombstones.jsonl").write_bytes(
        b"".join(canonical_json_bytes(t) for t in tombstones)
    )
    (output_dir / "reports" / "classifications.json").write_bytes(
        canonical_json_bytes(classifications)
    )

    stats = {
        "protocol": "QSOL-IMPORT/STATISTICS/1",
        "source_type": "openai.export",
        "profile": policy["profile"],
        "conversations": len(conversations),
        "messages": len(message_lines),
        "files_seen": sum(counts.values()),
        "files_retained": counts["keep"],
        "files_tombstoned": counts["tombstone"] + counts["extract"],
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
    for path in sorted(
        p for p in output_dir.rglob("*") if p.is_file() and p.name != "SHA256SUMS"
    ):
        checksums.append(
            f"{sha256_file(path)}  {path.relative_to(output_dir).as_posix()}\n"
        )
    (output_dir / "SHA256SUMS").write_text(
        "".join(checksums),
        encoding="utf-8",
        newline="\n",
    )
    return receipt
