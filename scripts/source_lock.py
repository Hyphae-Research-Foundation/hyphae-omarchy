# SPDX-License-Identifier: Apache-2.0
"""Verify and fetch the exact public Hyphae source used by a plugin release."""
from __future__ import annotations

import json
import os
from pathlib import Path
import re
import shutil
import subprocess
import tempfile
from urllib.parse import urlsplit

ROOT = Path(__file__).resolve().parents[1]
OBJECT_ID = re.compile(r"[0-9a-f]{40}")


def git(directory: Path, *arguments: str) -> str:
    environment = {**os.environ, "GIT_TERMINAL_PROMPT": "0"}
    return subprocess.check_output(
        ["git", "-C", str(directory), *arguments],
        env=environment, text=True, stderr=subprocess.PIPE, timeout=180,
    ).strip()


def load_lock(path: Path = ROOT / "source.lock.json") -> dict:
    lock = json.loads(path.read_text(encoding="utf-8"))
    if lock.get("schema") != "hyphae-omarchy-source-lock-v2" or lock.get("published") is not True:
        raise ValueError("A release requires a published source lock.")
    identity = lock.get("hyphae")
    if not isinstance(identity, dict) or set(identity) != {"repository", "commit", "tree"}:
        raise ValueError("The source identity must contain repository, commit and tree.")
    url = urlsplit(identity["repository"])
    if url.scheme != "https" or url.hostname != "github.com" or url.username or url.password or url.query or url.fragment:
        raise ValueError("Published source must use a public GitHub HTTPS repository URL.")
    if any(not isinstance(identity.get(field), str) or OBJECT_ID.fullmatch(identity[field]) is None
           for field in ("commit", "tree")):
        raise ValueError("The source commit and tree must be exact Git object identities.")
    return lock


def verify_checkout(directory: Path, identity: dict) -> None:
    if git(directory, "status", "--porcelain=v1", "--untracked-files=all"):
        raise ValueError("The source checkout has local changes; it has been preserved.")
    if (git(directory, "rev-parse", "HEAD"), git(directory, "rev-parse", "HEAD^{tree}")) != (
        identity["commit"], identity["tree"]
    ):
        raise ValueError("The source checkout differs from its exact commit/tree lock; it has been preserved.")


def fetch_source(destination: Path, identity: dict) -> None:
    if destination.exists():
        verify_checkout(destination, identity)
        return
    destination.parent.mkdir(parents=True, exist_ok=True)
    staging = Path(tempfile.mkdtemp(prefix=".hyphae-source-", dir=destination.parent))
    try:
        git(staging, "init", "--quiet")
        git(staging, "remote", "add", "origin", identity["repository"])
        git(staging, "fetch", "--no-tags", "--depth=1", "origin", identity["commit"])
        git(staging, "checkout", "--detach", identity["commit"])
        verify_checkout(staging, identity)
        if destination.exists():
            raise ValueError("The destination appeared during the fetch; it has been preserved.")
        staging.rename(destination)
    finally:
        if staging.exists():
            shutil.rmtree(staging)
