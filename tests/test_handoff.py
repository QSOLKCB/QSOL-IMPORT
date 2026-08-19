import json
import tempfile
import unittest
from pathlib import Path

from qsol_import.canonical import canonical_json_bytes, sha256_bytes, sha256_file
from qsol_import.handoff import (
    HandoffError,
    stage_control_handoff,
    verify_candidate_root,
    verify_context_decision,
)
from roadmap_helpers import (
    build_candidate,
    build_decision,
    build_thoth_route_receipt,
)


def rewrite_self_receipt(path: Path, mutate) -> dict:
    value = json.loads(path.read_text(encoding="utf-8"))
    mutate(value)
    body = {key: item for key, item in value.items() if key != "receipt_sha256"}
    value["receipt_sha256"] = sha256_bytes(canonical_json_bytes(body))
    path.write_bytes(canonical_json_bytes(value))
    return value


def rewrite_decision(path: Path, mutate) -> dict:
    value = json.loads(path.read_text(encoding="utf-8"))
    mutate(value)
    body = {key: item for key, item in value.items() if key != "decision_sha256"}
    value["decision_sha256"] = sha256_bytes(canonical_json_bytes(body))
    path.write_bytes(canonical_json_bytes(value))
    return value


class ContextHandoffTests(unittest.TestCase):
    def test_partial_acceptance_stages_control_pack_without_roles_or_route_churn(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            candidate_root = root / "candidate"
            build_candidate(
                candidate_root,
                {
                    "records/accepted.jsonl": b'{"id":"accepted"}\n',
                    "records/rejected.jsonl": b'{"id":"rejected"}\n',
                },
            )
            decision_path = root / "decision.json"
            build_decision(
                candidate_root,
                decision_path,
                {
                    "records/accepted.jsonl": "accept",
                    "records/rejected.jsonl": "reject",
                },
            )
            route = root / "thoth-route.json"
            route_receipt = build_thoth_route_receipt(route)
            route_before = sha256_file(route)

            handoff = stage_control_handoff(
                candidate_root,
                decision_path,
                root / "handoff",
                privacy_class="RESTRICTED",
                recovery_class="OUTER_SHELL",
                thoth_route_receipt=route,
            )
            self.assertEqual(handoff["decision"], "partially_accepted")
            self.assertFalse(handoff["concap_roles_assigned"])
            route_binding = handoff["thoth_route_receipt"]
            self.assertEqual(route_binding["protocol"], "QSOL-THOTH/ROUTE-DECISION/1")
            self.assertEqual(route_binding["decision_sha256"], route_receipt["decision_sha256"])
            self.assertEqual(route_binding["file_sha256_before"], route_before)
            self.assertEqual(route_binding["file_sha256_after"], route_before)
            self.assertTrue(route_binding["unchanged"])
            self.assertEqual(sha256_file(route), route_before)

            output = root / "handoff"
            self.assertTrue((output / "accepted/records/accepted.jsonl").exists())
            self.assertFalse((output / "accepted/records/rejected.jsonl").exists())
            pack = json.loads((output / "CONTROL-PACK.spec.json").read_text())
            self.assertEqual(pack["protocol"], "qsol-control-restore-pack-spec/1")
            self.assertEqual(pack["capsule"], "qsol-import-accepted.dat")
            self.assertTrue(pack["entries"])
            self.assertTrue(all("role_id" not in entry for entry in pack["entries"]))
            self.assertTrue(
                all(
                    entry["recovery_class"] == pack["recovery_class"]
                    for entry in pack["entries"]
                )
            )
            self.assertIn(
                "CONTROL-PACK.spec.json",
                (output / "SHA256SUMS").read_text(),
            )

    def test_rejected_candidate_emits_handoff_but_no_control_pack(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            candidate_root = root / "candidate"
            build_candidate(
                candidate_root,
                {"records/item.jsonl": b'{"id":"x"}\n'},
            )
            decision_path = root / "decision.json"
            build_decision(
                candidate_root,
                decision_path,
                {"records/item.jsonl": "reject"},
            )
            handoff = stage_control_handoff(
                candidate_root,
                decision_path,
                root / "handoff",
            )
            self.assertEqual(handoff["decision"], "rejected")
            self.assertIsNone(handoff["control_pack_spec_path"])
            self.assertFalse((root / "handoff/CONTROL-PACK.spec.json").exists())
            self.assertTrue(
                (root / "handoff/review/CONTEXT-DECISION.json").exists()
            )

    def test_context_decision_must_cover_every_artifact(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            candidate_root = root / "candidate"
            build_candidate(candidate_root, {"a.txt": b"a", "b.txt": b"b"})
            decision_path = root / "decision.json"
            build_decision(
                candidate_root,
                decision_path,
                {"a.txt": "accept", "b.txt": "accept"},
            )
            rewrite_decision(decision_path, lambda value: value["artifacts"].pop())
            candidate = verify_candidate_root(candidate_root)
            with self.assertRaises(HandoffError) as ctx:
                verify_context_decision(candidate, decision_path)
            self.assertEqual(ctx.exception.code, "decision_artifact_coverage")

    def test_candidate_artifact_tamper_fails_closed(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            candidate_root = root / "candidate"
            build_candidate(candidate_root, {"a.txt": b"a"})
            (candidate_root / "a.txt").write_bytes(b"tampered")
            with self.assertRaises(HandoffError) as ctx:
                verify_candidate_root(candidate_root)
            self.assertEqual(ctx.exception.code, "artifact_size_mismatch")

    def test_unlisted_candidate_file_fails_closed(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            candidate_root = root / "candidate"
            build_candidate(candidate_root, {"a.txt": b"a"})
            (candidate_root / "unlisted.txt").write_text("not receipted")
            with self.assertRaises(HandoffError) as ctx:
                verify_candidate_root(candidate_root)
            self.assertEqual(ctx.exception.code, "candidate_tree_mismatch")

    def test_import_receipt_output_identity_is_recomputed(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            candidate_root = root / "candidate"
            build_candidate(candidate_root, {"a.txt": b"a"})
            rewrite_self_receipt(
                candidate_root / "IMPORT.json",
                lambda value: value.__setitem__("output_sha256", "0" * 64),
            )
            with self.assertRaises(HandoffError) as ctx:
                verify_candidate_root(candidate_root)
            self.assertEqual(ctx.exception.code, "output_identity_mismatch")

    def test_import_receipt_counters_must_be_nonnegative_and_consistent(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            candidate_root = root / "candidate"
            build_candidate(candidate_root, {"a.txt": b"a"})
            rewrite_self_receipt(
                candidate_root / "IMPORT.json",
                lambda value: value.__setitem__("files_seen", -1),
            )
            with self.assertRaises(HandoffError) as ctx:
                verify_candidate_root(candidate_root)
            self.assertEqual(ctx.exception.code, "invalid_integer")

    def test_malformed_thoth_route_receipt_is_not_bound(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            candidate_root = root / "candidate"
            build_candidate(candidate_root, {"a.txt": b"a"})
            decision_path = root / "decision.json"
            build_decision(candidate_root, decision_path, {"a.txt": "accept"})
            route = root / "route.json"
            route.write_text('{"protocol":"QSOL-THOTH/ROUTE-DECISION/1"}')
            with self.assertRaises(HandoffError) as ctx:
                stage_control_handoff(
                    candidate_root,
                    decision_path,
                    root / "handoff",
                    thoth_route_receipt=route,
                )
            self.assertEqual(ctx.exception.code, "field_mismatch")
            self.assertFalse((root / "handoff").exists())

    def test_output_must_not_overlap_candidate_source(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            candidate_root = root / "candidate"
            build_candidate(candidate_root, {"a.txt": b"original"})
            decision_path = root / "decision.json"
            build_decision(candidate_root, decision_path, {"a.txt": "accept"})
            original_candidate = (candidate_root / "CANDIDATE.json").read_bytes()
            original_artifact = (candidate_root / "a.txt").read_bytes()

            with self.assertRaises(HandoffError) as ctx:
                stage_control_handoff(
                    candidate_root,
                    decision_path,
                    candidate_root,
                )
            self.assertEqual(ctx.exception.code, "output_overlap")
            self.assertEqual(
                (candidate_root / "CANDIDATE.json").read_bytes(),
                original_candidate,
            )
            self.assertEqual(
                (candidate_root / "a.txt").read_bytes(),
                original_artifact,
            )

    def test_existing_file_output_is_rejected_without_replacement(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            candidate_root = root / "candidate"
            build_candidate(candidate_root, {"a.txt": b"a"})
            decision_path = root / "decision.json"
            build_decision(candidate_root, decision_path, {"a.txt": "accept"})
            output = root / "handoff"
            output.write_bytes(b"sentinel")

            with self.assertRaises(HandoffError) as ctx:
                stage_control_handoff(candidate_root, decision_path, output)
            self.assertEqual(ctx.exception.code, "output_type")
            self.assertTrue(output.is_file())
            self.assertEqual(output.read_bytes(), b"sentinel")

    def test_existing_symlink_output_is_rejected_without_replacement(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            candidate_root = root / "candidate"
            build_candidate(candidate_root, {"a.txt": b"a"})
            decision_path = root / "decision.json"
            build_decision(candidate_root, decision_path, {"a.txt": "accept"})
            target = root / "target"
            target.mkdir()
            output = root / "handoff"
            try:
                output.symlink_to(target, target_is_directory=True)
            except OSError as exc:
                self.skipTest(f"directory symlink unavailable: {exc}")

            with self.assertRaises(HandoffError) as ctx:
                stage_control_handoff(candidate_root, decision_path, output)
            self.assertEqual(ctx.exception.code, "output_type")
            self.assertTrue(output.is_symlink())


if __name__ == "__main__":
    unittest.main()
