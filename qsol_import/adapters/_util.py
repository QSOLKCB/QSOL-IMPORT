from __future__ import annotations

from typing import Any, Iterable, Mapping

from qsol_import.adapter_contract import AdapterError, AdapterResult
from qsol_import.canonical import loads_strict


def parse_json(data: bytes, *, code: str = "invalid_json") -> Any:
    try:
        return loads_strict(data)
    except (UnicodeDecodeError, ValueError) as exc:
        raise AdapterError(code, "adapter source is not strict JSON") from exc


def parse_jsonl(data: bytes) -> list[Any]:
    rows: list[Any] = []
    for line_number, raw in enumerate(data.splitlines(), start=1):
        if not raw.strip():
            continue
        try:
            rows.append(loads_strict(raw))
        except (UnicodeDecodeError, ValueError) as exc:
            raise AdapterError("invalid_jsonl", f"invalid JSONL record at line {line_number}") from exc
    return rows


def first_value(mapping: Mapping[str, Any], keys: Iterable[str]) -> Any:
    for key in keys:
        value = mapping.get(key)
        if value is not None:
            return value
    return None


def first_string(mapping: Mapping[str, Any], keys: Iterable[str]) -> str | None:
    value = first_value(mapping, keys)
    return value if isinstance(value, str) else None


def attachment_refs(value: Any) -> list[str]:
    if not isinstance(value, list):
        return []
    refs: set[str] = set()
    for item in value:
        if isinstance(item, str) and item:
            refs.add(item)
        elif isinstance(item, dict):
            for key in ("id", "uuid", "file_id", "asset_id", "name", "file_name"):
                candidate = item.get(key)
                if isinstance(candidate, str) and candidate:
                    refs.add(candidate)
                    break
    return sorted(refs)


def sorted_result(
    conversations: list[dict[str, Any]],
    messages: list[dict[str, Any]],
    attachment_index: dict[str, list[dict[str, Any]]] | None = None,
) -> AdapterResult:
    conversations.sort(
        key=lambda row: (
            str(row.get("source_path") or ""),
            int(row.get("source_index") or 0),
            str(row.get("source_conversation_id") or ""),
        )
    )
    messages.sort(
        key=lambda row: (
            str(row.get("conversation_id") or ""),
            str(row.get("create_time") or ""),
            int(row.get("source_index") or 0),
            str(row.get("source_message_id") or ""),
        )
    )
    normalized_index = {
        key: tuple(
            sorted(
                rows,
                key=lambda row: (
                    str(row.get("source_path") or ""),
                    int(row.get("source_index") or 0),
                    str(row.get("conversation_id") or ""),
                    str(row.get("source_message_id") or ""),
                ),
            )
        )
        for key, rows in sorted((attachment_index or {}).items())
    }
    return AdapterResult(tuple(conversations), tuple(messages), normalized_index)
