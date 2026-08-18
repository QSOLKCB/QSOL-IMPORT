from __future__ import annotations

from dataclasses import dataclass
from pathlib import PurePosixPath


TEXT_EXTENSIONS = {
    ".json", ".jsonl", ".txt", ".md", ".markdown", ".csv", ".tsv", ".html", ".htm",
    ".xml", ".yaml", ".yml", ".toml", ".ini", ".cfg", ".log", ".py", ".js", ".ts",
    ".tsx", ".jsx", ".css", ".scss", ".c", ".h", ".cc", ".cpp", ".hpp", ".rs", ".go",
    ".java", ".kt", ".kts", ".swift", ".sh", ".bash", ".zsh", ".fish", ".ps1", ".sql",
    ".lean", ".adb", ".ads", ".f", ".f90", ".f95", ".cob", ".cbl",
}
DOCUMENT_EXTENSIONS = {".pdf", ".docx", ".pptx", ".odt", ".ods", ".odp", ".rtf"}
AUDIO_EXTENSIONS = {".wav", ".wave", ".mp3", ".m4a", ".aac", ".flac", ".ogg", ".opus", ".aiff", ".aif"}
VIDEO_EXTENSIONS = {".mp4", ".mov", ".m4v", ".webm", ".mkv", ".avi", ".mpeg", ".mpg"}
IMAGE_EXTENSIONS = {".png", ".jpg", ".jpeg", ".gif", ".webp", ".bmp", ".tif", ".tiff", ".svg"}
EXECUTABLE_EXTENSIONS = {".exe", ".dll", ".so", ".dylib", ".msi", ".apk", ".appimage", ".bin"}


@dataclass(frozen=True)
class FileClassification:
    kind: str
    media_type: str
    decision: str
    reason: str


def sniff_media_type(head: bytes, extension: str) -> tuple[str, str] | None:
    if len(head) >= 12 and head[:4] == b"RIFF" and head[8:12] == b"WAVE":
        return "audio", "audio/wav"
    if head.startswith(b"fLaC"):
        return "audio", "audio/flac"
    if head.startswith(b"OggS"):
        return "audio", "audio/ogg"
    if head.startswith(b"ID3") or (len(head) >= 2 and head[0] == 0xFF and head[1] & 0xE0 == 0xE0):
        return "audio", "audio/mpeg"
    if len(head) >= 12 and head[4:8] == b"ftyp":
        brand = head[8:12].lower()
        if extension in {".m4a", ".aac"} or brand in {b"m4a ", b"m4b ", b"f4a "}:
            return "audio", "audio/mp4"
        return "video", "video/mp4"
    if head.startswith(b"\x1aE\xdf\xa3"):
        return ("video", "video/webm") if extension == ".webm" else ("video", "video/x-matroska")
    if head.startswith(b"\x89PNG\r\n\x1a\n"):
        return "image", "image/png"
    if head.startswith(b"\xff\xd8\xff"):
        return "image", "image/jpeg"
    if head.startswith((b"GIF87a", b"GIF89a")):
        return "image", "image/gif"
    if head.startswith(b"%PDF-"):
        return "document", "application/pdf"
    if head.startswith(b"PK\x03\x04"):
        if extension == ".docx":
            return "document", "application/vnd.openxmlformats-officedocument.wordprocessingml.document"
        if extension == ".pptx":
            return "document", "application/vnd.openxmlformats-officedocument.presentationml.presentation"
        return "archive", "application/zip"
    if head.startswith(b"MZ"):
        return "executable", "application/vnd.microsoft.portable-executable"
    return None


def classify_file(path: str, size_bytes: int, head: bytes, policy: dict) -> FileClassification:
    extension = PurePosixPath(path).suffix.lower()
    sniffed = sniff_media_type(head, extension)
    kind, media_type = sniffed or ("unknown", "application/octet-stream")

    if sniffed is None:
        if extension in TEXT_EXTENSIONS:
            kind, media_type = "structured_text", "text/plain"
        elif extension in DOCUMENT_EXTENSIONS:
            kind, media_type = "document", "application/octet-stream"
        elif extension in AUDIO_EXTENSIONS:
            kind, media_type = "audio", "application/octet-stream"
        elif extension in VIDEO_EXTENSIONS:
            kind, media_type = "video", "application/octet-stream"
        elif extension in IMAGE_EXTENSIONS:
            kind, media_type = "image", "application/octet-stream"
        elif extension in EXECUTABLE_EXTENSIONS:
            kind, media_type = "executable", "application/octet-stream"

    if kind in {"audio", "video"}:
        return FileClassification(kind, media_type, policy[kind]["default"], "media_policy")
    if kind == "image":
        limit = int(policy["images"]["keep_under_bytes"])
        return FileClassification(kind, media_type, "keep" if size_bytes <= limit else "tombstone", "image_size_policy")
    if kind == "document":
        return FileClassification(kind, media_type, "extract", "document_policy")
    if kind == "structured_text":
        return FileClassification(kind, media_type, "keep", "structured_text_policy")
    if kind == "executable":
        return FileClassification(kind, media_type, "reject", "executable_policy")
    if kind == "archive":
        return FileClassification(kind, media_type, "reject", "nested_archive_policy")

    opaque_limit = int(policy["opaque"]["keep_under_bytes"])
    decision = "keep" if size_bytes <= opaque_limit else "tombstone"
    return FileClassification(kind, media_type, decision, "opaque_size_policy")
