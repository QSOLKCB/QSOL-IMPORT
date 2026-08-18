from __future__ import annotations

import re
from collections import defaultdict
from dataclasses import dataclass
from pathlib import Path
from typing import Iterable, TextIO

from qsol_import.canonical import canonical_json_bytes, sha256_bytes


@dataclass(frozen=True)
class PrivacyRule:
    rule_id: str
    category: str
    pattern: str
    flags: int = 0


# Every rule is deliberately bounded so a finite overlap is sufficient to catch
# matches that cross scanner chunk boundaries. Long token-like values are still
# detected through their bounded prefix; raw match bytes are never emitted.
RULES = (
    PrivacyRule(
        "email_address",
        "privacy",
        r"(?<![A-Za-z0-9._%+-])[A-Za-z0-9._%+-]{1,128}@[A-Za-z0-9.-]{1,253}\.[A-Za-z]{2,63}(?![A-Za-z0-9._%+-])",
        re.IGNORECASE,
    ),
    PrivacyRule(
        "openai_api_key",
        "secret",
        r"(?<![A-Za-z0-9_-])sk-[A-Za-z0-9_-]{20,4096}",
    ),
    PrivacyRule(
        "github_token",
        "secret",
        r"(?<![A-Za-z0-9_])gh[pousr]_[A-Za-z0-9]{20,1024}",
    ),
    PrivacyRule(
        "aws_access_key",
        "secret",
        r"(?<![A-Z0-9])(?:AKIA|ASIA)[A-Z0-9]{16}(?![A-Z0-9])",
    ),
    PrivacyRule(
        "private_key_header",
        "secret",
        r"-----BEGIN (?:RSA |EC |OPENSSH )?PRIVATE KEY-----",
    ),
    PrivacyRule(
        "bearer_token",
        "secret",
        r"(?i)(?<![A-Za-z0-9])Bearer[ \t]{1,32}[A-Za-z0-9._~+/=-]{20,4096}",
    ),
)

_SCAN_CHUNK_CHARS = 64 * 1024
_SCAN_OVERLAP_CHARS = 8 * 1024
_COMPILED_RULES = tuple((rule, re.compile(rule.pattern, rule.flags)) for rule in RULES)


def _rule_spec(rule: PrivacyRule) -> dict:
    return {
        "rule_id": rule.rule_id,
        "category": rule.category,
        "pattern": rule.pattern,
        "flags": "IGNORECASE" if rule.flags & re.IGNORECASE else "",
    }


def _rule_sha256(rule: PrivacyRule) -> str:
    return sha256_bytes(canonical_json_bytes(_rule_spec(rule)))


def ruleset_sha256() -> str:
    body = {
        "protocol": "QSOL-IMPORT/PRIVACY-RULESET/1",
        "rules": [_rule_spec(rule) for rule in RULES],
    }
    return sha256_bytes(canonical_json_bytes(body))


def _scan_window(
    window: str,
    *,
    start_limit: int,
    rel: str,
    aggregate: dict[tuple[str, str], dict[str, int]],
) -> None:
    """Count matches whose start is in the committed prefix of a scan window."""
    for rule, pattern in _COMPILED_RULES:
        for match in pattern.finditer(window):
            if match.start() >= start_limit:
                break
            digest = sha256_bytes(match.group(0).encode("utf-8"))
            aggregate[(rel, rule.rule_id)][digest] += 1


def _scan_bounded_text(
    handle: TextIO,
    *,
    rel: str,
    aggregate: dict[tuple[str, str], dict[str, int]],
) -> None:
    """Scan without ever materializing an unbounded line or whole text file.

    Matches starting in the final overlap are deferred until the next window.
    Because every bundled rule has a maximum match span below the overlap size,
    a cross-boundary match is present in full when its start is committed.
    """
    carry = ""
    while True:
        chunk = handle.read(_SCAN_CHUNK_CHARS)
        if not chunk:
            break
        window = carry + chunk
        committed = max(0, len(window) - _SCAN_OVERLAP_CHARS)
        _scan_window(
            window,
            start_limit=committed,
            rel=rel,
            aggregate=aggregate,
        )
        carry = window[committed:]

    if carry:
        _scan_window(
            carry,
            start_limit=len(carry),
            rel=rel,
            aggregate=aggregate,
        )


def scan_files(root: Path, relative_paths: Iterable[str]) -> dict:
    aggregate: dict[tuple[str, str], dict[str, int]] = defaultdict(lambda: defaultdict(int))
    scanned: list[str] = []

    for rel in sorted(set(relative_paths), key=lambda item: item.encode("utf-8")):
        path = root / rel
        if not path.is_file():
            continue
        scanned.append(rel)
        with path.open("r", encoding="utf-8", errors="replace", newline="") as handle:
            _scan_bounded_text(handle, rel=rel, aggregate=aggregate)

    findings = []
    rule_totals = {rule.rule_id: {"occurrences": 0, "files": set()} for rule in RULES}
    total_occurrences = 0
    rules_by_id = {rule.rule_id: rule for rule in RULES}
    for (path, rule_id), matches in sorted(aggregate.items()):
        rule = rules_by_id[rule_id]
        occurrence_count = sum(matches.values())
        total_occurrences += occurrence_count
        rule_totals[rule_id]["occurrences"] += occurrence_count
        rule_totals[rule_id]["files"].add(path)
        findings.append(
            {
                "path": path,
                "rule_id": rule_id,
                "category": rule.category,
                "occurrences": occurrence_count,
                "matches": [
                    {"sha256": digest, "occurrences": count}
                    for digest, count in sorted(matches.items())
                ],
            }
        )

    rule_receipts = []
    for rule in RULES:
        totals = rule_totals[rule.rule_id]
        rule_receipts.append(
            {
                "rule_id": rule.rule_id,
                "category": rule.category,
                "rule_sha256": _rule_sha256(rule),
                "files_with_findings": len(totals["files"]),
                "occurrences": totals["occurrences"],
            }
        )

    body = {
        "protocol": "QSOL-IMPORT/PRIVACY-SCAN/1",
        "schema_version": "1.0.0",
        "ruleset_protocol": "QSOL-IMPORT/PRIVACY-RULESET/1",
        "ruleset_sha256": ruleset_sha256(),
        "scanned_files": scanned,
        "files_scanned": len(scanned),
        "files_with_findings": len({item["path"] for item in findings}),
        "finding_groups": len(findings),
        "finding_occurrences": total_occurrences,
        "rule_receipts": rule_receipts,
        "findings": findings,
        "raw_matches_emitted": False,
    }
    return {
        **body,
        "scan_sha256": sha256_bytes(canonical_json_bytes(body)),
    }
