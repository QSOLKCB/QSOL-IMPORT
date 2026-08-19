import tempfile
import unittest
from pathlib import Path

from qsol_import.ark_cleanroom import ArkCleanroomError, evaluate_clean_room
from qsol_import.canonical import canonical_json_bytes, sha256_file


class ArkCleanroomTests(unittest.TestCase):
    def build_fixture(self, root: Path) -> tuple[Path, Path]:
        objects = root / "objects"
        objects.mkdir()
        object_path = objects / "synthetic-portable-object.dat"
        object_path.write_bytes(b"synthetic portable candidate object\n")
        object_id = "sha256:" + sha256_file(object_path)
        object_row = {
            "object_id": object_id,
            "size_bytes": object_path.stat().st_size,
            "bytes_sha256": object_id,
        }
        observation = {
            "protocol": "QSOL-ARK/THOTH-EVALUATION-OBSERVATION/1",
            "schema_version": "1.0.0",
            "trial_id": "qsol_import_synthetic_clean_room",
            "assessment_authority": "explicit-observations-not-automatic-truth",
            "route": {
                "selected_role_ids": ["concap.identity.core/1", "concap.workstyle.engineering/1"],
                "required_role_ids": ["concap.identity.core/1", "concap.workstyle.engineering/1"],
                "justified_role_ids": ["concap.identity.core/1", "concap.workstyle.engineering/1"],
            },
            "style_fidelity": {
                "obligations": [
                    {"id": "compact_engineering_delivery", "outcome": "pass"},
                    {"id": "receiver_style_preserved", "outcome": "pass"},
                ]
            },
            "factual_accuracy": {
                "claims": [
                    {"id": "identity_claim", "outcome": "correct"},
                    {"id": "optional_unverified_claim", "outcome": "unverified"},
                ]
            },
            "historical_reconstruction": {
                "obligations": [
                    {"id": "candidate_lineage", "outcome": "covered"},
                    {"id": "unknown_external_history", "outcome": "unverified"},
                ]
            },
            "clean_room": {
                "portable_inputs_only": True,
                "private_source_repository_access": False,
                "private_context_connector_access": False,
                "hidden_provider_memory_dependency": False,
            },
            "transports": [
                {"id": transport, "objects": [dict(object_row)]}
                for transport in (
                    "local-directory",
                    "archive",
                    "static-http",
                    "capability-relay",
                )
            ],
            "negative_space": {
                "style_leakage": False,
                "unsupported_historical_interpolation": False,
                "accidental_private_source_dependency": False,
            },
            "boundaries": [
                "STYLE_FIDELITY != FACTUAL_ACCURACY != PHYSICAL_TRUTH",
                "ROUTE_SUFFICIENCY != ROUTE_MINIMALITY",
                "HISTORICAL_COVERAGE != HISTORICAL_TRUTH",
                "TRANSPORT_EQUIVALENCE != AUTHORITY",
                "CLEAN_ROOM_SUCCESS != PRIVATE_SOURCE_ACCESS",
                "MEASURED_OBSERVATION != AUTOMATIC_TRUTH",
                "AGGREGATE_SCORE = FORBIDDEN",
            ],
        }
        observation_path = root / "observation.json"
        observation_path.write_bytes(canonical_json_bytes(observation))
        return observation_path, objects

    def test_synthetic_clean_room_conformance_is_separate_from_model_execution(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            observation, objects = self.build_fixture(root)
            receipt = evaluate_clean_room(
                observation,
                objects,
                ark_trial_id="P1",
                record_class="synthetic-conformance",
            )
            self.assertTrue(receipt["conformance_pass"])
            self.assertFalse(receipt["model_execution_claimed"])
            self.assertFalse(receipt["t5_ai_reconstruction_implemented"])
            self.assertFalse(receipt["aggregate_score_emitted"])
            self.assertEqual(receipt["ark_contract_protocol"], "QSOL-ARK/PERSONAL-CONTINUITY/1")
            self.assertTrue(receipt["transport_equivalence"]["pass"])

    def test_transport_identity_drift_fails_closed(self):
        import json

        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            observation_path, objects = self.build_fixture(root)
            observation = json.loads(observation_path.read_text())
            observation["transports"][1]["objects"] = []
            observation_path.write_bytes(canonical_json_bytes(observation))
            with self.assertRaises(ArkCleanroomError) as ctx:
                evaluate_clean_room(observation_path, objects, ark_trial_id="P1")
            self.assertEqual(ctx.exception.code, "transport_equivalence")

    def test_external_execution_claim_requires_receipt_hash(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            observation, objects = self.build_fixture(root)
            with self.assertRaises(ArkCleanroomError) as ctx:
                evaluate_clean_room(
                    observation,
                    objects,
                    ark_trial_id="P2",
                    record_class="externally-observed-clean-room",
                )
            self.assertEqual(ctx.exception.code, "execution_receipt")

    def test_private_source_dependency_is_rejected(self):
        import json

        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            observation_path, objects = self.build_fixture(root)
            observation = json.loads(observation_path.read_text())
            observation["clean_room"]["private_source_repository_access"] = True
            observation_path.write_bytes(canonical_json_bytes(observation))
            with self.assertRaises(ArkCleanroomError) as ctx:
                evaluate_clean_room(observation_path, objects, ark_trial_id="P1")
            self.assertEqual(ctx.exception.code, "clean_room_boundary")


if __name__ == "__main__":
    unittest.main()
