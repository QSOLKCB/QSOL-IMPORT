import json
import tempfile
import unittest
import warnings
import zipfile
from pathlib import Path

from qsol_import.core import import_openai_zip


POLICY = Path(__file__).parents[1] / "policies" / "conversation-first.json"


class OpenAIImportTests(unittest.TestCase):
    def build_export(self, root: Path, conversation_name: str = "conversations.json") -> Path:
        path = root / "export.zip"
        conversations = [{
            "id": "conv-1",
            "title": "Sonification demo",
            "mapping": {
                "node-user": {
                    "id": "node-user",
                    "parent": None,
                    "children": ["node-assistant"],
                    "message": {
                        "id": "msg-user",
                        "author": {"role": "user", "name": None},
                        "create_time": 1.0,
                        "content": {"content_type": "text", "parts": ["Here is demo.wav and a note."]},
                        "status": "finished_successfully",
                        "recipient": "all",
                    },
                },
                "node-assistant": {
                    "id": "node-assistant",
                    "parent": "node-user",
                    "children": [],
                    "message": {
                        "id": "msg-assistant",
                        "author": {"role": "assistant", "name": None},
                        "create_time": 2.0,
                        "content": {"content_type": "text", "parts": ["Received."]},
                        "status": "finished_successfully",
                        "recipient": "all",
                    },
                },
            },
        }]
        with zipfile.ZipFile(path, "w", compression=zipfile.ZIP_DEFLATED) as zf:
            zf.writestr(conversation_name, json.dumps(conversations))
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
            self.assertEqual(receipt["messages"], 2)
            self.assertEqual(receipt["files_extracted"], 1)
            self.assertEqual(receipt["files_tombstoned"], 2)
            self.assertEqual(receipt["files_seen"], 4)
            self.assertTrue((root / "out" / "retained" / "notes" / "readme.md").exists())
            classifications = json.loads((root / "out" / "reports" / "classifications.json").read_text())
            conversation = next(r for r in classifications if r["path"] == "conversations.json")
            self.assertEqual(conversation["decision"], "extract")
            self.assertEqual(conversation["reason"], "conversation_normalized")

    def test_message_graph_preserves_source_order_and_links(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            source = self.build_export(root)
            import_openai_zip(source, root / "out", POLICY)
            messages = [json.loads(line) for line in (root / "out" / "messages" / "messages.jsonl").read_text().splitlines()]
            self.assertEqual([m["source_node_index"] for m in messages], [0, 1])
            self.assertEqual(messages[0]["children_node_ids"], ["node-assistant"])
            self.assertEqual(messages[1]["parent_node_id"], "node-user")

    def test_invalid_timestamp_shapes_normalize_to_null(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            source = root / "times.zip"
            conversations = [{"id": "conv", "mapping": {"n": {"message": {"id": "m", "create_time": {"bad": True}, "update_time": False, "content": {}}}}}]
            with zipfile.ZipFile(source, "w") as zf:
                zf.writestr("conversations.json", json.dumps(conversations))
            import_openai_zip(source, root / "out", POLICY)
            message = json.loads((root / "out/messages/messages.jsonl").read_text())
            self.assertIsNone(message["create_time"])
            self.assertIsNone(message["update_time"])
            self.assertEqual(message["message"]["create_time"], {"bad": True})

    def test_numbered_conversation_file_is_discovered(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            source = self.build_export(root, "conversations-0002.json")
            receipt = import_openai_zip(source, root / "out", POLICY)
            self.assertEqual(receipt["conversations"], 1)

    def test_nested_asset_named_conversations_json_is_not_vendor_data(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            source = self.build_export(root)
            with zipfile.ZipFile(source, "a") as zf:
                zf.writestr("assets/conversations.json", json.dumps([{"uploaded": True}]))
            receipt = import_openai_zip(source, root / "out", POLICY)
            self.assertEqual(receipt["conversations"], 1)
            self.assertTrue((root / "out/retained/assets/conversations.json").exists())

    def test_candidate_manifest_is_candidate_only_and_role_free(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            source = self.build_export(root)
            receipt = import_openai_zip(source, root / "out", POLICY)
            candidate = json.loads((root / "out" / "CANDIDATE.json").read_text())
            self.assertEqual(candidate["authority"], "candidate-only")
            self.assertFalse(candidate["concap_roles_assigned"])
            self.assertEqual(receipt["candidate_sha256"], candidate["candidate_sha256"])

    def test_repeated_import_is_byte_identical(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            source = self.build_export(root)
            import_openai_zip(source, root / "a", POLICY)
            import_openai_zip(source, root / "b", POLICY)
            a_files = {p.relative_to(root / "a").as_posix(): p.read_bytes() for p in (root / "a").rglob("*") if p.is_file()}
            b_files = {p.relative_to(root / "b").as_posix(): p.read_bytes() for p in (root / "b").rglob("*") if p.is_file()}
            self.assertEqual(a_files, b_files)

    def test_failed_import_preserves_previous_output(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            source = self.build_export(root)
            import_openai_zip(source, root / "out", POLICY)
            prior = (root / "out/IMPORT.json").read_bytes()
            bad = root / "bad.zip"
            with zipfile.ZipFile(bad, "w") as zf:
                zf.writestr("../escape.txt", "nope")
            with self.assertRaises(ValueError):
                import_openai_zip(bad, root / "out", POLICY)
            self.assertEqual((root / "out/IMPORT.json").read_bytes(), prior)

    def test_zip_traversal_fails_closed(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            source = root / "bad.zip"
            with zipfile.ZipFile(source, "w") as zf:
                zf.writestr("../escape.txt", "nope")
            with self.assertRaises(ValueError):
                import_openai_zip(source, root / "out", POLICY)

    def test_duplicate_and_normalized_collision_fail_closed(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            duplicate = root / "duplicate.zip"
            with warnings.catch_warnings():
                warnings.simplefilter("ignore")
                with zipfile.ZipFile(duplicate, "w") as zf:
                    zf.writestr("conversations.json", "[]")
                    zf.writestr("notes.txt", "one")
                    zf.writestr("notes.txt", "two")
            with self.assertRaises(ValueError):
                import_openai_zip(duplicate, root / "out", POLICY)

            collision = root / "collision.zip"
            with zipfile.ZipFile(collision, "w") as zf:
                zf.writestr("conversations.json", "[]")
                zf.writestr("./same.txt", "one")
                zf.writestr("same.txt", "two")
            with self.assertRaises(ValueError):
                import_openai_zip(collision, root / "out2", POLICY)

    def test_control_character_path_is_rejected(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            source = root / "control.zip"
            with zipfile.ZipFile(source, "w") as zf:
                zf.writestr("conversations.json", "[]")
                zf.writestr("bad\nname.txt", "x")
            with self.assertRaises(ValueError):
                import_openai_zip(source, root / "out", POLICY)

    def test_nested_sha256sums_is_covered(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            source = root / "checksums.zip"
            with zipfile.ZipFile(source, "w") as zf:
                zf.writestr("conversations.json", "[]")
                zf.writestr("notes/SHA256SUMS", "source")
            import_openai_zip(source, root / "out", POLICY)
            self.assertIn("retained/notes/SHA256SUMS", (root / "out/SHA256SUMS").read_text())

    def test_non_finite_json_is_rejected(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            source = root / "nan.zip"
            with zipfile.ZipFile(source, "w") as zf:
                zf.writestr("conversations.json", '[{"value": NaN}]')
            with self.assertRaises(ValueError):
                import_openai_zip(source, root / "out", POLICY)

    def test_oversized_document_classification_matches_tombstone(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            custom_policy = json.loads(POLICY.read_text())
            custom_policy["documents"]["keep_original_under_bytes"] = 1
            policy_path = root / "policy.json"
            policy_path.write_text(json.dumps(custom_policy))
            source = root / "doc.zip"
            with zipfile.ZipFile(source, "w") as zf:
                zf.writestr("conversations.json", "[]")
                zf.writestr("large.pdf", b"%PDF-1.7\nhello")
            receipt = import_openai_zip(source, root / "out", policy_path)
            self.assertEqual(receipt["files_tombstoned"], 1)
            records = json.loads((root / "out/reports/classifications.json").read_text())
            doc = next(r for r in records if r["path"] == "large.pdf")
            self.assertEqual(doc["decision"], "tombstone")
            self.assertEqual(doc["reason"], "document_over_retention_limit")


if __name__ == "__main__":
    unittest.main()
