# QSOL-IMPORT Architecture

## Role

QSOL-IMPORT is the deterministic ingestion airlock between untrusted vendor exports and candidate normalized context.

```text
EXTERNAL EXPORT
      |
      v
 QSOL-IMPORT
      |
      v
NORMALIZED CANDIDATE
      |
      v
 QSOL-CONTEXT
      |
      v
 QSOL-CONTROL
      |
      v
portable CONCAP objects
      |
      v
 QSOL-THOTH
      |
      v
 QSOL-ARK evaluation
```

It does not route CONCAP roles, assert truth, make normalized input canonical, or claim model-instance reconstruction.

## Adapter boundary

Phase 3 freezes a parser boundary that keeps vendor formats out of downstream schemas.

```text
OpenAI / xAI / Anthropic / Google / GitHub / generic JSON
                         |
                         v
              vendor adapter module
                         |
                         v
             QSOL-IMPORT/ADAPTER/1
                         |
          +--------------+--------------+
          |              |              |
          v              v              v
 CONVERSATION/1      MESSAGE/1      PROVENANCE/1
          |              |              |
          +--------------+--------------+
                         |
                         v
                  candidate layer
```

Canonical adapter records contain normalized source identity, ordering, role/text/timing/link fields, hashes, and dispositions. They do **not** contain a raw vendor payload field.

```text
VENDOR_FORMAT != CANONICAL_FORMAT
VENDOR_PAYLOAD != CANONICAL_RECORD
ADAPTER_PARSE_SUCCESS != FACTUAL_ACCEPTANCE
```

Vendor-specific parsing remains under `qsol_import/adapters/`. The shared runner owns container safety, classification, tombstones, document extraction, privacy scanning, provenance, receipts, and atomic output replacement.

## Source containers

The common adapter runner accepts:

- ZIP;
- TAR / TAR.GZ;
- single JSON;
- single JSONL.

ZIP reuses the existing hostile-archive validator. TAR independently rejects traversal, backslash paths, control-character paths, duplicate/normalized collisions, links/devices/non-regular members, entry/member/total limits, and excessive archive-level compression ratio. Source bytes are read-only and re-hashed after import before output is committed.

## Current adapters

### OpenAI

`--adapter openai` remains the Phase 1 hardened implementation and is intentionally not rewritten by Phase 3.

`--adapter openai-common` is an additive projection of the same source conversation graph into `CONVERSATION/1`, `MESSAGE/1`, and `PROVENANCE/1`.

### Grok / xAI

The Grok adapter is based on the observed personal-export shape:

```text
prod-grok-backend.json
  conversations[]
    conversation
    responses[]
      response
```

It preserves visible conversation/response ids, parent/child links, message text, sender, model, timestamps, and exact file attachment ids. It does not normalize `agent_thinking_traces`.

Exact source policy:

- `prod-mc-auth-mgmt-api.json` -> REJECT;
- `prod-mc-billing.json` -> REJECT;
- `prod-mc-asset-server/**` -> TOMBSTONE bytes;
- `canvas_thumbnails/**` -> TOMBSTONE bytes.

Asset-server ids are matched exactly to normalized message attachment references when producing tombstone semantic context.

### Claude

Supports the narrow exported `conversations.json` conformance shape with conversation rows containing `chat_messages`. Unsupported shapes fail closed.

### Gemini

Supports narrowly defined conversation/entry or flat conversation-keyed JSON shapes. Export availability does not imply a stable universal JSON schema, so unknown layouts fail closed.

### GitHub

Supports GitHub migration TAR/TAR.GZ metadata resources for issue/pull-request threads and comments. Attachment payloads are tombstoned; repository Git payloads are rejected from the conversation import surface.

### Generic JSON / JSONL

Provides an explicit vendor-neutral interchange adapter. JSON accepts conversations with message arrays. JSONL requires an exact conversation/thread/chat id on each message row.

## Acceptance and CONTROL handoff

Phase 4 separates candidate production from acceptance authority.

```text
CANDIDATE.json
      |
      v
QSOL-CONTEXT/IMPORT-DECISION/1
      |
      v
QSOL-IMPORT verification and staging
      |
      v
qsol-control-restore-pack-spec/1
```

