import copy
import json
import unittest
from pathlib import Path

from qsol_import.classify import classify_file


POLICY = json.loads((Path(__file__).parents[1] / "policies" / "conversation-first.json").read_text())


class ClassificationTests(unittest.TestCase):
    def test_wav_magic_beats_dat_extension(self):
        head = b"RIFF" + (100).to_bytes(4, "little") + b"WAVEfmt "
        result = classify_file("mystery.dat", 50_000_000, head, POLICY)
        self.assertEqual(result.kind, "audio")
        self.assertEqual(result.media_type, "audio/wav")
        self.assertEqual(result.decision, "tombstone")

    def test_mp4_is_tombstoned(self):
        head = b"\x00\x00\x00\x18ftypisom" + b"\x00" * 32
        result = classify_file("clip.mp4", 10, head, POLICY)
        self.assertEqual(result.kind, "video")
        self.assertEqual(result.decision, "tombstone")

    def test_text_honors_policy(self):
        changed = copy.deepcopy(POLICY)
        changed["structured_text"]["default"] = "tombstone"
        result = classify_file("notes.md", 10, b"# hello", changed)
        self.assertEqual(result.decision, "tombstone")

    def test_odt_zip_signature_is_document(self):
        result = classify_file("paper.odt", 10, b"PK\x03\x04" + b"x" * 32, POLICY)
        self.assertEqual(result.kind, "document")
        self.assertEqual(result.decision, "extract")

    def test_elf_magic_is_rejected_even_as_text(self):
        result = classify_file("payload.txt", 10, b"\x7fELF" + b"x" * 32, POLICY)
        self.assertEqual(result.kind, "executable")
        self.assertEqual(result.decision, "reject")

    def test_non_zip_nested_archives_are_rejected(self):
        cases = [
            ("backup.tar.gz", b"\x1f\x8b" + b"x" * 32),
            ("backup.7z", b"7z\xbc\xaf'\x1c" + b"x" * 32),
            ("backup.rar", b"Rar!\x1a\x07\x00" + b"x" * 32),
        ]
        for name, head in cases:
            with self.subTest(name=name):
                result = classify_file(name, 10, head, POLICY)
                self.assertEqual(result.kind, "archive")
                self.assertEqual(result.decision, "reject")


if __name__ == "__main__":
    unittest.main()
