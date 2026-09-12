# Hyphae candidate source

Generic memory operations, capture policy, proofs, local embeddings and host
adapters belong in Hyphae. This directory retains the exact unpublished source
candidate as a Git bundle plus a readable patch for review. Both are pinned in
`source.lock.json`; the plugin does not maintain a second memory engine.

Run `python3 scripts/prepare-upstream.py` from the plugin root to reconstruct
the candidate in the persistent `.upstream/hyphae` checkout. Existing modified
checkouts are preserved. Then use `scripts/verify-upstream.py` and
`scripts/build-runtime.py --source .upstream/hyphae`.

The public base commit remains a prerequisite of the bundle. The candidate is
not a published Hyphae crate release, and its local validation does not replace
the upstream release process or exact-commit G7/G8 evidence. The proposed
upstream diff is `hyphae-agent-memory.patch`; publish/submit only after owner
review.
