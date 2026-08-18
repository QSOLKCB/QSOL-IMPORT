from __future__ import annotations

import stat
import zipfile
from pathlib import PurePosixPath


class UnsafeArchiveError(ValueError):
    pass


def validate_member(info: zipfile.ZipInfo) -> None:
    path = PurePosixPath(info.filename)
    if (
        info.filename.startswith(("/", "\\"))
        or "\\" in info.filename
        or path.is_absolute()
        or ".." in path.parts
    ):
        raise UnsafeArchiveError(f"unsafe archive path: {info.filename!r}")
    unix_mode = (info.external_attr >> 16) & 0xFFFF
    if unix_mode and stat.S_ISLNK(unix_mode):
        raise UnsafeArchiveError(f"symlink member rejected: {info.filename!r}")


def validate_archive(zf: zipfile.ZipFile, policy: dict) -> None:
    members = zf.infolist()
    limits = policy["archive_limits"]
    if len(members) > int(limits["max_entries"]):
        raise UnsafeArchiveError("archive entry limit exceeded")

    seen_names: set[str] = set()
    total_uncompressed = 0
    for info in members:
        validate_member(info)
        if info.filename in seen_names:
            raise UnsafeArchiveError(f"duplicate archive member rejected: {info.filename!r}")
        seen_names.add(info.filename)

        total_uncompressed += info.file_size
        if info.file_size > int(limits["max_member_uncompressed_bytes"]):
            raise UnsafeArchiveError(f"member too large: {info.filename!r}")
        if (
            info.compress_size > 0
            and info.file_size / info.compress_size > float(limits["max_compression_ratio"])
        ):
            raise UnsafeArchiveError(f"compression ratio limit exceeded: {info.filename!r}")
    if total_uncompressed > int(limits["max_total_uncompressed_bytes"]):
        raise UnsafeArchiveError("archive total uncompressed size limit exceeded")
