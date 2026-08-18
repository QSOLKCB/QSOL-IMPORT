from __future__ import annotations

from pathlib import PurePosixPath
from typing import Any, Mapping, Sequence

from qsol_import.adapter_contract import (
    AdapterError,
    AdapterResult,
    MemberDisposition,
    SourceMember,
    adapter_descriptor,
    conversation_record,
    message_record,
)
from qsol_import.adapters._util import attachment_refs, first_value, parse_json, parse_jsonl, sorted_result


class GenericAdapter:
    adapter_id = "generic-json-jsonl/1"
    source_vendor = "generic"
    source_type = "generic.conversation.export"

    def descriptor(self) -> dict[str, Any]:
        return adapter_descriptor(self.adapter_id, self.source_vendor, self.source_type)

    def discover(self, members: Sequence[SourceMember]) -> tuple[str, ...]:
        matches = [member.path for member in members if PurePosixPath(member.path).suffix.casefold() in {".json", ".jsonl"}]
        if len(matches) != 1:
            raise AdapterError("generic_source_cardinality", f"generic adapter requires exactly one JSON/JSONL member, found {len(matches)}")
        return (matches[0],)

    def member_disposition(self, path: str) -> MemberDisposition | None:
        return None

    def member_reference_key(self, path: str) -> str | None:
        return PurePosixPath(path).name

    def _message(self, source_path: str, source_index: int, conversation_id: Any, row: Mapping[str, Any]) -> dict[str, Any]:
        return message_record(
            adapter_id=self.adapter_id,
            source_vendor=self.source_vendor,
            source_type=self.source_type,
            source_path=source_path,
            source_index=source_index,
            source_message_id=first_value(row, ("id", "message_id")),
            conversation_id=conversation_id,
            role=first_value(row, ("role", "author", "sender")),
            text=first_value(row, ("text", "content", "message")),
            name=row.get("name"),
            create_time=first_value(row, ("create_time", "created_at", "timestamp")),
            update_time=first_value(row, ("update_time", "updated_at")),
            parent_id=first_value(row, ("parent_id", "parent_message_id")),
            children=row.get("children"),
            model=row.get("model"),
            status=row.get("status"),
            attachment_refs=attachment_refs(first_value(row, ("attachments", "files", "attachment_refs"))),
        )

    def parse(self, payloads: Mapping[str, bytes]) -> AdapterResult:
        source_path, raw = next(iter(payloads.items()))
        suffix = PurePosixPath(source_path).suffix.casefold()
        value = parse_jsonl(raw) if suffix == ".jsonl" else parse_json(raw)

        conversations: list[dict[str, Any]] = []
        messages: list[dict[str, Any]] = []
        attachment_index: dict[str, list[dict[str, Any]]] = {}

        if suffix == ".jsonl":
            if not isinstance(value, list):
                raise AdapterError("invalid_generic_jsonl", "JSONL parser did not return records")
            grouped: dict[str, list[tuple[int, Mapping[str, Any]]]] = {}
            titles: dict[str, Any] = {}
            for row_index, row in enumerate(value):
                if not isinstance(row, dict):
                    raise AdapterError("invalid_generic_jsonl_row", f"JSONL row {row_index} is not an object")
                conversation_id = first_value(row, ("conversation_id", "thread_id", "chat_id"))
                if conversation_id is None:
                    raise AdapterError("generic_missing_conversation_id", f"JSONL row {row_index} lacks conversation_id")
                key = str(conversation_id)
                grouped.setdefault(key, []).append((row_index, row))
                titles.setdefault(key, row.get("title"))
            for conversation_index, conversation_id in enumerate(sorted(grouped)):
                conversations.append(
                    conversation_record(
                        adapter_id=self.adapter_id,
                        source_vendor=self.source_vendor,
                        source_type=self.source_type,
                        source_path=source_path,
                        source_index=conversation_index,
                        conversation_id=conversation_id,
                        title=titles.get(conversation_id),
                    )
                )
                for row_index, row in grouped[conversation_id]:
                    record = self._message(source_path, row_index, conversation_id, row)
                    messages.append(record)
        else:
            raw_conversations: Any
            if isinstance(value, dict) and isinstance(value.get("conversations"), list):
                raw_conversations = value["conversations"]
            elif isinstance(value, list):
                raw_conversations = value
            else:
                raise AdapterError("unsupported_generic_shape", "generic JSON must be a conversation list or an object containing conversations")

            for conversation_index, row in enumerate(raw_conversations):
                if not isinstance(row, dict):
                    raise AdapterError("invalid_generic_conversation", f"conversation {conversation_index} is not an object")
                conversation_id = first_value(row, ("id", "conversation_id", "thread_id", "chat_id"))
                conversations.append(
                    conversation_record(
                        adapter_id=self.adapter_id,
                        source_vendor=self.source_vendor,
                        source_type=self.source_type,
                        source_path=source_path,
                        source_index=conversation_index,
                        conversation_id=conversation_id,
                        title=row.get("title"),
                        create_time=first_value(row, ("create_time", "created_at")),
                        update_time=first_value(row, ("update_time", "updated_at")),
                    )
                )
                raw_messages = row.get("messages")
                if not isinstance(raw_messages, list):
                    raise AdapterError("generic_missing_messages", f"conversation {conversation_index} lacks a messages array")
                for message_index, message in enumerate(raw_messages):
                    if not isinstance(message, dict):
                        continue
                    record = self._message(source_path, message_index, conversation_id, message)
                    messages.append(record)

        for record in messages:
            for ref in record["attachment_refs"]:
                attachment_index.setdefault(ref, []).append(
                    {
                        "conversation_id": record["conversation_id"],
                        "source_message_id": record["source_message_id"],
                        "source_path": record["source_path"],
                        "source_index": record["source_index"],
                    }
                )
        return sorted_result(conversations, messages, attachment_index)
