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
IMPORT != ROUTING
ROUTING != RESOLUTION
RESOLUTION != TRANSPORT
TRANSPORT != AUTHORITY
```

## Current implementation

- Python stdlib only.
- OpenAI ZIP adapter first.
- Discovers `conversations.json` and numbered conversation JSON variants instead of depending on one full directory layout.
- Rejects duplicate JSON object members.
- Detects common media from magic bytes before extension fallback.
- Tombstones audio/video by default.
- Keeps small images and structured text according to explicit policy.
- Rejects executables and nested archives in the bootstrap.
- Rejects ZIP traversal, symlinks, oversize members, excessive compression ratios, and excessive archive totals.
- Emits `IMPORT.json`, canonical JSONL conversation/tombstone records, classification/statistics reports, retained files, and `SHA256SUMS`.

## THOTH relationship

QSOL-IMPORT sits upstream of QSOL-CONTEXT. THOTH remains the deterministic semantic router and should never inspect raw vendor exports merely to route context.
