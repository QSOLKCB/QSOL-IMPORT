# QSOL-IMPORT Roadmap

**Engineering status:** complete as of 2026-08-19.

All repository-owned implementation phases are complete. One operator-owned evidence gate remains open because this repository and working session do not contain two real personal ChatGPT export snapshots. Synthetic fixtures are not promoted into real-export evidence.

## Phase 0 - Bootstrap

- [x] Define the ingestion-airlock architecture and trust boundaries.
- [x] Add deterministic canonical JSON and SHA-256 helpers.
- [x] Add explicit `conversation-first/1` import policy.
- [x] Add file signature plus extension classification.
- [x] Add semantic tombstones for omitted media bytes.
- [x] Add strict ZIP path, symlink, size, total-size, and compression guards.
- [x] Add OpenAI conversation JSON discovery and canonical JSONL output.
- [x] Add deterministic import receipts and checksums.
- [x] Add tests and CI.
- [x] Document the upstream relationship to QSOL-THOTH portable CONCAP delivery.

## Phase 1 - OpenAI adapter hardening

- [x] Add a deterministic local multi-snapshot validation harness that does not persist source export bytes or emit source paths.
- [x] Require two or more byte-distinct snapshots before emitting `QSOL-IMPORT/OPENAI-SNAPSHOT-VALIDATION/1`.
- [x] Add fixture-derived support for numbered conversation file naming variants.
- [x] Normalize message graph records while retaining source identifiers and source ordering.
- [x] Resolve attachment references through exact basenames and exact file or asset identifiers without fuzzy matching.
- [x] Add deterministic document text extraction only where a parser contract can be frozen and tested (`QSOL-IMPORT/DOCX-BODY-TEXT/1`).
- [x] Add optional exact-path, exact-field allow-listed account metadata import, disabled by default.
- [x] Add privacy and secret scanning with deterministic rule receipts and hashed rather than raw matches.
- [x] Reject duplicate ZIP member names and non-canonical backslash paths before materialization.
- [x] Bound privacy scanning, DOCX extraction, inner archives, XML parsing, and TAR processing against hostile inputs.

## Phase 2 - Grok/xAI adapter

- [x] Implement deterministic Grok export discovery from exactly one `prod-grok-backend.json` at any safe archive depth.
- [x] Reuse the common classification and tombstone contracts, including exact asset-id semantic context and no binary asset copying for xAI asset-server or thumbnail paths.
- [x] Produce the vendor-neutral `QSOL-IMPORT/CONVERSATION/1`, `QSOL-IMPORT/MESSAGE/1`, and `QSOL-IMPORT/PROVENANCE/1` surface while preserving source identities and ordering.
- [x] Exclude `agent_thinking_traces` from normalized messages.
- [x] Reject exact xAI authentication and billing source files from candidate content.

Phase 2 is fixture-derived from an observed xAI/Grok personal export structure. Adapter conformance does not claim support for every future xAI export revision.

## Phase 3 - Generic adapter contract

- [x] Freeze `QSOL-IMPORT/ADAPTER/1` with vendor-neutral conversation, message, and provenance schemas.
- [x] Add Claude, Gemini, GitHub migration, and generic JSON/JSONL adapters as independently testable modules.
- [x] Keep vendor-specific parsing outside canonical downstream context schemas.
- [x] Prohibit raw vendor payload fields and extra properties in canonical records.
- [x] Validate complete required canonical record shapes before writing JSONL.
- [x] Add a non-breaking `openai-common` projection without changing the existing `openai` CLI behavior.
- [x] Support guarded ZIP, TAR/TAR.GZ, JSON, and JSONL source containers.
- [x] Preserve exact OpenAI attachment provenance in common records and tombstone context.
- [x] Resolve GitHub inline review comments through exact review-to-pull-request relationships.

Claude and Gemini adapters intentionally support narrow conformance shapes and fail closed on unrecognized layouts. An implemented module is not evidence that every historical or future vendor export revision has been validated.

## Phase 4 - QSOL-CONTEXT handoff

