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

- [ ] Implement deterministic Grok export discovery.
- [ ] Reuse the common classification/tombstone contracts.
- [ ] Produce the same normalized conversation and provenance surface as the OpenAI adapter.

## Phase 3 — Generic adapter contract

- [ ] Freeze a versioned adapter interface.
- [ ] Add Claude, Gemini, GitHub, and generic JSON/JSONL adapters as independently testable modules.
- [ ] Keep vendor-specific parsing outside canonical downstream context schemas.

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
DETERMINISTIC_LABEL != AI_INTERPRETATION
NO_SILENT_DELETION
CLAIMED_EXECUTION != EXECUTED
```
