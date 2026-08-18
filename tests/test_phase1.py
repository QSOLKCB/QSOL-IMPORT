import io
import json
import tempfile
import unittest
import zipfile
from pathlib import Path

from qsol_import.adapters.openai import conversation_file_sort_key, is_conversation_file
from qsol_import.core import import_openai_zip


ROOT = Path(__file__).parents[1]
POLICY = ROOT / "policies" / "conversation-first.json"
NAME_FIXTURE = ROOT / "tests" / "fixtures" / "openai" / "numbered-conversation-names.json"


def conversation_with_text(text: str) -> list[dict]:
    return [
        {
            "id": "conv-phase1",
            "title": "Phase 1 fixture",
            "mapping": {
                "node-1": {
                    "id": "node-1",
                    "parent": None,
                    "children": [],
                    "message": {
                        "id": "message-1",
                        "author": {"role": "user"},
                        "content": {"content_type": "text", "parts": [text]},
                        "status": "finished_successfully",
                    },
                }
            },
        }
    ]


def minimal_docx() -> bytes:
    buffer = io.BytesIO()
    document_xml = (
        '<?xml version="1.0" encoding="UTF-8"?>'
        '<w:document xmlns:w="http://schemas.openxmlformats.org/wordprocessingml/2006/main">'
        '<w:body>'
        '<w:p><w:r><w:t>Hello</w:t></w:r><w:tab/><w:r><w:t>world</w:t></w:r></w:p>'
        '<w:p><w:r><w:t>Second line</w:t></w:r></w:p>'
        '</w:body></w:document>'
    )
    with zipfile.ZipFile(buffer, "w", compression=zipfile.ZIP_DEFLATED) as zf:
        zf.writestr("[Content_Types].xml", "<Types/>")
        zf.writestr("word/document.xml", document_xml)
    return buffer.getvalue()


class Phase1OpenAIHardeningTests(unittest.TestCase):
    def test_numbered_conversation_name_fixture(self):
        fixture = json.loads(NAME_FIXTURE.read_text())
        for name in fixture["accepted"]:
            with self.subTest(accepted=name):
                self.assertTrue(is_conversation_file(name))
        for name in fixture["rejected"]:
            with self.subTest(rejected=name):
                self.assertFalse(is_conversation_file(name))
        ordered = sorted(fixture["accepted"], key=conversation_file_sort_key)
        self.assertEqual(ordered[0], "conversations.json")
        self.assertEqual(ordered[-1], "conversation-5.json")

    def test_exact_file_identifier_resolves_attachment_context(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            source = root / "export.zip"
            wav = b"RIFF" + (16).to_bytes(4, "little") + b"WAVEfmt " + b"x" * 32
            with zipfile.ZipFile(source, "w") as zf:
                zf.writestr(
                    "conversations.json",
                    json.dumps(conversation_with_text("attachment pointer file-service://file-ABC12345")),
                )
                zf.writestr("assets/file-ABC12345.wav", wav)

            import_openai_zip(source, root / "out", POLICY)
            tombstone = json.loads((root / "out/tombstones/tombstones.jsonl").read_text())
            semantic = tombstone["semantic_context"]
            self.assertEqual(semantic["reference_match"], "exact")
            self.assertIn("id:file-abc12345", semantic["reference_keys"])
            self.assertEqual(semantic["conversation_id"], "conv-phase1")

    def test_docx_text_extraction_uses_frozen_contract(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            source = root / "export.zip"
            with zipfile.ZipFile(source, "w") as zf:
                zf.writestr("conversations.json", json.dumps(conversation_with_text("paper.docx")))
                zf.writestr("documents/paper.docx", minimal_docx())

            receipt = import_openai_zip(source, root / "out", POLICY)
            extracted = root / "out/extracted/documents/documents/paper.docx.txt"
            self.assertEqual(extracted.read_text(), "Hello\tworld\nSecond line\n")
            records = json.loads((root / "out/reports/classifications.json").read_text())
            document = next(item for item in records if item["path"] == "documents/paper.docx")
            self.assertEqual(document["decision"], "extract")
            self.assertEqual(document["reason"], "document_text_extracted")
            self.assertEqual(document["extractor_contract"], "QSOL-IMPORT/DOCX-BODY-TEXT/1")
            self.assertEqual(receipt["files_extracted"], 2)

    def test_account_metadata_requires_exact_path_and_field_allowlist(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            policy = json.loads(POLICY.read_text())
            policy["account_metadata"] = {
                "enabled": True,
                "max_member_bytes": 1024 * 1024,
                "allowlist": [
                    {"path": "user.json", "fields": ["id", "email"]},
                ],
            }
            policy_path = root / "policy.json"
            policy_path.write_text(json.dumps(policy))
            source = root / "export.zip"
            with zipfile.ZipFile(source, "w") as zf:
                zf.writestr("conversations.json", "[]")
                zf.writestr(
                    "user.json",
                    json.dumps(
                        {
                            "id": "user-1",
                            "email": "person@example.com",
                            "phone": "+61 400 000 000",
                            "secret": "do-not-copy",
                        }
                    ),
                )

            import_openai_zip(source, root / "out", policy_path)
            account = json.loads((root / "out/account/user.json").read_text())
            self.assertEqual(account["metadata"], {"id": "user-1", "email": "person@example.com"})
            self.assertNotIn("phone", account["metadata"])
            self.assertNotIn("secret", account["metadata"])
            self.assertFalse((root / "out/retained/user.json").exists())

    def test_privacy_scan_hashes_matches_instead_of_copying_them(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            source = root / "export.zip"
            fake_key = "sk-proj-abcdefghijklmnopqrstuvwxyz1234567890"
            with zipfile.ZipFile(source, "w") as zf:
                zf.writestr(
                    "conversations.json",
                    json.dumps(conversation_with_text(f"mail person@example.com key {fake_key}")),
                )

            import_openai_zip(source, root / "out", POLICY)
            report_path = root / "out/reports/privacy-scan.json"
            report = json.loads(report_path.read_text())
            rule_ids = {item["rule_id"] for item in report["findings"]}
            self.assertIn("email_address", rule_ids)
            self.assertIn("openai_api_key", rule_ids)
            self.assertGreater(report["finding_occurrences"], 0)
            self.assertFalse(report["raw_matches_emitted"])
            self.assertNotIn(fake_key, report_path.read_text())
            self.assertNotIn("person@example.com", report_path.read_text())


if __name__ == "__main__":
    unittest.main()
