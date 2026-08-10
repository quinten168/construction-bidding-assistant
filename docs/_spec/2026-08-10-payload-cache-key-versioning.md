# Spec — version the report payload cache key so a mapping change invalidates it

Status: **proposed, not built.** Owner decision required before any code.
Date: 2026-08-10. Author: timeout-safety agent (item 3 spillover).
Related: `docs/_session/2026-08-10-timeout-safety.md` (the measurement), `docs/_spec/mapping_architecture.md`.

---

## 1. The problem, in the repo's own terms

`apps/api/backend/report.py:57`:

```python
def _payload_cache_path(content_hash: str) -> Path:
    return _PAYLOAD_CACHE / (content_hash + ".json")
```

The key is **the PDF's content hash and nothing else**. The cached value, however, is not a
function of the PDF alone — it is a function of the PDF *and* the seven quantity field
descriptions in `pipelines/plan_reader/01_pipeline/schema.py`, which is the live path's entire
mapping (HANDOFF §2). Those descriptions changed at `2026-08-10T13:06:13-05:00`
(commits `5972199`, `b8d283a`). Every one of the 12 cached payloads predates that.

So a re-drop of a demo plan returns in ~0 s **and returns the pre-ruling numbers**, with no
signal anywhere that it did. Stearns (`f19c9df671fd2fd7.json`) serves `MILL=70263` where the
post-ruling answer is 140,430.

This is the repo's standing failure class one more time: a fast, successful-looking response
answering from a state nobody realised was stale. The cache cannot currently *know* it is stale,
because the thing that changed is not in the key.

## 2. Goal and non-goals

**Goal.** A change to the live mapping invalidates exactly the cached payloads that the change
could affect, automatically, with no human remembering to clear anything.

**Non-goals.**
- Removing or demoting the cache. Owner decision: it stays as the speed layer.
- Deleting existing entries as part of shipping this. See §5.
- Unifying the four mapping artifacts. That is `mapping_architecture.md`'s job; this spec assumes
  `schema.py` remains the live mapping for now and only asks how the cache tracks it.

## 3. Options

### A. Hash the mapping into the key (recommended)

Key becomes `f"{content_hash}-{mapping_version}"`, where `mapping_version` is a short digest
computed at import time from the exact text the LLM is asked with — the seven field descriptions
in `schema.py`, not the whole file (so an unrelated edit, a comment, a new unrelated field, does
not invalidate anything).

```
mapping_version = sha256("\n".join(desc for the seven quantity fields)).hexdigest()[:8]
```

- **Invalidation is automatic and exact.** Edit a description → new key → miss → re-extract.
- **Old entries stay on disk** under their old keys. Nothing is deleted; they simply stop being
  found. That is a feature during a demo week: a rollback of `schema.py` re-finds them.
- Cost: the first re-drop after any mapping edit pays the full 2–5 min run. Acceptable, and it is
  exactly the cost the current design is hiding.
- Risk: the digest must be computed from a **stable serialisation**. If the seven descriptions are
  gathered by iterating a dict whose order can vary, the digest churns and the cache never hits.
  Must sort by field name explicitly.

### B. Store the mapping version *inside* the payload and validate on read

Key unchanged; `process_pdf` writes `"mapping_version": ...` into the JSON, and the cache-hit
branch compares it to the current value and falls through on mismatch.

- Same invalidation behaviour as A.
- Advantage: one cache entry per PDF, no accumulation of superseded files.
- Disadvantage: **the 12 existing payloads have no `mapping_version` field**, so the read path
  needs an explicit rule for absent — and "absent" must mean *stale*, never *current*. Getting
  that backwards silently preserves the exact bug this spec is about. A is harder to get wrong.

### C. Do nothing; clear the cache by hand after a mapping change

Status quo plus discipline. Rejected as a design, but see §5 — it is the correct *immediate*
action for the Aug 12 demo regardless of which option ships, because neither A nor B retroactively
fixes an already-cached number.

## 4. Recommendation

**Option A**, with the digest computed over the seven descriptions sorted by field name, and the
version string logged on every cache hit and miss (`report: payload cache hit (%s)` already logs
the filename — the filename would now carry the version, so the log gets this for free).

Explicitly: the cache-hit log line must make the mapping version visible, so that "why is this
number old?" is answerable from the log rather than from a file mtime.

## 5. What this spec does NOT fix

Shipping A does not change what the 12 existing payloads contain. They become unreachable under the
new key scheme, which is the desired outcome — but until then, and for anything demoed before this
ships, **the stale-number list in `docs/_session/2026-08-10-timeout-safety.md` §4 is the operational
answer**: re-drop a demo plan only if you have first confirmed its cached numbers are the ones you
want on screen, and if they are not, the owner (not an agent) decides whether that one entry gets
removed. A teammate is running the app live; nothing gets deleted without them.

## 6. Open questions for the owner

1. Does `mapping_version` cover only `schema.py`'s seven descriptions, or also the extraction
   model id (`settings.chat_model`)? A model swap changes the answer too, by the same argument.
2. Should the same versioning apply to the sibling `_report_competitor_prediction_cache`
   (`report.py:65`)? It is keyed the same way and has the same class of dependency on CI-model
   state. Not currently present on disk, so this is cheap to decide now.
3. Retention: do superseded entries get swept on a schedule, or kept indefinitely as a rollback
   safety net?
