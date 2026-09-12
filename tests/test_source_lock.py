# SPDX-License-Identifier: Apache-2.0
"""Published source pins must reject drift and preserve local work."""
import json
from pathlib import Path
import subprocess
import sys
import tempfile
import unittest
from unittest.mock import patch

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "scripts"))
import source_lock


class SourceLockTests(unittest.TestCase):
    def checkout(self, directory):
        root = Path(directory) / "source"
        root.mkdir()
        subprocess.run(["git", "init", "--quiet", str(root)], check=True)
        (root / "content.txt").write_text("reviewed source\n")
        subprocess.run(["git", "-C", str(root), "add", "content.txt"], check=True)
        subprocess.run(["git", "-C", str(root), "-c", "user.name=Source Fixture",
                        "-c", "user.email=source@example.invalid", "commit", "--quiet", "-m", "Fixture"], check=True)
        identity = {"repository": "https://github.com/example/source.git",
                    "commit": source_lock.git(root, "rev-parse", "HEAD"),
                    "tree": source_lock.git(root, "rev-parse", "HEAD^{tree}")}
        return root, identity

    def test_local_changes_are_preserved_instead_of_reset(self):
        with tempfile.TemporaryDirectory() as temporary:
            root, identity = self.checkout(temporary)
            (root / "content.txt").write_text("local work\n")
            with self.assertRaisesRegex(ValueError, "local changes"):
                source_lock.fetch_source(root, identity)
            self.assertEqual((root / "content.txt").read_text(), "local work\n")

    def test_tree_drift_is_rejected_even_with_the_expected_commit(self):
        with tempfile.TemporaryDirectory() as temporary:
            root, identity = self.checkout(temporary)
            identity["tree"] = "0" * 40
            with self.assertRaisesRegex(ValueError, "commit/tree lock"):
                source_lock.verify_checkout(root, identity)
            self.assertEqual((root / "content.txt").read_text(), "reviewed source\n")

    def test_failed_fetch_does_not_leave_a_partial_checkout(self):
        with tempfile.TemporaryDirectory() as temporary:
            target = Path(temporary) / "checkout"
            with patch.object(source_lock, "git", side_effect=subprocess.CalledProcessError(1, "git")):
                with self.assertRaises(subprocess.CalledProcessError):
                    source_lock.fetch_source(target, {"commit": "1" * 40})
            self.assertFalse(target.exists())
            self.assertEqual(list(Path(temporary).iterdir()), [])

    def test_unpublished_and_credential_bearing_sources_are_rejected(self):
        with tempfile.TemporaryDirectory() as temporary:
            path = Path(temporary) / "source.lock.json"
            lock = {"schema": "hyphae-omarchy-source-lock-v2", "published": True,
                    "hyphae": {"repository": "https://user:secret@github.com/example/source.git",
                               "commit": "1" * 40, "tree": "2" * 40}}
            path.write_text(json.dumps(lock))
            with self.assertRaisesRegex(ValueError, "public GitHub HTTPS"):
                source_lock.load_lock(path)
            lock["published"] = False
            path.write_text(json.dumps(lock))
            with self.assertRaisesRegex(ValueError, "published source lock"):
                source_lock.load_lock(path)


if __name__ == "__main__":
    unittest.main()
