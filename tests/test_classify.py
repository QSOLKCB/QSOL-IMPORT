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

    def test_text_is_kept(self):
        result = classify_file("notes.md", 10, b"# hello", POLICY)
        self.assertEqual(result.decision, "keep")


if __name__ == "__main__":
    unittest.main()
