import unittest
from pathlib import Path

from qsol_import.canonical import loads_strict


ROOT = Path(__file__).parents[1]


class RoadmapCompletionTests(unittest.TestCase):
    def test_engineering_phases_have_no_open_checkbox(self):
        roadmap = (ROOT / "ROADMAP.md").read_text(encoding="utf-8")
        engineering, external = roadmap.split("## External evidence gate", 1)
        self.assertNotIn("- [ ]", engineering)
        self.assertEqual(external.count("- [ ]"), 1)
        self.assertIn("real personal ChatGPT export snapshots", external)
        self.assertIn("CLAIMED_EXECUTION != EXECUTED", roadmap)

    def test_completion_contract_schemas_are_strict_json_with_unique_ids(self):
        names = [
            "context-import-decision.schema.json",
            "control-handoff.schema.json",
            "retention-obligations.schema.json",
            "evaluation.schema.json",
            "ark-cleanroom-receipt.schema.json",
            "portability-receipt.schema.json",
        ]
        ids: set[str] = set()
        for name in names:
            with self.subTest(schema=name):
                value = loads_strict((ROOT / "schemas" / name).read_bytes())
                self.assertIsInstance(value, dict)
                self.assertEqual(value["$schema"], "https://json-schema.org/draft/2020-12/schema")
                self.assertNotIn(value["$id"], ids)
                ids.add(value["$id"])
                self.assertFalse(value.get("additionalProperties", True))

    def test_completion_documentation_is_present(self):
        for relative in (
            "docs/CONTEXT-HANDOFF.md",
            "docs/EVALUATION.md",
            "PORTABILITY.md",
        ):
            with self.subTest(path=relative):
                path = ROOT / relative
                self.assertTrue(path.is_file())
                self.assertGreater(path.stat().st_size, 500)


if __name__ == "__main__":
    unittest.main()
