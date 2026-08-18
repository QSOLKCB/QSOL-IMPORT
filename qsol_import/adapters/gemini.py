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
from qsol_import.adapters._util import attachment_refs, first_value, parse_json, sorted_result


class GeminiAdapter:
    adapter_id = "google-gemini-export/1"
    source_vendor = "google"
    source_type = "google.gemini.export"

    def descriptor(self) -> dict[str, Any]:
        return adapter_descriptor(self.adapter_id, self.source_vendor, self.source_type)

    def discover(self, members: Sequence[SourceMember]) -> tuple[str, ...]:
        preferred = {
            "gemini.json",
            "myactivity.json",
            "my activity.json",
            "conversations.json",
        }
        matches = [
            member.path
            for member in members
            if PurePosixPath(member.path).name.casefold() in preferred
        ]
        if len(matches) != 1:
            raise AdapterError(
                "gemini_source_cardinality",
                f"Gemini adapter requires exactly one supported JSON member, found {len(matches)}",
            )
        return (matches[0],)

    def member_disposition(self, path: str) -> MemberDisposition | None:
        return None

    def member_reference_key(self, path: str) -> str | None:
        return PurePosixPath(path).name

    def _emit_message(
        self,
        source_path: str,
        message_index: int,
        conversation_id: Any,
        row: Mapping[str, Any],
    ) -> dict[str, Any]:
        return message_record(
            adapter_id=self.adapter_id,
            source_vendor=self.source_vendor,
            source_type=self.source_type,
            source_path=source_path,
            source_index=message_index,
            source_message_id=first_value(row, ("id", "message_id", "entry_id")),
            conversation_id=conversation_id,
            role=first_value(row, ("role", "author", "sender")),
            text=first_value(row, ("text", "content", "message", "prompt", "response")),
            create_time=first_value(row, ("create_time", "created_at", "timestamp", "time")),
            update_time=first_value(row, ("update_time", "updated_at")),
            parent_id=first_value(row, ("parent_id", "parent_message_id")),
            model=row.get("model"),
            attachment_refs=attachment_refs(first_value(row, ("attachments", "files"))),
        )

    def parse(self, payloads: Mapping[str, bytes]) -> AdapterResult:
        source_path, raw = next(iter(payloads.items()))
        value = parse_json(raw, code="invalid_gemini_json")
        conversations: list[dict[str, Any]] = []
        messages: list[dict[str, Any]] = []

        if isinstance(value, dict) and isinstance(value.get("conversations"), list):
            rows = value["conversations"]
            recognized = 0
            for conversation_index, row in enumerate(rows):
                if not isinstance(row, dict):
                    continue
                raw_messages = row.get("entries")
                if not isinstance(raw_messages, list):
                    raw_messages = row.get("messages")
                if not isinstance(raw_messages, list):
                    continue
                recognized += 1
                conversation_id = first_value(row, ("id", "conversation_id", "thread_id"))
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
                for message_index, message in enumerate(raw_messages):
                    if isinstance(message, dict):
                        messages.append(self._emit_message(source_path, message_index, conversation_id, message))
            if recognized == 0 and rows:
                raise AdapterError("unsupported_gemini_shape", "Gemini conversations contain neither entries nor messages arrays")
        elif isinstance(value, list):
            grouped: dict[str, list[tuple[int, Mapping[str, Any]]]] = {}
            for row_index, row in enumerate(value):
                if not isinstance(row, dict):
                    continue
                conversation_id = first_value(row, ("conversation_id", "thread_id", "chat_id"))
                if conversation_id is None:
                    raise AdapterError("unsupported_gemini_shape", "flat Gemini records require conversation_id/thread_id/chat_id")
                grouped.setdefault(str(conversation_id), []).append((row_index, row))
            for conversation_index, conversation_id in enumerate(sorted(grouped)):
                first_row = grouped[conversation_id][0][1]
                conversations.append(
                    conversation_record(
                        adapter_id=self.adapter_id,
                        source_vendor=self.source_vendor,
                        source_type=self.source_type,
                        source_path=source_path,
                        source_index=conversation_index,
                        conversation_id=conversation_id,
                        title=first_row.get("title"),
                    )
                )
                for row_index, row in grouped[conversation_id]:
                    messages.append(self._emit_message(source_path, row_index, conversation_id, row))
        else:
            raise AdapterError(
                "unsupported_gemini_shape",
                "Gemini adapter supports an object with conversations or a flat conversation-keyed array",
            )

        return sorted_result(conversations, messages)
