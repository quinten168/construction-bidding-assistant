# Where the vector store should live

**Status:** decision memo for the handoff · written 2026-08-08 · re-examines GitHub #22
**Decision horizon that matters:** Mon Aug 17 (handoff to CSI IT / Shane), not Wed Aug 12 (demo).

---

## 0. What we are actually deciding

Two different questions have been travelling together under one issue number. Separating them is
most of the work:

| Question | Horizon | Who lives with the answer |
|---|---|---|
| **Q1 — how do 3–4 teammates share one corpus for ~10 days of demo prep?** | now → Aug 12 | us |
| **Q2 — where does the vector store live once CSI runs one app on one internal server?** | Aug 17 → forever | Shane / CSI IT |

They have different right answers, and **Q2 is the one that outlives us.** Everything below is
weighted for Q2, with Q1 handled as disposable scaffolding.

### Verified facts this rests on

| Fact | How verified |
|---|---|
| Store is `pipelines/plan_reader/06_chroma/`, **1.6 GB** — `chroma.sqlite3` alone is 1,565,155,328 bytes (1.46 GiB); six HNSW segment dirs add ~177 MB | `du -sh`, `ls -la`, 2026-08-08 |
| **75,080** embeddings, **210** distinct `doc_id`, collection `csi_plans` | direct `sqlite3` query against `chroma.sqlite3` |
| **A client is constructed in exactly two places, both `PersistentClient`** | grep, below |
| Embeddings are **local MiniLM** (`all-MiniLM-L6-v2`, 384-dim, cosine), bound to the collection | `pipelines/plan_reader/01_pipeline/lib.py:193,197-209` |
| Installed `chromadb` is **1.5.9**; `requirements.txt` pins only `chromadb>=0.5` | `.venv/bin/python -c "import chromadb"`; `apps/api/requirements.txt:7`, `pipelines/plan_reader/requirements.txt:10` |
| **The source PDF corpus is not on this machine** — `00_input/plans/` contains **1** PDF (`8370470.pdf`) plus the manifest | `find … -name "*.pdf" \| wc -l` → 1 |
| A teammate can run the full PDF-drop → report flow with an **empty** `06_chroma/` | `docs/DATA_ACCESS.md:184` |

That last-but-one row is load-bearing and is the single biggest constraint in this memo:
**"rebuild from source" is currently blocked on Box access to 183+ PDFs (~4.5 GB), on a machine that
does not have them.** Any option whose plan begins "first rebuild the store" has an unfunded
prerequisite with 9 days left.

### Every Chroma call site in the repo (verified by grep, 2026-08-08)

**Client construction — two sites, both `PersistentClient`. No `HttpClient`, no `CloudClient`
anywhere in the tree.**

| File:line | What it does |
|---|---|
| `pipelines/plan_reader/01_pipeline/lib.py:205` | `chromadb.PersistentClient(path=str(CHROMA_DIR))` inside `get_collection()` — **the one that matters** |
| `pipelines/plan_reader/01_pipeline/s2_indexer.py:228-229` | a *second* `PersistentClient`, used only by the `--reset` branch to call `delete_collection()` |

The claim "`lib.py::get_collection` is the single place a client is constructed" is **very nearly
true but not exactly true** — `s2_indexer.py:228-229` is a second one. It only runs under `--reset`,
so it is not on the serving path, but any hosted option must change **two** lines, not one.

**Callers of `lib.get_collection()` — 9 sites:**

| File:line | Role |
|---|---|
| `apps/api/backend/plan_reader_bridge.py:30` (via `:35` `retrieve`, `:47` `indexed_plans`) | **runtime read** — backs the `search_plans` chat tool |
| `apps/api/backend/report.py:160` | **runtime write** — ingests each dropped PDF |
| `pipelines/plan_reader/run.py:110` | CLI ingest |
| `pipelines/plan_reader/01_pipeline/s2_indexer.py:235` | CLI ingest |
| `pipelines/plan_reader/01_pipeline/retriever.py:125` | CLI query |
| `pipelines/plan_reader/03_evaluation/eval_extraction.py:236`, `rag_report.py:176` | eval |
| `pipelines/plan_reader/04_tools/rebuild_aggregates.py:36`, `retag_sections.py:43` | tools |
| `pipelines/plan_reader/07_archive/location_map.py:58`, `flag_suspect_tags.py:54` | archived |

