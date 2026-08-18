from __future__ import annotations

from dataclasses import dataclass
from typing import Any

from qsol_import.canonical import loads_strict


@dataclass(frozen=True)
class AccountMetadataConfig:
    path: str
    fields: tuple[str, ...]
    max_member_bytes: int


def account_metadata_config(policy: dict[str, Any], path: str) -> AccountMetadataConfig | None:
    section = policy.get("account_metadata")
    if not isinstance(section, dict) or not section.get("enabled", False):
        return None

    max_member_bytes = int(section.get("max_member_bytes", 1024 * 1024))
    allowlist = section.get("allowlist", [])
    if not isinstance(allowlist, list):
        raise ValueError("account_metadata.allowlist must be a list")

    for item in allowlist:
        if not isinstance(item, dict) or item.get("path") != path:
            continue
        fields = item.get("fields")
        if not isinstance(fields, list) or not fields or not all(isinstance(field, str) and field for field in fields):
            raise ValueError(f"invalid account metadata field allowlist for {path!r}")
        if len(set(fields)) != len(fields):
            raise ValueError(f"duplicate account metadata field allowlist entry for {path!r}")
        return AccountMetadataConfig(
            path=path,
            fields=tuple(fields),
            max_member_bytes=max_member_bytes,
        )
    return None


def filter_account_metadata(data: bytes, config: AccountMetadataConfig) -> dict[str, Any]:
    value = loads_strict(data)
    if not isinstance(value, dict):
        raise ValueError(f"allow-listed account metadata must be a JSON object: {config.path!r}")

    selected = {field: value[field] for field in config.fields if field in value}
    return {
        "protocol": "QSOL-IMPORT/OPENAI-ACCOUNT-METADATA/1",
        "schema_version": "1.0.0",
        "source_path": config.path,
        "allowlisted_fields": list(config.fields),
        "present_fields": [field for field in config.fields if field in value],
        "metadata": selected,
    }
