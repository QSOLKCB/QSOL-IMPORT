from __future__ import annotations

import re
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
from qsol_import.adapters._util import first_value, parse_json, parse_jsonl, sorted_result


_RESOURCE_RE = re.compile(
    r"^(issues|pull_requests|issue_comments|review_comments|pull_request_reviews)(?:[_-][0-9]+)?\.jsonl?$",
    re.IGNORECASE,
)


class GitHubAdapter:
    adapter_id = "github-migration-export/1"
    source_vendor = "github"
    source_type = "github.migration.export"

    def descriptor(self) -> dict[str, Any]:
        return adapter_descriptor(self.adapter_id, self.source_vendor, self.source_type)

    def discover(self, members: Sequence[SourceMember]) -> tuple[str, ...]:
        matches = sorted(
            (member.path for member in members if _RESOURCE_RE.fullmatch(PurePosixPath(member.path).name)),
            key=lambda value: value.encode("utf-8"),
        )
        if not matches:
            raise AdapterError("github_resource_discovery", "no supported GitHub migration JSON resources found")
        if not any(PurePosixPath(path).name.casefold().startswith(("issues", "pull_requests")) for path in matches):
            raise AdapterError("github_thread_discovery", "GitHub adapter requires issues or pull_requests resources")
        return tuple(matches)

    def member_disposition(self, path: str) -> MemberDisposition | None:
        parts = {part.casefold() for part in PurePosixPath(path).parts}
        if "attachments" in parts:
            return MemberDisposition("tombstone", "github_attachment_payload")
        if "repositories" in parts:
            return MemberDisposition("reject", "github_git_payload_out_of_scope")
        return None

    def member_reference_key(self, path: str) -> str | None:
        return PurePosixPath(path).name

    def _rows(self, path: str, raw: bytes) -> list[dict[str, Any]]:
        if PurePosixPath(path).suffix.casefold() == ".jsonl":
            value = parse_jsonl(raw)
        else:
            value = parse_json(raw, code="invalid_github_json")
        if isinstance(value, dict):
            for key in ("items", "records", "issues", "pull_requests", "issue_comments", "review_comments", "pull_request_reviews"):
                if isinstance(value.get(key), list):
                    value = value[key]
                    break
        if not isinstance(value, list):
            raise AdapterError("invalid_github_resource_shape", f"{path!r} must contain a JSON array")
        if not all(isinstance(item, dict) for item in value):
            raise AdapterError("invalid_github_resource_shape", f"{path!r} contains non-object records")
        return value

    @staticmethod
    def _resource(path: str) -> str:
        match = _RESOURCE_RE.fullmatch(PurePosixPath(path).name)
        if match is None:
            raise AdapterError("invalid_github_resource_name", f"unsupported GitHub resource path {path!r}")
        return match.group(1).casefold()

    @staticmethod
    def _login(row: Mapping[str, Any]) -> str | None:
        user = row.get("user")
        if isinstance(user, dict) and isinstance(user.get("login"), str):
            return user["login"]
        author = row.get("author")
        if isinstance(author, dict) and isinstance(author.get("login"), str):
            return author["login"]
        return author if isinstance(author, str) else None

    def parse(self, payloads: Mapping[str, bytes]) -> AdapterResult:
        resources = {path: self._rows(path, raw) for path, raw in payloads.items()}
        comments_by_parent: dict[str, list[tuple[str, int, dict[str, Any]]]] = {}

        for path, rows in resources.items():
            resource = self._resource(path)
            if resource not in {"issue_comments", "review_comments", "pull_request_reviews"}:
                continue
            for index, row in enumerate(rows):
                parent = first_value(
                    row,
                    (
                        "issue_id",
                        "pull_request_id",
                        "pull_request_review_id",
                        "subject_id",
                    ),
                )
                if parent is not None:
                    comments_by_parent.setdefault(str(parent), []).append((path, index, row))

        conversations: list[dict[str, Any]] = []
        messages: list[dict[str, Any]] = []
        conversation_index = 0

        for path in sorted(resources, key=lambda value: value.encode("utf-8")):
            resource = self._resource(path)
            if resource not in {"issues", "pull_requests"}:
                continue
            for row_index, row in enumerate(resources[path]):
                thread_id = first_value(row, ("id", "node_id", "number"))
                if thread_id is None:
                    raise AdapterError("github_missing_thread_id", f"{resource} record {row_index} lacks an id")
                title = row.get("title")
                if title is None:
                    number = row.get("number")
                    title = f"GitHub {resource[:-1].replace('_', ' ')} {number if number is not None else thread_id}"
                conversations.append(
                    conversation_record(
                        adapter_id=self.adapter_id,
                        source_vendor=self.source_vendor,
                        source_type=self.source_type,
                        source_path=path,
                        source_index=conversation_index,
                        conversation_id=thread_id,
                        title=title,
                        create_time=row.get("created_at"),
                        update_time=row.get("updated_at"),
                    )
                )
                conversation_index += 1
                body = row.get("body") if isinstance(row.get("body"), str) else ""
                if body:
                    messages.append(
                        message_record(
                            adapter_id=self.adapter_id,
                            source_vendor=self.source_vendor,
                            source_type=self.source_type,
                            source_path=path,
                            source_index=0,
                            source_message_id=f"{thread_id}:body",
                            conversation_id=thread_id,
                            role="author",
                            name=self._login(row),
                            text=body,
                            create_time=row.get("created_at"),
                            update_time=row.get("updated_at"),
                        )
                    )
                for comment_path, comment_index, comment in sorted(
                    comments_by_parent.get(str(thread_id), []),
                    key=lambda item: (
                        str(item[2].get("created_at") or ""),
                        item[0].encode("utf-8"),
                        item[1],
                    ),
                ):
                    text = comment.get("body") if isinstance(comment.get("body"), str) else ""
                    if not text:
                        continue
                    messages.append(
                        message_record(
                            adapter_id=self.adapter_id,
                            source_vendor=self.source_vendor,
                            source_type=self.source_type,
                            source_path=comment_path,
                            source_index=comment_index,
                            source_message_id=first_value(comment, ("id", "node_id")),
                            conversation_id=thread_id,
                            role="commenter",
                            name=self._login(comment),
                            text=text,
                            create_time=comment.get("created_at"),
                            update_time=comment.get("updated_at"),
                        )
                    )

        return sorted_result(conversations, messages)
