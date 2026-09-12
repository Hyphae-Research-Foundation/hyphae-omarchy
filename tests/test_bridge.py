# SPDX-License-Identifier: Apache-2.0
"""A timed-out host operation must not leave a configuration writer running."""
import os
from pathlib import Path
import signal
import subprocess
import sys
import tempfile
import time
import unittest
from unittest.mock import patch

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "scripts"))
import bridge


@unittest.skipUnless(os.name == "posix", "The Omarchy bridge owns a POSIX process group")
class BridgeTimeoutTests(unittest.TestCase):
    def test_timeout_stops_descendants_before_they_can_write_configuration(self):
        with tempfile.TemporaryDirectory(prefix="hyphae-bridge-") as temporary:
            root = Path(temporary)
            marker = root / "late-config-write"
            started = root / "started"
            executable = root / "runtime"
            child = "import pathlib,sys,time; time.sleep(0.7); pathlib.Path(sys.argv[1]).touch()"
            executable.write_text(
                f"#!{sys.executable}\n"
                "import os,pathlib,subprocess,sys,time\n"
                f"subprocess.Popen([sys.executable, '-c', {child!r}, {str(marker)!r}])\n"
                f"pathlib.Path({str(started)!r}).write_text(str(os.getpid()))\n"
                "time.sleep(60)\n"
            )
            executable.chmod(0o700)
            real_popen = subprocess.Popen

            class ShortDeadline(real_popen):
                def communicate(self, input=None, timeout=None):
                    return super().communicate(input, timeout=0.3 if timeout is not None else None)

            try:
                with patch.object(bridge, "runtime_binary", return_value=str(executable)), \
                        patch.object(bridge.subprocess, "Popen", ShortDeadline):
                    with self.assertRaises(subprocess.TimeoutExpired):
                        bridge.execute({"schema": bridge.SCHEMA, "operation": "configure",
                                        "arguments": {"host": "claude", "access": "read"}, "id": 1})
                self.assertTrue(started.exists(), "The real child process must have started")
                time.sleep(0.8)
                self.assertFalse(marker.exists(), "A descendant changed configuration after timeout")
            finally:
                if started.exists():
                    try:
                        os.killpg(int(started.read_text()), signal.SIGKILL)
                    except ProcessLookupError:
                        pass


if __name__ == "__main__":
    unittest.main()
