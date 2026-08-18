import json
import tempfile
import unittest
import zipfile
from pathlib import Path

from qsol_import.adapter_pipeline import import_with_adapter
from qsol_import.adapters.grok import GrokAdapter


POLICY = Path(__file__).parents[1] / "policies" / "conversation-first.json"


class GrokAdapterTests(unittest.TestCase):
    def build_export(self, root: Path) -> Path:
        source = root / "grok.zip"
        backend = {
            "conversations": [
                {
                    "conversation": {
                        "id": "conv-1",
                        "title": "Observed Grok export",
                        "create_time": "2026-08-17T00:00:00Z",
                        "modify_time": "2026-08-17T00:01:00Z",
                    },
                    "responses": [
                        {
                            "response": {
                                "_id": "resp-1",
                                "conversation_id": "conv-1",
                                "sender": "human",
                                "message": "please inspect the attachment",
                                "create_time": "2026-08-17T00:00:01Z",
                                "file_attachments": ["asset-123456"],
                                "children": ["resp-2"],
                                "agent_thinking_traces": ["NEVER NORMALIZE THIS"],
                            }
                        },
                        {
                            "response": {
                                "_id": "resp-2",
                                "conversation_id": "conv-1",
                                "sender": "assistant",
                                "model": "grok-test",
                                "message": "done",
                                "create_time": "2026-08-17T00:00:02Z",
                                "parent_response_id": "resp-1",
                                "children": [],
                                "partial": False,
                            }
                        },
                    ],
                }
            ],
            "projects": [],
            "tasks": [],
            "media_posts": [],
        }
        prefix = "export_data/aaaaaaaa-bbbb-cccc-dddd-eeeeeeeeeeee"
        with zipfile.ZipFile(source, "w", compression=zipfile.ZIP_DEFLATED) as zf:
            zf.writestr(f"{prefix}/prod-grok-backend.json", json.dumps(backend))
            zf.writestr(f"{prefix}/prod-mc-auth-mgmt-api.json", '{"token":"secret"}')
            zf.writestr(f"{prefix}/prod-mc-billing.json", '{"card":"secret"}')
            zf.writestr(
                f"{prefix}/prod-mc-asset-server/asset-123456/content",
                b"RIFF" + (16).to_bytes(4, "little") + b"WAVEfmt " + b"x" * 32,
            )
        return source

    def test_grok_export_uses_common_surface_and_tombstones_assets(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            source = self.build_export(root)
            receipt = import_with_adapter(source, root / "out", POLICY, GrokAdapter())

            self.assertEqual(receipt["adapter_id"], "xai-grok-export/1")
            self.assertEqual(receipt["conversations"], 1)
            self.assertEqual(receipt["messages"], 2)
            self.assertEqual(receipt["files_tombstoned"], 1)
            self.assertEqual(receipt["files_rejected"], 2)

            conversations = [json.loads(line) for line in (root / "out/conversations/conversations.jsonl").read_text().splitlines()]
            messages = [json.loads(line) for line in (root / "out/messages/messages.jsonl").read_text().splitlines()]
            self.assertEqual(conversations[0]["protocol"], "QSOL-IMPORT/CONVERSATION/1")
            self.assertTrue(all(row["protocol"] == "QSOL-IMPORT/MESSAGE/1" for row in messages))
            self.assertEqual(messages[0]["role"], "user")
            self.assertEqual(messages[0]["attachment_refs"], ["asset-123456"])
            self.assertNotIn("NEVER NORMALIZE THIS", (root / "out/messages/messages.jsonl").read_text())

            tombstone = json.loads((root / "out/tombstones/tombstones.jsonl").read_text())
            self.assertEqual(tombstone["source_vendor"], "xai")
            self.assertEqual(tombstone["reason"], "xai_binary_asset_policy")
            self.assertEqual(tombstone["semantic_context"]["reference_match"], "exact")
            self.assertEqual(tombstone["semantic_context"]["conversation_id"], "conv-1")

            classifications = json.loads((root / "out/reports/classifications.json").read_text())
            rejected = {Path(row["path"]).name for row in classifications if row["decision"] == "reject"}
            self.assertEqual(rejected, {"prod-mc-auth-mgmt-api.json", "prod-mc-billing.json"})

    def test_grok_discovery_fails_closed_on_multiple_backends(self):
        adapter = GrokAdapter()
        from qsol_import.adapter_contract import AdapterError, SourceMember

        with self.assertRaises(AdapterError) as ctx:
            adapter.discover(
                (
                    SourceMember("a/prod-grok-backend.json", 1),
                    SourceMember("b/prod-grok-backend.json", 1),
                )
            )
        self.assertEqual(ctx.exception.code, "grok_backend_cardinality")


if __name__ == "__main__":
    unittest.main()
