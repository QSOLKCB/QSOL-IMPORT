from __future__ import annotations

import math
from dataclasses import dataclass, field
from typing import Any, Mapping, Protocol, Sequence


ADAPTER_PROTOCOL = "QSOL-IMPORT/ADAPTER/1"
ADAPTER_SCHEMA_VERSION = "1.0.0"
CONVERSATION_PROTOCOL = "QSOL-IMPORT/CONVERSATION/1"
MESSAGE_PROTOCOL = "QSOL-IMPORT/MESSAGE/1"
PROVENANCE_PROTOCOL = "QSOL-IMPORT/PROVENANCE/1"

_CONVERSATION_KEYS = frozenset(
    {
        "protocol",
        "adapter_protocol",
        "adapter_id",
        "source_vendor",
        "source_type",
        "source_path",
        "source_index",
        "source_conversation_id",
        "title",
        "create_time",
        "update_time",
    }
)
_MESSAGE_KEYS = frozenset(
    {
        "protocol",
        "adapter_protocol",
        "adapter_id",
        "source_vendor",
        "source_type",
        "source_path",
        "source_index",
        "source_message_id",
        "source_parent_id",
        "source_children_ids",
        "conversation_id",
        "role",
        "name",
        "create_time",
        "update_time",
        "model",
        "status",
        "text",
        "attachment_refs",
    }
)


class AdapterError(ValueError):
    def __init__(self, code: str, message: str):
        super().__init__(message)
        self.code = code


@dataclass(frozen=True)
class SourceMember:
    path: str
    size_bytes: int


@dataclass(frozen=True)
class MemberDisposition:
    decision: str
    reason: str


@dataclass(frozen=True)
class AdapterResult:
    conversations: tuple[dict[str, Any], ...]
    messages: tuple[dict[str, Any], ...]
    attachment_index: Mapping[str, tuple[dict[str, Any], ...]] = field(default_factory=dict)


class Adapter(Protocol):
    adapter_id: str
    source_vendor: str
    source_type: str

    def descriptor(self) -> dict[str, Any]: ...

    def discover(self, members: Sequence[SourceMember]) -> tuple[str, ...]: ...

    def parse(self, payloads: Mapping[str, bytes]) -> AdapterResult: ...

    def member_disposition(self, path: str) -> MemberDisposition | None: ...

    def member_reference_key(self, path: str) -> str | None: ...


def adapter_descriptor(adapter_id: str, source_vendor: str, source_type: str) -> dict[str, Any]:
    return {
        "protocol": ADAPTER_PROTOCOL,
        "schema_version": ADAPTER_SCHEMA_VERSION,
        "adapter_id": adapter_id,
        "source_vendor": source_vendor,
        "source_type": source_type,
        "canonical_conversation_protocol": CONVERSATION_PROTOCOL,
        "canonical_message_protocol": MESSAGE_PROTOCOL,
        "canonical_provenance_protocol": PROVENANCE_PROTOCOL,
        "vendor_payload_in_canonical_records": False,
    }


def normalized_time(value: Any) -> int | float | str | None:
    if value is None or isinstance(value, str):
        return value
    if isinstance(value, bool):
        return None
    if isinstance(value, (int, float)):
        return value
    return None


def normalized_text(value: Any) -> str:
    if isinstance(value, str):
        return value
    if isinstance(value, list):
        parts: list[str] = []
        for item in value:
            if isinstance(item, str):
                parts.append(item)
            elif isinstance(item, dict) and isinstance(item.get("text"), str):
                parts.append(item["text"])
        return "\n".join(parts)
    if isinstance(value, dict) and isinstance(value.get("text"), str):
        return value["text"]
    return ""


def normalize_role(value: Any) -> str | None:
    if not isinstance(value, str) or not value:
        return None
    lowered = value.casefold()
    if lowered in {"human", "user"}:
        return "user"
    if lowered in {"assistant", "model", "grok", "claude", "gemini"}:
        return "assistant"
    if lowered == "system":
        return "system"
    if lowered == "tool":
        return "tool"
    return value


def conversation_record(
    *,
    adapter_id: str,
    source_vendor: str,
    source_type: str,
    source_path: str,
    source_index: int,
    conversation_id: Any,
    title: Any,
    create_time: Any = None,
    update_time: Any = None,
) -> dict[str, Any]:
    return {
        "protocol": CONVERSATION_PROTOCOL,
        "adapter_protocol": ADAPTER_PROTOCOL,
        "adapter_id": adapter_id,
        "source_vendor": source_vendor,
        "source_type": source_type,
        "source_path": source_path,
        "source_index": source_index,
        "source_conversation_id": str(conversation_id) if conversation_id is not None else None,
        "title": str(title) if title is not None else None,
        "create_time": normalized_time(create_time),
        "update_time": normalized_time(update_time),
    }


