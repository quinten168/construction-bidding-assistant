# Vector store: install, verify, back up, restore

Companion to [`vector_hosting.md`](vector_hosting.md). That document decides **where**; this one is
the walkthrough for the option it recommends: **Chroma stays local, `PersistentClient`, on CSI's app
server.**

Written to be followed at 11pm without surprises. Every step ends with **"working looks like"** — a
concrete observation. If the observation does not match, **stop at that step**; do not continue and
discover it three steps later. That failure pattern is the whole reason this document is shaped this
way (CLAUDE.md, rough edge 2 and the #65 note: a success signal at the wrong layer is not evidence).

Three parts:

- **Part A** — install the store on CSI's app server (the Aug 17 handoff procedure).
- **Part B** — backup + restore, written for Shane to run and own.
- **Part C** — the 10-day team bridge (optional, disposable) and its rollback.

Throughout: `$REPO` is the repo root on the target machine, e.g. `/opt/csi-bid-intelligence`.
On the dev laptop it is `/Users/t/dev/csi/csi-bid-intelligence`.

---

## Part A — Install on CSI's app server

### A0. Facts you should confirm before starting (2 min)

Run on the **source machine** (the laptop that has the store):

```bash
cd /Users/t/dev/csi/csi-bid-intelligence
du -sh pipelines/plan_reader/06_chroma
ls -la pipelines/plan_reader/06_chroma
```

**Working looks like:** `1.6G` total, a `chroma.sqlite3` of ~1,565,155,328 bytes, and six
UUID-named directories (the HNSW segments, ~177 MB combined). If `chroma.sqlite3` is there but the
UUID directories are missing, **stop** — you have the metadata without the indexes and retrieval
will be slow or empty.

```bash
/Users/t/dev/csi/csi-bid-intelligence/.venv/bin/python - <<'PY'
import sqlite3
c = sqlite3.connect("/Users/t/dev/csi/csi-bid-intelligence/pipelines/plan_reader/06_chroma/chroma.sqlite3")
print("embeddings:", c.execute("select count(*) from embeddings").fetchone()[0])
print("doc_ids:", c.execute("select count(distinct string_value) from embedding_metadata where key='doc_id'").fetchone()[0])
print("collections:", c.execute("select name from collections").fetchall())
PY
```

**Working looks like — memorise these three numbers, they are the acceptance test for the whole
procedure:**

```
embeddings: 75080
doc_ids: 210
collections: [('csi_plans',)]
```

Also note the Chroma version that wrote it, because the server must be able to read it:

```bash
/Users/t/dev/csi/csi-bid-intelligence/.venv/bin/python -c "import chromadb; print(chromadb.__version__)"
```

**Working looks like:** `1.5.9` (as of 2026-08-08). Write this number in the handoff notes. A newer
`chromadb` may silently migrate the SQLite schema on first open, and that migration is not
reversible — which is why Part B's step B1 takes a backup *before* the app ever opens the store on
the new machine.

### A1. Get the repo and the venv onto the server

```bash
git clone <repo-url> /opt/csi-bid-intelligence
cd /opt/csi-bid-intelligence
python3 -m venv .venv
./.venv/bin/pip install -r apps/api/requirements.txt
./.venv/bin/pip install -r pipelines/plan_reader/requirements.txt
```

**Working looks like:**

```bash
./.venv/bin/python -c "import chromadb, sentence_transformers, torch; print(chromadb.__version__, torch.__version__)"
```

prints two version numbers with no traceback. Expect this install to be **several GB** — `torch`
alone dwarfs the 1.6 GB vector store, so if disk is tight it is not the vector store that is the
problem.

If `pip install` dies on `torch`, that is a known environment issue and unrelated to the vector
store (CLAUDE.md rough edge 7 records the same failure on a Windows sandbox). Resolve it before
continuing; nothing below works without `sentence-transformers`.

### A2. Pre-download the embedding model (do this while you have internet)

MiniLM downloads once (~80 MB) to the HuggingFace cache and is then used offline (`lib.py:191-193`).
If the app server is firewalled, this step **must** happen now or the first query fails.

```bash
./.venv/bin/python -c "
from sentence_transformers import SentenceTransformer
SentenceTransformer('all-MiniLM-L6-v2')
print('model cached')"
```

**Working looks like:** `model cached`, and `~/.cache/huggingface/` (or `$HF_HOME`) now exists with
content. Re-running it prints instantly with no download progress bars — that is the proof it is
cached, not just that it worked once.

### A3. Copy the store across

The store is one directory. It does not need to be exported, dumped, or converted.

**Option 1 — over the network (preferred).** From the source laptop:

```bash
cd /Users/t/dev/csi/csi-bid-intelligence/pipelines/plan_reader
tar czf /tmp/06_chroma_2026-08-17.tar.gz 06_chroma
ls -lh /tmp/06_chroma_2026-08-17.tar.gz
shasum -a 256 /tmp/06_chroma_2026-08-17.tar.gz | tee /tmp/06_chroma_2026-08-17.sha256
scp /tmp/06_chroma_2026-08-17.tar.gz /tmp/06_chroma_2026-08-17.sha256 user@csi-app-server:/tmp/
```

`chroma.sqlite3` is mostly float blobs, so expect only modest compression — plan for a **1.2–1.6 GB
transfer**, not 400 MB. (Exact ratio UNVERIFIED; check the `ls -lh` output and size the transfer
window off the real number, not off this sentence.)

**Option 2 — USB drive.** Same `tar czf`, same `shasum`, carry it over. Use this if the LAN transfer
would take longer than the maintenance window.

Then on the server:

```bash
cd /tmp
shasum -a 256 -c 06_chroma_2026-08-17.sha256
cd /opt/csi-bid-intelligence/pipelines/plan_reader
tar xzf /tmp/06_chroma_2026-08-17.tar.gz
du -sh 06_chroma
```

**Working looks like:** `06_chroma_2026-08-17.tar.gz: OK` from the checksum check, then `1.6G` from
`du`. **A checksum mismatch means stop and re-transfer** — a truncated SQLite file opens fine and
returns a lower count, which is exactly the kind of quiet wrongness this whole document is arranged
to catch.

`lib.py:52` already defines `CHROMA_DIR = MODULE_ROOT / "06_chroma"`, so no path configuration is
needed. The directory being in the right place *is* the configuration.

### A4. Prove the app can read it — the acceptance test

```bash
cd /opt/csi-bid-intelligence
./.venv/bin/python - <<'PY'
import sys, pathlib
sys.path.insert(0, str(pathlib.Path("pipelines/plan_reader/01_pipeline").resolve()))
import lib
col = lib.get_collection()
print("collection:", col.name)
print("count:", col.count())
hits = col.query(query_texts=["bituminous pavement quantity"], n_results=3)
for d, m in zip(hits["documents"][0], hits["metadatas"][0]):
    print("-", m.get("doc_id"), "p." + str(m.get("page")), "|", d[:70].replace("\n", " "))
PY
```

**Working looks like:**

```
collection: csi_plans
count: 75080
- <a real doc_id> p.<n> | <a real sentence of plan text>
- ...
```

**Three specific failure signatures, and what each means:**

| What you see | What it means | Do this |
|---|---|---|
| `count: 0` | Chroma created a *new empty* collection because it did not find the store — wrong path, or the tar extracted one level too deep | check `ls pipelines/plan_reader/06_chroma/chroma.sqlite3` exists; you probably have `06_chroma/06_chroma/` |
| `count:` some number **other than 75080** | truncated transfer, or a schema migration dropped rows | restore from the tarball again after verifying the checksum |
| count is right but `query` returns nothing / errors | the HNSW segment directories did not come across, or the MiniLM model is not cached | re-check A0's `ls -la` (six UUID dirs) and A2 |

**Do not proceed past a `count` that is not 75080.** A store that opens and answers is not a store
that is complete.

### A5. Start the app and prove it end-to-end

```bash
cd /opt/csi-bid-intelligence/apps/api
../../.venv/bin/python -m uvicorn app:app --port 8010
```

**Working looks like:** the server starts, and in another shell the chat `search_plans` path returns
cited excerpts rather than "no results." The path under test is
`apps/api/backend/plan_reader_bridge.py:30 → :35 → retriever.retrieve` — the same
`lib.get_collection()` you just proved in A4, so if A4 passed and this fails, the problem is the
app, not the store.

A cheap independent check that the *backend process* sees the corpus:

```bash
cd /opt/csi-bid-intelligence
./.venv/bin/python -c "
import sys; sys.path.insert(0, 'apps/api')
from backend import plan_reader_bridge as b
print(len(b.indexed_plans()), 'plans indexed')"
```

**Working looks like:** `210 plans indexed`. That number matching A0's `doc_ids: 210` is the proof
that the backend and the file agree.

### A6. The persistence proof — the step people skip

The concern that motivated hosting in the first place was "a redeploy silently loses the store."
On a local install the equivalent risks are: the deploy process wiping untracked files, a `git
clean`, or a container/service restart mounting a different working directory. Prove it survives:

```bash
# 1. Note the current state
cd /opt/csi-bid-intelligence
./.venv/bin/python -c "
import sys,pathlib; sys.path.insert(0,str(pathlib.Path('pipelines/plan_reader/01_pipeline').resolve()))
import lib; print('before:', lib.get_collection().count())"

# 2. Do the most destructive thing your normal deploy does
sudo systemctl restart csi-bid-api      # or: kill uvicorn and restart it
git pull                                 # a real code update
# and, deliberately, the one that would wipe it if the deploy ever ran it:
git status --porcelain --ignored pipelines/plan_reader/06_chroma | head -3

# 3. Re-check
./.venv/bin/python -c "
import sys,pathlib; sys.path.insert(0,str(pathlib.Path('pipelines/plan_reader/01_pipeline').resolve()))
import lib; print('after:', lib.get_collection().count())"
```

**Working looks like:** `before: 75080` and `after: 75080`, and the `git status` line shows the
directory as **ignored** (`!! pipelines/plan_reader/06_chroma/`).

**The trap to write into the runbook:** `06_chroma/` is gitignored. That means `git clean -xdf` —
a command deploy scripts genuinely contain — **will delete the entire vector store without a single
error message**, and the app will come back up, return HTTP 200, and answer every question with
nothing. This is the local-server version of the unmounted-volume failure, and it is the one thing
about this setup that can bite silently.

**Mitigation, do this now:** either (a) never use `-x` in a deploy `git clean`, or (b) store the
canonical copy outside the repo and symlink it in:

```bash
sudo mkdir -p /var/lib/csi-bid-intelligence
sudo mv /opt/csi-bid-intelligence/pipelines/plan_reader/06_chroma /var/lib/csi-bid-intelligence/
ln -s /var/lib/csi-bid-intelligence/06_chroma /opt/csi-bid-intelligence/pipelines/plan_reader/06_chroma
```

Then re-run A4. **Working looks like:** `count: 75080` again, through the symlink, with **no code
change** — `lib.py:52` follows the symlink transparently. Option (b) is recommended: it puts the
1.6 GB somewhere a code deploy cannot reach and somewhere a server backup policy will naturally
pick up.

### A7. Auth

There is nothing to configure, and that is the point. The store is a file on a server CSI controls;
access is governed by filesystem permissions and by whoever can reach port 8010. Recommended:

```bash
sudo chown -R csi-app:csi-app /var/lib/csi-bid-intelligence/06_chroma
sudo chmod -R o-rwx /var/lib/csi-bid-intelligence/06_chroma
```

**Working looks like:** `ls -ld /var/lib/csi-bid-intelligence/06_chroma` shows the app's service
account as owner and no world permissions, and A4 still prints `count: 75080` **when run as the
service account** (`sudo -u csi-app ...`) — not just as root.

The real auth surface is the FastAPI app on :8010 and the Next.js app on :3000, which is a separate
conversation and is not changed by this document. Note only that the corpus is now reachable by
anyone who can reach :8010.

### A8. The code change

**There is none.** `pipelines/plan_reader/01_pipeline/lib.py:205` stays exactly as it is:

```python
client = chromadb.PersistentClient(path=str(CHROMA_DIR))
```

If you are reading this document to find the one-line change: the recommendation is that there
isn't one. The line already does the right thing. (The env-gated `HttpClient` variant exists only
for the optional 10-day bridge — Part C — and is explicitly not part of the handoff.)