- [x] Define an explicit candidate manifest consumable by QSOL-CONTEXT review policy.
- [x] Define `QSOL-CONTEXT/IMPORT-DECISION/1` for exact accepted, rejected, or partially accepted artifact dispositions.
- [x] Verify candidate, import receipt, artifact, review-policy, and decision identities before staging.
- [x] Require every candidate artifact to be decided exactly once.
- [x] Preserve QSOL-CONTEXT as acceptance authority and prohibit CONCAP-role assignment in import decisions.
- [x] Emit `QSOL-IMPORT/CONTROL-HANDOFF/1` with deterministic accepted and rejected summaries.
- [x] Stage accepted candidate artifacts into a `qsol-control-restore-pack-spec/1` source tree.
- [x] Emit no CONTROL pack specification for a fully rejected candidate.
- [x] Verify optional THOTH route-receipt bytes remain unchanged throughout handoff staging.
- [x] Document the separation between candidate acceptance, CONTROL packing, CONTEXT export policy, and THOTH routing.

```text
QSOL_CONTEXT_ACCEPTS != QSOL_IMPORT_ACCEPTS
IMPORT_DECISION != FACTUAL_AUTHORITY
CONTROL_PACK_SPEC != CONCAP_ROLE_BINDING
CANDIDATE_MANIFEST != CONCAP_EXPORT_SPEC
IMPORT_ACCEPTANCE != ROUTING
```

## Phase 5 - Evaluation

- [x] Measure source archive bytes, source member bytes, candidate bytes, retained bytes, normalized bytes, extracted text, tombstoned bytes, and rejected bytes.
- [x] Define explicit conversation, message, attachment-reference, and negative-space retention obligations.
- [x] Keep byte reduction, semantic retention, and factual authority separate.
- [x] Emit `unassessed` rather than pass or fail when semantic obligations are absent.
- [x] Add a declared adversarial fixture matrix covering malformed JSON, duplicate JSON members, non-finite values, disguised media, duplicate ZIP members, normalized collisions, decompression bombs, TAR links, and traversal.
- [x] Add complete-tree byte comparison receipts.
- [x] Document and test the portability boundary for CPython 3.11 through 3.13 on Linux, macOS, and Windows.
- [x] Add QSOL-ARK and THOTH clean-room conformance receipts with separate route, style, factual, historical, transport, and negative-space dimensions.
- [x] Verify portable object identities across local-directory, archive, static-HTTP, and capability-relay transport profiles.
- [x] Require an explicit execution-receipt hash before classifying a clean-room observation as externally executed.
- [x] Preserve `t5_ai_reconstruction_implemented: false` until an actual AI reconstruction implementation and execution evidence exist.
- [x] Forbid aggregate evaluation scores.

```text
BYTE_REDUCTION != CONTEXT_RETENTION
SEMANTIC_COVERAGE != FACTUAL_TRUTH
PERSONAL_CONTEXT_RECONSTRUCTION != MODEL_INSTANCE_RECONSTRUCTION
CLEAN_ROOM_SUCCESS != ORIGINAL_ASSISTANT_CONTINUITY
AGGREGATE_SCORE = FORBIDDEN
```

## External evidence gate

This is not unfinished repository engineering.

- [ ] Run the validation harness against at least two byte-distinct real personal ChatGPT export snapshots and retain the resulting `QSOL-IMPORT/OPENAI-SNAPSHOT-VALIDATION/1` receipt.

Command:

```bash
python -m qsol_import.validation \
  export-old.zip \
  export-new.zip \
  --output validation.json
```

The checkbox must remain open until the real source snapshots are actually supplied and the receipt is produced. Synthetic exports, renamed copies, and byte-identical copies do not satisfy the gate.

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
BYTE_IDENTICAL_OUTPUT != FACTUAL_TRUTH
SUPPORTED_ENVIRONMENT != ALL_FUTURE_ENVIRONMENTS
PERSONAL_CONTEXT_RECONSTRUCTION != MODEL_INSTANCE_RECONSTRUCTION
NO_SILENT_DELETION
CLAIMED_EXECUTION != EXECUTED
```
