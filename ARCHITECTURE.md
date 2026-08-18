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
```

It does not route CONCAP roles, assert truth, or make normalized input canonical.

## Alignment with QSOL-THOTH portable CONCAP delivery

QSOL-THOTH PR #4 separates semantic routing, immutable object resolution, and transport. QSOL-IMPORT is intentionally upstream of those contracts and does not modify the frozen THOTH router.

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
```

QSOL-CONTEXT remains the downstream authority for accepted canonical context.
