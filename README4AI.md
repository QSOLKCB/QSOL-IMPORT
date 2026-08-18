# QSOL-IMPORT — AI Bootstrap

## One-line role

QSOL-IMPORT deterministically normalizes untrusted vendor exports into candidate context plus provenance-preserving tombstones for omitted bytes.

## Hard boundaries

Do not reinterpret QSOL-IMPORT as:

- a factual authority;
- a CONCAP router;
- a replacement for QSOL-CONTEXT;
- a transport layer;
- an LLM summarizer;
- a backup system that promises verbatim recovery.

Canonical invariants:

```text
SOURCE != NORMALIZED_OUTPUT
PARSED != TRUSTED
NORMALIZED != CANONICAL
SEMANTIC_PRESERVATION != BYTE_PRESERVATION
OMITTED_BYTES != OMITTED_MEANING
TOMBSTONE != SOURCE_OBJECT
IMPORT != FACTUAL_AUTHORITY
IMPORT != ROUTING
ROUTING != RESOLUTION
RESOLUTION != TRANSPORT
TRANSPORT != AUTHORITY
CLAIMED_EXECUTION != EXECUTED
```

## Current implementation

- Python stdlib only.
- OpenAI ZIP adapter first.
- Discovers `conversations.json` and deterministic numbered variants without depending on one complete vendor directory layout.
- Preserves message graph source order, node ids, parent/child links, source message ids, and original message objects.
- Resolves attachment context only through exact deterministic keys: exact basename and exact `file-*` / `asset-*` identifiers. No fuzzy matching is allowed on the canonical path.
- Detects common media from magic bytes before extension fallback.
- Tombstones audio/video by default.
- Keeps small images and structured text according to explicit policy.
- Supports frozen deterministic DOCX body-text extraction as `QSOL-IMPORT/DOCX-BODY-TEXT/1`; PDF and other document formats remain retained/tombstoned unless a separately frozen parser contract exists.
- Validates the DOCX inner ZIP independently, including traversal, symlink, encryption, duplicate member, size, total-size, and compression-ratio guards; DTD/entity XML is rejected.
- Supports optional exact-path, top-level-field allow-listed account metadata extraction as `QSOL-IMPORT/OPENAI-ACCOUNT-METADATA/1`. The bundled policy keeps this disabled with an empty allowlist.
- Emits `QSOL-IMPORT/PRIVACY-SCAN/1` over normalized conversations/messages, extracted text, allow-listed account metadata, and retained structured text. Match values are never copied into the report; only SHA-256 match receipts are emitted.
- Rejects executables and nested archives in the bootstrap.
- Rejects ZIP traversal, symlinks, duplicate members, normalized collisions, control-character paths, oversize members, excessive compression ratios, and excessive archive totals.
- Emits `IMPORT.json`, `CANDIDATE.json`, canonical JSONL conversation/message/tombstone records, classification/statistics/privacy reports, retained files, deterministic extracted text, and `SHA256SUMS`.

## Real-snapshot validation

`python -m qsol_import.validation export-old.zip export-new.zip --output validation.json`

The validation harness requires at least two snapshots. Each snapshot is imported twice and the complete emitted trees are compared. The validation receipt contains source hashes and import statistics but does not emit source paths or persist source export bytes.

Synthetic fixtures do **not** satisfy the roadmap claim "validated against multiple real personal ChatGPT export snapshots". That checkbox may only be closed after actual local snapshots are run.

## Optional account metadata policy

Enable account metadata only with exact source paths and exact top-level fields, for example:

```json
{
  "account_metadata": {
    "enabled": true,
    "max_member_bytes": 1048576,
    "allowlist": [
      {
        "path": "user.json",
        "fields": ["id", "email"]
      }
    ]
  }
}
```

Do not infer metadata filenames, field aliases, or nested paths. Unknown paths remain subject to normal file classification.

## THOTH relationship

QSOL-IMPORT sits upstream of QSOL-CONTEXT. QSOL-CONTEXT decides acceptance/export policy. QSOL-CONTROL packages approved immutable objects. QSOL-THOTH remains the deterministic semantic router and should never inspect raw vendor exports merely to route context.
