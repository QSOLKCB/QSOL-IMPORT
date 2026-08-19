import json
import tempfile
import unittest
from pathlib import Path

from qsol_import.canonical import canonical_json_bytes, sha256_file
from qsol_import.evaluation import EvaluationError, evaluate_import
from roadmap_helpers import build_candidate, build_obligations


class EvaluationTests(unittest.TestCase):
    def build_output(
        self,
        root: Path,
        *,
        retained_note: bytes = b"small retained note\n",
        classifications_override: list[dict] | None = None,
    ) -> tuple[Path, Path]:
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
        classifications = classifications_override or [
            {
                "path": "conversations.json",
                "size_bytes": 200,
                "decision": "extract",
            },
            {
                "path": "asset.wav",
                "size_bytes": 400,
                "decision": "tombstone",
            },
            {
                "path": "payload.exe",
                "size_bytes": 50,
                "decision": "reject",
            },
            {
                "path": "note.txt",
                "size_bytes": len(retained_note),
                "decision": "keep",
            },
        ]
        output = root / "output"
        build_candidate(
            output,
            {
                "conversations/conversations.jsonl": conversations,
                "messages/messages.jsonl": messages,
                "tombstones/tombstones.jsonl": tombstone,
                "reports/classifications.json": canonical_json_bytes(
                    classifications
                ),
                "retained/note.txt": retained_note,
            },
            input_sha256=sha256_file(source),
            receipt_counts={
                "files_seen": 4,
                "files_retained": 1,
                "files_extracted": 1,
                "files_tombstoned": 1,
                "files_rejected": 1,
            },
        )
        return source, output

    def test_measures_bytes_and_explicit_semantic_obligations_separately(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            source, output = self.build_output(root)
            obligations_path = root / "obligations.json"
            build_obligations(
                obligations_path,
                required_conversation_ids=["conv-1"],
                required_message_ids=["msg-1"],
                required_attachment_refs=["asset-123456"],
                forbidden_text_fragments=["FORBIDDEN PRIVATE FRAGMENT"],
            )
            report = evaluate_import(source, output, obligations_path)

            self.assertEqual(report["protocol"], "QSOL-IMPORT/EVALUATION/1")
            self.assertEqual(report["semantic_retention"]["status"], "pass")
            self.assertEqual(
                report["semantic_retention"]
                ["attachment_reference_retention"]["covered"],
                ["asset-123456"],
            )
            self.assertEqual(
                report["byte_metrics"]["tombstoned_source_bytes"],
                400,
            )
            self.assertEqual(
                report["byte_metrics"]["rejected_source_bytes"],
                50,
            )
            self.assertFalse(report["aggregate_score_emitted"])
            self.assertNotIn("score", report)

    def test_missing_obligation_is_reported_without_becoming_truth_claim(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            source, output = self.build_output(root)
            obligations_path = root / "obligations.json"
            build_obligations(
                obligations_path,
                required_conversation_ids=["conv-1", "conv-missing"],
            )
            report = evaluate_import(source, output, obligations_path)
            dimension = report["semantic_retention"]["conversation_retention"]
            self.assertEqual(dimension["status"], "fail")
            self.assertEqual(dimension["missing"], ["conv-missing"])
            self.assertIn(
                "SEMANTIC_COVERAGE != FACTUAL_TRUTH",
                report["boundaries"],
            )

    def test_no_obligations_file_means_unassessed_not_failed(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            source, output = self.build_output(root)
            report = evaluate_import(source, output)
            self.assertEqual(
                report["semantic_retention"]["status"],
                "unassessed",
            )
            self.assertEqual(
                report["semantic_retention"]
                ["conversation_retention"]["status"],
                "unassessed",
            )

    def test_empty_receipted_obligations_remain_unassessed(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            source, output = self.build_output(root)
            obligations_path = root / "obligations.json"
            build_obligations(obligations_path)
            report = evaluate_import(source, output, obligations_path)
            semantic = report["semantic_retention"]
            self.assertEqual(semantic["status"], "unassessed")
            self.assertEqual(semantic["negative_space"]["status"], "unassessed")
            self.assertTrue(
                all(
                    semantic[key]["status"] == "unassessed"
                    for key in (
                        "conversation_retention",
                        "message_retention",
                        "attachment_reference_retention",
                    )
                )
            )

    def test_evaluation_rejects_unrelated_source_bytes(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            _source, output = self.build_output(root)
            unrelated = root / "unrelated.zip"
            unrelated.write_bytes(b"not the import source")
            with self.assertRaises(EvaluationError) as ctx:
                evaluate_import(unrelated, output)
            self.assertEqual(ctx.exception.code, "source_candidate_mismatch")

    def test_unlisted_post_import_file_cannot_influence_semantic_result(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            source, output = self.build_output(root)
            extra = output / "unlisted/private.jsonl"
            extra.parent.mkdir(parents=True)
            extra.write_bytes(
                canonical_json_bytes(
                    {
                        "source_message_id": "fabricated-message",
                        "text": "post-import addition",
                    }
                )
            )
            obligations_path = root / "obligations.json"
            build_obligations(
                obligations_path,
                required_message_ids=["fabricated-message"],
            )
            with self.assertRaises(EvaluationError) as ctx:
                evaluate_import(source, output, obligations_path)
            self.assertEqual(ctx.exception.code, "candidate_invalid")

    def test_negative_classification_size_is_rejected(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            rows = [
                {
                    "path": "conversations.json",
                    "size_bytes": 200,
                    "decision": "extract",
                },
                {
                    "path": "asset.wav",
                    "size_bytes": -400,
                    "decision": "tombstone",
                },
                {
                    "path": "payload.exe",
                    "size_bytes": 50,
                    "decision": "reject",
                },
                {
                    "path": "note.txt",
                    "size_bytes": 20,
                    "decision": "keep",
                },
            ]
            source, output = self.build_output(
                root,
                classifications_override=rows,
            )
            with self.assertRaises(EvaluationError) as ctx:
                evaluate_import(source, output)
            self.assertEqual(ctx.exception.code, "classification_size")

    def test_forbidden_fragment_is_scanned_in_retained_artifacts(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            fragment = "FORBIDDEN PRIVATE FRAGMENT"
            source, output = self.build_output(
                root,
                retained_note=(fragment + "\n").encode("utf-8"),
            )
            obligations_path = root / "obligations.json"
            build_obligations(
                obligations_path,
                forbidden_text_fragments=[fragment],
            )
            report = evaluate_import(source, output, obligations_path)
            negative = report["semantic_retention"]["negative_space"]
            self.assertEqual(negative["status"], "fail")
            self.assertEqual(negative["forbidden_fragments_found"], [fragment])
            self.assertEqual(report["semantic_retention"]["status"], "fail")

    def test_obligation_self_receipt_is_verified(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            source, output = self.build_output(root)
            obligations_path = root / "obligations.json"
            build_obligations(
                obligations_path,
                required_message_ids=["msg-1"],
            )
            value = json.loads(obligations_path.read_text(encoding="utf-8"))
            value["required_message_ids"] = ["fabricated"]
            obligations_path.write_bytes(canonical_json_bytes(value))
            with self.assertRaises(EvaluationError) as ctx:
                evaluate_import(source, output, obligations_path)
            self.assertEqual(ctx.exception.code, "self_hash_mismatch")


if __name__ == "__main__":
    unittest.main()
