from __future__ import annotations

import tarfile
import zipfile
from contextlib import contextmanager
from pathlib import Path, PurePosixPath
from typing import BinaryIO, Iterator

from qsol_import.adapter_contract import AdapterError, SourceMember
from qsol_import.archive import validate_archive


def _validate_path(name: str) -> str:
    path = PurePosixPath(name)
    if (
        not name
        or name.startswith(("/", "\\"))
        or "\\" in name
        or path.is_absolute()
        or ".." in path.parts
        or any(ord(ch) < 32 or ord(ch) == 127 for ch in name)
    ):
        raise AdapterError("unsafe_source_path", f"unsafe source member path: {name!r}")
    return path.as_posix()


class SourceArchive:
    def __init__(self, path: Path, policy: dict):
        self.path = path
        self.policy = policy
        self.kind: str | None = None
        self._zip: zipfile.ZipFile | None = None
        self._tar: tarfile.TarFile | None = None
        self._zip_infos: dict[str, zipfile.ZipInfo] = {}
        self._tar_infos: dict[str, tarfile.TarInfo] = {}
        self._members: tuple[SourceMember, ...] = ()

    def __enter__(self) -> "SourceArchive":
        if zipfile.is_zipfile(self.path):
            self.kind = "zip"
            self._zip = zipfile.ZipFile(self.path, "r")
            validate_archive(self._zip, self.policy)
            infos = [info for info in self._zip.infolist() if not info.is_dir()]
            self._zip_infos = {info.filename: info for info in infos}
            self._members = tuple(
                SourceMember(info.filename, info.file_size)
                for info in sorted(infos, key=lambda item: item.filename.encode("utf-8"))
            )
            return self

        if tarfile.is_tarfile(self.path):
            self.kind = "tar"
            self._tar = tarfile.open(self.path, "r:*")
            self._validate_tar()
            return self

        if self.path.suffix.casefold() in {".json", ".jsonl"}:
            self.kind = "single"
            size = self.path.stat().st_size
            limit = int(self.policy["archive_limits"]["max_member_uncompressed_bytes"])
            if size > limit:
                raise AdapterError("source_member_limit", "single source file exceeds member limit")
            self._members = (SourceMember(self.path.name, size),)
            return self

        raise AdapterError("unsupported_source_container", "source must be ZIP, TAR/TAR.GZ, JSON, or JSONL")

    def __exit__(self, exc_type, exc, tb) -> None:
        if self._zip is not None:
            self._zip.close()
        if self._tar is not None:
            self._tar.close()

    def _validate_tar(self) -> None:
        assert self._tar is not None
        limits = self.policy["archive_limits"]
        max_entries = int(limits["max_entries"])
        max_member = int(limits["max_member_uncompressed_bytes"])
        max_total = int(limits["max_total_uncompressed_bytes"])
        max_ratio = float(limits["max_compression_ratio"])
        archive_bytes = self.path.stat().st_size

        seen_names: set[str] = set()
        seen_normalized: set[str] = set()
        total = 0
        entry_count = 0
        files: list[tarfile.TarInfo] = []

        # TarFile iteration is incremental: each TarInfo header is returned before
        # advancing over that member's payload. Enforce limits immediately so an
        # oversized early member or too many tiny entries cannot force a complete
        # decompression/materialization pass before rejection.
        for info in self._tar:
            entry_count += 1
            if entry_count > max_entries:
                raise AdapterError("source_entry_limit", "TAR source entry limit exceeded")

            normalized = _validate_path(info.name)
            if info.name in seen_names or normalized in seen_normalized:
                raise AdapterError("source_path_collision", f"duplicate/colliding TAR member: {info.name!r}")
            seen_names.add(info.name)
            seen_normalized.add(normalized)

            if info.isdir():
                continue
            if info.issym() or info.islnk() or info.isdev() or not info.isfile():
                raise AdapterError("unsafe_tar_member", f"non-regular TAR member rejected: {info.name!r}")
            if info.size > max_member:
                raise AdapterError("source_member_limit", f"TAR member too large: {info.name!r}")

            total += info.size
            if total > max_total:
                raise AdapterError("source_total_limit", "TAR source total uncompressed size limit exceeded")
            if archive_bytes > 0 and total / archive_bytes > max_ratio:
                raise AdapterError("source_compression_ratio", "TAR source compression ratio limit exceeded")
            files.append(info)

        self._tar_infos = {info.name: info for info in files}
        self._members = tuple(
            SourceMember(info.name, info.size)
            for info in sorted(files, key=lambda item: item.name.encode("utf-8"))
        )

    @property
    def members(self) -> tuple[SourceMember, ...]:
        return self._members

    def size(self, path: str) -> int:
        for member in self._members:
            if member.path == path:
                return member.size_bytes
        raise AdapterError("unknown_source_member", f"unknown source member: {path!r}")

    @contextmanager
    def open_member(self, path: str) -> Iterator[BinaryIO]:
        if self.kind == "zip":
            assert self._zip is not None
            info = self._zip_infos.get(path)
            if info is None:
                raise AdapterError("unknown_source_member", f"unknown ZIP member: {path!r}")
            with self._zip.open(info, "r") as handle:
                yield handle
            return
        if self.kind == "tar":
            assert self._tar is not None
            info = self._tar_infos.get(path)
            if info is None:
                raise AdapterError("unknown_source_member", f"unknown TAR member: {path!r}")
            handle = self._tar.extractfile(info)
            if handle is None:
                raise AdapterError("unreadable_source_member", f"cannot read TAR member: {path!r}")
            with handle:
                yield handle
            return
        if self.kind == "single" and path == self.path.name:
            with self.path.open("rb") as handle:
                yield handle
            return
        raise AdapterError("unknown_source_member", f"unknown source member: {path!r}")

    def read_bytes(self, path: str, max_bytes: int) -> bytes:
        declared = self.size(path)
        if declared > max_bytes:
            raise AdapterError("adapter_member_limit", f"adapter member too large: {path!r}")
        with self.open_member(path) as handle:
            data = handle.read(max_bytes + 1)
        if len(data) > max_bytes:
            raise AdapterError("adapter_member_limit", f"adapter member exceeded read limit: {path!r}")
        return data

    def head(self, path: str, size: int = 512) -> bytes:
        with self.open_member(path) as handle:
            return handle.read(size)
