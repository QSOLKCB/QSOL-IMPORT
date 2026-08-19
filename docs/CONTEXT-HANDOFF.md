# QSOL-CONTEXT Acceptance Handoff

## Purpose

QSOL-IMPORT produces candidate evidence. QSOL-CONTEXT decides whether candidate artifacts may enter its reviewed authoring and export process.

```text
untrusted vendor export
        |
        v
QSOL-IMPORT/CANDIDATE-MANIFEST/1
        |
        v
QSOL-CONTEXT/IMPORT-DECISION/1
        |
        v
QSOL-IMPORT verification and staging
        |
        v
qsol-control-restore-pack-spec/1
        |
        v
QSOL-CONTROL pack and verify
        |
        v
QSOL-CONTEXT CONCAP export policy
        |
        v
QSOL-THOTH routing and resolution
```

Each layer retains its own authority domain.

```text
QSOL_CONTEXT_ACCEPTS != QSOL_IMPORT_ACCEPTS
IMPORT_DECISION != FACTUAL_AUTHORITY
ACCEPTED_CANDIDATE != CONCAP_ROLE
CONTROL_HANDOFF != CONCAP_EXPORT_SPEC
ROUTING_RECEIPT != IMPORT_DECISION
```

## CONTEXT decision contract

A `QSOL-CONTEXT/IMPORT-DECISION/1` receipt binds to:

- the exact `candidate_sha256`;
- the SHA-256 of the exact `IMPORT.json` bytes;
- an exact review policy identity;
- every candidate artifact path, SHA-256, and byte size;
- one explicit `accept` or `reject` disposition for every artifact;
- a summary decision of `accepted`, `rejected`, or `partially_accepted`.

The receipt must cover every candidate artifact exactly once. It cannot assign CONCAP roles. Rejected artifacts remain in the source candidate tree and are not silently deleted.

## Verify a decision

```bash
python -m qsol_import.handoff verify \
  /path/to/import-output \
  /path/to/CONTEXT-DECISION.json
```

Verification checks the candidate manifest self-hash, import receipt self-hash, artifact hashes and sizes, decision self-hash, decision coverage, policy identity, authority fields, and disposition summary.

## Stage accepted artifacts for CONTROL

```bash
python -m qsol_import.handoff stage \
  /path/to/import-output \
  /path/to/CONTEXT-DECISION.json \
  --output /path/to/control-handoff \
  --privacy-class RESTRICTED \
  --recovery-class OUTER_SHELL \
  --capsule qsol-import-accepted.dat
```

The staged directory contains:

```text
HANDOFF.json
SHA256SUMS
review/CANDIDATE.json
review/IMPORT.json
review/CONTEXT-DECISION.json
accepted/...
CONTROL-PACK.spec.json     only when one or more artifacts are accepted
```

`CONTROL-PACK.spec.json` conforms to `qsol-control-restore-pack-spec/1`. Its entries reference only staged source paths. It contains no `role_id`, no THOTH route mutation, and no factual-authority claim.

A fully rejected candidate still produces a verifiable `HANDOFF.json` and review record, but no CONTROL pack specification.

## Routing-receipt immutability check

A caller may bind an existing THOTH route receipt during staging:

```bash
python -m qsol_import.handoff stage \
  /path/to/import-output \
  /path/to/CONTEXT-DECISION.json \
  --output /path/to/control-handoff \
  --thoth-route-receipt /path/to/route-decision.json
```

QSOL-IMPORT hashes the route receipt before and after staging and fails closed if the bytes change. This proves that candidate acceptance and CONTROL staging do not silently rewrite a THOTH routing receipt.

```text
ROUTING_RECEIPT_IMMUTABLE_DURING_HANDOFF
IMPORT_ACCEPTANCE != ROUTING
```

## Integration boundary

The emitted CONTROL pack specification is a staging artifact. It may be consumed by QSOL-CONTROL's existing pack and verification machinery. QSOL-CONTEXT remains responsible for deciding which reviewed pack specifications are mapped to CONCAP roles through its separate export policy.

```text
CONTROL_PACK_SPEC != CONCAP_ROLE_BINDING
STAGED_FOR_PACKING != FACTUAL_AUTHORITY
QSOL_CONTEXT_REMAINS_ACCEPTANCE_AUTHORITY
```
