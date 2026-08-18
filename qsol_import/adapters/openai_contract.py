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
from qsol_import.adapters._util import sorted_result
from qsol_import.adapters.openai import (
    context_for,
    conversation_file_sort_key,
    is_conversation_file,
    iter_message_records,
    iter_strings,
    load_conversations,
    reference_keys_for_path,
    reference_keys_from_text,
)


def _raw_reference_value(key: str) -> str:
    return key.split(":", 1)[1]


def _message_attachment_refs(message: dict[str, Any]) -> list[str]:
    refs: set[str] = set()
    for text in iter_strings(message):
        for key in reference_keys_from_text(text):
            refs.add(_raw_reference_value(key))
    return sorted(refs)


class OpenAIContractAdapter:
    adapter_id = "openai-export-common/1"
    source_vendor = "openai"
    source_type = "openai.export"

    def descriptor(self) -> dict[str, Any]:
        return adapter_descriptor(self.adapter_id, self.source_vendor, self.source_type)

    def discover(self, members: Sequence[SourceMember]) -> tuple[str, ...]:
        matches = [member.path for member in members if is_conversation_file(member.path)]
        if not matches:
            raise AdapterError("openai_conversation_discovery", "no OpenAI conversation JSON members found")
        return tuple(sorted(matches, key=conversation_file_sort_key))

    def member_disposition(self, path: str) -> MemberDisposition | None:
        return None

    def member_reference_key(self, path: str) -> str | None:
        keys = reference_keys_for_path(path)
        identifier_keys = sorted(key for key in keys if key.startswith("id:"))
        if identifier_keys:
            return _raw_reference_value(identifier_keys[0])
        return PurePosixPath(path).name.lower()

    def parse(self, payloads: Mapping[str, bytes]) -> AdapterResult:
        conversations: list[dict[str, Any]] = []
        messages: list[dict[str, Any]] = []
        attachment_index: dict[str, list[dict[str, Any]]] = {}
        global_conversation_index = 0

        for source_path in sorted(payloads, key=conversation_file_sort_key):
            items = load_conversations(payloads[source_path])
            for local_index, conversation in enumerate(items):
                ctx = context_for(conversation, source_path, local_index)
                conversations.append(
                    conversation_record(
                        adapter_id=self.adapter_id,
                        source_vendor=self.source_vendor,
                        source_type=self.source_type,
                        source_path=source_path,
                        source_index=global_conversation_index,
                        conversation_id=ctx.conversation_id,
                        title=ctx.title,
                        create_time=conversation.get("create_time"),
                        update_time=conversation.get("update_time"),
                    )
                )
                global_conversation_index += 1
                for legacy in iter_message_records(ctx, conversation):
                    message = legacy["message"]
                    content = message.get("content") if isinstance(message.get("content"), dict) else {}
                    text_value: Any = content.get("parts")
                    if text_value is None:
                        text_value = content.get("text")
                    refs = _message_attachment_refs(message)
                    record = message_record(
                        adapter_id=self.adapter_id,
                        source_vendor=self.source_vendor,
                        source_type=self.source_type,
                        source_path=source_path,
                        source_index=legacy["source_node_index"],
                        source_message_id=legacy["source_message_id"],
                        conversation_id=ctx.conversation_id,
                        role=legacy["author_role"],
                        name=legacy["author_name"],
                        text=text_value,
                        create_time=legacy["create_time"],
                        update_time=legacy["update_time"],
                        parent_id=legacy["parent_node_id"],
                        children=legacy["children_node_ids"],
                        status=legacy["status"],
                        attachment_refs=refs,
                    )
                    messages.append(record)
                    for ref in refs:
                        attachment_index.setdefault(ref, []).append(
                            {
                                "conversation_id": record["conversation_id"],
                                "source_message_id": record["source_message_id"],
                                "source_path": source_path,
                                "source_index": record["source_index"],
                            }
                        )

        return sorted_result(conversations, messages, attachment_index)
