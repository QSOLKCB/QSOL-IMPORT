import json
import tempfile
import unittest
from pathlib import Path

from qsol_import.adapter_pipeline import import_with_adapter
from qsol_import.adapters.generic import GenericAdapter


POLICY = Path(__file__).parents[1] / "policies" / "conversation-first.json"


class AdapterPipelineTests(unittest.TestCase):
    def test_plain_json_import_is_byte_identical(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            source = root / "conversation.json"
            source.write_text(
                json.dumps(
                    {
                        "conversations": [
                            {
                                "id": "conv",
                                "title": "determinism",
                                "messages": [
                                    {"id": "m1", "role": "user", "text": "hello"},
                                    {"id": "m2", "role": "assistant", "text": "world"},
                                ],
                            }
                        ]
                    }
                ),
                encoding="utf-8",
            )
            receipt_a = import_with_adapter(source, root / "a", POLICY, GenericAdapter())
            receipt_b = import_with_adapter(source, root / "b", POLICY, GenericAdapter())
            self.assertEqual(receipt_a, receipt_b)
            a_files = {
                path.relative_to(root / "a").as_posix(): path.read_bytes()
                for path in (root / "a").rglob("*")
                if path.is_file()
            }
            b_files = {
                path.relative_to(root / "b").as_posix(): path.read_bytes()
                for path in (root / "b").rglob("*")
                if path.is_file()
            }
            self.assertEqual(a_files, b_files)
            self.assertEqual(receipt_a["provenance_records"], 1)
            self.assertEqual(receipt_a["files_seen"], 1)

    def test_unknown_generic_shape_fails_without_committing_output(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            source = root / "bad.json"
            source.write_text('{"not_conversations":true}', encoding="utf-8")
            with self.assertRaises(ValueError):
                import_with_adapter(source, root / "out", POLICY, GenericAdapter())
            self.assertFalse((root / "out").exists())


if __name__ == "__main__":
    unittest.main()
