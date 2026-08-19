import json
import tempfile
import unittest
from pathlib import Path

from qsol_import.canonical import sha256_file
from qsol_import.handoff import HandoffError, stage_control_handoff, verify_candidate_root, verify_context_decision
from roadmap_helpers import build_candidate, build_decision


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
            route.write_bytes(
                b'{"protocol":"QSOL-THOTH/ROUTE-DECISION/1","decision_sha256":"sha256:b7cce93e193dad6a488b2ed0354ee06856bc24b6da3f1787a5a7eac9dc5a1b19"}\n'
            )
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
            self.assertEqual(handoff["thoth_route_receipt"]["sha256_before"], route_before)
            self.assertTrue(handoff["thoth_route_receipt"]["unchanged"])
            self.assertEqual(sha256_file(route), route_before)

            output = root / "handoff"
            self.assertTrue((output / "accepted/records/accepted.jsonl").exists())
            self.assertFalse((output / "accepted/records/rejected.jsonl").exists())
            pack = json.loads((output / "CONTROL-PACK.spec.json").read_text())
            self.assertEqual(pack["protocol"], "qsol-control-restore-pack-spec/1")
            self.assertEqual(pack["capsule"], "qsol-import-accepted.dat")
            self.assertTrue(pack["entries"])
            self.assertTrue(all("role_id" not in entry for entry in pack["entries"]))
            self.assertTrue(all(entry["recovery_class"] == pack["recovery_class"] for entry in pack["entries"]))
            self.assertIn("CONTROL-PACK.spec.json", (output / "SHA256SUMS").read_text())

    def test_rejected_candidate_emits_handoff_but_no_control_pack(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            candidate_root = root / "candidate"
            build_candidate(candidate_root, {"records/item.jsonl": b'{"id":"x"}\n'})
            decision_path = root / "decision.json"
            build_decision(candidate_root, decision_path, {"records/item.jsonl": "reject"})
            handoff = stage_control_handoff(candidate_root, decision_path, root / "handoff")
            self.assertEqual(handoff["decision"], "rejected")
            self.assertIsNone(handoff["control_pack_spec_path"])
            self.assertFalse((root / "handoff/CONTROL-PACK.spec.json").exists())
            self.assertTrue((root / "handoff/review/CONTEXT-DECISION.json").exists())

    def test_context_decision_must_cover_every_artifact(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            candidate_root = root / "candidate"
            build_candidate(candidate_root, {"a.txt": b"a", "b.txt": b"b"})
            decision_path = root / "decision.json"
            build_decision(candidate_root, decision_path, {"a.txt": "accept", "b.txt": "accept"})
            decision = json.loads(decision_path.read_text())
            decision["artifacts"].pop()
            decision_path.write_text(json.dumps(decision))
            candidate = verify_candidate_root(candidate_root)
            with self.assertRaises(HandoffError):
                verify_context_decision(candidate, decision_path)

    def test_candidate_artifact_tamper_fails_closed(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            candidate_root = root / "candidate"
            build_candidate(candidate_root, {"a.txt": b"a"})
            (candidate_root / "a.txt").write_bytes(b"tampered")
            with self.assertRaises(HandoffError) as ctx:
                verify_candidate_root(candidate_root)
            self.assertEqual(ctx.exception.code, "artifact_size_mismatch")


if __name__ == "__main__":
    unittest.main()