### A9. Rollback

Every step above is additive; rollback is deletion.

| If this went wrong | Roll back by |
|---|---|
| Store copied but wrong/corrupt | `rm -rf` the directory, re-extract from the tarball, re-run A4 |
| Symlink move (A6b) broke something | `rm` the symlink, `mv /var/lib/csi-bid-intelligence/06_chroma` back into `pipelines/plan_reader/`, re-run A4 |
| Everything is broken and you need the app up now | `rm -rf` the store entirely. **The app still runs** — `docs/DATA_ACCESS.md:184` records that the full PDF-drop → report flow works with an empty `06_chroma/`. You lose cross-plan retrieval, not the product. |

That last row is the safety net worth stating out loud in the handoff meeting: **the vector store is
required for good answers, not for the app to start.** Nothing here can brick the deployment.

### A10. Rebuilding from source instead of copying (the alternative to A3)

Only do this if the copy is impossible, or once someone wants to fix #58 and #85.

**Prerequisite that is currently unmet:** the source PDFs. `pipelines/plan_reader/00_input/plans/`
on the dev laptop contains **1 PDF** (`8370470.pdf`) plus `plans_manifest.csv` — the other ~183
(~4.5 GB) are in Box only. Confirm before starting:

```bash
find pipelines/plan_reader/00_input/plans -name '*.pdf' | wc -l
```

