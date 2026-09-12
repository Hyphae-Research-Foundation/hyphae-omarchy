# Verified Hyphae source and runtime provenance

Agent Memory operations, capture policy, proofs, local embeddings and host
adapters live in the public Hyphae repository. `source.lock.json` pins the
exact public merge commit and its Git tree. Prepare it with:

```bash
python3 scripts/prepare-upstream.py
```

The helper verifies the commit and tree and preserves an existing checkout
with local changes or another revision. `scripts/lock-upstream.py` accepts a
new clean revision only after fetching the same public Git object.

The runtime reuses the exact Linux executable from the signed Hyphae Release
workflow. `release.lock.json` binds its archive, executable, workflow,
certificate identity and source equivalence. `release-verification.json`
records verification of all four platform archives, 12 signatures and 12
attestations using the upstream verifier. The source tree at the build commit
is identical to the pinned merge commit.

`native-g8.json` is the closed nine-requirement G8 aggregate for that merge.
It covers the upstream native engine and its release evidence. The optional
Candle worker and the Omarchy integration have additional runtime, model,
agent-host and VM checks recorded under `docs/validation/`.

The public plugin release retains the original upstream artifacts and G8
receipts in `hyphae-memory-0.1.0-upstream-evidence.zip`, so verification does
not depend on expiring GitHub Actions downloads. The older unpublished
candidate bundle and patch were retired after their code was integrated.
Historical source and validation remain recoverable from repository history.
