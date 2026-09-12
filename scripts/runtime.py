# SPDX-License-Identifier: Apache-2.0
"""Install only version-pinned, digest-checked runtime/model artifacts."""
from __future__ import annotations
import hashlib
import json
import os
from pathlib import Path, PurePosixPath
import platform
import shutil
import tarfile
import tempfile
import time
import urllib.parse
import urllib.request

PLUGIN = Path(__file__).resolve().parents[1]
MAX_BUNDLE_BYTES = 256 * 1024 * 1024
MAX_UNPACKED_BYTES = 512 * 1024 * 1024

def sync_directory(path: Path) -> None:
    descriptor = os.open(path, os.O_RDONLY | os.O_DIRECTORY)
    try:
        os.fsync(descriptor)
    finally:
        os.close(descriptor)


def share() -> Path:
    return Path(os.environ.get("XDG_DATA_HOME", str(Path.home() / ".local/share")))


def private_directory(path: Path) -> None:
    if path.is_symlink():
        raise ValueError("installation directory must not be a symlink")
    path.mkdir(parents=True, exist_ok=True, mode=0o700)
    if path.stat().st_uid != os.getuid():
        raise ValueError("installation directory must belong to the user")
    path.chmod(0o700)


def write_json(path: Path, value: dict) -> None:
    private_directory(path.parent)
    descriptor, temporary = tempfile.mkstemp(prefix=".pending-", dir=path.parent)
    try:
        with os.fdopen(descriptor, "w", encoding="utf-8") as output:
            json.dump(value, output, indent=2)
            output.write("\n")
            output.flush()
            os.fsync(output.fileno())
        os.replace(temporary, path)
        sync_directory(path.parent)
    finally:
        if os.path.exists(temporary):
            os.unlink(temporary)


def digest(path: Path) -> str:
    with path.open("rb") as source:
        return hashlib.file_digest(source, "sha256").hexdigest()


def checked_file(path: Path, expected: dict) -> bool:
    return (path.is_file() and not path.is_symlink() and path.stat().st_size == expected["bytes"]
            and digest(path) == expected["sha256"])


def download(expected: dict, cache: Path) -> Path:
    checksum = expected["sha256"]
    if len(checksum) != 64 or any(character not in "0123456789abcdef" for character in checksum):
        raise ValueError("invalid pinned digest")
    size = expected["bytes"]
    if not isinstance(size, int) or not 0 < size <= MAX_UNPACKED_BYTES:
        raise ValueError("artifact size is outside its bound")
    private_directory(cache)
    destination = cache / checksum
    if checked_file(destination, expected):
        return destination
    url = expected.get("url")
    if not isinstance(url, str) or urllib.parse.urlsplit(url).scheme != "https":
        raise ValueError("no published HTTPS artifact is configured; select a verified local bundle")
    descriptor, name = tempfile.mkstemp(prefix=".download-", dir=cache)
    deadline = time.monotonic() + 300
    try:
        total = 0
        hasher = hashlib.sha256()
        with os.fdopen(descriptor, "wb") as target, urllib.request.urlopen(url, timeout=45) as response:
            if urllib.parse.urlsplit(response.geturl()).scheme != "https":
                raise ValueError("artifact redirects must remain on HTTPS")
            while chunk := response.read(128 * 1024):
                total += len(chunk)
                if total > size or time.monotonic() > deadline:
                    raise ValueError("download exceeded its bound")
                hasher.update(chunk)
                target.write(chunk)
            target.flush()
            os.fsync(target.fileno())
        if total != size or hasher.hexdigest() != checksum:
            raise ValueError("download digest mismatch")
        os.replace(name, destination)
        sync_directory(cache)
        return destination
    finally:
        if os.path.exists(name):
            os.unlink(name)


