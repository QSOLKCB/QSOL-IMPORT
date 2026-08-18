# QSOL-IMPORT Roadmap

## Phase 0 — Bootstrap

- [x] Define the ingestion-airlock architecture and trust boundaries.
- [x] Add deterministic canonical JSON and SHA-256 helpers.
- [x] Add explicit `conversation-first/1` import policy.
- [x] Add file signature + extension classification.
- [x] Add semantic tombstones for omitted media bytes.
- [x] Add strict ZIP path/symlink/size/compression guards.
- [x] Add OpenAI conversation JSON discovery and canonical JSONL output.
- [x] Add deterministic import receipt and checksums.
- [x] Add tests and CI.
- [x] Document the upstream relationship to QSOL-THOTH portable CONCAP delivery.

## Phase 1 — OpenAI adapter hardening

- [ ] Validate against multiple real personal ChatGPT export snapshots.
- [x] Add a deterministic local multi-snapshot validation harness that does not persist source export bytes or emit source paths.
- [x] Add fixture-derived support for numbered conversation file naming variants.
- [x] Normalize message graph records while retaining source identifiers and source ordering.
- [x] Resolve more attachment references through exact basenames and exact file/asset identifiers without fuzzy matching.
- [x] Add deterministic document text extraction only where a parser contract can be frozen and tested (`QSOL-IMPORT/DOCX-BODY-TEXT/1`).
- [x] Add optional exact-path, exact-field allow-listed account metadata import, disabled by default.
- [x] Add privacy/secret scanner with deterministic rule receipts and hashed rather than raw matches.
- [x] Reject duplicate ZIP member names and non-canonical backslash paths before materialization.

The remaining real-snapshot checkbox is evidence-gated: synthetic fixtures and unit tests do not satisfy it. Run at least two real local ChatGPT export snapshots through `python -m qsol_import.validation ...` and retain the resulting `QSOL-IMPORT/OPENAI-SNAPSHOT-VALIDATION/1` receipt before marking it complete.

## Phase 2 — Grok/xAI adapter

- [x] Implement deterministic Grok export discovery from exactly one `prod-grok-backend.json` at any safe archive depth.
- [x] Reuse the common classification/tombstone contracts, including exact asset-id semantic context and no binary asset copying for xAI asset-server/thumbnail paths.
- [x] Produce the vendor-neutral `QSOL-IMPORT/CONVERSATION/1`, `QSOL-IMPORT/MESSAGE/1`, and `QSOL-IMPORT/PROVENANCE/1` surface while preserving source ids/order and excluding agent thinking traces.

Phase 2 is fixture-derived from the observed xAI/Grok personal export shape. Authentication and billing sources are exact-basename rejects; `prod-mc-asset-server/**` and `canvas_thumbnails/**` use the common tombstone contract.

## Phase 3 — Generic adapter contract

- [x] Freeze `QSOL-IMPORT/ADAPTER/1` with vendor-neutral conversation, message, and provenance schemas.
- [x] Add Claude, Gemini, GitHub migration, and generic JSON/JSONL adapters as independently testable modules.
- [x] Keep vendor-specific parsing outside canonical downstream context schemas; raw vendor objects are prohibited from canonical records.
- [x] Add a non-breaking `openai-common` projection so Phase 1 OpenAI exports can be rendered into the same Phase 3 contract without changing the existing `openai` CLI behavior.
- [x] Support guarded ZIP, TAR/TAR.GZ, JSON, and JSONL source containers for the common adapter runner.

Claude and Gemini adapters intentionally support narrow conformance shapes and fail closed on unrecognized layouts. A module being implemented is not a claim that every future vendor export revision has been validated.

## Phase 4 — QSOL-CONTEXT handoff

- [x] Define an explicit import-candidate manifest consumable by QSOL-CONTEXT review/export policy.
- [ ] Add deterministic acceptance/rejection receipt handoff without granting QSOL-IMPORT factual authority.
- [ ] Ensure candidate records can flow into QSOL-CONTROL portable bundle generation without changing THOTH routing receipts.

`QSOL-IMPORT/CANDIDATE-MANIFEST/1` is intentionally candidate-only and assigns no CONCAP roles. QSOL-CONTEXT remains the canonical acceptance/export-policy layer, and its `restore/CONCAP-EXPORT.spec.json` remains responsible for mapping approved pack specs to CONCAP roles.

## Phase 5 — Evaluation

- [ ] Measure context retention versus byte reduction.
- [ ] Add adversarial archives, malformed JSON, disguised-media, duplicate-member, and decompression-bomb fixtures.
- [ ] Verify repeated runs are byte-identical across supported Python versions/platforms or document the exact portability boundary.
- [ ] Add clean-room reconstruction tests through QSOL-ARK.

## Long-term invariants

```text
SOURCE != NORMALIZED_OUTPUT
PARSED != TRUSTED
NORMALIZED != CANONICAL
EXTRACTED != TRUE
SEMANTIC_PRESERVATION != BYTE_PRESERVATION
OMITTED_BYTES != OMITTED_MEANING
TOMBSTONE != SOURCE_OBJECT
IMPORT != FACTUAL_AUTHORITY
IMPORT != ROUTING
CANDIDATE_MANIFEST != CONCAP_EXPORT_SPEC
ROUTING != RESOLUTION
RESOLUTION != TRANSPORT
TRANSPORT != AUTHORITY
VENDOR_FORMAT != CANONICAL_FORMAT
VENDOR_PAYLOAD != CANONICAL_RECORD
DETERMINISTIC_LABEL != AI_INTERPRETATION
NO_SILENT_DELETION
CLAIMED_EXECUTION != EXECUTED
```
