import json
import tempfile
import unittest
import zipfile
from pathlib import Path

from qsol_import.validation import validate_openai_snapshots


POLICY = Path(__file__).parents[1] / "policies" / "conversation-first.json"


def build_snapshot(path: Path, conversation_id: str) -> None:
    conversations = [
        {
            "id": conversation_id,
            "title": conversation_id,
            "mapping": {},
        }
    ]
    with zipfile.ZipFile(path, "w", compression=zipfile.ZIP_DEFLATED) as zf:
        zf.writestr("conversations.json", json.dumps(conversations))


class SnapshotValidationTests(unittest.TestCase):
    def test_two_snapshots_emit_path_free_determinism_receipt(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            first = root / "private-one.zip"
            second = root / "private-two.zip"
            build_snapshot(first, "one")
            build_snapshot(second, "two")

            report = validate_openai_snapshots([first, second], POLICY)
            self.assertEqual(report["snapshot_count"], 2)
            self.assertTrue(all(item["repeat_byte_identical"] for item in report["snapshots"]))
            self.assertFalse(report["source_paths_emitted"])
            self.assertFalse(report["source_bytes_persisted"])
            encoded = json.dumps(report)
            self.assertNotIn("private-one.zip", encoded)
            self.assertNotIn("private-two.zip", encoded)

    def test_validation_requires_multiple_snapshots(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            only = root / "only.zip"
            build_snapshot(only, "one")
            with self.assertRaises(ValueError):
                validate_openai_snapshots([only], POLICY)


if __name__ == "__main__":
    unittest.main()
