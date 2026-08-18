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
VENDOR_FORMAT != CANONICAL_FORMAT
VENDOR_PAYLOAD != CANONICAL_RECORD
CLAIMED_EXECUTION != EXECUTED
```

## Frozen adapter surface

Phase 3 defines:

```text
QSOL-IMPORT/ADAPTER/1
QSOL-IMPORT/CONVERSATION/1
QSOL-IMPORT/MESSAGE/1
QSOL-IMPORT/PROVENANCE/1
```

Vendor parsers live under `qsol_import/adapters/`. They may inspect vendor-specific structures, but canonical conversation/message/provenance records must not contain raw vendor objects.

The common runner owns source-container validation, file classification, tombstones, frozen document extraction, privacy scanning, provenance receipts, candidate manifests, checksums, and atomic output commit.

## CLI adapters

```bash
qsol-import export.zip --adapter openai --output out
qsol-import export.zip --adapter openai-common --output out-common
qsol-import grok_data.zip --adapter grok --output grok-out
qsol-import claude-export.zip --adapter claude --output claude-out
qsol-import gemini.json --adapter gemini --output gemini-out
qsol-import github-migration.tar.gz --adapter github --output github-out
qsol-import conversations.jsonl --adapter generic --output generic-out
```

`openai` remains the Phase 1 hardened implementation. `openai-common` is additive and projects the same source graph through the frozen Phase 3 vendor-neutral contracts.

## Grok / xAI adapter

Deterministic discovery requires exactly one archive member whose basename is `prod-grok-backend.json`.

Observed source shape:

```text
conversations[]
  conversation
  responses[]
    response
```

The adapter preserves visible source conversation/response ids, parent-child links, sender, message text, timestamps, model, partial status, and exact `file_attachments`. It does not normalize `agent_thinking_traces`.

Hard source dispositions:

- `prod-mc-auth-mgmt-api.json` -> REJECT;
- `prod-mc-billing.json` -> REJECT;
- `prod-mc-asset-server/**` -> TOMBSTONE;
- `canvas_thumbnails/**` -> TOMBSTONE.

Asset-server identifiers are matched exactly to normalized message attachment references for tombstone semantic context.

## Claude / Gemini / GitHub / generic

- Claude supports a narrow `conversations.json` shape containing `chat_messages`.
- Gemini supports a narrow conversation/entry shape or a flat conversation-keyed array.
- GitHub supports migration TAR/TAR.GZ metadata resources for issue/pull-request thread material; attachment payloads are tombstoned and repository Git payloads are rejected from this conversation surface.
- Generic JSON accepts conversations with message arrays; generic JSONL requires an exact conversation/thread/chat id per row.

Unknown layouts fail closed. Adapter existence is not evidence that every historical or future vendor export revision has been validated.

## Source-container boundary

The common runner accepts ZIP, TAR/TAR.GZ, JSON, and JSONL.

It rejects traversal, non-canonical backslash paths, control-character paths, duplicate/normalized collisions, links/devices/non-regular TAR members, oversized members/totals, and excessive compression ratios. Source bytes are never modified and are re-hashed before output commit.

## Phase 1 OpenAI hardening retained

- Discovers `conversations.json` and deterministic numbered variants.
- Preserves graph source order, node ids, parent/child links, source message ids, and original message objects on the legacy OpenAI surface.
- Resolves attachment context only through exact deterministic keys.
- Supports frozen deterministic DOCX body-text extraction as `QSOL-IMPORT/DOCX-BODY-TEXT/1`.
- Supports optional exact-path, top-level-field allow-listed account metadata extraction, disabled by default.
- Emits `QSOL-IMPORT/PRIVACY-SCAN/1`; match values are never copied into the report, only SHA-256 match receipts.

## Real OpenAI snapshot validation

`python -m qsol_import.validation export-old.zip export-new.zip --output validation.json`

The validation harness requires at least two byte-distinct snapshots, imports each twice, and compares complete emitted trees. Synthetic fixtures do **not** satisfy the roadmap claim "validated against multiple real personal ChatGPT export snapshots".

## THOTH relationship

QSOL-IMPORT sits upstream of QSOL-CONTEXT. QSOL-CONTEXT decides acceptance/export policy. QSOL-CONTROL packages approved immutable objects. QSOL-THOTH remains the deterministic semantic router and should never inspect raw vendor exports merely to route context.
