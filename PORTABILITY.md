# QSOL-IMPORT Portability Boundary

## Verified runtime boundary

The deterministic output contract is verified for:

```text
implementation: CPython
versions:       >=3.11,<3.14
platforms:      Linux, macOS, Windows
```

GitHub Actions runs the complete unit and adversarial test suite for Python 3.11, 3.12, and 3.13 on all three operating-system families.

```text
SUPPORTED_ENVIRONMENT != ALL_FUTURE_ENVIRONMENTS
CI_MATRIX_PASS != EVERY_FILESYSTEM_BEHAVIOUR
```

## Canonical dependencies

Byte identity depends on the exact:

- source bytes;
- policy bytes;
- implementation bytes;
- UTF-8 byte ordering rules;
- adapter selection;
- explicit evaluation or handoff inputs.

Changes to any of those inputs may legitimately change output identity.

```text
IMPLEMENTATION_CHANGE != SILENT_BASELINE_REFRESH
POLICY_CHANGE != SAME_RECEIPT
SOURCE_CHANGE != SAME_OUTPUT
```

## Excluded dependencies

Canonical output must not depend on:

- wall-clock time;
- randomness;
- network availability;
- locale;
- absolute filesystem paths;
- host username;
- process identifier;
- source or output directory name.

All paths written into canonical receipts are POSIX-style relative paths.

```text
PLATFORM_PATH != CANONICAL_PATH
LOCALE != CANONICAL_COLLATION
```

## Tree comparison receipt

Two output trees can be compared directly:

```bash
python -m qsol_import.portability /path/to/run-a /path/to/run-b
```

The command emits `QSOL-IMPORT/PORTABILITY-RECEIPT/1`, containing the exact file path, byte-size, and SHA-256 inventory hash for both trees.

A successful comparison means every emitted file is byte-identical. It does not grant factual authority to the content.

```text
BYTE_IDENTICAL_OUTPUT != FACTUAL_TRUTH
```

## Outside the verified boundary

The current project does not claim byte-level portability for:

- PyPy or other Python implementations;
- CPython 3.10 or earlier;
- CPython 3.14 or later until tested;
- operating systems outside Linux, macOS, and Windows;
- filesystems that rewrite filenames or file bytes;
- vendor-export layouts not accepted by a frozen adapter contract;
- manually edited outputs;
- optional external parsers not included in the standard-library implementation.

Unsupported environments may still work, but that is not the same as a verified portability claim.
