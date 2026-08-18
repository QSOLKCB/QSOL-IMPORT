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

## Layer ownership

QSOL-IMPORT normalizes external inputs. QSOL-CONTEXT decides canonical acceptance. QSOL-CONTROL packages approved objects. QSOL-THOTH routes semantic roles. Do not collapse these responsibilities.
