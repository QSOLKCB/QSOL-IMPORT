import json
import tempfile
import unittest
import zipfile
from pathlib import Path

from qsol_import.core import import_openai_zip


POLICY = Path(__file__).parents[1] / "policies" / "conversation-first.json"


class OpenAIImportTests(unittest.TestCase):
    def build_export(self, root: Path) -> Path:
        path = root / "export.zip"
        conversations = [{
            "id": "conv-1",
            "title": "Sonification demo",
            "mapping": {"node": {"message": {"content": {"parts": ["Here is demo.wav and a note."]}}}},
        }]
        with zipfile.ZipFile(path, "w", compression=zipfile.ZIP_DEFLATED) as zf:
            zf.writestr("conversations.json", json.dumps(conversations))
            zf.writestr("notes/readme.md", "hello\n")
            zf.writestr("assets/demo.wav", b"RIFF" + (16).to_bytes(4, "little") + b"WAVEfmt " + b"x" * 32)
            zf.writestr("assets/fake.dat", b"RIFF" + (16).to_bytes(4, "little") + b"WAVEfmt " + b"y" * 32)
        return path

    def test_import_tombstones_media_and_keeps_context(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            source = self.build_export(root)
            receipt = import_openai_zip(source, root / "out", POLICY)
            self.assertEqual(receipt["conversations"], 1)
            self.assertEqual(receipt["files_tombstoned"], 2)
            self.assertTrue((root / "out" / "retained" / "notes" / "readme.md").exists())
            lines = (root / "out" / "tombstones" / "tombstones.jsonl").read_text().splitlines()
            tombstones = [json.loads(line) for line in lines]
            demo = next(t for t in tombstones if t["original_name"] == "demo.wav")
            self.assertEqual(demo["semantic_context"]["conversation_title"], "Sonification demo")
            fake = next(t for t in tombstones if t["original_name"] == "fake.dat")
            self.assertEqual(fake["detected_type"], "audio/wav")

    def test_repeated_import_is_byte_identical(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            source = self.build_export(root)
            import_openai_zip(source, root / "a", POLICY)
            import_openai_zip(source, root / "b", POLICY)
            a_files = {p.relative_to(root / "a").as_posix(): p.read_bytes() for p in (root / "a").rglob("*") if p.is_file()}
            b_files = {p.relative_to(root / "b").as_posix(): p.read_bytes() for p in (root / "b").rglob("*") if p.is_file()}
            self.assertEqual(a_files, b_files)

    def test_zip_traversal_fails_closed(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            source = root / "bad.zip"
            with zipfile.ZipFile(source, "w") as zf:
                zf.writestr("../escape.txt", "nope")
            with self.assertRaises(ValueError):
                import_openai_zip(source, root / "out", POLICY)


if __name__ == "__main__":
    unittest.main()
