import io
import json
import tarfile
import tempfile
import unittest
from pathlib import Path

from qsol_import.adapter_pipeline import import_with_adapter
from qsol_import.adapters.github import GitHubAdapter


POLICY = Path(__file__).parents[1] / "policies" / "conversation-first.json"


def add_bytes(tf: tarfile.TarFile, name: str, data: bytes) -> None:
    info = tarfile.TarInfo(name)
    info.size = len(data)
    info.mtime = 0
    tf.addfile(info, io.BytesIO(data))


class GitHubAdapterTests(unittest.TestCase):
    def build_archive(self, root: Path) -> Path:
        source = root / "github-migration.tar.gz"
        issues = [
            {
                "id": 101,
                "number": 7,
                "title": "Migration issue",
                "body": "Issue body",
                "created_at": "2026-01-01T00:00:00Z",
                "user": {"login": "trent"},
            }
        ]
        comments = [
            {
                "id": 201,
                "issue_id": 101,
                "body": "Issue comment",
                "created_at": "2026-01-01T00:01:00Z",
                "user": {"login": "reviewer"},
            }
        ]
        with tarfile.open(source, "w:gz") as tf:
            add_bytes(tf, "issues.json", json.dumps(issues).encode())
            add_bytes(tf, "issue_comments.json", json.dumps(comments).encode())
            add_bytes(tf, "attachments/screenshot.png", b"\x89PNG\r\n\x1a\n" + b"x" * 32)
            add_bytes(tf, "repositories/example.git/HEAD", b"ref: refs/heads/main\n")
        return source

    def test_github_tar_migration_normalizes_threads(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            source = self.build_archive(root)
            receipt = import_with_adapter(source, root / "out", POLICY, GitHubAdapter())
            self.assertEqual(receipt["adapter_id"], "github-migration-export/1")
            self.assertEqual(receipt["conversations"], 1)
            self.assertEqual(receipt["messages"], 2)
            self.assertEqual(receipt["files_tombstoned"], 1)
            self.assertEqual(receipt["files_rejected"], 1)

            messages = [json.loads(line) for line in (root / "out/messages/messages.jsonl").read_text().splitlines()]
            self.assertEqual([row["text"] for row in messages], ["Issue body", "Issue comment"])
            self.assertEqual([row["name"] for row in messages], ["trent", "reviewer"])

            provenance = [json.loads(line) for line in (root / "out/provenance/provenance.jsonl").read_text().splitlines()]
            self.assertEqual(len(provenance), 4)
            self.assertTrue(all(row["protocol"] == "QSOL-IMPORT/PROVENANCE/1" for row in provenance))

            tombstone = json.loads((root / "out/tombstones/tombstones.jsonl").read_text())
            self.assertEqual(tombstone["reason"], "github_attachment_payload")

    def test_tar_traversal_fails_closed(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            source = root / "bad.tar.gz"
            with tarfile.open(source, "w:gz") as tf:
                add_bytes(tf, "../escape.json", b"[]")
            with self.assertRaises(ValueError):
                import_with_adapter(source, root / "out", POLICY, GitHubAdapter())


if __name__ == "__main__":
    unittest.main()
