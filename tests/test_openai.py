import json
import tempfile
import unittest
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
            zf.writestr(
                "assets/demo.wav",
                b"RIFF" + (16).to_bytes(4, "little") + b"WAVEfmt " + b"x" * 32,
            )
            zf.writestr(
                "assets/fake.dat",
                b"RIFF" + (16).to_bytes(4, "little") + b"WAVEfmt " + b"y" * 32,
            )
        return path

    def test_import_tombstones_media_and_keeps_context(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            source = self.build_export(root)
            receipt = import_openai_zip(source, root / "out", POLICY)
            self.assertEqual(receipt["conversations"], 1)
            self.assertEqual(receipt["messages"], 2)
            self.assertEqual(receipt["files_tombstoned"], 2)
            self.assertTrue((root / "out" / "retained" / "notes" / "readme.md").exists())
            lines = (root / "out" / "tombstones" / "tombstones.jsonl").read_text().splitlines()
            tombstones = [json.loads(line) for line in lines]
            demo = next(t for t in tombstones if t["original_name"] == "demo.wav")
            self.assertEqual(demo["semantic_context"]["conversation_title"], "Sonification demo")
            fake = next(t for t in tombstones if t["original_name"] == "fake.dat")
            self.assertEqual(fake["detected_type"], "audio/wav")

    def test_message_graph_preserves_source_order_and_links(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            source = self.build_export(root)
            import_openai_zip(source, root / "out", POLICY)
            lines = (root / "out" / "messages" / "messages.jsonl").read_text().splitlines()
            messages = [json.loads(line) for line in lines]
            self.assertEqual([m["source_node_index"] for m in messages], [0, 1])
            self.assertEqual([m["author_role"] for m in messages], ["user", "assistant"])
            self.assertEqual(messages[0]["children_node_ids"], ["node-assistant"])
            self.assertEqual(messages[1]["parent_node_id"], "node-user")
            self.assertEqual(messages[0]["source_message_id"], "msg-user")

    def test_numbered_conversation_file_is_discovered(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            source = self.build_export(root, "conversations-0002.json")
            receipt = import_openai_zip(source, root / "out", POLICY)
            self.assertEqual(receipt["conversations"], 1)
            line = (root / "out" / "conversations" / "conversations.jsonl").read_text().splitlines()[0]
            self.assertEqual(json.loads(line)["source_file"], "conversations-0002.json")

    def test_candidate_manifest_is_candidate_only_and_role_free(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            source = self.build_export(root)
            receipt = import_openai_zip(source, root / "out", POLICY)
            candidate = json.loads((root / "out" / "CANDIDATE.json").read_text())
            self.assertEqual(candidate["authority"], "candidate-only")
            self.assertFalse(candidate["concap_roles_assigned"])
            self.assertEqual(receipt["candidate_sha256"], candidate["candidate_sha256"])
            self.assertIn("CANDIDATE_MANIFEST != CONCAP_EXPORT_SPEC", candidate["boundaries"])
            paths = [item["path"] for item in candidate["artifacts"]]
            self.assertIn("messages/messages.jsonl", paths)
            self.assertNotIn("IMPORT.json", paths)

    def test_repeated_import_is_byte_identical(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            source = self.build_export(root)
            import_openai_zip(source, root / "a", POLICY)
            import_openai_zip(source, root / "b", POLICY)
            a_files = {
                p.relative_to(root / "a").as_posix(): p.read_bytes()
                for p in (root / "a").rglob("*")
                if p.is_file()
            }
            b_files = {
                p.relative_to(root / "b").as_posix(): p.read_bytes()
                for p in (root / "b").rglob("*")
                if p.is_file()
            }
            self.assertEqual(a_files, b_files)

    def test_zip_traversal_fails_closed(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            source = root / "bad.zip"
            with zipfile.ZipFile(source, "w") as zf:
                zf.writestr("../escape.txt", "nope")
            with self.assertRaises(ValueError):
                import_openai_zip(source, root / "out", POLICY)

    def test_duplicate_zip_member_fails_closed(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            source = root / "duplicate.zip"
            with zipfile.ZipFile(source, "w") as zf:
                zf.writestr("conversations.json", "[]")
                zf.writestr("notes.txt", "one")
                zf.writestr("notes.txt", "two")
            with self.assertRaises(ValueError):
                import_openai_zip(source, root / "out", POLICY)


if __name__ == "__main__":
    unittest.main()
