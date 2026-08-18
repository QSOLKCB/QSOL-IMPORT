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


class ClaudeAdapter:
    adapter_id = "anthropic-claude-export/1"
    source_vendor = "anthropic"
    source_type = "anthropic.claude.export"

    def descriptor(self) -> dict[str, Any]:
        return adapter_descriptor(self.adapter_id, self.source_vendor, self.source_type)

    def discover(self, members: Sequence[SourceMember]) -> tuple[str, ...]:
        matches = [member.path for member in members if PurePosixPath(member.path).name.casefold() == "conversations.json"]
        if len(matches) != 1:
            raise AdapterError("claude_conversation_cardinality", f"Claude adapter requires exactly one conversations.json, found {len(matches)}")
        return (matches[0],)

    def member_disposition(self, path: str) -> MemberDisposition | None:
        if PurePosixPath(path).name.casefold() in {"users.json", "user.json", "account.json"}:
            return MemberDisposition("reject", "claude_account_metadata_out_of_scope")
        return None

    def member_reference_key(self, path: str) -> str | None:
        return PurePosixPath(path).name

    def parse(self, payloads: Mapping[str, bytes]) -> AdapterResult:
        source_path, raw = next(iter(payloads.items()))
        value = parse_json(raw, code="invalid_claude_json")
        if isinstance(value, dict) and isinstance(value.get("conversations"), list):
            raw_conversations = value["conversations"]
        elif isinstance(value, list):
            raw_conversations = value
        else:
            raise AdapterError("unsupported_claude_shape", "Claude conversations.json must be a list or contain conversations")

        conversations: list[dict[str, Any]] = []
        messages: list[dict[str, Any]] = []
        attachment_index: dict[str, list[dict[str, Any]]] = {}
        recognized = 0

        for conversation_index, row in enumerate(raw_conversations):
            if not isinstance(row, dict):
                continue
            raw_messages = row.get("chat_messages")
            if not isinstance(raw_messages, list):
                continue
            recognized += 1
            conversation_id = first_value(row, ("uuid", "id", "conversation_id"))
            conversations.append(
                conversation_record(
                    adapter_id=self.adapter_id,
                    source_vendor=self.source_vendor,
                    source_type=self.source_type,
                    source_path=source_path,
                    source_index=conversation_index,
                    conversation_id=conversation_id,
                    title=first_value(row, ("name", "title")),
                    create_time=first_value(row, ("created_at", "create_time")),
                    update_time=first_value(row, ("updated_at", "update_time")),
                )
            )
            for message_index, message in enumerate(raw_messages):
                if not isinstance(message, dict):
                    continue
                refs = attachment_refs(first_value(message, ("attachments", "files")))
                record = message_record(
                    adapter_id=self.adapter_id,
                    source_vendor=self.source_vendor,
                    source_type=self.source_type,
                    source_path=source_path,
                    source_index=message_index,
                    source_message_id=first_value(message, ("uuid", "id", "message_id")),
                    conversation_id=conversation_id,
                    role=first_value(message, ("sender", "role", "author")),
                    text=first_value(message, ("text", "content", "message")),
                    create_time=first_value(message, ("created_at", "create_time")),
                    update_time=first_value(message, ("updated_at", "update_time")),
                    attachment_refs=refs,
                )
                messages.append(record)
                for ref in refs:
                    attachment_index.setdefault(ref, []).append(
                        {
                            "conversation_id": record["conversation_id"],
                            "source_message_id": record["source_message_id"],
                            "source_path": source_path,
                            "source_index": message_index,
                        }
                    )

        if recognized == 0 and raw_conversations:
            raise AdapterError("unsupported_claude_shape", "no conversation with a chat_messages array was found")
        return sorted_result(conversations, messages, attachment_index)
