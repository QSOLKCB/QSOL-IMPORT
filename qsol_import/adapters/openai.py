from __future__ import annotations

import re
from collections import defaultdict
from dataclasses import dataclass
from pathlib import PurePosixPath
from typing import Any, Iterable

from qsol_import.canonical import loads_strict


CONVERSATION_FILE_RE = re.compile(r"(?:^|/)(?:conversations(?:[-_]?[0-9]+)?|conversation[-_]?[0-9]+)\.json$", re.IGNORECASE)
MEDIA_NAME_RE = re.compile(r"([^/\\\s\"']+\.(?:wav|wave|mp3|m4a|aac|flac|ogg|opus|mp4|mov|m4v|webm|mkv|png|jpe?g|gif|webp|pdf|docx|pptx))", re.IGNORECASE)


@dataclass(frozen=True)
class ConversationContext:
    conversation_id: str | None
    title: str | None
    source_file: str
    source_index: int


def is_conversation_file(path: str) -> bool:
    return bool(CONVERSATION_FILE_RE.search(path))


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


def iter_strings(value: Any) -> Iterable[str]:
    if isinstance(value, str):
        yield value
    elif isinstance(value, dict):
        for key in sorted(value):
            yield from iter_strings(value[key])
    elif isinstance(value, list):
        for item in value:
            yield from iter_strings(item)


def build_attachment_reference_index(conversations: list[tuple[ConversationContext, dict[str, Any]]]) -> dict[str, list[ConversationContext]]:
    refs: dict[str, set[ConversationContext]] = defaultdict(set)
    for ctx, conversation in conversations:
        for text in iter_strings(conversation):
            for match in MEDIA_NAME_RE.finditer(text):
                refs[PurePosixPath(match.group(1)).name.lower()].add(ctx)
    return {key: sorted(value, key=lambda c: (c.source_file, c.source_index)) for key, value in refs.items()}


def semantic_context_for_path(path: str, kind: str, refs: dict[str, list[ConversationContext]]) -> dict[str, Any]:
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
