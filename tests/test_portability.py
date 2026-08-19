import tempfile
import unittest
from pathlib import Path

from qsol_import.portability import assert_supported_runtime, compare_trees, tree_sha256


class PortabilityTests(unittest.TestCase):
    def test_supported_ci_runtime_and_identical_trees(self):
        assert_supported_runtime()
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            first = root / "first"
            second = root / "second"
            (first / "nested").mkdir(parents=True)
            (second / "nested").mkdir(parents=True)
            (first / "a.txt").write_bytes(b"alpha\n")
            (second / "a.txt").write_bytes(b"alpha\n")
            (first / "nested/b.bin").write_bytes(bytes(range(32)))
            (second / "nested/b.bin").write_bytes(bytes(range(32)))
            receipt = compare_trees(first, second)
            self.assertTrue(receipt["byte_identical"])
            self.assertEqual(receipt["first_tree_sha256"], receipt["second_tree_sha256"])
            self.assertEqual(tree_sha256(first), tree_sha256(second))

    def test_different_tree_is_not_byte_identical(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            first = root / "first"
            second = root / "second"
            first.mkdir()
            second.mkdir()
            (first / "value.txt").write_bytes(b"one")
            (second / "value.txt").write_bytes(b"two")
            receipt = compare_trees(first, second)
            self.assertFalse(receipt["byte_identical"])


if __name__ == "__main__":
    unittest.main()
