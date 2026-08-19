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

## Candidate verification

Before a CONTEXT decision can be used, QSOL-IMPORT verifies:

- the exact `CANDIDATE.json` field set and self-receipt;
- required candidate authority boundaries;
- every declared artifact path, size, and SHA-256;
- the exact candidate file set, rejecting unlisted files and symlinks;
- the complete `IMPORT.json` field set;
- all receipt hashes and non-negative counters;
- `files_seen == retained + extracted + tombstoned + rejected`;
- the import receipt self-receipt;
- candidate and import-receipt source, policy, implementation, and candidate identities;
- a recomputed `output_sha256` over `CANDIDATE.json` plus every candidate artifact.

```text
SELF_CONSISTENT_RECEIPT != VERIFIED_OUTPUT_TREE
UNLISTED_FILE != CANDIDATE_ARTIFACT
```

## CONTEXT decision contract

A `QSOL-CONTEXT/IMPORT-DECISION/1` receipt binds to:

- the exact `candidate_sha256`;
- the SHA-256 of the exact `IMPORT.json` bytes;
- an exact review-policy identity;
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

Verification checks the candidate tree, import receipt, artifact identities, decision self-receipt, decision coverage, review-policy identity, authority fields, required boundaries, and disposition summary.

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

## Destination safety

The output must not be the candidate root, live inside the candidate root, contain the candidate root, overlap the decision file, or overlap an optional THOTH route receipt.

An existing output may be a real directory. An existing regular file or symlink is rejected before any rename or replacement occurs.

```text
HANDOFF_OUTPUT != INPUT_TREE
FAILED_HANDOFF != DESTROYED_CANDIDATE
```

## Routing-receipt verification and immutability

A caller may bind an existing THOTH route receipt during staging:

```bash
python -m qsol_import.handoff stage \
  /path/to/import-output \
  /path/to/CONTEXT-DECISION.json \
  --output /path/to/control-handoff \
  --thoth-route-receipt /path/to/route-decision.json
```

QSOL-IMPORT does not trust a file merely because it has a route-like name or a SHA-256. It validates the complete `QSOL-THOTH/ROUTE-DECISION/1` contract:

- exact fields;
- canonical intent and style tokens;
- unique, versioned CONCAP role IDs;
- request, configuration, and implementation hash references;
- all required THOTH authority boundaries;
- the canonical `decision_sha256` self-receipt.

It then hashes the exact route file bytes before and after staging and fails closed if they change. `HANDOFF.json` records both the semantic route decision identity and the unchanged file-byte identity.

```text
RECEIPT_HASH != RECEIPT_VERIFICATION
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
