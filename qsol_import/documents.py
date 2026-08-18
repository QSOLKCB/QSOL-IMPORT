from __future__ import annotations

import io
import stat
import zipfile
from dataclasses import dataclass
from pathlib import PurePosixPath
from xml.etree import ElementTree as ET


DOCX_MEDIA_TYPE = "application/vnd.openxmlformats-officedocument.wordprocessingml.document"
DOCX_TEXT_CONTRACT = "QSOL-IMPORT/DOCX-BODY-TEXT/1"
_WORD_NS = "{http://schemas.openxmlformats.org/wordprocessingml/2006/main}"


class DocumentExtractionError(ValueError):
    def __init__(self, code: str, message: str):
        super().__init__(message)
        self.code = code


@dataclass(frozen=True)
class DocumentExtraction:
    contract: str
    media_type: str
    text_bytes: bytes


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


def _render_word_document(xml_bytes: bytes) -> bytes:
    if b"<!DOCTYPE" in xml_bytes.upper() or b"<!ENTITY" in xml_bytes.upper():
        raise DocumentExtractionError("xml_doctype_rejected", "DOCX XML DTD/entity declarations are rejected")

    parts: list[str] = []
    try:
        for event, elem in ET.iterparse(io.BytesIO(xml_bytes), events=("end",)):
            tag = elem.tag
            if tag == _WORD_NS + "t" and elem.text:
                parts.append(elem.text)
            elif tag == _WORD_NS + "tab":
                parts.append("\t")
            elif tag in {_WORD_NS + "br", _WORD_NS + "cr"}:
                parts.append("\n")
            elif tag == _WORD_NS + "p":
                parts.append("\n")
            elem.clear()
    except ET.ParseError as exc:
        raise DocumentExtractionError("invalid_word_xml", "invalid word/document.xml") from exc

    text = "".join(parts).replace("\r\n", "\n").replace("\r", "\n")
    if text and not text.endswith("\n"):
        text += "\n"
    return text.encode("utf-8")


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
            xml_bytes = zf.read("word/document.xml")
    except zipfile.BadZipFile as exc:
        raise DocumentExtractionError("invalid_docx_zip", "invalid DOCX ZIP container") from exc

    return DocumentExtraction(
        contract=contract,
        media_type=media_type,
        text_bytes=_render_word_document(xml_bytes),
    )
