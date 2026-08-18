import json
import unittest

from qsol_import.adapters.openai_contract import OpenAIContractAdapter


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


if __name__ == "__main__":
    unittest.main()
