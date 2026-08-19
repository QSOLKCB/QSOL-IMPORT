import tempfile
import unittest
from pathlib import Path

from qsol_import.canonical import canonical_json_bytes
from qsol_import.evaluation import evaluate_import
from roadmap_helpers import build_candidate


class EvaluationTests(unittest.TestCase):
    def build_output(self, root: Path) -> tuple[Path, Path]:
        source = root / "source.zip"
        source.write_bytes(b"source-archive-bytes" * 20)
        conversations = canonical_json_bytes(
            {
                "protocol": "QSOL-IMPORT/CONVERSATION/1",
                "source_conversation_id": "conv-1",
            }
        )
        messages = canonical_json_bytes(
            {
                "protocol": "QSOL-IMPORT/MESSAGE/1",
                "source_message_id": "msg-1",
                "conversation_id": "conv-1",
                "text": "retained message",
                "attachment_refs": ["asset-123456"],
            }
        )
        tombstone = canonical_json_bytes(
            {
                "protocol": "QSOL-IMPORT/TOMBSTONE/1",
                "semantic_context": {
                    "reference_match": "exact",
                    "reference_key": "asset-123456",
                },
            }
        )
        classifications = canonical_json_bytes(
            [
                {"path": "conversations.json", "size_bytes": 200, "decision": "extract"},
                {"path": "asset.wav", "size_bytes": 400, "decision": "tombstone"},
                {"path": "payload.exe", "size_bytes": 50, "decision": "reject"},
            ]
        )
        output = root / "output"
        build_candidate(
            output,
            {
                "conversations/conversations.jsonl": conversations,
                "messages/messages.jsonl": messages,
                "tombstones/tombstones.jsonl": tombstone,
                "reports/classifications.json": classifications,
                "retained/note.txt": b"small retained note\n",
            },
        )
        return source, output

    def test_measures_bytes_and_explicit_semantic_obligations_separately(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            source, output = self.build_output(root)
            obligations = {
                "protocol": "QSOL-IMPORT/RETENTION-OBLIGATIONS/1",
                "schema_version": "1.0.0",
                "required_conversation_ids": ["conv-1"],
                "required_message_ids": ["msg-1"],
                "required_attachment_refs": ["asset-123456"],
                "forbidden_text_fragments": ["FORBIDDEN PRIVATE FRAGMENT"],
                "boundaries": ["SEMANTIC_COVERAGE != FACTUAL_TRUTH"],
            }
            obligations_path = root / "obligations.json"
            obligations_path.write_bytes(canonical_json_bytes(obligations))
            report = evaluate_import(source, output, obligations_path)

            self.assertEqual(report["protocol"], "QSOL-IMPORT/EVALUATION/1")
            self.assertEqual(report["semantic_retention"]["status"], "pass")
            self.assertEqual(
                report["semantic_retention"]["attachment_reference_retention"]["covered"],
                ["asset-123456"],
            )
            self.assertEqual(report["byte_metrics"]["tombstoned_source_bytes"], 400)
            self.assertEqual(report["byte_metrics"]["rejected_source_bytes"], 50)
            self.assertFalse(report["aggregate_score_emitted"])
            self.assertNotIn("score", report)

    def test_missing_obligation_is_reported_without_becoming_truth_claim(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            source, output = self.build_output(root)
            obligations = {
                "protocol": "QSOL-IMPORT/RETENTION-OBLIGATIONS/1",
                "schema_version": "1.0.0",
                "required_conversation_ids": ["conv-1", "conv-missing"],
                "required_message_ids": [],
                "required_attachment_refs": [],
                "forbidden_text_fragments": [],
                "boundaries": [],
            }
            obligations_path = root / "obligations.json"
            obligations_path.write_bytes(canonical_json_bytes(obligations))
            report = evaluate_import(source, output, obligations_path)
            dimension = report["semantic_retention"]["conversation_retention"]
            self.assertEqual(dimension["status"], "fail")
            self.assertEqual(dimension["missing"], ["conv-missing"])
            self.assertIn("SEMANTIC_COVERAGE != FACTUAL_TRUTH", report["boundaries"])

    def test_no_obligations_means_unassessed_not_failed(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            source, output = self.build_output(root)
            report = evaluate_import(source, output)
            self.assertEqual(report["semantic_retention"]["status"], "unassessed")
            self.assertEqual(
                report["semantic_retention"]["conversation_retention"]["status"],
                "unassessed",
            )


if __name__ == "__main__":
    unittest.main()
