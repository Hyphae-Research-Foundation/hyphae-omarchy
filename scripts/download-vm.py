#!/usr/bin/env python3
# SPDX-License-Identifier: Apache-2.0
"""Download the pinned Omarchy ISO in resumable bounded ranges, then verify it."""
import concurrent.futures
import hashlib
import json
from pathlib import Path
import shutil
import subprocess
import time

ROOT = Path(__file__).resolve().parents[1]
LOCK = json.loads((ROOT / "tests/omarchy/image.lock.json").read_text())
DESTINATION = ROOT / "target/vm"
CHUNK = 128 * 1024 * 1024


def sha(path):
    with path.open("rb") as source:
        return hashlib.file_digest(source, "sha256").hexdigest()


def main():
    DESTINATION.mkdir(parents=True, exist_ok=True)
    image = DESTINATION / f"omarchy-{LOCK['version']}.iso"
    if image.is_file() and image.stat().st_size == LOCK["bytes"] and sha(image) == LOCK["sha256"]:
        print("Pinned Omarchy ISO is already verified.", flush=True)
        return
    parts = DESTINATION / f"iso-{LOCK['sha256']}.parts"
    parts.mkdir(exist_ok=True)
    count = (LOCK["bytes"] + CHUNK - 1) // CHUNK
    # Reuse complete ranges from an interrupted sequential download.
    if image.is_file() and image.stat().st_size < LOCK["bytes"]:
        with image.open("rb") as source:
            for i in range(image.stat().st_size // CHUNK):
                part = parts / f"{i:03d}"
                payload = source.read(CHUNK)
                if not part.is_file() or part.stat().st_size != CHUNK:
                    part.write_bytes(payload)

    def download(i):
        start = i * CHUNK
        end = min(LOCK["bytes"], start + CHUNK) - 1
        part = parts / f"{i:03d}"
        if part.is_file() and part.stat().st_size == end - start + 1:
            return
        temporary = part.with_suffix(".partial")
        stalls = 0
        while (offset := temporary.stat().st_size if temporary.exists() else 0) < end-start+1:
            stop = min(end, start + offset + 32 * 1024 * 1024 - 1)
            with temporary.open("ab") as output:
                result = subprocess.run(["curl", "-L", "--fail", "--silent", "--show-error",
                    "--connect-timeout", "15", "--max-time", "300", "--range", f"{start+offset}-{stop}",
                    "--max-filesize", str(stop-start-offset+1), LOCK["url"]], stdout=output, stderr=subprocess.PIPE)
            if temporary.stat().st_size == offset:
                stalls += 1
                if stalls >= 5:
                    raise RuntimeError(f"ISO range {i} stalled: {result.stderr.decode(errors='replace')[:180]}")
                time.sleep(1)
            else:
                stalls = 0
        if temporary.stat().st_size != end-start+1:
            raise ValueError("The ISO server returned an unexpected range.")
        temporary.replace(part)
        print(json.dumps({"downloaded_part":i+1,"parts":count}), flush=True)

    with concurrent.futures.ThreadPoolExecutor(max_workers=16) as executor:
        list(executor.map(download, range(count)))
    temporary = image.with_suffix(".verified-pending")
    with temporary.open("wb") as output:
        for i in range(count):
            with (parts / f"{i:03d}").open("rb") as source:
                shutil.copyfileobj(source, output, 1024 * 1024)
    if temporary.stat().st_size != LOCK["bytes"] or sha(temporary) != LOCK["sha256"]:
        raise ValueError("The ISO differs from the official published checksum.")
    temporary.replace(image)
    print(json.dumps({"status":"verified","image":str(image),"sha256":LOCK["sha256"]}), flush=True)


if __name__ == "__main__":
    main()
