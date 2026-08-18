import json
import tempfile
import unittest
import zipfile
from pathlib import Path

from qsol_import.adapter_pipeline import import_with_adapter
from qsol_import.adapters.openai_contract import OpenAIContractAdapter


POLICY = Path(__file__).parents[1] / "policies" / "conversation-first.json"


class OpenAICommonAdapterTests(unittest.TestCase):
    def test_openai_projects_to_common_contract_without_changing_legacy_parser(self):
        payload = [
            {
                "id": "conv-1",
                "title": "OpenAI common projection",
                "mapping": {
                    "node-user": {
                        "parent": None,
                        "children": ["node-assistant"],
                        "message": {
                            "id": "msg-user",
                            "author": {"role": "user", "name": None},
                            "content": {"content_type": "text", "parts": ["hello"]},
                            "create_time": 1.0,
                            "status": "finished_successfully",
                        },
                    },
                    "node-assistant": {
                        "parent": "node-user",
                        "children": [],
                        "message": {
                            "id": "msg-assistant",
                            "author": {"role": "assistant", "name": None},
                            "content": {"content_type": "text", "parts": ["hi"]},
                            "create_time": 2.0,
                            "status": "finished_successfully",
                        },
                    },
                },
            }
        ]
        adapter = OpenAIContractAdapter()
        result = adapter.parse({"conversations.json": json.dumps(payload).encode()})
        self.assertEqual(result.conversations[0]["protocol"], "QSOL-IMPORT/CONVERSATION/1")
        self.assertEqual([row["protocol"] for row in result.messages], ["QSOL-IMPORT/MESSAGE/1"] * 2)
        self.assertEqual([row["text"] for row in result.messages], ["hello", "hi"])
        self.assertEqual(result.messages[1]["source_parent_id"], "node-user")

    def test_openai_common_preserves_exact_attachment_reference_for_tombstone(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            source = root / "openai.zip"
            attachment_id = "file-abcdef1234"
            payload = [
                {
                    "id": "conv-attachment",
                    "title": "Attachment provenance",
                    "mapping": {
                        "node-user": {
                            "parent": None,
                            "children": [],
                            "message": {
                                "id": "msg-attachment",
                                "author": {"role": "user", "name": None},
                                "content": {
                                    "content_type": "text",
                                    "parts": [f"Please inspect {attachment_id}"],
                                },
                                "create_time": 1.0,
                                "status": "finished_successfully",
                            },
                        }
                    },
                }
            ]
            with zipfile.ZipFile(source, "w", compression=zipfile.ZIP_DEFLATED) as zf:
                zf.writestr("conversations.json", json.dumps(payload))
                zf.writestr(
                    f"assets/{attachment_id}/demo.wav",
                    b"RIFF" + (16).to_bytes(4, "little") + b"WAVEfmt " + b"x" * 32,
                )

            receipt = import_with_adapter(
                source,
                root / "out",
                POLICY,
                OpenAIContractAdapter(),
            )
            self.assertEqual(receipt["files_tombstoned"], 1)

            message = json.loads((root / "out/messages/messages.jsonl").read_text())
            self.assertIn(attachment_id, message["attachment_refs"])

            tombstone = json.loads((root / "out/tombstones/tombstones.jsonl").read_text())
            self.assertEqual(tombstone["semantic_context"]["reference_match"], "exact")
            self.assertEqual(tombstone["semantic_context"]["reference_key"], attachment_id)
            self.assertEqual(tombstone["semantic_context"]["conversation_id"], "conv-attachment")
            self.assertEqual(tombstone["semantic_context"]["source_message_id"], "msg-attachment")


if __name__ == "__main__":
    unittest.main()
