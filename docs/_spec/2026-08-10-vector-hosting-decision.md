# Vector hosting — decision

**Status:** decision, not a menu · written 2026-08-10 · **supersedes `docs/_spec/vector_hosting.md`**
**Companion walkthrough:** [`2026-08-10-vector-hosting-setup.md`](2026-08-10-vector-hosting-setup.md)
**Supersedes because:** four load-bearing facts in the 2026-08-08 memo are now measured rather than
inferred, and **three of them came back different from what that memo assumed.** See §5.

---

## 0. The one-sentence recommendation

> **Deploy the `chromadb/chroma:1.5.9` Docker image on Railway Hobby with a 5 GB volume and *no
> public domain*, put a Caddy basic-auth service in front of it as the only public entry point, seed
> it by uploading a 581 MB tarball of `06_chroma/` straight into the volume with
> `railway volume files upload`, and delete the whole thing on Aug 17.**
> **Runner-up: Fly.io. It lost because both of its decisive advantages evaporated** — see §3.

**Two services, not one, and that is not optional: self-hosted Chroma 1.x has no authentication of
any kind** (§4.1). A bare Chroma container on a public Railway domain is CSI's entire plan corpus,
open to the internet.

Everything about the destination is unchanged and not re-argued here: local `PersistentClient` is
what ships to CSI on Aug 17, hosted is a **disposable bridge**, and the code change that enables the
bridge is env-gated so tear-down is deleting four `.env` lines, not reverting a commit.

---

## 1. The three questions that were blocking this, answered

The 2026-08-08 memo left these as `UNVERIFIED`. Inheriting them as fact was the failure mode. Each
is now answered with **two independent methods, both named.**

### Q1 — Does `chromadb` 1.5.9 embed client-side, or does the server need the model?

> ## **Client-side. Always. The server never sees text that needs embedding, and therefore needs no model and no extra RAM.**

**Method 1 — reading the installed package source** (`.venv/lib/python3.9/site-packages/chromadb/`,
version confirmed `1.5.9` by `pip show chromadb` and `chromadb.__version__`). This is stronger than
reading docs, and it is unambiguous:

- `api/models/CollectionCommon.py:210` `_validate_and_prepare_add_request` and `:295`
  `_validate_and_prepare_query_request` both call `self._embed_record_set(...)` → `:746 _embed()`
  **before** handing anything to `self._client`. `_embed` uses `self._embedding_function` — the one
  bound at `get_or_create_collection(embedding_function=ef)` in
  `pipelines/plan_reader/01_pipeline/lib.py:206-211`.
- `api/fastapi.py:638 _add(... embeddings: Embeddings ...)` and `:731 _query(... query_embeddings:
  Embeddings ...)` take embeddings as **non-Optional**. The JSON body built at `fastapi.py:750`
  contains `query_embeddings` and **has no `query_texts` field at all.** There is no wire
  representation for "here is text, you embed it."
- `chromadb/__init__.py:260 HttpClient(...)` merely sets `chroma_api_impl =
  "chromadb.api.fastapi.FastAPI"` and returns the same client/`Collection` classes as
  `PersistentClient`. **The embedding path is identical for local and hosted.**

**Method 2 — live empirical test against a real Chroma server** (`chroma run` on :8767 and the real
`chromadb/chroma:1.5.9` container on :8770), with the outbound payload instrumented:

```
EF calls after upsert (client-side): 1  dim: 384
WIRE add payload: {"url": ".../upsert", "n_ids": 2, "embeddings_present": true,
                   "embedding_dim": 384, "documents_present": true}
EF calls after query (client-side): 1
WIRE query payload: {"query_embeddings_present": true, "dim": 384,
                     "kwargs_keys": ["database","ids","include","n_results","tenant","where","where_document"]}
```

384-dimension float vectors go over the wire; the MiniLM function fires on the client once per call;
no `query_texts` key is present in the request.