**Working looks like:** a number near 184. **If it prints `1`, stop — you cannot rebuild.** Copy the
store (A3) instead. This is not a soft warning; a rebuild from 1 PDF produces a 1-PDF store and
gives you no error.

With the corpus present:

```bash
cd /opt/csi-bid-intelligence
P=pipelines/plan_reader
./.venv/bin/python $P/01_pipeline/s1_convert.py $P/00_input/plans
./.venv/bin/python $P/01_pipeline/s2_indexer.py $P/00_input/plans --reset --trace
```

`--reset` drops the whole collection first (`s2_indexer.py:225-232`) — this is what fixes #58's
`doc_id` namespace split, because every chunk is re-stamped from `plans_manifest.csv`. Budget hours,
not minutes: 75k chunks of MiniLM on CPU. Cost in dollars: **$0** — embeddings are local
(CLAUDE.md invariant 3), which is why a rebuild is cheap in money and expensive only in wall clock.

**Working looks like:** the indexer's own before/after count (`s2_indexer.py:236,265`) reports a
final count, and A4's checks pass with **a smaller number than 75,080** — the audit in #22 expects
roughly a third of the size once the 42% duplicates and 14.8% noise are gone. A rebuilt store that
still reports ~75,080 means `--reset` did not take.

**A rebuild does not fix #58 permanently.** `apps/api/backend/report.py:123` still stamps `doc_id`
from the PDF stem (`report.py:98`), so the split re-opens on the next web upload. That is issue #58's
fix, not this document's.

