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
- declared uncompressed source-member bytes;
- emitted candidate artifact bytes;
- verbatim retained bytes;
- normalized conversation and message bytes;
- extracted document-text bytes;
- tombstoned source bytes;
- rejected source bytes;
- archive-to-candidate byte reduction;
- source-member-to-verbatim-carried reduction.

These numbers are kept as separate fields. A compact candidate is not automatically a useful candidate, and a large candidate is not automatically a faithful one.

## Retention obligations

Semantic retention is assessed only against explicit `QSOL-IMPORT/RETENTION-OBLIGATIONS/1` input.

```json
{
  "protocol": "QSOL-IMPORT/RETENTION-OBLIGATIONS/1",
  "schema_version": "1.0.0",
  "required_conversation_ids": ["conversation-1"],
  "required_message_ids": ["message-1"],
  "required_attachment_refs": ["asset-123456"],
  "forbidden_text_fragments": ["private phrase that must not survive"],
  "boundaries": [
    "SEMANTIC_COVERAGE != FACTUAL_TRUTH"
  ]
}
```

The lists must be UTF-8 sorted and duplicate-free. The evaluator reports covered and missing obligations for each dimension. If no obligation file is supplied, semantic retention is `unassessed`, not failed and not passed.

```text
UNASSESSED != FAILED
UNASSESSED != PASSED
```

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
- clean-room declarations;
- exact object identities and byte sizes;
- transport equivalence across local directory, archive, static HTTP, and capability relay profiles;
- negative-space checks for style leakage, unsupported interpolation, and private-source dependency.

No aggregate score is emitted. Unverified claims do not become incorrect merely because they were not assessed.

## Synthetic and externally observed records

`synthetic-conformance` verifies the public machinery and fixtures. It sets:

```text
model_execution_claimed = false
t5_ai_reconstruction_implemented = false
```

An externally observed clean-room run must use:

```bash
--record-class externally-observed-clean-room \
--execution-receipt-sha256 <64-lowercase-hex>
```

That receipt hash binds the observation to an external execution record. It still does not prove model identity, hidden provider memory, or factual truth.

```text
PERSONAL_CONTEXT_RECONSTRUCTION != MODEL_INSTANCE_RECONSTRUCTION
RESTORED_STYLE != IDENTITY_PROOF
CLEAN_ROOM_SUCCESS != ORIGINAL_ASSISTANT_CONTINUITY
CLAIMED_EXECUTION != EXECUTED
```

## Current evidence status

The repository includes deterministic synthetic conformance coverage. It does not claim that a fresh external model session was executed by these tests. Real clean-room observations may be supplied later with explicit external execution receipts.