Because every one of them goes through `get_collection()`, they are all insulated from the client
type. That is the reason the Chroma-to-Chroma options are one-line changes and pgvector is not.

**Collection API surface actually used** (this is what a pgvector rewrite must reimplement):

- `.query(query_texts=[q], n_results=k, where=where)` — `retriever.py:50-54`
- `.upsert(ids=, documents=, metadatas=)` — `s2_indexer.py:183`
- `.count()` — `s2_indexer.py:236,265`
- `.get(include=["metadatas"], limit=, offset=)` — paginated, `plan_reader_bridge.py:51`
- `client.delete_collection(...)` — `s2_indexer.py:230`

Small surface. Five methods. Note `query_texts=` (not `query_embeddings=`): the embedding function
is bound to the collection precisely so ingest and query cannot drift to different models
(`lib.py:200-202`). Any rewrite must preserve that invariant by hand.

### The 1.6 GB is not 1.6 GB of value

Two open issues both say the same thing about this store:

- **#58** — two writers stamp `doc_id` differently (`s2_indexer.py:96` uses manifest `plan_id`;
  `report.py:123` → `ingest_pdf` uses the PDF stem, defaulted at `report.py:98`). 21 PDFs indexed
  twice, **10,046 redundant chunks**, 9 doc_ids are raw upload UUIDs, `contract_id` blank on 100%
  of chunks. Metadata-filtered queries silently return half the corpus; unfiltered queries return
  passages twice.
- **#85** — **11,133 chunks (14.8%)** are unretrievable noise: 9,306 CAD vector text (12.4%),
  1,745 mojibake (2.3%, 79.6% of it one PDF). 5,093 of them are tagged `DECISION`.
- #22's own audit comment adds: **30,984 duplicate chunks (42.4%)**, 81 chunks over 50,000 chars.

**A rebuild from source fixes all of it for $0 in embedding cost** (MiniLM is local) and produces a
store the audit estimates at ~350–500 MB. It costs CPU hours and the Box PDFs we do not have.

So for every option below there are two numbers: what it costs to host the **1.6 GB as-is**, and
what it costs to host a **rebuilt ~500 MB** store. And one honest sentence: *we are 9 days out and
the source PDFs are not on the build machine, so plan for hosting 1.6 GB as-is and treat the
rebuild as a handoff to-do, not a prerequisite.*

---

## 1. The options

Cost basis for all of them: one always-on container, ~2 GB RAM, one persistent volume large enough
for 1.6 GB (call it 5 GB provisioned), negligible egress at 3–4 users. All pricing fetched
**2026-08-08**; URLs cited; anything not on a real pricing page is marked **UNVERIFIED**.

---

### (a) Railway — self-hosted `chromadb/chroma` Docker image

**Setup effort:** ~3–5 h to a working authenticated service. Add ~2–4 h for getting 1.6 GB *into*
the volume, which is the part people underestimate — Railway has no "upload a file to a volume"
button. You either `chroma copy --from-local --to <host>` (re-sends all 75,080 documents; the
client re-embeds them, so budget CPU time on your laptop) or attach the volume to a throwaway
service that pulls a tarball. Add ~1 h for the redeploy-persistence proof. **Call it a full day
including the proof, not the half-day #22 estimated.**

