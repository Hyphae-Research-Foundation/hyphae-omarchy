# SPDX-License-Identifier: Apache-2.0
"""Exercise artifact trust boundaries and preservation using disposable profiles."""
import hashlib
import io
import json
import os
from pathlib import Path
import sys
import tarfile
import tempfile
import unittest
from unittest.mock import patch

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "scripts"))
import runtime


class InstallerTests(unittest.TestCase):
    def setUp(self):
        self.temporary = tempfile.TemporaryDirectory(prefix="hyphae-installer-")
        self.root = Path(self.temporary.name)
        self.plugin = self.root / "plugin"
        self.plugin.mkdir()
        self.data = self.root / "data"
        self.environment = patch.dict(os.environ, {"XDG_DATA_HOME": str(self.data)})
        self.environment.start()
        self.location = patch.object(runtime, "PLUGIN", self.plugin)
        self.location.start()
        self.files = {"bin/hyphae":b"native-runtime", "bin/hyphae-embed":b"native-candle-worker"}

    def tearDown(self):
        self.location.stop()
        self.environment.stop()
        self.temporary.cleanup()

    def bundle(self, extra=None):
        path = self.plugin / "runtime.tar.gz"
        with tarfile.open(path,"w:gz") as archive:
            for name, value in self.files.items():
                entry = tarfile.TarInfo(name)
                entry.size = len(value)
                archive.addfile(entry,io.BytesIO(value))
            if extra is not None:
                archive.addfile(extra)
        descriptor = {"name":path.name,"bytes":path.stat().st_size,"sha256":runtime.digest(path)}
        inventory = {name:{"bytes":len(value),"sha256":hashlib.sha256(value).hexdigest()} for name,value in self.files.items()}
        lock = {"schema":"hyphae-omarchy-runtime-lock-v1","source_commit":"a"*40,"bundle":descriptor,"files":inventory}
        (self.plugin/"runtime.lock.json").write_text(json.dumps(lock))
        return path,lock

    def test_install_is_idempotent_and_tampered_runtime_is_preserved_and_rejected(self):
        bundle,lock = self.bundle()
        runtime.install_runtime({"bundle":str(bundle)})
        receipt = self.data / "hyphae-omarchy/runtime.json"
        installed = json.loads(receipt.read_text())
        self.assertTrue(installed["activation_pending"])
        self.assertEqual(Path(installed["binary"]).stat().st_mode & 0o777,0o700)
        runtime.install_runtime({"bundle":str(bundle)})
        Path(installed["binary"]).write_bytes(b"changed")
        with self.assertRaisesRegex(ValueError,"inventory differs"):
            runtime.install_runtime({"bundle":str(bundle)})
        self.assertEqual(Path(installed["binary"]).read_bytes(),b"changed")
        self.assertEqual(json.loads(receipt.read_text())["bundle_sha256"],lock["bundle"]["sha256"])

    def test_archive_digest_mismatch_does_not_create_an_active_receipt(self):
        bundle,_ = self.bundle()
        with bundle.open("ab") as output: output.write(b"tampered")
        with self.assertRaisesRegex(ValueError,"reviewed lock"):
            runtime.install_runtime({"bundle":str(bundle)})
        self.assertFalse((self.data/"hyphae-omarchy/runtime.json").exists())

    def test_symlink_and_path_traversal_members_never_escape_staging(self):
        for name,kind in (("../../outside",tarfile.REGTYPE),("bin/unexpected",tarfile.SYMTYPE)):
            with self.subTest(name=name):
                extra=tarfile.TarInfo(name); extra.type=kind; extra.linkname="../../outside"
                bundle,_=self.bundle(extra)
                with self.assertRaises(ValueError): runtime.install_runtime({"bundle":str(bundle)})
                self.assertFalse((self.root/"outside").exists())
                self.assertFalse((self.data/"hyphae-omarchy/runtime.json").exists())

    def test_model_is_verified_offline_and_a_different_existing_model_is_preserved(self):
        files=[]
        cache=self.data/"hyphae-omarchy/downloads"
        cache.mkdir(parents=True)
        for name in ("config.json","tokenizer.json","model.safetensors"):
            payload=name.encode(); digest=hashlib.sha256(payload).hexdigest()
            (cache/digest).write_bytes(payload)
            files.append({"path":name,"sha256":digest,"bytes":len(payload),"url":"https://example.invalid/pinned"})
        (self.plugin/"models.lock.json").write_text(json.dumps({"schema":"hyphae-omarchy-model-lock-v1","id":"bge-small-en-v1.5","files":files}))
        with patch("urllib.request.urlopen",side_effect=AssertionError("must use verified cache")):
            result=runtime.install_model({})
            runtime.install_model({})
        model=Path(result["model_dir"])/"model.safetensors"
        model.write_bytes(b"user-model")
        with self.assertRaisesRegex(ValueError,"preserved"):
            runtime.install_model({})
        self.assertEqual(model.read_bytes(),b"user-model")

    def test_symlinked_immutable_runtime_is_rejected(self):
        bundle,lock=self.bundle()
        versions=self.data/"hyphae-omarchy/runtimes"
        versions.mkdir(parents=True)
        (versions/lock["bundle"]["sha256"]).symlink_to(self.plugin,target_is_directory=True)
        with self.assertRaisesRegex(ValueError,"symlink"):
            runtime.install_runtime({"bundle":str(bundle)})


if __name__ == "__main__":
    unittest.main()