**Method 3 (corroborating) — inspecting the image itself.** `docker image inspect
chromadb/chroma:1.5.9` → entrypoint `dumb-init -- chroma run /config.yaml`, 165 MB content size, a
single 525 MB Rust binary at `/usr/local/bin/chroma`. **There is no Python interpreter, no `torch`,
no `sentence-transformers` in it.** It could not embed for us even if we asked.

**Consequences, which is the point of the question:**

| | Answer |
|---|---|
| Does the Railway container need MiniLM baked in? | **No.** Use the stock image unmodified. |
| How much RAM does it need? | **Measured 184.6 MiB RSS** serving all 76,540 chunks through ten real queries (`docker stats`). Provision **1 GB**; 2 GB was overkill. |
| Does CLAUDE.md invariant 3 (embeddings local, no API call) survive the bridge? | **Yes, structurally** — not by configuration, by the absence of any wire format for server-side embedding. |
| What must every client still do? | Pass `embedding_function=ef` when it opens the collection. `lib.py:206-211` already does. A client that forgets gets Chroma's *default* ONNX MiniLM, which is a **different model** — that is the real drift risk, and it is client-side, not server-side. |

### Q2 — Railway's default volume-backup behaviour

> ## **HANDOFF §7's "Railway is the only candidate with no automatic volume backups" is FALSE as written. Railway has scheduled volume backups. What is true is narrower: no Railway document states they are on by default, and a Railway guide tells you to turn them on — so treat them as opt-in and turn them on explicitly.**

**Method 1 — direct WebFetch of `docs.railway.com` HTML pages.**
**Method 2 — the raw-markdown corpus** (`docs.railway.com/<path>.md` and the full
`docs.railway.com/llms-full.txt`, 2.34 MB, grepped for all 210 occurrences of "backup").
**Method 3 (corroborating) — the Railway CLI installed locally**, `railway 5.31.0`, `--help` output.

From <https://docs.railway.com/volumes/backups>, verbatim:

> "When a volume is mounted to a service, backups can be manually created, deleted and restored. And
> they can also be scheduled to run on a Daily / Weekly / Monthly schedule."
> "- **Daily** — Backed up every 24 hours, kept for 6 days
> - **Weekly** — Backed up every 7 days, kept for 1 month
> - **Monthly** — Backed up every 30 days, kept for 3 months"
> "Backups are incremental and Copy-on-Write, we only charge for the data exclusive to them…"
> "You are only billed for the incremental size of the backup at a rate per GB / minutely."

