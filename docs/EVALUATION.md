# QSOL-IMPORT Evaluation

## Measurement model

QSOL-IMPORT keeps byte reduction, semantic retention, reconstruction observations, and factual authority separate.

```text
BYTE_REDUCTION != CONTEXT_RETENTION
SEMANTIC_COVERAGE != FACTUAL_TRUTH
TOMBSTONED_BYTES != RESTORED_BYTES
MEASUREMENT != ACCEPTANCE_AUTHORITY
AGGREGATE_SCORE = FORBIDDEN
```

The tooling emits deterministic receipts. It does not decide whether a claim is true or whether a candidate belongs in QSOL-CONTEXT.

## Candidate and source binding

Evaluation starts by verifying the complete candidate tree:

- `CANDIDATE.json` self-receipt;
- `IMPORT.json` exact fields, counters, and self-receipt;
- recomputed `output_sha256`;
- every candidate artifact path, size, and SHA-256;
- the exact candidate file set, with no unlisted side inputs;
- the source export SHA-256 against `candidate.input_sha256`.

An unrelated archive cannot be combined with an existing candidate to manufacture misleading reduction metrics.

```text
EVALUATED_SOURCE != CALLER_SELECTED_LOOKALIKE
UNLISTED_OUTPUT_FILE != CANDIDATE_ARTIFACT
```

## Byte and semantic-retention report

```bash
python -m qsol_import.evaluation \
  /path/to/source-export.zip \
  /path/to/import-output \
  --obligations /path/to/retention-obligations.json \
  --output /path/to/evaluation.json
```

The resulting `QSOL-IMPORT/EVALUATION/1` receipt records:

- source archive bytes;
- validated uncompressed source-member bytes;
- emitted candidate artifact bytes;
- verbatim retained bytes;
- normalized conversation and message bytes;
- extracted document-text bytes;
- tombstoned source bytes;
- rejected source bytes;
- archive-to-candidate byte reduction;
- source-member-to-verbatim-carried reduction.

Classification sizes must be non-negative integers, classification paths must be unique and canonical, and classification disposition counts must reproduce the counters in `IMPORT.json`.

These numbers remain separate. A compact candidate is not automatically useful, and a large candidate is not automatically faithful.

## Retention obligations

Semantic retention is assessed only against explicit, receipted `QSOL-IMPORT/RETENTION-OBLIGATIONS/1` input.

```json
{
  "protocol": "QSOL-IMPORT/RETENTION-OBLIGATIONS/1",
  "schema_version": "1.0.0",
  "authority": "measurement-obligations-only",
  "required_conversation_ids": ["conversation-1"],
  "required_message_ids": ["message-1"],
  "required_attachment_refs": ["asset-123456"],
  "forbidden_text_fragments": ["private phrase that must not survive"],
  "boundaries": [
    "ABSENT_OBLIGATION != ABSENT_CONTEXT",
    "OBLIGATION_SET != SOURCE_EVIDENCE",
    "RETENTION_OBLIGATION != FACTUAL_AUTHORITY"
  ],
  "obligations_sha256": "<sha256 of canonical object without obligations_sha256>"
}
```

The identifier and boundary lists must be UTF-8 sorted and duplicate-free. The self-receipt is recomputed before the obligations influence any result.

The evaluator reports covered and missing obligations for each dimension. An absent obligations file is `unassessed`. A present but empty obligation set is also `unassessed`, not a synthetic success.

```text
UNASSESSED != FAILED
UNASSESSED != PASSED
```

Forbidden fragments are searched in bounded overlapping byte windows across every verified candidate artifact, including retained structured text and extracted documents. A fragment cannot hide merely by moving outside conversation JSONL.

## ARK clean-room evaluation

QSOL-IMPORT can verify an observation compatible with the public THOTH evaluation contract and the QSOL-ARK personal-continuity recovery contract.

```bash
python -m qsol_import.ark_cleanroom \
  /path/to/observation.json \
  /path/to/portable-objects \
  --ark-trial P1 \
  --record-class synthetic-conformance \
  --output /path/to/ark-cleanroom-receipt.json
```

The evaluator checks:

- separate route sufficiency and route minimality;
- style-fidelity observations;
- factual-accuracy observations;
- historical-reconstruction coverage observations;
- a non-empty observation trial identifier;
- clean-room declarations;
- exact object identities and byte sizes;
- exact equality between the declared object inventory and the object-root inventory;
- transport equivalence across local directory, archive, static HTTP, and capability relay profiles;
- negative-space checks for style leakage, unsupported interpolation, and private-source dependency.

Extra files, directory symlinks, duplicate object identities, or missing objects fail closed. No aggregate score is emitted. Unverified claims do not become incorrect merely because they were not assessed.

## Synthetic and externally observed records

`synthetic-conformance` verifies public machinery and fixtures. It sets:

```text
model_execution_claimed = false
execution_receipt_sha256 = null
t5_ai_reconstruction_implemented = false
```

An externally observed clean-room run must supply a complete receipt file:

```bash
python -m qsol_import.ark_cleanroom \
  /path/to/observation.json \
  /path/to/portable-objects \
  --ark-trial P2 \
  --record-class externally-observed-clean-room \
  --execution-receipt /path/to/EXTERNAL-EXECUTION.json \
  --output /path/to/ark-clean-room-receipt.json
```

The `QSOL-IMPORT/EXTERNAL-EXECUTION-RECEIPT/1` file must contain:

- the exact observation SHA-256;
- the exact ARK trial ID;
- authority `external-execution-observation-only`;
- record class `externally-observed-clean-room`;
- bounded execution, executor, and environment identifiers;
- outcome `completed`;
- required epistemic boundaries;
- a valid canonical self-receipt.

QSOL-IMPORT validates the receipt bytes and records their file SHA-256. A caller-provided hexadecimal string is not execution evidence.

```text
RECEIPT_HASH != RECEIPT_VERIFICATION
PERSONAL_CONTEXT_RECONSTRUCTION != MODEL_INSTANCE_RECONSTRUCTION
RESTORED_STYLE != IDENTITY_PROOF
CLEAN_ROOM_SUCCESS != ORIGINAL_ASSISTANT_CONTINUITY
CLAIMED_EXECUTION != EXECUTED
```

## Current evidence status

The repository includes deterministic synthetic conformance coverage. It does not claim that a fresh external model session was executed by those tests. Real clean-room observations may be supplied later with a complete, verified external execution receipt.