---

## Part B — Backup and restore (for Shane, from Aug 17)

This is the whole operational burden of the recommended option. It is two commands.

### B1. What to back up

One directory: `/var/lib/csi-bid-intelligence/06_chroma` (or
`/opt/csi-bid-intelligence/pipelines/plan_reader/06_chroma` if you skipped A6b). ~1.6 GB. It is a
SQLite database plus HNSW index files.

**It is not in git**, deliberately — it is derived data, and it is too large. Do not expect a `git
pull` to restore it.

### B2. Backup procedure

**Stop the app first.** SQLite tolerates a live copy far better than it used to, but the HNSW
segment files are written outside the SQLite transaction, so a hot copy can be internally
inconsistent — the copy succeeds and the restore is subtly wrong. Take the 60 seconds.

```bash
sudo systemctl stop csi-bid-api

STAMP=$(date +%F)
sudo tar czf /backup/06_chroma_$STAMP.tar.gz -C /var/lib/csi-bid-intelligence 06_chroma
sudo shasum -a 256 /backup/06_chroma_$STAMP.tar.gz | sudo tee /backup/06_chroma_$STAMP.sha256

sudo systemctl start csi-bid-api
```

**Working looks like:** a `.tar.gz` of roughly **1.2–1.6 GB** in `/backup/`, a `.sha256` beside it,
and the app back up. **A tarball of a few megabytes means the directory was empty or the path was
wrong — check before you trust it.** That check is the entire point of quoting the expected size
here.

As a cron entry (weekly is ample — the store only changes when plans are ingested):

```cron
0 2 * * 0 systemctl stop csi-bid-api && tar czf /backup/06_chroma_$(date +\%F).tar.gz -C /var/lib/csi-bid-intelligence 06_chroma && systemctl start csi-bid-api
```

Keep 4 weeks. Total backup footprint ~6 GB.

