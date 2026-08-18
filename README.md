# QSOL-IMPORT

**Deterministic, vendor-neutral ingestion for portable AI context.**

QSOL-IMPORT converts raw exports from AI platforms and other external systems into compact, inspectable, provenance-preserving context records suitable for the wider QSOL context stack.

It is deliberately **not** a backup utility, semantic router, factual authority, or capsule store.

Its job is much narrower:

> Take an ugly external export, determine what it contains, preserve the useful context, replace unnecessary bulk with deterministic semantic records, and emit a normalized import result.

---

## Why QSOL-IMPORT exists

AI platform exports tend to contain a mixture of:

- conversations;
- account and conversation metadata;
- uploaded files;
- generated images;
- audio;
- video;
- documents;
- code;
- temporary artifacts;
- duplicated assets;
- vendor-specific identifiers and structures.

For context reconstruction, keeping every byte is often unnecessary.

A 300 MB `.wav` file may matter because a conversation discussed what it represented, but the context system may not need the complete waveform.

Likewise, a large `.mp4` may be relevant as:

> Screen recording demonstrating a particular project state.

rather than as several hundred megabytes of video.

QSOL-IMPORT therefore separates **semantic preservation** from **byte preservation**.

```text
SEMANTIC_PRESERVATION != BYTE_PRESERVATION
```

---

# Architecture

```text
RAW EXTERNAL EXPORT

OpenAI
Grok / xAI
Claude
Gemini
GitHub
other sources
      |
      v
+----------------------+
|     QSOL-IMPORT      |
|----------------------|
| detect format        |
| validate archive     |
| classify files       |
| extract context      |
| normalize records    |
| redact secrets       |
| tombstone media      |
| generate receipts    |
+----------+-----------+
           |
           v
   NORMALIZED CONTEXT
           |
           v
      QSOL-CONTEXT
           |
           v
      QSOL-CONTROL
           |
           v
 deterministic portable
     CONCAP objects
           |
           v
      QSOL-THOTH
           |
           v
    CONCAP resolution
           |
           v
          model
```

QSOL-IMPORT sits **upstream** of QSOL-CONTEXT.

It does not replace QSOL-THOTH, QSOL-CONTROL, CONCAP resolution, or canonical context authority.

---

# Responsibility boundaries

QSOL-IMPORT answers:

> **What is this external data, and how can it be safely normalized?**

QSOL-THOTH answers:

> **Which semantic context roles are required for this intent?**

QSOL-CONTROL answers:

> **How are approved context objects deterministically packaged and verified?**

QSOL-CONTEXT remains responsible for canonical accepted context.

```text
IMPORT != ROUTING
IMPORT != FACTUAL_AUTHORITY
IMPORT != TRANSPORT

NORMALIZED != CANONICAL
PARSED != TRUSTED
EXTRACTED != TRUE
```

---

# Core design principles

## 1. Never mutate the source

The original export is treated as immutable input.

```text
source.zip
    |
    +---- read only ----> QSOL-IMPORT
                              |
                              v
                        sanitized output
```

QSOL-IMPORT should never rewrite or silently alter the original archive.

---

## 2. Deterministic canonical layer

Canonical processing must not depend on:

- an LLM;
- embeddings;
- random numbers;
- network access;
- current time;
- fuzzy classification;
- nondeterministic file ordering.

Equivalent source bytes plus equivalent policy must produce equivalent normalized output.

```text
SOURCE + POLICY + IMPLEMENTATION
            |
            v
      DETERMINISTIC RESULT
```

---

## 3. No silent deletion

Files may be omitted from the normalized context package, but they must not disappear without a record.

Every rejected object produces a deterministic tombstone.

Example:

```json
{
  "protocol": "QSOL-IMPORT/TOMBSTONE/1",
  "path": "attachments/session-demo.mp4",
  "decision": "omit_bytes",
  "class": "video",
  "media_type": "video/mp4",
  "size_bytes": 284991102,
  "sha256": "…",
  "reason": "media_policy",
  "semantic_context": {
    "conversation_title": "QSOL-SUBSTRATE Demo",
    "attachment_label": "screen recording"
  }
}
```

The bytes are omitted.

The fact that the object existed — and why it mattered — survives.

```text
OMITTED_BYTES != OMITTED_MEANING
```

---

# Classification model

QSOL-IMPORT should support three primary outcomes.

## KEEP

