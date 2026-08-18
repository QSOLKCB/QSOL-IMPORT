import json
import unittest

from qsol_import.adapter_contract import AdapterError, SourceMember
from qsol_import.adapters.claude import ClaudeAdapter
from qsol_import.adapters.gemini import GeminiAdapter
from qsol_import.adapters.generic import GenericAdapter
from qsol_import.adapters.registry import adapter_registry


class GenericAdapterContractTests(unittest.TestCase):
    def test_registry_freezes_unique_vendor_neutral_contract(self):
        rows = adapter_registry()
        ids = [row["adapter_id"] for row in rows]
        self.assertEqual(len(ids), len(set(ids)))
        self.assertTrue(all(row["protocol"] == "QSOL-IMPORT/ADAPTER/1" for row in rows))
        self.assertTrue(all(row["vendor_payload_in_canonical_records"] is False for row in rows))
        self.assertTrue(all(row["canonical_message_protocol"] == "QSOL-IMPORT/MESSAGE/1" for row in rows))

    def test_claude_conformance_shape(self):
        adapter = ClaudeAdapter()
        payload = [
            {
                "uuid": "c-1",
                "name": "Claude export",
                "created_at": "2026-01-01T00:00:00Z",
                "chat_messages": [
                    {"uuid": "m-1", "sender": "human", "text": "hello"},
                    {"uuid": "m-2", "sender": "assistant", "text": "hi"},
                ],
                "vendor_only": {"must_not_cross": True},
            }
        ]
        result = adapter.parse({"conversations.json": json.dumps(payload).encode()})
        self.assertEqual(result.conversations[0]["source_conversation_id"], "c-1")
        self.assertEqual([row["role"] for row in result.messages], ["user", "assistant"])
        encoded = json.dumps([*result.conversations, *result.messages])
        self.assertNotIn("vendor_only", encoded)
        self.assertNotIn("must_not_cross", encoded)

    def test_gemini_conformance_shape(self):
        adapter = GeminiAdapter()
        payload = {
            "conversations": [
                {
                    "id": "g-1",
                    "title": "Gemini export",
                    "entries": [
                        {"id": "g-m1", "role": "user", "text": "one"},
                        {"id": "g-m2", "role": "model", "text": "two"},
                    ],
                }
            ]
        }
        result = adapter.parse({"Gemini.json": json.dumps(payload).encode()})
        self.assertEqual(len(result.conversations), 1)
        self.assertEqual([row["role"] for row in result.messages], ["user", "assistant"])

    def test_generic_json_and_jsonl_are_independently_supported(self):
        adapter = GenericAdapter()
        json_payload = {
            "conversations": [
                {
                    "id": "x",
                    "title": "generic",
                    "messages": [
                        {"id": "1", "role": "user", "content": "alpha"},
                        {"id": "2", "role": "assistant", "content": "beta"},
                    ],
                }
            ]
        }
        result = adapter.parse({"input.json": json.dumps(json_payload).encode()})
        self.assertEqual([row["text"] for row in result.messages], ["alpha", "beta"])

        jsonl = b'{' + b'"conversation_id":"z","message_id":"1","role":"user","text":"a"}' + b'\n' + b'{' + b'"conversation_id":"z","message_id":"2","role":"assistant","text":"b"}' + b'\n'
        result_jsonl = adapter.parse({"input.jsonl": jsonl})
        self.assertEqual(len(result_jsonl.conversations), 1)
        self.assertEqual([row["text"] for row in result_jsonl.messages], ["a", "b"])

    def test_generic_json_rejects_non_object_message_without_silent_loss(self):
        adapter = GenericAdapter()
        payload = {
            "conversations": [
                {
                    "id": "x",
                    "messages": [
                        {"id": "1", "role": "user", "text": "kept"},
                        "truncated-message",
                    ],
                }
            ]
        }
        with self.assertRaises(AdapterError) as ctx:
            adapter.parse({"input.json": json.dumps(payload).encode()})
        self.assertEqual(ctx.exception.code, "invalid_generic_message")

    def test_adapter_discovery_is_explicit_not_fuzzy(self):
        claude = ClaudeAdapter()
        self.assertEqual(
            claude.discover((SourceMember("export/conversations.json", 10),)),
            ("export/conversations.json",),
        )
        with self.assertRaises(ValueError):
            claude.discover((SourceMember("export/conversation-ish.json", 10),))


if __name__ == "__main__":
    unittest.main()
