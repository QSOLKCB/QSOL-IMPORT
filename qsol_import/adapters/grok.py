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
from qsol_import.adapters._util import parse_json, sorted_result


BACKEND_BASENAME = "prod-grok-backend.json"
DENY_BASENAMES = {"prod-mc-auth-mgmt-api.json", "prod-mc-billing.json"}
ASSET_PATH_PARTS = {"prod-mc-asset-server", "canvas_thumbnails"}


class GrokAdapter:
    adapter_id = "xai-grok-export/1"
    source_vendor = "xai"
    source_type = "xai.grok.export"

    def descriptor(self) -> dict[str, Any]:
        return adapter_descriptor(self.adapter_id, self.source_vendor, self.source_type)

    def discover(self, members: Sequence[SourceMember]) -> tuple[str, ...]:
        matches = [member.path for member in members if PurePosixPath(member.path).name == BACKEND_BASENAME]
        if len(matches) != 1:
            raise AdapterError(
                "grok_backend_cardinality",
                f"expected exactly one {BACKEND_BASENAME}, found {len(matches)}",
            )
        return (matches[0],)

    def member_disposition(self, path: str) -> MemberDisposition | None:
        pure = PurePosixPath(path)
        if pure.name in DENY_BASENAMES:
            return MemberDisposition("reject", "xai_sensitive_account_source")
        if any(part in ASSET_PATH_PARTS for part in pure.parts):
            return MemberDisposition("tombstone", "xai_binary_asset_policy")
        return None

    def member_reference_key(self, path: str) -> str | None:
        parts = PurePosixPath(path).parts
        if "prod-mc-asset-server" in parts:
            index = parts.index("prod-mc-asset-server")
            if index + 1 < len(parts):
                return parts[index + 1]
        if "canvas_thumbnails" in parts:
            return PurePosixPath(path).stem
        return None

    def parse(self, payloads: Mapping[str, bytes]) -> AdapterResult:
        if len(payloads) != 1:
            raise AdapterError("grok_backend_cardinality", "Grok adapter requires exactly one backend payload")
        source_path, raw = next(iter(payloads.items()))
        data = parse_json(raw, code="invalid_grok_backend_json")
        if not isinstance(data, dict):
            raise AdapterError("invalid_grok_backend_shape", "prod-grok-backend.json must contain an object")
        raw_conversations = data.get("conversations")
        if not isinstance(raw_conversations, list):
            raise AdapterError("invalid_grok_conversations", "Grok backend conversations must be an array")

        conversations: list[dict[str, Any]] = []
        messages: list[dict[str, Any]] = []
        attachment_index: dict[str, list[dict[str, Any]]] = {}

        for conversation_index, wrapper in enumerate(raw_conversations):
            if not isinstance(wrapper, dict):
                continue
            conversation = wrapper.get("conversation")
            if not isinstance(conversation, dict):
                raise AdapterError(
                    "invalid_grok_conversation_wrapper",
                    f"conversation wrapper {conversation_index} is missing its conversation object",
                )
            conversation_id = conversation.get("id")
            conversations.append(
                conversation_record(
                    adapter_id=self.adapter_id,
                    source_vendor=self.source_vendor,
                    source_type=self.source_type,
                    source_path=source_path,
                    source_index=conversation_index,
                    conversation_id=conversation_id,
                    title=conversation.get("title"),
                    create_time=conversation.get("create_time"),
                    update_time=conversation.get("modify_time"),
                )
            )

            responses = wrapper.get("responses")
            if not isinstance(responses, list):
                responses = []
            for response_index, wrapped_response in enumerate(responses):
                if not isinstance(wrapped_response, dict):
                    continue
                response = wrapped_response.get("response")
                if not isinstance(response, dict):
                    continue
                refs = sorted(
                    item
                    for item in (response.get("file_attachments") or [])
                    if isinstance(item, str) and item
                ) if isinstance(response.get("file_attachments"), list) else []
                children = response.get("children") if isinstance(response.get("children"), list) else []
                record = message_record(
                    adapter_id=self.adapter_id,
                    source_vendor=self.source_vendor,
                    source_type=self.source_type,
                    source_path=source_path,
                    source_index=response_index,
                    source_message_id=response.get("_id"),
                    conversation_id=response.get("conversation_id") or conversation_id,
                    role=response.get("sender"),
                    text=response.get("message") if isinstance(response.get("message"), str) else "",
                    create_time=response.get("create_time"),
                    parent_id=response.get("parent_response_id"),
                    children=children,
                    model=response.get("model"),
                    status="partial" if bool(response.get("partial")) else None,
                    attachment_refs=refs,
                )
                messages.append(record)
                for ref in refs:
                    attachment_index.setdefault(ref, []).append(
                        {
                            "conversation_id": record["conversation_id"],
                            "source_message_id": record["source_message_id"],
                            "source_path": source_path,
                            "source_index": response_index,
                        }
                    )

        return sorted_result(conversations, messages, attachment_index)
