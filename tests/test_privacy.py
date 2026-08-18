import json
import tempfile
import unittest
from pathlib import Path

from qsol_import.canonical import sha256_bytes
from qsol_import.privacy import scan_files


class PrivacyScannerTests(unittest.TestCase):
    def test_newline_free_file_is_scanned_in_bounded_overlapping_chunks(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            path = root / "large.txt"
            secret = "sk-" + ("A" * 40)
            prefix = ("x" * ((64 * 1024) - 6)) + " "
            path.write_text(prefix + secret + " tail", encoding="utf-8")

            report = scan_files(root, ["large.txt"])
            finding = next(
                item for item in report["findings"] if item["rule_id"] == "openai_api_key"
            )
            self.assertEqual(finding["occurrences"], 1)
            self.assertEqual(
                finding["matches"],
                [
                    {
                        "sha256": sha256_bytes(secret.encode("utf-8")),
                        "occurrences": 1,
                    }
                ],
            )
            self.assertNotIn(secret, json.dumps(report))
            self.assertFalse(report["raw_matches_emitted"])


if __name__ == "__main__":
    unittest.main()