**Better than the cron, if CSI already backs up `/var/lib`:** do nothing. The store is a directory
under a standard path and is covered by whatever policy already protects that server. That is the
main reason `/var/lib` was chosen in A6b. Confirm it with CSI's backup admin rather than assuming
it — and confirm by *restoring a test file*, not by reading the policy document.

### B3. Restore procedure

```bash
sudo systemctl stop csi-bid-api

cd /backup
sudo shasum -a 256 -c 06_chroma_<STAMP>.sha256          # must print: OK

sudo rm -rf /var/lib/csi-bid-intelligence/06_chroma
sudo tar xzf /backup/06_chroma_<STAMP>.tar.gz -C /var/lib/csi-bid-intelligence
sudo chown -R csi-app:csi-app /var/lib/csi-bid-intelligence/06_chroma

# Verify BEFORE starting the app
sudo -u csi-app /opt/csi-bid-intelligence/.venv/bin/python - <<'PY'
import sys, pathlib
sys.path.insert(0, "/opt/csi-bid-intelligence/pipelines/plan_reader/01_pipeline")
import lib
col = lib.get_collection()
print("count:", col.count())
PY

sudo systemctl start csi-bid-api
```

**Working looks like:** `OK` from the checksum, then `count: 75080` (or whatever count the backup was
taken at — **record that number in the backup log next to each tarball**, otherwise you have nothing
to compare against and "it printed a number" becomes the success signal, which is exactly the
mistake this project keeps making).

### B4. Quarterly restore drill — the part that makes the backup real

A backup that has never been restored is a hypothesis. Once a quarter, on any machine with the venv:

```bash
mkdir -p /tmp/restore-drill && tar xzf /backup/06_chroma_<latest>.tar.gz -C /tmp/restore-drill
/opt/csi-bid-intelligence/.venv/bin/python - <<'PY'
import sqlite3
c = sqlite3.connect("/tmp/restore-drill/06_chroma/chroma.sqlite3")
print("embeddings:", c.execute("select count(*) from embeddings").fetchone()[0])
PY
rm -rf /tmp/restore-drill
```

**Working looks like:** the recorded count. Five minutes, no downtime, and it converts "we have
backups" from a claim into an observation.

### B5. What Shane needs to know, in four lines

1. The vector store is one directory, ~1.6 GB, at `/var/lib/csi-bid-intelligence/06_chroma`.
2. It is not in git and cannot be restored by redeploying. Back it up with the server.
3. If it is lost, the app still starts and still processes PDFs — it just stops answering questions
   about *other* plans. It can be rebuilt from the plan PDFs (Box) in a few hours, at no cash cost.
4. Never run `git clean -x` in the app directory. It is gitignored; that command deletes it silently.

---

## Part C — Optional: the 10-day team bridge (disposable, delete on Aug 17)

Only build this if the team demonstrably cannot do Aug 12 demo prep with local copies.
**Cheapest correct answer first:** hand each teammate the tarball from A3. One transfer, $0, no
account, no auth, done in 20 minutes. Try that before standing up infrastructure that has to be
torn down in nine days.

If a live shared endpoint is genuinely needed, here is the shape — **written so that removal on
Aug 17 is deleting an environment variable, not reverting a commit.**

### C1. The code change — env-gated, two call sites

`pipelines/plan_reader/01_pipeline/lib.py`, inside `get_collection()`, replacing line 205:

```python
    import os
    host = os.environ.get("CHROMA_HOST")
    if host:
        client = chromadb.HttpClient(
            host=host,
            port=int(os.environ.get("CHROMA_PORT", "443")),
            ssl=os.environ.get("CHROMA_SSL", "1") == "1",
            headers={"x-chroma-token": os.environ["CHROMA_TOKEN"]},
        )
    else:
        client = chromadb.PersistentClient(path=str(CHROMA_DIR))
```

Everything below that line — the `SentenceTransformerEmbeddingFunction`, the
`get_or_create_collection(name=COLLECTION, embedding_function=ef, metadata={"hnsw:space": "cosine"})`
— **stays byte-for-byte identical.** So do `retriever.py`'s `where` filters,
`s4_extract_rag`'s `{"doc_id": …}` scoping, `s2_indexer.py:183`'s `upsert`, and
`plan_reader_bridge.py:51`'s paginated `get`. That is the whole appeal of a Chroma-to-Chroma move.

