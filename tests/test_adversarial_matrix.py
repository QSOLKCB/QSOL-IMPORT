import io
import json
import tarfile
import tempfile
import unittest
import warnings
import zipfile
from pathlib import Path

from qsol_import.adapter_pipeline import import_with_adapter
from qsol_import.adapters.generic import GenericAdapter
from qsol_import.core import import_openai_zip


POLICY = Path(__file__).parents[1] / "policies" / "conversation-first.json"
MANIFEST = Path(__file__).parent / "fixtures" / "adversarial" / "manifest.json"
FIXED_ZIP_TIME = (1980, 1, 1, 0, 0, 0)


def write_member(zf: zipfile.ZipFile, name: str, data: bytes) -> None:
    info = zipfile.ZipInfo(name, date_time=FIXED_ZIP_TIME)
    info.compress_type = zipfile.ZIP_DEFLATED
    info.external_attr = 0o100644 << 16
    zf.writestr(info, data)


def build_zip(path: Path, members: list[tuple[str, bytes]]) -> None:
    with zipfile.ZipFile(path, "w") as zf:
        for name, data in members:
            write_member(zf, name, data)


def add_tar_bytes(tf: tarfile.TarFile, name: str, data: bytes) -> None:
    info = tarfile.TarInfo(name)
    info.size = len(data)
    info.mtime = 0
    tf.addfile(info, io.BytesIO(data))


class AdversarialMatrixTests(unittest.TestCase):
    def test_manifest_declares_every_exercised_case(self):
        manifest = json.loads(MANIFEST.read_text())
        self.assertEqual(manifest["protocol"], "QSOL-IMPORT/ADVERSARIAL-FIXTURE-MANIFEST/1")
        declared = {row["id"] for row in manifest["cases"]}
        self.assertEqual(
            declared,
            {
                "malformed-json",
                "duplicate-json-member",
                "nonfinite-json",
                "disguised-wav",
                "duplicate-zip-member",
                "normalized-path-collision",
                "decompression-bomb-ratio",
                "tar-symlink",
                "tar-traversal",
            },
        )

    def test_malformed_duplicate_and_nonfinite_json_fail_closed(self):
        cases = {
            "malformed-json": b'[{"id":',
            "duplicate-json-member": b'[{"id":"a","id":"b"}]',
            "nonfinite-json": b'[{"value":NaN}]',
        }
        for case_id, payload in cases.items():
            with self.subTest(case=case_id), tempfile.TemporaryDirectory() as tmp:
                root = Path(tmp)
                source = root / "source.zip"
                build_zip(source, [("conversations.json", payload)])
                with self.assertRaises(ValueError):
                    import_openai_zip(source, root / "out", POLICY)
                self.assertFalse((root / "out").exists())

    def test_disguised_wav_is_tombstoned_not_retained_as_text(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            source = root / "source.zip"
            wav = b"RIFF" + (16).to_bytes(4, "little") + b"WAVEfmt " + b"x" * 64
            build_zip(source, [("conversations.json", b"[]"), ("notes/apparently.txt", wav)])
            receipt = import_openai_zip(source, root / "out", POLICY)
            self.assertEqual(receipt["files_tombstoned"], 1)
            classifications = json.loads((root / "out/reports/classifications.json").read_text())
            row = next(item for item in classifications if item["path"] == "notes/apparently.txt")
            self.assertEqual(row["kind"], "audio")
            self.assertEqual(row["decision"], "tombstone")

    def test_duplicate_and_normalized_zip_collisions_fail_closed(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            duplicate = root / "duplicate.zip"
            with warnings.catch_warnings():
                warnings.simplefilter("ignore")
                with zipfile.ZipFile(duplicate, "w") as zf:
                    write_member(zf, "conversations.json", b"[]")
                    write_member(zf, "same.txt", b"one")
                    write_member(zf, "same.txt", b"two")
            with self.assertRaises(ValueError):
                import_openai_zip(duplicate, root / "out", POLICY)

            collision = root / "collision.zip"
            build_zip(
                collision,
                [("conversations.json", b"[]"), ("./same.txt", b"one"), ("same.txt", b"two")],
            )
            with self.assertRaises(ValueError):
                import_openai_zip(collision, root / "out2", POLICY)

    def test_high_compression_ratio_fixture_is_rejected(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            policy = json.loads(POLICY.read_text())
            policy["archive_limits"]["max_compression_ratio"] = 2.0
            policy_path = root / "policy.json"
            policy_path.write_text(json.dumps(policy))
            source = root / "bomb.zip"
            build_zip(source, [("conversations.json", b"[]"), ("bomb.txt", b"0" * 200_000)])
            with self.assertRaises(ValueError):
                import_openai_zip(source, root / "out", policy_path)

    def test_tar_links_and_traversal_fail_closed(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            symlink_tar = root / "symlink.tar"
            with tarfile.open(symlink_tar, "w") as tf:
                add_tar_bytes(tf, "conversations.json", b'{"conversations":[]}')
                info = tarfile.TarInfo("link.json")
                info.type = tarfile.SYMTYPE
                info.linkname = "conversations.json"
                info.mtime = 0
                tf.addfile(info)
            with self.assertRaises(ValueError):
                import_with_adapter(symlink_tar, root / "out", POLICY, GenericAdapter())

            traversal_tar = root / "traversal.tar"
            with tarfile.open(traversal_tar, "w") as tf:
                add_tar_bytes(tf, "../escape.json", b"[]")
            with self.assertRaises(ValueError):
                import_with_adapter(traversal_tar, root / "out2", POLICY, GenericAdapter())


if __name__ == "__main__":
    unittest.main()