A CONTEXT decision binds to the exact candidate, exact `IMPORT.json` bytes, review-policy identity, and every artifact identity. Every artifact is explicitly accepted or rejected. Partial acceptance is supported.

QSOL-IMPORT verifies that decision and stages accepted bytes into a source tree consumable by existing QSOL-CONTROL pack machinery. A rejected candidate produces a review receipt but no pack specification.

The handoff never assigns CONCAP roles. QSOL-CONTEXT remains responsible for role-to-pack export policy after review.

```text
QSOL_CONTEXT_ACCEPTS != QSOL_IMPORT_ACCEPTS
IMPORT_DECISION != FACTUAL_AUTHORITY
CONTROL_HANDOFF != CONCAP_EXPORT_SPEC
CONTROL_PACK_SPEC != CONCAP_ROLE_BINDING
ACCEPTED_CANDIDATE != CANONICAL_CONTEXT
```

An optional THOTH route receipt can be bound during staging. Its SHA-256 must remain unchanged before and after the handoff.

```text
IMPORT_ACCEPTANCE != ROUTING
ROUTING_RECEIPT_IMMUTABLE_DURING_HANDOFF
```

## Evaluation and recovery boundary

Phase 5 measures byte reduction and semantic retention separately.

`QSOL-IMPORT/EVALUATION/1` records source, candidate, retained, normalized, extracted, tombstoned, and rejected byte counts. Semantic retention is assessed only against explicit `QSOL-IMPORT/RETENTION-OBLIGATIONS/1` input.

```text
BYTE_REDUCTION != CONTEXT_RETENTION
SEMANTIC_COVERAGE != FACTUAL_TRUTH
UNASSESSED != FAILED
AGGREGATE_SCORE = FORBIDDEN
```

The ARK clean-room evaluator consumes `QSOL-ARK/THOTH-EVALUATION-OBSERVATION/1` plus verified portable object bytes. It preserves separate route, style, factual, historical, transport, clean-room, and negative-space results.

Synthetic conformance does not claim external model execution. An externally observed run requires an explicit execution-receipt hash.

```text
PERSONAL_CONTEXT_RECONSTRUCTION != MODEL_INSTANCE_RECONSTRUCTION
RESTORED_STYLE != IDENTITY_PROOF
CLEAN_ROOM_SUCCESS != ORIGINAL_ASSISTANT_CONTINUITY
CLAIMED_EXECUTION != EXECUTED
```

## Portability boundary

The verified byte-portability boundary is:

```text
CPython >=3.11,<3.14
Linux, macOS, Windows
```

Canonical output depends on exact source, policy, implementation, and explicit contract inputs. It excludes wall clock, randomness, network, locale, absolute paths, and host identity.

`QSOL-IMPORT/PORTABILITY-RECEIPT/1` compares complete output trees by relative path, byte size, and SHA-256.

```text
BYTE_IDENTICAL_OUTPUT != FACTUAL_TRUTH
SUPPORTED_ENVIRONMENT != ALL_FUTURE_ENVIRONMENTS
IMPLEMENTATION_CHANGE != SILENT_BASELINE_REFRESH
```

## Alignment with QSOL-THOTH portable CONCAP delivery

QSOL-THOTH separates semantic routing, immutable object resolution, and transport. QSOL-IMPORT is intentionally upstream of those contracts and does not modify the frozen THOTH router.

```text
IMPORT != ROUTING
NORMALIZATION != AUTHORITY
TOMBSTONE != SOURCE_BYTES
ROUTING != RESOLUTION
RESOLUTION != TRANSPORT
TRANSPORT != AUTHORITY
```

## Determinism boundary

The canonical import path uses exact bytes, explicit policy, strict JSON parsing, stable ordering, SHA-256 receipts, and no network/LLM/embedding/random/clock dependency.

Optional semantic enrichment belongs in a non-canonical projection layer and must never replace deterministic source-derived labels.

## Trust boundary

Parsing success is not acceptance.

```text
PARSED != TRUSTED
NORMALIZED != CANONICAL
EXTRACTED != TRUE
IMPORT != FACTUAL_AUTHORITY
```

QSOL-CONTEXT remains the downstream authority for accepted canonical context.