**Second call site, easy to miss:** `pipelines/plan_reader/01_pipeline/s2_indexer.py:228-229`
constructs its own `PersistentClient` for the `--reset` branch. It needs the same treatment or
`--reset` will drop the *local* collection while the app reads the *remote* one — a silent no-op
that looks like it worked.

Env vars go in the **root `.env`** (`/Users/t/dev/csi/csi-bid-intelligence/.env`, the canonical file
per `.env.example`), added alongside `ANTHROPIC_API_KEY` and `SUPABASE_TEAM_DB_URL`:

```
CHROMA_HOST='chroma-production-xxxx.up.railway.app'
CHROMA_PORT='443'
CHROMA_SSL='1'
CHROMA_TOKEN='<a long random string you generate>'
```

Caveat: `lib.py` itself reads only `ENV_PATH = MODULE_ROOT / ".env"` (`lib.py:53`) for the Anthropic
key and otherwise uses `os.environ` — so for CLI scripts you must
`set -a; source .env; set +a` first, exactly as `.env.example` documents.

**Rollback is: delete the four lines from `.env`.** No code revert, no redeploy. That is the design
requirement — on Aug 17 the handoff server simply never sets `CHROMA_HOST` and is on the local path
by construction.

### C2. Verify the embedding still runs locally (invariant 3)

Before trusting the bridge, confirm that the client — not the server — computes the vectors, because
CLAUDE.md invariant 3 says embeddings are local. With `chromadb` 1.5.9 this is expected but
**UNVERIFIED**; Chroma 1.x also persists an embedding-function config server-side.

Cheapest proof: on a machine with `CHROMA_HOST` set, temporarily rename the HuggingFace cache
(`mv ~/.cache/huggingface ~/.cache/huggingface.off`) and run a query with no network access to
huggingface.co.

**Working looks like:** it **fails**, trying to fetch the model. That failure is the proof that the
model is being loaded and run client-side. If it *succeeds*, the server is embedding for you and the
invariant is broken — stop and reconsider. Restore the cache afterwards.

### C3. Deploy, with the persistence proof that actually proves something

Deploy `chromadb/chroma` **pinned to a tag matching 1.5.9**, not `:latest` (a newer server may
migrate our SQLite schema irreversibly). Set the auth env vars — **the image is unauthenticated by
default**, and on a public hostname that is the entire CSI plan corpus readable by anyone who finds
the URL.

**Mount a volume at the container's data path.** Then, before putting any real data in it:

1. Write a marker: create a tiny collection, note the count.
2. **Force a redeploy** (push a trivial change, or hit "Redeploy" in the console).
3. Read the count back.

**Working looks like:** the marker collection is still there with the same count after the redeploy.

**Not working looks like:** the service is green, the URL responds, and the collection is gone. That
is the exact failure the owner said would not be accepted, and it is invisible from the deploy log —
a healthy container with an empty store returns HTTP 200 for everything. **Prove it with a count
before and after a redeploy. A green deployment is a transport fact; a surviving collection is the
application fact.** Do this with the marker collection *before* spending an hour uploading 1.6 GB.

Then seed the real data — `chroma copy --from-local collections csi_plans --to <host>` re-sends all
75,080 documents (the client re-embeds; budget CPU time on the laptop), or push a tarball into the
volume if the platform allows direct file access (Fly's `fly sftp` does; Railway does not).

**Working looks like:** `col.count() == 75080` against the remote host, then **redeploy once more**
and confirm it is still 75080. Two proofs, not one.

### C4. Tear-down on Aug 17

1. Confirm the app server passes Part A's A4 acceptance test (`count: 75080` locally).
2. Remove `CHROMA_HOST` / `CHROMA_PORT` / `CHROMA_SSL` / `CHROMA_TOKEN` from every `.env`.
3. Re-run A4. **Working looks like:** still `count: 75080`, now served from the local directory.
4. Delete the hosted service and its volume. Cancel the plan.
5. Confirm the bill stops. Check the vendor console at the start of September — an orphaned $5/mo
   service that nobody at CSI knows about is precisely the handoff debt this whole memo is arranged
   to avoid.

The env-gate code from C1 can stay in `lib.py` permanently. It is inert with no `CHROMA_HOST` set,
and it leaves the door open for whoever revisits #22 later.
