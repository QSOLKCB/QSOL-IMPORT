# Agent Instructions

## Prime directive

Keep QSOL-IMPORT small, deterministic, offline-capable, and auditable.

## Canonical-path prohibitions

Do not add any of the following to canonical import decisions:

- LLM calls;
- embeddings;
- fuzzy semantic classifiers;
- current timestamps;
- randomness;
- network availability;
- mutable remote lookups.

Optional enrichment must be explicitly non-canonical and separately receipted.

## Safety

Treat every imported archive as hostile input. Never extract a member before validating its path and archive limits. Never silently discard a source member: KEEP, EXTRACT, TOMBSTONE, or REJECT it and record the decision.

Treat QSOL-CONTEXT decisions, retention obligations, ARK observations, portable object directories, and external execution receipts as hostile inputs too. Validate exact protocols, fields, paths, hashes, sizes, authority declarations, and self-receipts before use.

## Layer ownership

QSOL-IMPORT normalizes external inputs. QSOL-CONTEXT decides canonical acceptance. QSOL-CONTROL packages approved objects. QSOL-THOTH routes semantic roles. QSOL-ARK defines recovery semantics and clean-room evaluation. Do not collapse these responsibilities.

```text
QSOL_CONTEXT_ACCEPTS != QSOL_IMPORT_ACCEPTS
CONTROL_PACK_SPEC != CONCAP_ROLE_BINDING
IMPORT_ACCEPTANCE != ROUTING
MEASUREMENT != ACCEPTANCE_AUTHORITY
```

## Evaluation

Keep byte reduction, semantic retention, style fidelity, factual accuracy, historical coverage, transport equivalence, and clean-room status separate.

Never emit one aggregate score to hide those distinctions.

```text
AGGREGATE_SCORE = FORBIDDEN
SEMANTIC_COVERAGE != FACTUAL_TRUTH
BYTE_IDENTICAL_OUTPUT != FACTUAL_TRUTH
```

## Evidence gates

Do not mark a real-export or external-model execution gate complete from synthetic fixtures.

```text
SYNTHETIC_CONFORMANCE != EXTERNALLY_EXECUTED
CLAIMED_EXECUTION != EXECUTED
PERSONAL_CONTEXT_RECONSTRUCTION != MODEL_INSTANCE_RECONSTRUCTION
```
