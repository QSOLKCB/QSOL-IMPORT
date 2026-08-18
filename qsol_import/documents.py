from __future__ import annotations

import io
import stat
import zipfile
from dataclasses import dataclass
from pathlib import PurePosixPath
from typing import BinaryIO
from xml.parsers import expat


DOCX_MEDIA_TYPE = "application/vnd.openxmlformats-officedocument.wordprocessingml.document"
DOCX_TEXT_CONTRACT = "QSOL-IMPORT/DOCX-BODY-TEXT/1"
_WORD_NS_URI = "http://schemas.openxmlformats.org/wordprocessingml/2006/main"
_XML_PARSE_CHUNK_BYTES = 64 * 1024


class DocumentExtractionError(ValueError):
    def __init__(self, code: str, message: str):
        super().__init__(message)
        self.code = code


@dataclass(frozen=True)
class DocumentExtraction:
    contract: str
    media_type: str
    text_bytes: bytes


class _BoundedTextBuffer:
    def __init__(self, max_bytes: int):
        if max_bytes <= 0:
            raise DocumentExtractionError(
                "invalid_extracted_text_limit",
                "DOCX extracted text limit must be positive",
            )
        self._max_bytes = max_bytes
        self._data = bytearray()

    def append(self, text: str) -> None:
        if not text:
            return
        normalized = text.replace("\r\n", "\n").replace("\r", "\n")
        encoded = normalized.encode("utf-8")
        if len(self._data) + len(encoded) > self._max_bytes:
            raise DocumentExtractionError(
                "extracted_text_limit",
                "DOCX extracted text limit exceeded",
            )
        self._data.extend(encoded)

    def finish(self) -> bytes:
        if self._data and not self._data.endswith(b"\n"):
            self.append("\n")
        return bytes(self._data)


def frozen_extractor_contract(media_type: str) -> str | None:
    if media_type == DOCX_MEDIA_TYPE:
        return DOCX_TEXT_CONTRACT
    return None


def _validate_inner_path(info: zipfile.ZipInfo) -> None:
    path = PurePosixPath(info.filename)
    if (
        info.filename.startswith(("/", "\\"))
        or "\\" in info.filename
        or path.is_absolute()
        or ".." in path.parts
        or any(ord(ch) < 32 or ord(ch) == 127 for ch in info.filename)
    ):
        raise DocumentExtractionError("unsafe_inner_path", f"unsafe DOCX member path: {info.filename!r}")
    unix_mode = (info.external_attr >> 16) & 0xFFFF
    if unix_mode and stat.S_ISLNK(unix_mode):
        raise DocumentExtractionError("inner_symlink", f"DOCX symlink member rejected: {info.filename!r}")
    if info.flag_bits & 0x1:
        raise DocumentExtractionError("encrypted_inner_member", f"encrypted DOCX member rejected: {info.filename!r}")


def _validate_docx_archive(zf: zipfile.ZipFile, policy: dict) -> None:
    limits = policy.get("inner_archive_limits", {})
    max_members = int(limits.get("max_entries", 4096))
    max_member = int(limits.get("max_member_uncompressed_bytes", 32 * 1024 * 1024))
    max_total = int(limits.get("max_total_uncompressed_bytes", 128 * 1024 * 1024))
    max_ratio = float(limits.get("max_compression_ratio", 200.0))

    members = zf.infolist()
    if len(members) > max_members:
        raise DocumentExtractionError("inner_entry_limit", "DOCX inner entry limit exceeded")

    seen: set[str] = set()
    total = 0
    for info in members:
        _validate_inner_path(info)
        if info.filename in seen:
            raise DocumentExtractionError("duplicate_inner_member", f"duplicate DOCX member: {info.filename!r}")
        seen.add(info.filename)
        total += info.file_size
        if info.file_size > max_member:
            raise DocumentExtractionError("inner_member_limit", f"oversized DOCX member: {info.filename!r}")
        if info.compress_size > 0 and info.file_size / info.compress_size > max_ratio:
            raise DocumentExtractionError("inner_compression_ratio", f"DOCX compression ratio exceeded: {info.filename!r}")
    if total > max_total:
        raise DocumentExtractionError("inner_total_limit", "DOCX inner uncompressed size limit exceeded")