def install_runtime(arguments: dict) -> dict:
    if set(arguments) - {"bundle"}:
        raise ValueError("unsupported installation arguments")
    if platform.system() != "Linux" or platform.machine() not in {"x86_64", "amd64"}:
        raise ValueError("this runtime bundle is for Linux x86_64")
    lock = json.loads((PLUGIN / "runtime.lock.json").read_text(encoding="utf-8"))
    if lock.get("schema") != "hyphae-omarchy-runtime-lock-v1":
        raise ValueError("unsupported runtime lock")
    root = share() / "hyphae-omarchy"
    private_directory(root)
    artifact = lock["bundle"]
    if Path(artifact["name"]).name != artifact["name"]:
        raise ValueError("unsafe runtime archive name")
    supplied = arguments.get("bundle")
    if supplied:
        bundle = Path(supplied).expanduser().resolve(strict=True)
    else:
        local = PLUGIN / "dist" / artifact["name"]
        bundle = local if checked_file(local, artifact) else download(artifact, root / "downloads")
    if artifact["bytes"] > MAX_BUNDLE_BYTES or not checked_file(bundle, artifact):
        raise ValueError("runtime bundle does not match the reviewed lock")
    files = lock["files"]
    if not isinstance(files, dict) or not 2 <= len(files) <= 16:
        raise ValueError("invalid runtime inventory")
    if not {"bin/hyphae", "bin/hyphae-embed"} <= set(files):
        raise ValueError("runtime executables are missing")
    for name in files:
        path = PurePosixPath(name)
        if path.is_absolute() or ".." in path.parts or str(path) != name:
            raise ValueError("unsafe runtime member")
    versions = root / "runtimes"
    private_directory(versions)
    destination = versions / artifact["sha256"]
    if destination.is_symlink():
        raise ValueError("runtime directory must not be a symlink")
    if not destination.exists():
        staging = Path(tempfile.mkdtemp(prefix=".install-", dir=versions))
        try:
            seen = set()
            unpacked = 0
            with bundle.open("rb") as source, tarfile.open(fileobj=source, mode="r:gz") as archive:
                for member in archive:
                    if not member.isfile() or member.name not in files or member.name in seen:
                        raise ValueError("runtime archive contains an unexpected member")
                    expected = files[member.name]
                    unpacked += member.size
                    if member.size != expected["bytes"] or unpacked > MAX_UNPACKED_BYTES:
                        raise ValueError("runtime member exceeds its bound")
                    target = staging / member.name
                    target.parent.mkdir(parents=True, exist_ok=True, mode=0o700)
                    payload = archive.extractfile(member)
                    if payload is None:
                        raise ValueError("runtime member is missing")
                    with target.open("xb") as output:
                        shutil.copyfileobj(payload, output, 128 * 1024)
                        output.flush()
                        os.fsync(output.fileno())
                    if not checked_file(target, expected):
                        raise ValueError("runtime member digest mismatch")
                    target.chmod(0o700 if member.name.startswith("bin/") else 0o600)
                    seen.add(member.name)
            if seen != set(files):
                raise ValueError("runtime archive is incomplete")
            os.rename(staging, destination)
            sync_directory(versions)
        finally:
            if staging.exists():
                shutil.rmtree(staging)
    for name, expected in files.items():
        if not checked_file(destination / name, expected):
            raise ValueError("installed runtime inventory differs")
    receipt = root / "runtime.json"
    if receipt.is_symlink():
        raise ValueError("runtime receipt must not be a symlink")
    if receipt.is_file():
        write_json(root / "runtime.previous.json", json.loads(receipt.read_text()))
    write_json(receipt, {"schema":"hyphae-omarchy-runtime-v1", "binary":str(destination / "bin/hyphae"),
                        "embed_binary":str(destination / "bin/hyphae-embed"), "sha256":files["bin/hyphae"]["sha256"],
                        "embed_sha256":files["bin/hyphae-embed"]["sha256"],
                        "bundle_sha256":artifact["sha256"], "source_commit":lock["source_commit"], "activation_pending":True})
    return {"message":"Verified runtime installed. Set up or activate local memory to use it."}


def install_model(arguments: dict) -> dict:
    if arguments:
        raise ValueError("the reference model has no arbitrary download arguments")
    lock = json.loads((PLUGIN / "models.lock.json").read_text(encoding="utf-8"))
    if lock.get("schema") != "hyphae-omarchy-model-lock-v1" or lock.get("id") != "bge-small-en-v1.5":
        raise ValueError("unsupported model lock")
    parent = share() / "hyphae/models"
    private_directory(parent)
    destination = parent / lock["id"]
    if destination.is_symlink():
        raise ValueError("model directory must not be a symlink")
    files = lock["files"]
    if {item["path"] for item in files} != {"config.json", "tokenizer.json", "model.safetensors"}:
        raise ValueError("invalid model inventory")
    if destination.exists():
        if all(checked_file(destination / item["path"], item) for item in files):
            return {"message":"Reference model is already installed.", "model_dir":str(destination)}
        raise ValueError("the existing model directory differs; it has been preserved")
    staging = Path(tempfile.mkdtemp(prefix=".model-", dir=parent))
    try:
        for item in files:
            source = download(item, share() / "hyphae-omarchy/downloads")
            target = staging / item["path"]
            with source.open("rb") as reader, target.open("xb") as writer:
                shutil.copyfileobj(reader, writer, 128 * 1024)
                writer.flush()
                os.fsync(writer.fileno())
            target.chmod(0o600)
        os.rename(staging, destination)
        sync_directory(parent)
    finally:
        if staging.exists():
            shutil.rmtree(staging)
    return {"message":"Reference model installed. Semantic search remains off until enabled.", "model_dir":str(destination)}
