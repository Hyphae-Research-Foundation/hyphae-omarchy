# SPDX-License-Identifier: Apache-2.0
"""Retain Cargo dependency identity and supplied license texts with the runtime."""
from datetime import datetime, timezone
import hashlib
import json
from pathlib import Path
import subprocess
import tomllib


def legal_files(package):
    directory = Path(package["manifest_path"]).parent
    paths = set()
    for child in directory.iterdir():
        if child.name.lower().startswith(("license", "licence", "notice", "copyright")):
            if child.is_file():
                paths.add(child)
            elif child.is_dir():
                paths.update(path for path in child.rglob("*") if path.is_file())
    if package.get("license_file"):
        paths.add(directory / package["license_file"])
    return sorted(paths)


def vcs_identity(package):
    file = Path(package["manifest_path"]).parent / ".cargo_vcs_info.json"
    if not file.is_file():
        return None
    value = json.loads(file.read_text())
    return (package.get("repository"), value.get("git", {}).get("sha1"))


def inventories(source, toolchain, revision, epoch, environment):
    packages = {}
    edges = {}
    roots = []
    checksums = {}

    def identity(package):
        origin = package["source"] or revision
        return "cargo:" + package["name"] + ":" + package["version"] + ":" + hashlib.sha256(origin.encode()).hexdigest()[:12]

    for manifest, name in ((source / "Cargo.toml", "hyphae-cli"), (source / "embed/Cargo.toml", "hyphae-embed")):
        metadata = json.loads(subprocess.check_output([
            "cargo", "+" + toolchain, "metadata", "--manifest-path", str(manifest),
            "--locked", "--format-version", "1", "--filter-platform", "x86_64-unknown-linux-gnu",
        ], cwd=source, env=environment))
        lock = tomllib.loads(manifest.with_name("Cargo.lock").read_text())
        for package in lock["package"]:
            checksums[(package["name"], package["version"], package.get("source"))] = package.get("checksum")
        found = {package["id"]: package for package in metadata["packages"]}
        nodes = {node["id"]: node for node in metadata["resolve"]["nodes"]}
        selected = next(package["id"] for package in found.values() if package["name"] == name)
        roots.append(identity(found[selected]))
        pending = [selected]
        visited = set()
        while pending:
            current = pending.pop()
            if current in visited:
                continue
            visited.add(current)
            package = found[current]
            reference = identity(package)
            packages[reference] = package
            children = [dependency["pkg"] for dependency in nodes[current]["deps"]
                if any(kind["kind"] != "dev" for kind in dependency["dep_kinds"])]
            edges.setdefault(reference, set()).update(identity(found[child]) for child in children)
            pending.extend(children)

    components = []
    notices = ["Hyphae Memory runtime dependency licenses\n\n"
        "This inventory includes resolved normal and build dependencies for Linux x86_64.\n"
        "It excludes dev-only dependencies, operating-system libraries and the Rust toolchain.\n"
        "Cargo metadata may conservatively unify features across workspace members.\n"
        "Copyright and license grants remain with the named packages and their authors.\n"]
    for reference, package in sorted(packages.items()):
        declared = package.get("license")
        if not declared:
            raise ValueError("A dependency needs explicit license review: " + package["name"])
        expression = declared.replace("/", " OR ")
        checksum = checksums.get((package["name"], package["version"], package["source"]))
        component = {"type": "application" if reference in roots else "library", "bom-ref": reference,
            "name": package["name"], "version": package["version"],
            "purl": "pkg:cargo/" + package["name"] + "@" + package["version"],
            "licenses": [{"expression": expression}],
            "properties": [{"name": "cargo:source", "value": package["source"] or "hyphae-source-commit:" + revision}]}
        if checksum:
            component["hashes"] = [{"alg": "SHA-256", "content": checksum}]
            component["externalReferences"] = [{"type": "distribution", "url":
                "https://crates.io/api/v1/crates/" + package["name"] + "/" + package["version"] + "/download"}]
        components.append(component)
        notices.append("\n" + "=" * 72 + "\n" + package["name"] + " " + package["version"] + "\n")
        notices.append("Declared license: " + declared + "\n")
        notices.append("Authors: " + "; ".join(package.get("authors", [])) + "\n")
        if package.get("repository"):
            notices.append("Repository: " + package["repository"] + "\n")
        files = legal_files(package)
        attribution = package["name"] + " " + package["version"]
        if not files:
            own_vcs = vcs_identity(package)
            siblings = [candidate for candidate in packages.values() if own_vcs and own_vcs[1]
                and vcs_identity(candidate) == own_vcs and candidate.get("license") == declared
                and legal_files(candidate)]
            if siblings:
                sibling = sorted(siblings, key=lambda item: item["name"])[0]
                files = legal_files(sibling)
                attribution = sibling["name"] + " " + sibling["version"] + " (same repository commit)"
            elif "Apache-2.0" in expression and (" OR " in expression or expression == "Apache-2.0"):
                files = [source / "LICENSE"]
                attribution = "Apache-2.0 license text; this permitted license alternative is selected"
            else:
                raise ValueError("A dependency's license text must be supplied: " + package["name"])
        for path in files:
            payload = path.read_text(encoding="utf-8")
            notices.append("\nLicense file: " + path.name + " — " + attribution + "\n\n" + payload + "\n")

    application = "hyphae-memory-runtime:" + revision
    sbom = {"bomFormat": "CycloneDX", "specVersion": "1.6", "version": 1,
        "metadata": {"timestamp": datetime.fromtimestamp(epoch, timezone.utc).isoformat(),
            "component": {"type": "application", "bom-ref": application, "name": "Hyphae Memory runtime", "version": "0.1.0+" + revision[:12]},
            "properties": [{"name": "hyphae:source_commit", "value": revision},
                {"name": "hyphae:inventory_scope", "value": "Cargo normal and build dependencies resolved for Linux x86_64; excludes dev-only dependencies, OS libraries and the Rust toolchain"}]},
        "components": components,
        "dependencies": [{"ref": application, "dependsOn": sorted(roots)}]
            + [{"ref": reference, "dependsOn": sorted(children)} for reference, children in sorted(edges.items())]}
    return (json.dumps(sbom, indent=2, sort_keys=True) + "\n").encode(), "".join(notices).encode()