def _word_tag(local_name: str) -> str:
    return f"{_WORD_NS_URI}}}{local_name}"


def _render_word_document(handle: BinaryIO, policy: dict) -> bytes:
    max_text_bytes = int(policy.get("max_extracted_text_bytes", 32 * 1024 * 1024))
    output = _BoundedTextBuffer(max_text_bytes)
    text_depth = 0

    parser = expat.ParserCreate(namespace_separator="}")

    def reject_dtd(*_args) -> None:
        raise DocumentExtractionError(
            "xml_doctype_rejected",
            "DOCX XML DTD/entity declarations are rejected",
        )

    def reject_external_entity(*_args) -> int:
        raise DocumentExtractionError(
            "xml_doctype_rejected",
            "DOCX XML external entities are rejected",
        )

    def start_element(name: str, _attrs: dict[str, str]) -> None:
        nonlocal text_depth
        if name == _word_tag("t"):
            text_depth += 1
        elif name == _word_tag("tab"):
            output.append("\t")
        elif name in {_word_tag("br"), _word_tag("cr")}:
            output.append("\n")

    def end_element(name: str) -> None:
        nonlocal text_depth
        if name == _word_tag("t"):
            if text_depth > 0:
                text_depth -= 1
        elif name == _word_tag("p"):
            output.append("\n")

    def character_data(data: str) -> None:
        if text_depth:
            output.append(data)

    # Expat performs encoding-aware XML tokenization, so DTD/entity rejection
    # works for supported XML encodings instead of relying on ASCII byte scans.
    parser.StartDoctypeDeclHandler = reject_dtd
    parser.EntityDeclHandler = reject_dtd
    parser.UnparsedEntityDeclHandler = reject_dtd
    parser.ExternalEntityRefHandler = reject_external_entity
    parser.StartElementHandler = start_element
    parser.EndElementHandler = end_element
    parser.CharacterDataHandler = character_data
    parser.SetParamEntityParsing(expat.XML_PARAM_ENTITY_PARSING_NEVER)

    try:
        while chunk := handle.read(_XML_PARSE_CHUNK_BYTES):
            parser.Parse(chunk, False)
        parser.Parse(b"", True)
    except DocumentExtractionError:
        raise
    except expat.ExpatError as exc:
        raise DocumentExtractionError("invalid_word_xml", "invalid word/document.xml") from exc

    return output.finish()


def extract_document_text(data: bytes, media_type: str, policy: dict) -> DocumentExtraction:
    contract = frozen_extractor_contract(media_type)
    if contract is None:
        raise DocumentExtractionError("unsupported_media_type", f"no frozen text extractor for {media_type!r}")

    if media_type != DOCX_MEDIA_TYPE:
        raise DocumentExtractionError("unsupported_media_type", f"unsupported frozen extractor media type: {media_type!r}")

    try:
        with zipfile.ZipFile(io.BytesIO(data), "r") as zf:
            _validate_docx_archive(zf, policy)
            names = set(zf.namelist())
            required = {"[Content_Types].xml", "word/document.xml"}
            if not required.issubset(names):
                raise DocumentExtractionError("missing_docx_member", "DOCX is missing required package members")
            with zf.open("word/document.xml", "r") as handle:
                text_bytes = _render_word_document(handle, policy)
    except zipfile.BadZipFile as exc:
        raise DocumentExtractionError("invalid_docx_zip", "invalid DOCX ZIP container") from exc

    return DocumentExtraction(
        contract=contract,
        media_type=media_type,
        text_bytes=text_bytes,
    )