Retain useful context-oriented formats such as:

- JSON;
- JSONL;
- Markdown;
- plain text;
- CSV;
- HTML;
- source code;
- small structured metadata.

---

## EXTRACT

For document containers, useful semantic content may be extracted into a normalized representation.

Potential examples:

- PDF;
- DOCX;
- PPTX;
- other text-bearing document formats.

The original may optionally be retained depending on policy.

---

## TOMBSTONE

Large or contextually unnecessary binary assets can be represented by metadata rather than raw bytes.

Typical examples:

- WAV;
- MP3;
- FLAC;
- M4A;
- MP4;
- MOV;
- WebM;
- large generated images;
- large GIFs;
- opaque binary assets.

```text
KEEP
EXTRACT
TOMBSTONE
REJECT
```

`REJECT` should be reserved for malformed, unsupported, dangerous, or policy-prohibited content.

---

# File identification

Classification must not rely only on filename extensions.

A robust importer should consider:

```text
extension
+
declared MIME type
+
file signature / magic bytes
+
size
+
archive metadata
+
conversation reference
```

For example:

```text
asset.dat
```

may still be detected as WAV data if its bytes contain a valid RIFF/WAVE signature.

```text
EXTENSION != FILE TYPE
```

---

# Semantic tombstones

A tombstone should preserve enough information for a later context consumer to understand what was omitted.

Useful fields include:

```json
{
  "protocol": "QSOL-IMPORT/TOMBSTONE/1",
  "source_vendor": "openai",
  "original_path": "…",
  "original_name": "…",
  "sha256": "…",
  "size_bytes": 0,
  "detected_type": "audio/wav",
  "decision": "omit_bytes",
  "reason": "large_binary_media",
  "conversation_id": "…",
  "conversation_title": "…",
  "message_id": "…",
  "semantic_label": "…"
}
```

The deterministic label should be derived from available source evidence such as:

- conversation title;
- attachment filename;
- surrounding message text;
- explicit MIME metadata;
- export metadata.

AI-generated enrichment may be added later, but it must remain outside the canonical deterministic layer.

```text
DETERMINISTIC LABEL != AI INTERPRETATION
```

---

# Import adapters

QSOL-IMPORT is vendor-neutral.

Each source format should be implemented as a separate adapter.

```text
adapters/
├── openai/
├── grok/
├── claude/
├── gemini/
├── github/
└── generic/
```

Adapters translate vendor-specific structures into a shared normalized model.

They should not define downstream routing or canonical factual authority.

---

# Normalized output

A possible import result:

```text
output/
├── IMPORT.json
├── conversations/
│   └── conversations.jsonl
├── messages/
│   └── messages.jsonl
├── attachments/
│   └── attachments.jsonl
├── tombstones/
│   └── tombstones.jsonl
├── retained/
│   ├── documents/
│   └── small-assets/
├── reports/
│   ├── classifications.json
│   ├── warnings.json
│   └── statistics.json
└── SHA256SUMS
```

The exact structure should be governed by versioned schemas rather than undocumented implementation assumptions.

---

# Import receipt

Every run should emit an independently verifiable receipt.

Example:

```json
{
  "protocol": "QSOL-IMPORT/RECEIPT/1",
  "source_type": "openai.export",
  "profile": "conversation-first/1",
  "input_sha256": "…",
  "policy_sha256": "…",
  "implementation_sha256": "…",
  "files_seen": 4281,
  "files_retained": 611,
  "files_tombstoned": 3670,
  "output_sha256": "…"
}
```

Receipts should use acyclic hashing.

The receipt identity must never include itself in its own hash input.

---

# Example policy

```json
{
  "protocol": "QSOL-IMPORT/POLICY/1",
  "profile": "conversation-first",
  "audio": {
    "default": "tombstone"
  },
  "video": {
    "default": "tombstone"
  },
  "images": {
    "keep_under_bytes": 10485760
  },
  "documents": {
    "extract_text": true,
    "keep_original_under_bytes": 26214400
  },
  "structured_text": {
    "default": "keep"
  }
}
```

Policies should be explicit, versioned and hashed.

---

# OpenAI export adapter

The initial adapter can target ChatGPT/OpenAI data exports.

Its priorities should be:

1. discover conversation data;
2. preserve conversation graph structure;
3. preserve message ordering and roles;
4. preserve relevant metadata;
5. resolve attachment references where possible;
6. classify exported assets;
7. tombstone unnecessary media;
8. retain useful textual and structured artifacts;
9. emit deterministic provenance receipts.