def message_record(
    *,
    adapter_id: str,
    source_vendor: str,
    source_type: str,
    source_path: str,
    source_index: int,
    source_message_id: Any,
    conversation_id: Any,
    role: Any,
    text: Any,
    name: Any = None,
    create_time: Any = None,
    update_time: Any = None,
    parent_id: Any = None,
    children: Any = None,
    model: Any = None,
    status: Any = None,
    attachment_refs: Any = None,
) -> dict[str, Any]:
    child_ids = [str(item) for item in children] if isinstance(children, list) else []
    refs = sorted({str(item) for item in attachment_refs if isinstance(item, str) and item}) if isinstance(attachment_refs, list) else []
    return {
        "protocol": MESSAGE_PROTOCOL,
        "adapter_protocol": ADAPTER_PROTOCOL,
        "adapter_id": adapter_id,
        "source_vendor": source_vendor,
        "source_type": source_type,
        "source_path": source_path,
        "source_index": source_index,
        "source_message_id": str(source_message_id) if source_message_id is not None else None,
        "source_parent_id": str(parent_id) if parent_id is not None else None,
        "source_children_ids": child_ids,
        "conversation_id": str(conversation_id) if conversation_id is not None else None,
        "role": normalize_role(role),
        "name": str(name) if name is not None else None,
        "create_time": normalized_time(create_time),
        "update_time": normalized_time(update_time),
        "model": str(model) if model is not None else None,
        "status": str(status) if status is not None else None,
        "text": normalized_text(text),
        "attachment_refs": refs,
    }


def _is_nullable_string(value: Any) -> bool:
    return value is None or isinstance(value, str)


def _is_json_time(value: Any) -> bool:
    if value is None or isinstance(value, str):
        return True
    if isinstance(value, bool):
        return False
    if isinstance(value, int):
        return True
    return isinstance(value, float) and math.isfinite(value)


def _is_index(value: Any) -> bool:
    return isinstance(value, int) and not isinstance(value, bool) and value >= 0


def _require_nonempty_string(record: Mapping[str, Any], key: str, code: str) -> None:
    value = record.get(key)
    if not isinstance(value, str) or not value:
        raise AdapterError(code, f"canonical record field {key!r} must be a non-empty string")


def _validate_conversation(record: Any, adapter_id: str) -> None:
    code = "invalid_conversation_record"
    if not isinstance(record, dict) or set(record) != _CONVERSATION_KEYS:
        raise AdapterError(code, "adapter emitted a conversation record that does not match the frozen field set")
    if record["protocol"] != CONVERSATION_PROTOCOL or record["adapter_protocol"] != ADAPTER_PROTOCOL:
        raise AdapterError(code, "adapter emitted an invalid conversation protocol")
    if record["adapter_id"] != adapter_id:
        raise AdapterError(code, "adapter emitted a conversation record for a different adapter")
    for key in ("adapter_id", "source_vendor", "source_type", "source_path"):
        _require_nonempty_string(record, key, code)
    if not _is_index(record["source_index"]):
        raise AdapterError(code, "conversation source_index must be a non-negative integer")
    for key in ("source_conversation_id", "title"):
        if not _is_nullable_string(record[key]):
            raise AdapterError(code, f"conversation field {key!r} must be a string or null")
    for key in ("create_time", "update_time"):
        if not _is_json_time(record[key]):
            raise AdapterError(code, f"conversation field {key!r} must be a finite number, string, or null")


def _validate_message(record: Any, adapter_id: str) -> None:
    code = "invalid_message_record"
    if not isinstance(record, dict) or set(record) != _MESSAGE_KEYS:
        raise AdapterError(code, "adapter emitted a message record that does not match the frozen field set")
    if record["protocol"] != MESSAGE_PROTOCOL or record["adapter_protocol"] != ADAPTER_PROTOCOL:
        raise AdapterError(code, "adapter emitted an invalid message protocol")
    if record["adapter_id"] != adapter_id:
        raise AdapterError(code, "adapter emitted a message record for a different adapter")
    for key in ("adapter_id", "source_vendor", "source_type", "source_path"):
        _require_nonempty_string(record, key, code)
    if not _is_index(record["source_index"]):
        raise AdapterError(code, "message source_index must be a non-negative integer")
    for key in (
        "source_message_id",
        "source_parent_id",
        "conversation_id",
        "role",
        "name",
        "model",
        "status",
    ):
        if not _is_nullable_string(record[key]):
            raise AdapterError(code, f"message field {key!r} must be a string or null")
    for key in ("create_time", "update_time"):
        if not _is_json_time(record[key]):
            raise AdapterError(code, f"message field {key!r} must be a finite number, string, or null")
    if not isinstance(record["text"], str):
        raise AdapterError(code, "message text must be a string")
    children = record["source_children_ids"]
    if not isinstance(children, list) or not all(isinstance(item, str) for item in children):
        raise AdapterError(code, "message source_children_ids must be an array of strings")
    refs = record["attachment_refs"]
    if (
        not isinstance(refs, list)
        or not all(isinstance(item, str) for item in refs)
        or len(refs) != len(set(refs))
    ):
        raise AdapterError(code, "message attachment_refs must be a unique array of strings")


def validate_result(result: AdapterResult, adapter_id: str) -> None:
    if not isinstance(result, AdapterResult):
        raise AdapterError("invalid_adapter_result", "adapter did not return AdapterResult")
    for record in result.conversations:
        _validate_conversation(record, adapter_id)
    for record in result.messages:
        _validate_message(record, adapter_id)
