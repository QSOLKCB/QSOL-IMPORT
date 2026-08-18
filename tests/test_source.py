import json
import tarfile
import tempfile
import unittest
from pathlib import Path

from qsol_import.adapter_contract import AdapterError
from qsol_import.source import SourceArchive


POLICY_PATH = Path(__file__).parents[1] / "policies" / "conversation-first.json"


class SourceArchiveTests(unittest.TestCase):
    def test_oversized_first_tar_member_is_rejected_from_header_before_payload_scan(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            source = root / "hostile.tar"

            info = tarfile.TarInfo("huge.bin")
            info.size = 4096
            # Deliberately write only the valid header and omit the declared payload.
            # Incremental validation must reject from TarInfo.size before attempting
            # to advance through that missing/oversized payload.
            source.write_bytes(info.tobuf())

            policy = json.loads(POLICY_PATH.read_text())
            policy["archive_limits"]["max_member_uncompressed_bytes"] = 1024

            with self.assertRaises(AdapterError) as ctx:
                with SourceArchive(source, policy):
                    self.fail("oversized TAR unexpectedly opened")
            self.assertEqual(ctx.exception.code, "source_member_limit")

    def test_tar_entry_limit_is_checked_incrementally(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            source = root / "entries.tar"
            chunks = []
            for index in range(3):
                info = tarfile.TarInfo(f"item-{index}.txt")
                info.size = 0
                chunks.append(info.tobuf())
            source.write_bytes(b"".join(chunks) + b"\0" * 1024)

            policy = json.loads(POLICY_PATH.read_text())
            policy["archive_limits"]["max_entries"] = 2

            with self.assertRaises(AdapterError) as ctx:
                with SourceArchive(source, policy):
                    self.fail("over-entry-limit TAR unexpectedly opened")
            self.assertEqual(ctx.exception.code, "source_entry_limit")


if __name__ == "__main__":
    unittest.main()