The adapter must avoid depending unnecessarily on one permanent vendor directory layout.

```text
VENDOR FORMAT != CANONICAL FORMAT
```

---

# Interaction with QSOL-THOTH

QSOL-IMPORT deliberately does **not** modify THOTH's deterministic routing algorithm.

The current portable-CONCAP architecture keeps separate:

```text
THOTH ROUTING
    decides WHAT semantic roles are needed

CONCAP RESOLUTION
    decides WHICH immutable objects satisfy them

TRANSPORT
    decides WHERE those bytes are obtained
```

QSOL-IMPORT introduces an earlier and separate operation:

```text
IMPORT
    decides HOW external material is normalized
```

Therefore:

```text
IMPORT != ROUTING
ROUTING != RESOLUTION
RESOLUTION != TRANSPORT
TRANSPORT != AUTHORITY
```

QSOL-IMPORT produces candidate normalized material.

QSOL-CONTEXT and its explicit policy determine what becomes accepted context.

---

# Trust boundary

External exports should be treated as untrusted input.

An import must not automatically become canonical context merely because it parsed successfully.

```text
EXTERNAL_SOURCE
      |
      v
 QSOL-IMPORT
      |
      v
NORMALIZED CANDIDATE
      |
      | explicit acceptance / policy
      v
 QSOL-CONTEXT
```

This prevents vendor exports, malformed files, old information, generated material, or hostile content from silently becoming trusted context.

---

# Security requirements

QSOL-IMPORT should eventually include protections against:

- ZIP path traversal;
- decompression bombs;
- absurd archive nesting;
- malformed JSON;
- duplicate JSON members;
- executable payloads;
- secret leakage;
- credentials;
- API tokens;
- private keys;
- unsafe filenames;
- symlinks escaping the extraction root;
- unsupported opaque binary formats.

Parsing should fail closed where deterministic interpretation is impossible.

---

# Example CLI

```bash
python3 -m qsol_import \
  openai-export.zip \
  --adapter openai \
  --profile conversation-first \
  --output ./normalized-openai
```

Example summary:

```text
QSOL-IMPORT

Source              OpenAI export
Profile             conversation-first/1

Conversations       6,842
Messages           91,304
Assets               4,291

Retained             1,103
Extracted              201
Tombstoned           2,987

Input bytes         31.8 GiB
Output bytes       904.2 MiB

Silent deletions          0
Receipt                   valid
Deterministic             yes
```

---

# Non-goals

QSOL-IMPORT is not intended to:

- recreate an AI account;
- recreate model memory automatically;
- judge factual truth;
- determine semantic CONCAP routing;
- provide a vector database;
- become a permanent media archive;
- replace canonical QSOL-CONTEXT;
- modify original exports;
- require cloud services;
- require an LLM.

---

# Long-term direction

Potential adapters include:

```text
OpenAI
xAI / Grok
Anthropic / Claude
Google Gemini
GitHub
Discord
email archives
local AI frontends
generic JSON / JSONL
```

All should converge on the same vendor-neutral normalized context contracts.

The objective is not to preserve every vendor's export format forever.

The objective is to preserve the **context that matters**.

---

# Core invariants

```text
SOURCE != NORMALIZED_OUTPUT

PARSED != TRUSTED
NORMALIZED != CANONICAL
EXTRACTED != TRUE

SEMANTIC_PRESERVATION != BYTE_PRESERVATION
OMITTED_BYTES != OMITTED_MEANING

TOMBSTONE != SOURCE_OBJECT

IMPORT != ROUTING
ROUTING != RESOLUTION
RESOLUTION != TRANSPORT
TRANSPORT != AUTHORITY

VENDOR_FORMAT != CANONICAL_FORMAT

DETERMINISTIC_LABEL != AI_INTERPRETATION

NO_SILENT_DELETION
```

---

## Status

Early architecture / bootstrap.

The first implementation target is a deterministic **OpenAI export adapter** using a conversation-first policy, followed by the existing Grok-export workflow.

QSOL-IMPORT should remain small, inspectable, offline-capable and aggressively resistant to becoming a universal blob-processing monster.

Because eventually somebody will suggest adding a web browser, vector database, agent framework and Kubernetes deployment to it.

The answer is **no**.