Billed at the volume rate: **$0.15 / GB / month** (<https://docs.railway.com/pricing/plans>).

**The default is genuinely unstated.** No page asserts on-by-default *or* off-by-default. The only
default-adjacent evidence in the entire corpus is an instruction implying opt-in:

> "**Enable backups.** Configure scheduled volume backups on the database service."
> — <https://docs.railway.com/guides/migrate-database-minimal-downtime>

(One unrelated exception: Pro-plan users get an automatic `Auto Update {image}` backup before a
database image auto-update. Not applicable to a Hobby Chroma service.)

**So the walkthrough does two things, not one:** it has an explicit *click* to turn the Daily
schedule on, **and** an explicit manual `tar czf` of the local store before cutover — because the
authoritative copy for the next 10 days is the laptop's directory, not the Railway volume, and a
backup you had to enable is a backup somebody can forget to enable. Three further constraints worth
knowing, all from `/volumes/backups`: *manual backups are limited to 50% of the volume's total
size*; *wiping a volume deletes all backups*; *backups restore only into the same project +
environment.*

**Correction to the record:** because this claim was the stated reason "Fly over Railway" was
recorded as a decision in HANDOFF §7, that decision's basis is gone. See §3.

### Q3 — Migration path for the store, and how long it runs

> ## **Copy the files, not the records. `tar czf` the directory, `railway volume files upload` the tarball into the volume, untar it in place via `railway ssh`. Measured end-to-end in a full local dress rehearsal against the real image and the real store. Estimated wall clock 15–25 minutes, dominated entirely by your upload bandwidth.**

**First, the store is bigger than the memo says.** Re-measured 2026-08-10 by direct `sqlite3` query
against `chroma.sqlite3`:

| | 2026-08-08 memo | **2026-08-10 measured** |
|---|---|---|
| embeddings | 75,080 | **76,540** |
| distinct `doc_id` | 210 | **213** |
| collection | `csi_plans` | `csi_plans` (unchanged) |
| on-disk bytes | "1.6 GB" | **1,716,394,506 bytes across 31 files** (`chroma.sqlite3` = 1,565,155,328 + six HNSW segment dirs) |

**Every "75080" acceptance check in the old setup doc is now wrong and would fail.** The store grows
whenever a plan is dropped through the web path, so **re-measure immediately before migrating and
use that number** — do not copy a count out of a document. That is the whole lesson.

**The decisive test — does the server image read our `PersistentClient` directory as-is?**
Yes. Verified by running `chromadb/chroma:1.5.9` with a *copy* of `06_chroma/` bind-mounted at
`/data` (the image's default `persist_path`, read out of its shipped `/config.yaml`):

```
collections: ['csi_plans']
count: 76540
query s: 0.14
- 2023_MARTIN-CO-MN_8436697_NOBID p.190 | **SECTION 32 01 16.13 - ASPHALT PAVEMENT MILLING** …
```

No conversion, no import step, no re-embedding. The 1.x Rust server and the 1.5.9 Python
`PersistentClient` share one on-disk format.

**And it round-trips.** A record written *through the hosted server* was then read back by
`PersistentClient` opening the same directory (`count: 76541`, probe document present). So if the
team ingests plans into the bridge before Aug 17, the volume can be pulled down and used locally —
the bridge is not a one-way door.

**Measured numbers for the file-level path** (all on this laptop, 2026-08-10):

| Step | Measured |
|---|---|
| `tar czf` of `06_chroma/` | **23 s → 608,924,336 bytes (581 MB)** |
| …after `chroma vacuum` on the copy first | 30 s extra → **452,147,921 bytes (431 MB)** |
| upload 581 MB | *not measured — depends on your uplink*, see arithmetic below |
| `tar xzf` inside the container | **14.8 s** (`tar` and `gzip` are both present in the image) |
| restart + verify `count()` | ~30 s |

**Compression is 2.82×, not the 1.1–1.4× the old memo guessed.** That guess ("mostly float blobs, so
expect modest compression") was wrong and it mattered: it is the difference between a 1.7 GB upload
and a 581 MB one. `chroma vacuum` buys another 149 MB of *tarball* despite reclaiming only 1% of raw
size — optional, run it on the copy, never on the original.

**Wall-clock estimate — this is arithmetic on a measured payload, not a measurement:**

| Your upload speed | 581 MB transfer | End-to-end incl. tar, untar, verify |
|---|---|---|
| 10 Mbps (1.25 MB/s) | 465 s ≈ 8 min | **~12 min** |
| 20 Mbps (2.5 MB/s) | 232 s ≈ 4 min | **~8 min** |
| 50 Mbps (6.25 MB/s) | 93 s ≈ 1.5 min | **~5 min** |

Budget **15–25 minutes** including Railway console clicks, the volume-mount proof, and one failed
attempt. Nothing here takes hours.

**The records-level alternative, measured and rejected.** Reading from `PersistentClient` with
`include=["documents","metadatas","embeddings"]` and `upsert`ing to an HTTP server at **1,209
records/s** on loopback → 76,540 records in ~63 s locally. But the wire payload is **10,934 bytes
per record** (measured on a real 1,000-record batch), so **837 MB of JSON** — *more* bytes than the
compressed tarball, over a slower path, and it rebuilds the HNSW index server-side instead of
copying it. It also does not reproduce the store byte-for-byte: the new collection's
embedding-function config and `hnsw:space` metadata are re-created by hand, which is a place for
ingest/query drift to enter. **Use it only if `railway volume files upload` is unavailable.**

**`chroma copy` does not do what the old setup doc says.** That doc's
`chroma copy --from-local collections csi_plans --to <host>` is not a valid command. Verified by
running it: `--from-local` and `--to-local` are **mutually exclusive**, and `chroma copy`'s own help
says *"Copy collection between local and Chroma Cloud"* — there is no arbitrary-host target and no
auth-header flag. The only supported pairings are local↔Chroma Cloud. **Do not plan around it.**

---

## 2. The recommendation, and what it costs

**Railway, Hobby plan, `chromadb/chroma:1.5.9` Docker image deployed directly** (not a GitHub
connect), one 5 GB volume mounted at `/data`, seeded by tarball upload, **deleted Aug 17.**

| | |
|---|---|
| Plan fee | **$5/mo Hobby**, includes $5 of usage credit |
| Memory | measured **0.18 GB**, metered at $0.00000386/GB-s ≈ $10.15/GB-month → **~$1.85/mo** |
| vCPU | idle between queries; metered — pennies at 3–4 users |
| Volume | 5 GB provisioned at **$0.15/GB/mo → $0.75/mo**; actual usage ~2.3 GB at peak (1.72 GB extracted + 581 MB tarball before you delete it) |
| Backups | incremental, same rate — cents |
| **10-day total** | **well under the $5 credit; call it $5.** |

Volume caps (<https://docs.railway.com/volumes/reference>): Free/Trial **0.5 GB** — *too small, the
store does not fit* — Hobby **5 GB**, Pro **50 GB** default, self-serve to 1 TB. **Hobby is the
minimum viable plan and it fits with headroom.** Note "each service can only have a single volume"
and "replicas cannot be used with volumes" — both fine for one Chroma container, both fatal if
anyone tries to scale it.

**Why Railway wins, in order of weight:**

1. **The two things it was previously bad at, it is now good at.** It has direct volume file upload
   (`railway volume files upload <LOCAL_PATH> <REMOTE_PATH>`, directories supported, `--concurrency
   32` — confirmed in the locally installed CLI 5.31.0 and in the docs), and it has scheduled
   backups. The 2026-08-08 memo's two Railway-specific objections — "no volume upload button" and
   "no automatic backups" — are both obsolete.
2. **It is where the work already is.** The owner has an account and in-progress setup. For a
   10-day disposable bridge, "the platform you are already logged into" is a real advantage and
   nothing on the merits list outweighs it by enough to justify starting over on a Tuesday with a
   Wednesday deadline.
3. **The code change is two lines, env-gated**, identical on any Chroma-to-Chroma target
   (`lib.py:205` and `s2_indexer.py:229`). Nothing about `retriever.py`'s `where` filters,
   `s2_indexer.py:183`'s `upsert`, `plan_reader_bridge.py:51`'s paginated `get`, or the bound
   embedding function changes.
4. **Tear-down is a first-class operation.** Delete the service, delete the volume, cancel Hobby,
   remove four `.env` lines. Nothing at CSI depends on it having existed.

## 3. The runner-up, and exactly why it lost

> ### **Fly.io. It lost because both of its decisive advantages were measured away.**

Fly was the right call in the 2026-08-08 memo, and HANDOFF §7 recorded "if hosted is ever needed,
Fly over Railway" for two stated reasons. Both are now void:

| Fly's advantage, as recorded | Status on 2026-08-10 |
|---|---|
| **"Easiest 1.6 GB seeding path"** — `fly sftp put` straight into the volume, vs Railway having no upload mechanism | **Gone.** `railway volume files upload` exists, takes directories, and is in the shipped CLI. Railway's own reference does say *"There is no built-in S/FTP support"* — but the CLI upload makes that irrelevant. |
| **"Automatic daily snapshots with 5 days retention, enabled by default"**, vs "Railway is the only candidate with no automatic volume backups" | **Half gone, and the half that remains is small.** Railway has Daily/Weekly/Monthly schedules with retention. Fly still wins on *default posture* — Fly's are on, Railway's are (apparently) not. That is worth exactly one extra click in §C of the walkthrough. |

What Fly still genuinely wins on: **~$12/mo vs Railway's $5–7** (irrelevant over 10 days on a $5
credit), and **private WireGuard networking**, which is a stronger security posture than a public
Railway domain. That second one is real and is the honest cost of this recommendation — see §4.

Against those: Fly means a new account, a new CLI, a new `fly.toml`, and a first deploy on the two
days before the final presentation. **A marginally better disposable thing is worse than an adequate
disposable thing you can have working today.** If Railway's deploy fights back for more than about
two hours, switching to Fly is the correct escalation and the walkthrough's §C notes are portable —
same image, same tarball, same two-line client change.

**Second runner-up: Chroma Cloud.** It is the *only* target `chroma copy` actually supports, and it
is the least work. It lost on the same ground it lost on in the 2026-08-08 memo, unchanged: it puts
the full text of CSI's plan corpus on a brand-new vendor relationship created four days before the
program ends. For a throwaway bridge that is not worth the conversation with Alex.

**Not reconsidered:** pgvector on Supabase (3–5 days of rewriting four modules, lands five days
before handoff — correct destination, wrong week; keep it as the documented next step if this ever
becomes a real hosted product), Pinecone (rejected, #22), Render (strictly dominated by Railway and
Fly here).

## 4. What this recommendation costs — stated plainly, not buried

**1. Self-hosted Chroma 1.x has NO authentication. None. This is the biggest thing this document
found, and it changes the shape of the deployment.**

> ### **A `chromadb/chroma:1.5.9` container on a public Railway domain is CSI's entire plan corpus, readable and writable by anyone who has the URL. There is no env var, no config key, and no flag that fixes this.**

The old setup doc's "Chroma supports static-token auth via env vars, just turn it on" is **0.x
advice applied to a 1.x image.** Three methods, all agreeing:

- **Method 1 — empirical, against the real image.** Ran `chromadb/chroma:1.5.9` with
  `CHROMA_SERVER_AUTHN_PROVIDER=chromadb.auth.token_authn.TokenAuthenticationServerProvider`,
  `CHROMA_SERVER_AUTHN_CREDENTIALS=…`, `CHROMA_AUTH_TOKEN_TRANSPORT_HEADER=X-Chroma-Token`.
  Unauthenticated `GET /api/v2/tenants/default_tenant/databases/default_database/collections` →
  **HTTP 200**. Wrong token → **HTTP 200**. The env vars are silently ignored: the Rust config loader
  (`rust/frontend/src/config.rs`) reads `CHROMA_*` via figment and serde discards fields no struct
  matches. *A config that is accepted is not auth that is enabled* — the #65 failure class again.
- **Method 2 — source read at git tag `1.5.9`.** `rust/frontend/src/auth/mod.rs` ships exactly one
  implementation of the `AuthenticateAndAuthorize` trait: `impl … for ()`, which unconditionally
  returns a default identity. `rust/cli/src/commands/run.rs:141` — the code path this container runs
  — passes `Arc::new(())` **hardcoded at the call site**. `FrontendServerConfig` has no `auth`,
  `authn`, `authz`, `token`, or `api_key` field at any level, and neither does the repo's own
  "every option" reference config `rust/frontend/sample_configs/single_node_full.yaml`. This is a
  verified absence from direct file reads, not a failed search.
- **Method 3 — official docs and maintainers.** `docs/mintlify/docs/overview/migration.mdx`, under
  1.0.0 **Breaking changes**: *"Chroma no longer provides built-in authentication implementations."*
  Chroma co-founder HammadB, issue #4288: *"Authentication is currently unsupported in chroma >=
  v1.0.0… we suggest that you use <1.0.0 if you need authentication."* Feature request #4965 is
  still open.

**A methodological warning worth keeping:** context7 and a plain web search both returned the 0.x
env-var recipe with no version context, reading exactly like a current answer. Stopping at either
would have produced the opposite of the truth. The empirical test is what caught it.

**The fix, tested end-to-end locally: put an authenticating reverse proxy in front and never expose
Chroma's own port.** Caddy 2 with `basic_auth`, Chroma reachable only on the private network,
the Python client passing `headers={"Authorization": "Basic <base64>"}`. Verified locally:

```
no creds:    401
wrong creds: 401
right creds: 200
Python client through the proxy →  count: 76540, query returns real doc_ids
Python client with no creds      →  correctly rejected (ValueError)
```

Full commands in the walkthrough, §C4. **Pinning `chromadb/chroma:0.6.3` to regain native token auth
is not an option** — our store was written by 1.5.9 and 0.6.3 cannot read it.

**Treat "the service is deployed" and "the service is protected" as two separate facts that must be
observed separately.** Until an unauthenticated request has been *observed to be refused*, assume
the corpus is world-readable.

**2. The corpus on a public hostname is CSI's plan text on someone else's infrastructure for 10
days.** That is the trade being made for multi-user access before Wednesday. It is defensible
because it is time-boxed and deleted on Aug 17 — it stops being defensible the moment the deletion
slips.

**3. The bridge is not the handoff architecture and must never be shown as one.** If it appears in
the Aug 12 presentation, it appears labelled as demo scaffolding.

**4. `06_chroma/` is gitignored, so `git clean -xdf` deletes it silently** — on the laptop, and on
CSI's server after Aug 17. Unchanged from the previous memo and still the single most likely way
this store dies.

## 5. Corrections to the 2026-08-08 memo and to HANDOFF §7

Recorded explicitly so they are not inherited a third time.

| Claim, as previously written | Status |
|---|---|
| "Railway is the only candidate with no automatic volume backups" (HANDOFF §7) — and the "Fly over Railway" decision that rested on it | **Refuted.** Railway has Daily/Weekly/Monthly scheduled volume backups. Default state undocumented, so treat as opt-in. |
| "Railway has no 'upload a file to a volume' button" | **Refuted.** `railway volume files upload` (and `railway volume browse`) ship in CLI 5.31.0. |
| `chroma copy --from-local collections csi_plans --to <host>` seeds a self-hosted server | **Refuted.** Invalid command; `chroma copy` is local↔Chroma Cloud only. |
| "`chroma.sqlite3` is mostly float blobs, expect 1.1–1.4× compression, plan a 1.2–1.6 GB transfer" | **Refuted.** Measured **2.82×** → 581 MB. |
| "75,080 chunks / 210 doc_ids" as an acceptance number | **Stale.** Now **76,540 / 213**, and rising. Measure at migration time. |
| Whether 1.5.9 embeds client-side against a hosted server — `UNVERIFIED` | **Answered: yes, always.** §Q1. |
| "Chroma supports static-token auth via env vars… must be turned on explicitly" | **Refuted, and it is the most dangerous inherited claim in the old doc.** Self-hosted Chroma 1.x has no auth at all. Requires a reverse proxy. §4.1. |
| "budget ~3–5 h to a working authenticated Railway service" | **Understated.** There is no authenticated Chroma service to reach; the proxy is a second Railway service. Budget the extra 30–45 min in §C4. |
| "budget ~2 GB RAM" | **Over-provisioned.** Measured 184.6 MiB. 1 GB is generous. |
| Rebuild from source "budget hours, not minutes" for embedding | **Partly wrong for the embedding step:** MiniLM ran at **149 docs/s** here → ~8.5 min for 76,540 chunks. The hours are in PDF conversion, not embedding. (Rebuild is still blocked on the Box PDFs and is still not a prerequisite for anything here.) |
| "the destination is local `PersistentClient` on CSI's server" | **Unchanged and reaffirmed.** Nothing measured this week argues against it. |

## 6. Still open

- **UNVERIFIED:** whether a Railway *dashboard* volume file browser exists (only the CLI TUI is
  documented). Does not matter — the CLI is the recommended path.
- **UNVERIFIED:** whether Railway scheduled backups are on by default. Resolved operationally by
  turning them on explicitly, so this never needs answering.
- **Not settled here:** #58 (duplicate `doc_id` namespaces, ~42% duplicate chunks) and #85 (~15%
  unretrievable noise). A rebuild fixes both. **Hosting duplicates costs nothing extra at this
  scale** — 1.72 GB on a 5 GB volume — so this is not a blocker, it is a post-handoff task.
- **Deliberately not attempted:** any change to `pipelines/ci_model/`, `road_midpoint.py`, Supabase,
  or `csi_v2.db`. Nothing in this decision touches them.
