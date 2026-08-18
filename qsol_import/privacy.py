from __future__ import annotations

import re
from collections import defaultdict
from dataclasses import dataclass
from pathlib import Path
from typing import Iterable

from qsol_import.canonical import canonical_json_bytes, sha256_bytes


@dataclass(frozen=True)
class PrivacyRule:
    rule_id: str
    category: str
    pattern: str
    flags: int = 0


RULES = (
    PrivacyRule(
        "email_address",
        "privacy",
        r"(?<![A-Za-z0-9._%+-])[A-Za-z0-9._%+-]+@[A-Za-z0-9.-]+\.[A-Za-z]{2,}(?![A-Za-z0-9._%+-])",
        re.IGNORECASE,
    ),
    PrivacyRule(
        "openai_api_key",
        "secret",
        r"(?<![A-Za-z0-9_-])sk-[A-Za-z0-9_-]{20,}(?![A-Za-z0-9_-])",
    ),
    PrivacyRule(
        "github_token",
        "secret",
        r"(?<![A-Za-z0-9_])gh[pousr]_[A-Za-z0-9]{20,}(?![A-Za-z0-9])",
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
        r"(?i)(?<![A-Za-z0-9])Bearer[ \t]+[A-Za-z0-9._~+/=-]{20,}(?![A-Za-z0-9._~+/=-])",
    ),
)


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


def scan_files(root: Path, relative_paths: Iterable[str]) -> dict:
    aggregate: dict[tuple[str, str], dict[str, int]] = defaultdict(lambda: defaultdict(int))
    scanned: list[str] = []

    for rel in sorted(set(relative_paths), key=lambda item: item.encode("utf-8")):
        path = root / rel
        if not path.is_file():
            continue
        scanned.append(rel)
        compiled = [(rule, re.compile(rule.pattern, rule.flags)) for rule in RULES]
        with path.open("r", encoding="utf-8", errors="replace", newline="") as handle:
            for line in handle:
                for rule, pattern in compiled:
                    for match in pattern.finditer(line):
                        digest = sha256_bytes(match.group(0).encode("utf-8"))
                        aggregate[(rel, rule.rule_id)][digest] += 1

    findings = []
    rule_totals = {rule.rule_id: {"occurrences": 0, "files": set()} for rule in RULES}
    total_occurrences = 0
    for (path, rule_id), matches in sorted(aggregate.items()):
        rule = next(item for item in RULES if item.rule_id == rule_id)
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