**Monthly cost:** plan fee **$5/mo Hobby** or **$20/mo Pro**, each including that much usage credit.
Memory **$0.00000386 per GB/second**, vCPU **$0.00000772 per vCPU/second**, volumes
**$0.00000006 per GB/second**, egress **$0.05/GB**
(https://railway.com/pricing, fetched 2026-08-08). Derived (arithmetic, not quoted): memory
≈ $10.15/GB-month → 2 GB ≈ $20/mo *if fully consumed*; a 5 GB volume ≈ **$0.79/mo**. **Volume size
caps: Free/Trial 0.5 GB, Hobby 5 GB, Pro 50 GB** — so 1.6 GB fits Hobby, but with almost no
headroom for a snapshot-alongside-restore. Realistic all-in: **$5–25/mo**, dominated by compute,
and Railway meters actual usage rather than allocation so an idle Chroma container is at the low
end. **The 1.6 GB itself is under a dollar a month; storage is not the cost driver — the always-on
container is.**

**Persistence + backup:** volumes are mounted at container start ("Volumes are mounted to your
service's container when it is started, not during build time"; "not mounted during pre-deploy
time" — https://docs.railway.com/volumes/reference.md). Backups are **manual or opt-in scheduled**
(daily/6-day, weekly/1-month, monthly/3-month), billed at volume rates
(https://docs.railway.com/volumes/backups.md). Whether any schedule is on by default:
**UNVERIFIED — the docs never say.** The commonly-quoted sentence "Railway volumes persist across
deploys and restarts" could not be located on any page actually fetched: **UNVERIFIED as a
quotable guarantee**, though the deployments reference implies it ("If your service requires data
to persist between deployments … you should add a volume").

**This is the failure mode to fear, and it is exactly CLAUDE.md's #65 class:** a Chroma container
with no volume mounted starts fine, answers fine, returns HTTP 200, and is *empty*. The service
being up is a transport fact; the corpus being there is an application fact. It must be proved by
observing `count() == 75080` **after** a forced redeploy, not by the deploy going green.

**Auth:** Chroma supports static-token auth via env vars. **A default deployment is
unauthenticated** — on a public Railway domain that is the entire CSI plan corpus readable by
anyone who finds the URL. Must be turned on explicitly.

**Our code change:** two lines. `lib.py:205` becomes `chromadb.HttpClient(host=…, port=…, ssl=True,
headers={"x-chroma-token": …})` behind an env check, and `s2_indexer.py:228-229` the same. Nothing
else moves: `retriever.py`'s `where` filters, `s4_extract_rag`'s `{"doc_id": …}` scoping,
`plan_reader_bridge.indexed_plans()`'s pagination, the `upsert`/`count`/`get` calls are all
identical against `HttpClient`. **This is genuinely its strongest property and it is worth saying
plainly.**

One caveat to verify rather than assume: with `chromadb` 1.5.9 the Python client is expected to run
the `SentenceTransformerEmbeddingFunction` **client-side** and ship vectors, which is what keeps
invariant 3 true (embeddings local, no API call). Chroma 1.x also persists an embedding-function
config server-side at collection creation. Which one wins for a self-hosted server on 1.5.9:
**UNVERIFIED** — check it with the one-liner in the setup doc before trusting it.

Also: the server image tag must be compatible with the `chroma.sqlite3` schema we already have.
Ours was written by whatever version was installed across Jun–Aug; 1.5.9 reads it today. A
`chromadb/chroma:latest` image that has moved ahead may migrate it irreversibly. **Pin the tag.**

**What CSI IT maintains after Aug 17:** a Railway account, a payment method, a token, and a backup
schedule nobody has set up — for a service their one app server could host locally for free. This
is the question that decides it. See §3.

---

### (b) Chroma Cloud (managed)

**Setup effort:** the lowest of any hosted option — ~1–2 h. `chroma copy --from-local collections
csi_plans` is a first-class CLI (https://docs.trychroma.com/docs/cli/copy) and
"Chroma Cloud implements the same APIs as open-source Chroma"
(https://docs.trychroma.com/cloud/getting-started).

**Monthly cost** (https://www.trychroma.com/pricing and https://docs.trychroma.com/cloud/pricing,
fetched 2026-08-08, numbers agree across both):
writes **$2.50 per logical GiB**, storage **$0.33 per GiB/month prorated hourly**, queries
**$0.0075 per TiB queried**, egress **$0.09 per GiB returned**. Starter is **$0/month + usage with
$5 free credits**; Team is **$250/month**. At our scale: storage on ~1.6 GB ≈ **$0.53/mo**; the
one-time write charge is billed on *logical* (uncompressed input) GiB, not the 1.5 GB index — for a
~4.5 GB PDF corpus reduced to text chunks this is plausibly a few dollars, but the exact logical
size of our documents is **UNVERIFIED**. Query volume at 3–4 users is rounding error.
**So: roughly $1–10/mo. Cheapest hosted option on paper.**

**Persistence + backup:** managed; the provider owns durability. A documented exit exists (`chroma
copy --from-cloud`, and the docs state Chroma will help transition data back to self-managed).
Their retention/PITR policy: **UNVERIFIED** — not on a page I fetched.

**Auth:** API key.

**Our code change:** same two lines, `CloudClient` instead of `HttpClient`. (The exact
`CloudClient(api_key=, tenant=, database=)` constructor signature: **UNVERIFIED** — the docs URL
for it 404'd.)

**What CSI IT maintains after Aug 17:** a third-party SaaS account holding **the full text of CSI's
plan corpus** on someone else's infrastructure, with a usage-metered bill. Cheap, easy, and the
hardest thing to justify to a construction company's IT lead in a handoff meeting. Note the
counter-argument from #22 that "Supabase is a third party too" is fair — but the distinction that
survives is *what is already contracted for*. Supabase is signed; Chroma Cloud would be a new
vendor relationship created 4 days before the program ends.

---

### (c) Render

**Setup effort:** same as Railway, ~1 day including the persistence proof. Same Docker image, same
volume-seeding awkwardness.

**Monthly cost** (https://render.com/pricing, https://render.com/docs/disks,
https://render.com/docs/new-workspace-plans, fetched 2026-08-08): workspace **Hobby free / Pro $25
flat / Scale $499 flat** (flat, not per-seat, since the 2026-04-23 plan revision). Compute:
Starter **$7/mo** (512 MB / 0.5 CPU), **Standard $25/mo (2 GB / 1 CPU)**. Persistent disk
**$0.25/GB per month** → 5 GB = **$1.25/mo**. Bandwidth included per workspace (Hobby 5 GB,
Pro 25 GB), overage **$0.15/GB**. **Disks are not available on the Free instance type**
("Local files lost on redeploy"), so Starter or above is mandatory. Realistic: **$7–26/mo**.

Whether Chroma runs acceptably in 512 MB with a 1.6 GB index (HNSW segments are memory-mapped, and
ours total ~177 MB): **UNVERIFIED** — plausible on Starter, but untested. Budget Standard.

**Persistence + backup:** **automatic and this is Render's one clear win** —
"Render automatically creates a snapshot of your persistent disk once every 24 hours" and
"Snapshots are available for at least seven days after they're created" (https://render.com/docs/disks).
No cron job to write, no schedule to remember to enable.

**Auth:** Chroma token auth, same as Railway. Same unauthenticated-by-default hazard.

**Our code change:** identical two lines to (a).

**What CSI IT maintains after Aug 17:** identical to Railway, minus the "did anyone turn backups
on?" question.

---

### (d) Fly.io

**Setup effort:** ~1 day, slightly more CLI-heavy than Railway/Render (`fly launch`, `fly volumes
create`, `fly.toml` mount stanza). Fly's `fly ssh sftp shell` / `fly sftp put` makes **seeding the
1.6 GB into the volume genuinely easier** than either — you can push the tarball straight into the
mounted path instead of round-tripping through `chroma copy` and re-embedding.

**Monthly cost** (https://fly.io/docs/about/pricing/, https://fly.io/pricing, fetched 2026-08-08):
**shared-cpu-1x with 2 GB RAM = $11.11/month** (Amsterdam region quote; varies by region);
volumes **$0.15/GB per month of provisioned capacity** → 5 GB = **$0.75/mo**; egress
**$0.02/GB** NA/EU. No platform or seat fee found (**UNVERIFIED** that none exists); paid support
starts at $29/mo. Realistic all-in: **~$12/mo — the cheapest self-hosted option.**

**Persistence + backup:** **"Automatic daily snapshots with 5 days retention are enabled by default
on new volumes"**; snapshot storage $0.08/GB-month with the first 10 GB free. Best default backup
posture of the three self-hosted options. Fly volumes are also single-node local NVMe — fine for
one instance, and a trap if anyone ever scales to two.

**Auth:** same Chroma token story; Fly additionally makes it easy to bind to the private WireGuard
network and expose nothing publicly, which is the strongest security posture of (a)/(c)/(d).

**Our code change:** identical two lines.

**What CSI IT maintains after Aug 17:** a Fly account, a card, `flyctl`, and a machine that
occasionally needs an image bump. Same category as Railway/Render.

---

### (e) pgvector on the Supabase we already pay for

**Setup effort:** **3–5 days, and it is the only option where that estimate is real work rather than
waiting.** `create extension vector`, a `scratch.plan_chunks` table (id, doc_id, text, metadata
jsonb, embedding vector(384)), an HNSW index with `vector_cosine_ops`, then a hand-written
replacement for all five Chroma methods across four files:

- `lib.py::get_collection` → a connection + a small shim object, or the callers change
- `retriever.py:50-54` `.query(query_texts=…, where=…)` → embed locally, then
  `ORDER BY embedding <=> $1 LIMIT k` with the `where` dict translated to jsonb predicates
- `s2_indexer.py:183` `.upsert` → `INSERT … ON CONFLICT (id) DO UPDATE`
- `s2_indexer.py:236,265` `.count()` → `SELECT count(*)`
- `plan_reader_bridge.py:51` paginated `.get()` → `SELECT DISTINCT metadata->>'doc_id'` (this one
  actually gets *simpler* and faster)
- plus: the ingest path must now embed explicitly, which **breaks the `lib.py:200-202` invariant
  that ingest and query cannot drift to different models.** That invariant currently exists for
  free; under pgvector it has to be re-established by discipline.

Add: `apps/api` gains a second Postgres consumer (invariant 6 already opened that door via
`ci_db.py`), and `pipelines/plan_reader` gains its first (invariant 7 set the precedent in
`ci_model`). Architecturally consistent. Also note pgvector's documented caveat that naive
filtering against an HNSW/IVFFlat index **can return fewer rows than requested** — our `where`
filters are used in anger (`s4_extract_rag`'s per-doc scoping), so this needs iterative search, not
a naive `WHERE … ORDER BY … LIMIT`.

**Monthly cost: ~$0 marginal.** Supabase Pro is **"from $25/month"** with **"8 GB disk size per
project included, then $0.125 per GB"** (https://supabase.com/pricing,
https://supabase.com/docs/guides/platform/compute-and-disk — both fetched 2026-08-08). 75,080 ×
384 × 4 bytes ≈ **110 MiB of raw vectors**; with text, jsonb metadata and the HNSW index, call it
600 MB–1.5 GB. **Inside the included 8 GB.** Caveat: "You can increase disk size but cannot
decrease it," and the Pro spend cap (on by default) blocks overage rather than billing it — a
migration that overshoots 8 GB fails rather than silently costing money, which is the good failure.

**Persistence + backup:** free and managed — Pro gets **"Daily backups stored for 7 days"**; PITR is
**"$100 per month per 7 days retention"** (https://supabase.com/pricing). Nothing to build.

**Auth:** existing Postgres roles, existing `SUPABASE_TEAM_DB_URL`. **Must go in `scratch`, not
`public`** or PostgREST exposes the whole corpus (the #64 concern).

**pgvector viability confirmed:** available as an extension, HNSW and IVFFlat both supported, index
dimension ceiling 2,000 for `vector` — MiniLM's 384 is nowhere near it
(https://supabase.com/docs/guides/database/extensions/pgvector,
https://supabase.com/docs/guides/ai/vector-indexes/hnsw-indexes).

**Unique benefit, and it is real:** chunks land in the same database as `bid_projects`, so metadata
filtering becomes a JOIN and `plan_uid` can be a genuine FK. That is the closest anything on this
list comes to closing the rough-edge-5 `plan_reader`/`ci_model` seam.

**What CSI IT maintains after Aug 17:** a Supabase project they already maintain — *if* the
Supabase account transfers to CSI and someone at CSI owns the bill after the program ends. **Nobody
has confirmed that.** It is the single biggest unverified assumption in the pgvector case, and it
is not a technical one.

---

### (f) Chroma local to CSI's app server, post-handoff

**Setup effort: zero.** `pip install -r requirements.txt` already installs `chromadb>=0.5`. Copy
the `06_chroma/` directory to `pipelines/plan_reader/06_chroma/` on the server. `lib.py:52`
(`CHROMA_DIR = MODULE_ROOT / "06_chroma"`) already points there. The app finds it. Total added
effort over "install the app at all": the ~15 minutes it takes to copy 1.6 GB and run one count
check.

**Monthly cost: $0.** No account, no card, no vendor, no renewal. 1.6 GB on a server that is
already provisioning tens of GB for a Python venv with PyTorch in it — `sentence-transformers` +
`torch` (2.8.0 here) is itself several GB, so the vector store is **not** the largest thing being
installed. Transfer cost: one 1.6 GB copy, once, over the LAN or from a USB drive. `chroma.sqlite3`
compresses well enough that a `tar czf` is a practical transport (exact ratio **UNVERIFIED** — it is
mostly float blobs, so expect modest, maybe 1.1–1.4×, not dramatic).

**Persistence + backup:** the file system. It persists because it is a directory, not because a
volume was correctly mounted. Backup is `tar czf` of one directory with the app stopped; restore is
`tar xzf`. Both are procedures Shane already knows how to run and already runs for everything else
on that box, and both are covered by whatever CSI already does for that server. **There is no new
failure mode, because there is no new moving part.**

**Auth:** file permissions. The store is reachable only by the process that reads it, on a server
CSI already controls. **No CSI data leaves CSI.** This is the only option on the list of which that
is true.

**Our code change: none. Zero lines.** `lib.py:205` stays exactly as written. This is not a
migration; it is the absence of one.

**What CSI IT maintains after Aug 17:** a directory. Include it in the server's existing backup set
and never think about it again.

**The honest weakness, stated plainly:** it does not solve Q1. It gives the team nothing for the
next 10 days — every teammate needs their own copy of the file or an empty store. And it means the
app is single-node: two app servers would need two copies that drift. Neither of those is a problem
CSI has. Both are problems *we* have, for 10 days.

---

## 2. Comparison

| | (a) Railway | (b) Chroma Cloud | (c) Render | (d) Fly.io | (e) Supabase pgvector | **(f) Local on CSI server** |
|---|---|---|---|---|---|---|
| Setup effort | ~1 day | 1–2 h | ~1 day | ~1 day | **3–5 days** | **~0** |
| $/month at our scale | $5–25 | ~$1–10 | $7–26 | ~$12 | **$0 marginal** (inside existing Pro) | **$0** |
| Cost of the 1.6 GB itself | ~$0.79/mo (5 GB vol) | ~$0.53/mo + one-time write fee | $1.25/mo (5 GB) | $0.75/mo (5 GB) | $0 (in the 8 GB) | $0 |
| Transfer of 1.6 GB in | awkward — no volume upload | `chroma copy` (easy) | awkward | **easiest** (`fly sftp`) | N/A — rebuild/re-embed | `scp`/USB, 15 min |
| Rebuild from source required? | optional | optional | optional | optional | **effectively required** (you re-embed anyway) | optional |
| Persistence risk | **volume-mount trap** | none (managed) | volume-mount trap | volume-mount trap | none | none |
| Automatic backups | **No** — opt-in schedules | managed, policy UNVERIFIED | **Yes**, daily/7 d | **Yes**, daily/5 d, on by default | **Yes**, daily/7 d | whatever CSI already does |
| Auth | token, **off by default** | API key | token, off by default | token + private network | existing PG roles | file permissions |
| Our code change | 2 lines | 2 lines | 2 lines | 2 lines | **4 files, 5 methods, +explicit embedding** | **0 lines** |
| CSI data leaves CSI? | yes | yes | yes | yes | yes (already does, for structured) | **no** |
| What Shane maintains | account, card, token, backup job | account, card, metered bill | account, card, token | account, card, flyctl | Supabase project — **if ownership transfers** | a directory |

---

## 3. Recommendation

> ### For after Aug 17: **(f) Chroma local to CSI's app server.** Keep `PersistentClient`. Change nothing.
>
> ### For the next 10 days: **do not host it — ship the file.** If a live shared endpoint is genuinely needed for demo prep, **Railway Hobby with an explicitly mounted volume, deleted on Aug 17**, labelled as disposable demo scaffolding and never presented as the handoff architecture.

This says the owner's in-progress Railway work is not wasted — it is just scoped to the 10 days
rather than to the handoff. That is a smaller claim than "Railway is the answer," and it is the one
the facts support.

**The reasoning, made explicit:**

**1. The stated end state removes the entire problem.** "After Aug 17, CSI runs ONE app instance on
ONE internal server." A vector store hosted *anywhere else* is then a network hop, a credential, a
bill, and a new failure mode added to an app that would otherwise read a local directory. Every
hosted option is solving *distribution* — and after Aug 17 there is nothing to distribute to. #22's
framing ("local Chroma is build-time only: not reachable by the team, not durable") was written when
"the team" meant four students on four laptops. Under one-server-at-CSI, "not reachable by the team"
stops being a defect and "not durable" is answered by CSI's existing server backups, not by a cloud
volume.

**2. Zero lines of code and zero new concepts is worth more than any monthly saving.** `lib.py:205`
already does the right thing. Option (f) is the only one where the handoff document says "it's a
directory, back it up with the rest of the server" instead of "here is a vendor account, here is
whose card it is on, here is the token to rotate, here is the backup job someone has to notice is
failing." A handoff artifact's real cost is the number of things the receiving team must understand,
and (f) scores zero on every count. Every hosted option adds an account CSI must adopt within four
days of the program ending — and the #1 way this system dies in October is a card expiring on a
service nobody at CSI remembers owning.

**3. CSI data staying on CSI hardware is a genuine differentiator, and only (f) has it.** #22's
counter-argument is correct as far as it goes — the `outcome` field (bid_won 726 / bid_lost 5,206 /
no_bid 23,732) already leaves our infrastructure via Supabase, so "third party" doesn't cleanly
separate Railway from Chroma Cloud. But it *does* separate all five hosted options from (f), which
is the only one where the answer to "who else holds CSI's plan corpus?" is "nobody." When the choice
is otherwise close, that decides it — and here the choice isn't close, because (f) also wins on
effort and cost.

**Why not pgvector, given #22's own recommendation was pgvector.** The pgvector case was the right
call for the world where this becomes a multi-user hosted product — one hosted system instead of
two, free backups, and the real prize of joining chunks to `bid_projects`. That world is not the one
in the calendar. It costs 3–5 days of rewriting four modules, landing **five days before handoff**,
against an owner who also has a final presentation on Aug 12; it converts a bound-embedding-function
invariant into a hand-maintained discipline; and its "$0 marginal cost" holds only if the Supabase
account transfers to CSI, which nobody has confirmed. **If the project were continuing, pgvector is
the right destination. It should stay open as the documented next step — but it is not a thing to
start on Aug 8.**

**Why not Fly, which is the best hosted option on the merits.** Fly is cheapest (~$12/mo), has
backups on by default, has the easiest 1.6 GB seeding path, and can hide behind a private network.
If the answer had to be "host it somewhere," it would be Fly, not Railway. It is still an account
CSI must adopt to solve a problem CSI does not have.

### What would change my mind

Any one of these flips the recommendation. They are listed in rough order of likelihood:

1. **CSI plans to run more than one app instance**, or to run the app somewhere the filesystem is
   ephemeral (a container platform, a PaaS, autoscaling). A local directory is single-node by
   construction. → then **pgvector** (they already have the DB) or **Fly**.
2. **Shane says "we don't want a 1.6 GB blob on the app server"** or their server backup policy
   excludes app data directories. → then **pgvector**, since it inherits Supabase's daily backups.
3. **Somebody at CSI confirms they will own and pay for the Supabase project indefinitely.** That
   converts pgvector's "$0 marginal" from an assumption into a fact and makes the one-hosted-system
   argument real. → then **pgvector**, scheduled post-handoff, not now.
4. **The Box PDFs land before Aug 12 and a rebuild happens.** A clean ~500 MB store is small enough
   that every option gets cheaper and a full pgvector migration gets less daunting — and it removes
   the "we'd be hosting 42% duplicates" objection that currently taints every hosted option.
5. **The team demonstrably cannot do demo prep without a shared live store** — i.e. `DATA_ACCESS.md`'s
   "works with an empty `06_chroma/`" claim turns out to be false in practice for the Aug 12 demo.
   → then stand up the Railway/Fly bridge immediately, and still tear it down on Aug 17.
6. **CSI IT says they'd rather have a managed service than a file to back up.** Some IT shops
   genuinely would. → then **Fly** (cheapest, backups on by default) or Chroma Cloud if they're
   comfortable with the vendor.

### Two-phase summary, in one table

| | Now → Aug 17 (us) | Aug 17 → forever (CSI) |
|---|---|---|
| Store lives | each laptop, or one disposable Railway/Fly container | `pipelines/plan_reader/06_chroma/` on CSI's app server |
| Code | `PersistentClient` (unchanged) or 2-line `HttpClient` behind an env var | `PersistentClient` — **unchanged, always** |
| Cost | $0, or $5–12/mo for ≤2 weeks | $0 |
| Backup | none needed (disposable) | `tar czf` in CSI's existing server backup |
| Owner | Tobias | Shane |

The two-line `HttpClient` change, **if** it is made for the bridge, must be gated on an env var
(`CHROMA_HOST` set → HTTP, unset → local) so that Aug 17 requires deleting an env var, not reverting
code. The setup document specifies exactly that.

---

## 4. Open items this memo does not settle

- **UNVERIFIED:** whether `chromadb` 1.5.9's Python client embeds client-side against a self-hosted
  `HttpClient` (invariant 3) or defers to a server-side EF config. One-liner check in the setup doc.
- **UNVERIFIED:** Railway's default volume-backup schedule; whether Railway volumes are contractually
  guaranteed to survive redeploys (implied by docs, never stated in those words).
- **UNVERIFIED:** Chroma Cloud's retention/PITR policy; the exact `CloudClient` constructor.
- **UNVERIFIED:** whether the Supabase project ownership/billing transfers to CSI after Aug 21. This
  is a people question and it gates option (e) entirely.
- **Not settled here:** #58 and #85. A rebuild fixes both and is recommended as a post-handoff task,
  not as a prerequisite to any hosting decision. Nothing in this memo depends on them being fixed
  first.
