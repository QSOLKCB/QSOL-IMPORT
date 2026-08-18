from __future__ import annotations

import re
from collections import defaultdict
from dataclasses import dataclass
from pathlib import PurePosixPath
from typing import Any, Iterable, MutableMapping, MutableSet

from qsol_import.canonical import loads_strict


CONVERSATION_FILE_RE = re.compile(
    r"^(?P<stem>conversations?)(?:[-_]?(?P<number>[0-9]+))?\.json$",
    re.IGNORECASE,
)
MEDIA_NAME_RE = re.compile(
    r"([^/\\\s\"']+\.(?:wav|wave|mp3|m4a|aac|flac|ogg|opus|mp4|mov|m4v|webm|mkv|png|jpe?g|gif|webp|pdf|docx|pptx))",
    re.IGNORECASE,
)


@dataclass(frozen=True)
class ConversationContext:
    conversation_id: str | None
    title: str | None
    source_file: str
    source_index: int


def is_conversation_file(path: str) -> bool:
    return bool(CONVERSATION_FILE_RE.fullmatch(path))


def conversation_file_sort_key(path: str) -> tuple[int, bytes]:
    match = CONVERSATION_FILE_RE.fullmatch(path)
    if match is None:
        raise ValueError(f"not a conversation file: {path!r}")
    number = int(match.group("number")) if match.group("number") is not None else -1
    return number, path.encode("utf-8")


def load_conversations(data: bytes) -> list[dict[str, Any]]:
    value = loads_strict(data)
    if isinstance(value, list):
        items = value
    elif isinstance(value, dict) and isinstance(value.get("conversations"), list):
        items = value["conversations"]
    else:
        raise ValueError("conversation JSON must be a list or object containing a conversations list")
    if not all(isinstance(item, dict) for item in items):
        raise ValueError("conversation list contains non-object entries")
    return items


def context_for(conversation: dict[str, Any], source_file: str, source_index: int) -> ConversationContext:
    conversation_id = conversation.get("id") or conversation.get("conversation_id")
    title = conversation.get("title")
    return ConversationContext(
        str(conversation_id) if conversation_id is not None else None,
        str(title) if title is not None else None,
        source_file,
        source_index,
    )


def _normalized_time(value: Any) -> int | float | str | None:
    if value is None or isinstance(value, str):
        return value
    if isinstance(value, bool):
        return None
    if isinstance(value, (int, float)):
        return value
    return None


def iter_message_records(
    context: ConversationContext,
    conversation: dict[str, Any],
) -> Iterable[dict[str, Any]]:
    mapping = conversation.get("mapping")
    if not isinstance(mapping, dict):
        return

    for source_node_index, (node_id, node) in enumerate(mapping.items()):
        if not isinstance(node, dict):
            continue
        message = node.get("message")
        if not isinstance(message, dict):
            continue

        author = message.get("author")
        if not isinstance(author, dict):
            author = {}
        content = message.get("content")
        if not isinstance(content, dict):
            content = {}

        parent = node.get("parent")
        children = node.get("children")
        if not isinstance(children, list):
            children = []

        message_id = message.get("id")
        yield {
            "protocol": "QSOL-IMPORT/OPENAI-MESSAGE/1",
            "source_file": context.source_file,
            "source_index": context.source_index,
            "source_node_index": source_node_index,
            "source_node_id": str(node_id),
            "conversation_id": context.conversation_id,
            "conversation_title": context.title,
            "source_message_id": str(message_id) if message_id is not None else None,
            "parent_node_id": str(parent) if parent is not None else None,
            "children_node_ids": [str(child) for child in children],
            "author_role": str(author["role"]) if author.get("role") is not None else None,
            "author_name": str(author["name"]) if author.get("name") is not None else None,
            "create_time": _normalized_time(message.get("create_time")),
            "update_time": _normalized_time(message.get("update_time")),
            "status": str(message["status"]) if message.get("status") is not None else None,
            "recipient": str(message["recipient"]) if message.get("recipient") is not None else None,
            "content_type": str(content["content_type"]) if content.get("content_type") is not None else None,
            "message": message,
        }


def iter_strings(value: Any) -> Iterable[str]:
    if isinstance(value, str):
        yield value
    elif isinstance(value, dict):
        for key in sorted(value):
            yield from iter_strings(value[key])
    elif isinstance(value, list):
        for item in value:
            yield from iter_strings(item)


def update_attachment_reference_index(
    refs: MutableMapping[str, MutableSet[ConversationContext]],
    context: ConversationContext,
    conversation: dict[str, Any],
) -> None:
    for text in iter_strings(conversation):
        for match in MEDIA_NAME_RE.finditer(text):
            refs.setdefault(PurePosixPath(match.group(1)).name.lower(), set()).add(context)


def finalize_attachment_reference_index(
    refs: MutableMapping[str, MutableSet[ConversationContext]],
) -> dict[str, list[ConversationContext]]:
    return {
        key: sorted(value, key=lambda c: (c.source_file, c.source_index))
        for key, value in refs.items()
    }


def build_attachment_reference_index(
    conversations: list[tuple[ConversationContext, dict[str, Any]]],
) -> dict[str, list[ConversationContext]]:
    refs: dict[str, set[ConversationContext]] = defaultdict(set)
    for context, conversation in conversations:
        update_attachment_reference_index(refs, context, conversation)
    return finalize_attachment_reference_index(refs)


def semantic_context_for_path(
    path: str,
    kind: str,
    refs: dict[str, list[ConversationContext]],
) -> dict[str, Any]:
    basename = PurePosixPath(path).name
    matches = refs.get(basename.lower(), [])
    result: dict[str, Any] = {
        "label": f"{kind} export asset: {basename}",
        "label_source": "deterministic_path_context",
    }
    if matches:
        first = matches[0]
        result.update(
            {
                "conversation_id": first.conversation_id,
                "conversation_title": first.title,
                "source_file": first.source_file,
                "source_index": first.source_index,
                "reference_count": len(matches),
                "label": f"{kind} referenced by conversation {first.title or first.conversation_id or first.source_index}: {basename}",
            }
        )
    return result
