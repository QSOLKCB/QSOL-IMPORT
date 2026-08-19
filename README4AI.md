# QSOL-IMPORT - AI Bootstrap

## One-line role

QSOL-IMPORT deterministically normalizes untrusted vendor exports into candidate context plus provenance-preserving tombstones for omitted bytes.

## Hard boundaries

Do not reinterpret QSOL-IMPORT as:

- a factual authority;
- a CONCAP router;
- a replacement for QSOL-CONTEXT;
- a transport layer;
- an LLM summarizer;
- a backup system that promises verbatim recovery;
- a model-instance reconstruction system.

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
PERSONAL_CONTEXT_RECONSTRUCTION != MODEL_INSTANCE_RECONSTRUCTION
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

## QSOL-CONTEXT acceptance handoff

QSOL-CONTEXT is the acceptance authority. QSOL-IMPORT verifies and stages its exact decision receipt.

```bash
python -m qsol_import.handoff verify \
  /path/to/import-output \
  /path/to/CONTEXT-DECISION.json

python -m qsol_import.handoff stage \
  /path/to/import-output \
  /path/to/CONTEXT-DECISION.json \
  --output /path/to/control-handoff \
  --privacy-class RESTRICTED \
  --recovery-class OUTER_SHELL
```

Contracts:

```text
QSOL-CONTEXT/IMPORT-DECISION/1
QSOL-IMPORT/CONTROL-HANDOFF/1
qsol-control-restore-pack-spec/1
```

The CONTEXT decision must cover every candidate artifact exactly once. Partial acceptance is valid. A rejected candidate yields a review receipt but no CONTROL pack specification.

The handoff assigns no CONCAP roles. A caller may bind a THOTH route receipt so its SHA-256 is proven unchanged during staging.

```text
QSOL_CONTEXT_ACCEPTS != QSOL_IMPORT_ACCEPTS
CONTROL_HANDOFF != CONCAP_EXPORT_SPEC
CONTROL_PACK_SPEC != CONCAP_ROLE_BINDING
IMPORT_ACCEPTANCE != ROUTING
```

## Retention evaluation

```bash
python -m qsol_import.evaluation \
  /path/to/source.zip \
  /path/to/import-output \
  --obligations /path/to/retention-obligations.json \
  --output /path/to/evaluation.json
```

Contracts:

```text
QSOL-IMPORT/RETENTION-OBLIGATIONS/1
QSOL-IMPORT/EVALUATION/1
```

The evaluator keeps byte reduction, conversation retention, message retention, attachment-reference retention, and negative-space findings separate. It emits no aggregate score. Without an obligation file, semantic retention is `unassessed`.

```text
BYTE_REDUCTION != CONTEXT_RETENTION
SEMANTIC_COVERAGE != FACTUAL_TRUTH
UNASSESSED != FAILED
AGGREGATE_SCORE = FORBIDDEN
```

## ARK clean-room evaluation

```bash
python -m qsol_import.ark_cleanroom \
  /path/to/observation.json \
  /path/to/portable-objects \
  --ark-trial P1 \
  --record-class synthetic-conformance \
  --output /path/to/ark-receipt.json
```

The evaluator verifies the public THOTH observation shape, QSOL-ARK P0-P3 trial identity, clean-room declarations, exact portable object bytes, four transport profiles, five separate measurement dimensions, and negative-space checks.

Synthetic conformance sets `model_execution_claimed: false` and `t5_ai_reconstruction_implemented: false`. An externally observed run requires an explicit external execution receipt hash.

## Portability boundary

Verified runtime boundary:

```text
CPython >=3.11,<3.14
Linux, macOS, Windows
```

Compare complete output trees with:

```bash
python -m qsol_import.portability /path/to/run-a /path/to/run-b
```

The resulting `QSOL-IMPORT/PORTABILITY-RECEIPT/1` proves byte equality only. It grants no truth authority.

## Phase 1 OpenAI hardening retained

- Discovers `conversations.json` and deterministic numbered variants.
- Preserves graph source order, node ids, parent/child links, source message ids, and original message objects on the legacy OpenAI surface.
- Resolves attachment context only through exact deterministic keys.
- Supports frozen deterministic DOCX body-text extraction as `QSOL-IMPORT/DOCX-BODY-TEXT/1`.
- Supports optional exact-path, top-level-field allow-listed account metadata extraction, disabled by default.
- Emits `QSOL-IMPORT/PRIVACY-SCAN/1`; match values are never copied into the report, only SHA-256 match receipts.

## Real OpenAI snapshot validation

```bash
python -m qsol_import.validation \
  export-old.zip \
  export-new.zip \
  --output validation.json
```

The validation harness requires at least two byte-distinct snapshots, imports each twice, and compares complete emitted trees.

This remains an external evidence gate. Synthetic fixtures do not satisfy the claim "validated against multiple real personal ChatGPT export snapshots".

## THOTH relationship

QSOL-IMPORT sits upstream of QSOL-CONTEXT. QSOL-CONTEXT decides acceptance/export policy. QSOL-CONTROL packages approved immutable objects. QSOL-THOTH remains the deterministic semantic router. QSOL-ARK owns recovery semantics and clean-room evaluation.
