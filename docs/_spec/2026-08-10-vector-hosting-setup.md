# Vector store — setup walkthrough

**Written 2026-08-10 · supersedes `docs/_spec/vector_hosting_setup.md`**
**Decision this implements:** [`2026-08-10-vector-hosting-decision.md`](2026-08-10-vector-hosting-decision.md)

Follow this top to bottom. Every step ends with **"Working looks like"** — a concrete observation —
and **"If it doesn't"** — what to do. **If the observation does not match, stop at that step.** Do
not continue and discover it three steps later.

That shape exists because of one rule this project keeps relearning: *a success signal at the wrong
layer is not evidence.* A green Railway deploy is a transport fact. A collection containing 76,540
chunks is the application fact. Only the second one counts.

| Part | What | When | Who |
|---|---|---|---|
| **A** | The 10-day Railway bridge — deploy, secure, seed, verify | **before Wed Aug 12** | Tobias |
| **B** | Tear-down | **Mon Aug 17** | Tobias |
| **C** | The handoff install — local `PersistentClient` on CSI's server | Mon Aug 17 | Tobias → Shane |
| **D** | Backup and restore | from Aug 17, forever | Shane |

Throughout, `$REPO` = `/Users/t/dev/csi/csi-bid-intelligence` on the laptop.

**Everything measured in this document was measured on 2026-08-10** against the real store and the
real `chromadb/chroma:1.5.9` image. Where a number is an estimate it says so and shows the
arithmetic.

---

# PART A — The Railway bridge

**Time budget: 90 minutes.** ~20 min of that is the upload; the rest is clicks and proofs.
**Cost: ~$5** (Hobby plan fee; measured usage sits inside the included credit).

## A0. Preflight — measure the store NOW (3 min)

**Do not trust any count written in any document, including this one.** The store grows every time
a plan is dropped through the web path. It was 75,080 chunks on Aug 8 and 76,540 on Aug 10.

```bash
cd /Users/t/dev/csi/csi-bid-intelligence
du -sh pipelines/plan_reader/06_chroma
ls -la pipelines/plan_reader/06_chroma
.venv/bin/python -c "
import sqlite3
c = sqlite3.connect('pipelines/plan_reader/06_chroma/chroma.sqlite3')
print('embeddings:', c.execute('select count(*) from embeddings').fetchone()[0])
print('doc_ids:', c.execute(\"select count(distinct string_value) from embedding_metadata where key='doc_id'\").fetchone()[0])
print('collections:', c.execute('select name from collections').fetchall())
"
.venv/bin/python -c "import chromadb; print('client version', chromadb.__version__)"
```

**Working looks like** (2026-08-10 values — yours may be higher):

```
1.6G    pipelines/plan_reader/06_chroma
  … chroma.sqlite3 (1,565,155,328 bytes) + six UUID-named directories …
embeddings: 76540
doc_ids: 213
collections: [('csi_plans',)]
client version 1.5.9
```

> ### ✏️ Write your three numbers here before continuing. They are the acceptance test for everything below.
> ```
> N_CHUNKS = ______    N_DOC_IDS = ______    CLIENT_VERSION = ______
> ```

**If it doesn't:**

| What you see | Meaning | Do this |
|---|---|---|
| `chroma.sqlite3` present, **no UUID directories** | you have metadata without HNSW indexes | stop — retrieval will be empty; find a complete copy |
| `client version` is not `1.5.9` | the image tag below must match your client's on-disk format | stop; either `pip install chromadb==1.5.9` or change every `1.5.9` below to your version |
| `collections` is empty or not `csi_plans` | wrong directory | check you are in `$REPO` |

## A1. Build the tarball (1 min)

```bash
cd /Users/t/dev/csi/csi-bid-intelligence/pipelines/plan_reader
COPYFILE_DISABLE=1 tar czf /tmp/06_chroma_2026-08-10.tar.gz -C 06_chroma .
ls -l /tmp/06_chroma_2026-08-10.tar.gz
shasum -a 256 /tmp/06_chroma_2026-08-10.tar.gz | tee /tmp/06_chroma_2026-08-10.sha256
```

Note `-C 06_chroma .` — the tarball contains `./chroma.sqlite3` and the UUID dirs **at its root**,
not nested under a `06_chroma/` folder. That is deliberate: it extracts straight into `/data`.

**Working looks like:** about **581 MB** (608,924,336 bytes on 2026-08-10) after roughly **23
seconds**. Compression is ~2.8×.

**If it doesn't:**
- **Tarball is a few MB** → you tarred an empty directory. Check `pwd` and re-run A0.
- **Tarball is ~1.6 GB** → `z` was omitted. Re-run with `czf`.
- `COPYFILE_DISABLE=1` suppresses macOS `._` resource forks. Without it you will see
  `tar: Ignoring unknown extended header keyword 'LIBARCHIVE.xattr.com.apple.provenance'` on
  extraction — **harmless**, but it clutters the output you need to read.

**Optional, saves ~150 MB of upload:** `chroma vacuum` shrinks the tarball to ~431 MB (it reclaims
only 1% of raw bytes but 26% of the *compressed* size). **Run it on a copy, never on the original:**

```bash
cp -R 06_chroma /tmp/06_chroma_vacuumed
/Users/t/dev/csi/csi-bid-intelligence/.venv/bin/chroma vacuum --path /tmp/06_chroma_vacuumed --force
COPYFILE_DISABLE=1 tar czf /tmp/06_chroma_2026-08-10.tar.gz -C /tmp/06_chroma_vacuumed .
```

Skip this if you are in a hurry. It takes 30 s and saves ~2 min of upload at 10 Mbps.

## A2. Create the Railway project and deploy the image (10 min)

**Console clicks, exactly:**

1. <https://railway.com/new> → **"Empty project"**.
2. Rename it (top-left of the canvas): **`csi-chroma-bridge`**. Naming it "bridge" is not cosmetic —
   it is what stops someone finding it in October and assuming it is production.
3. On the canvas press **`Cmd/Ctrl + K`** → **"Deploy a Docker image"** (equivalently: **`+ Create`**
   → **`Docker Image`**).
4. Image: **`chromadb/chroma:1.5.9`**. **Type the tag.** Do not use `:latest` — a newer server may
   migrate our SQLite schema irreversibly, and that migration has no undo.
5. Rename the service to **`chroma`** (service → **Settings** → **Name**). The name becomes the
   private hostname `chroma.railway.internal`, which A5 depends on.
6. **Do NOT generate a public domain.** If you already did: service → **Settings** → **Networking** →
   remove it. Chroma has no authentication (see the decision doc §4.1); a public domain here is the
   corpus on the open internet.
7. Service → **Variables** → **`+ New Variable`**, add exactly one:

   ```
   CHROMA_LISTEN_ADDRESS = ::
   ```

   Railway's private network is IPv6-only, and Chroma's default bind does not accept IPv6. Without
   this the Caddy proxy in A5 cannot reach it. *(Verified: this env var is honored — setting it to
   `127.0.0.1` makes the server unreachable, which is the negative control that proves the variable
   is not being silently ignored.)*
8. Ensure you are on the **Hobby** plan. Free/Trial caps volumes at **0.5 GB** and the store is
   1.72 GB — it will not fit. Hobby is 5 GB.

Then link the CLI:

```bash
railway login
cd /Users/t/dev/csi/csi-bid-intelligence
railway link          # pick: csi-chroma-bridge  → production → chroma
railway status
```

**Working looks like:** `railway status` names the project `csi-chroma-bridge`, environment
`production`, service `chroma`; the deployment goes green in the console within ~60 s.

**If it doesn't:**
- **Deploy crash-loops** → **Deployments** → click the deploy → **View logs**. A healthy start prints
  the Chroma ASCII banner and `No telemetry is configured.`
- **`railway link` shows no project** → wrong account; `railway whoami`.

## A3. Attach the volume and PROVE it persists — before uploading 1.6 GB (10 min)

**This is the step people skip and it is the one that silently destroys the work.** A Chroma
container with no volume mounted starts fine, answers fine, returns HTTP 200 — and is empty.

1. Select the `chroma` service → **`Cmd/Ctrl + K`** → **"Add volume"** (or right-click canvas →
   **`+ Create`** → **`Volume`** and attach it to `chroma`).
2. **Mount path: `/data`** — exactly. This is the image's own `persist_path`, read from the
   `/config.yaml` it ships. Any other path and Chroma writes to the ephemeral filesystem.
3. Name it `chroma-data`. Confirm the size shows **5 GB**.
4. Wait for the automatic redeploy to finish.

Now prove it, with a marker, **before** spending 20 minutes on an upload:

```bash
# 1. write a marker file into the volume
echo "marker-$(date +%s)" > /tmp/marker.txt
railway volume files upload /tmp/marker.txt /marker.txt
railway volume files list /

# 2. force a redeploy
railway redeploy --yes

# 3. read it back
railway volume files list /
railway volume files download /marker.txt /tmp/marker-back.txt && cat /tmp/marker-back.txt
```

**Working looks like:** `marker.txt` is listed both times, and the downloaded contents match what you
wrote. **That, and only that, is proof the volume is mounted and persistent.**

**If it doesn't:**
- **`marker.txt` missing after redeploy** → the volume is not actually attached, or is mounted
  somewhere other than `/data`. Fix it here. **Do not continue.** Every hour spent past this point
  with an unmounted volume is an hour thrown away.
- **`railway volume files` errors with "no volume"** → the CLI is linked to the wrong service; re-run
  `railway service` and pick `chroma`.
- Remember from Railway's docs: *"Volumes are mounted to your service's container when it is
  started, not during build time"* and *"Each service can only have a single volume."*

Clean up the marker: `railway volume files delete /marker.txt`

## A4. Turn on backups and take a manual one (3 min)

Railway **does** have scheduled volume backups — Daily (kept 6 days), Weekly (kept 1 month), Monthly
(kept 3 months), incremental and copy-on-write, billed at the volume rate of $0.15/GB/month. **No
Railway document states whether any schedule is on by default**, and one Railway guide instructs you
to "Enable backups", so treat them as opt-in and click it:

1. Select the `chroma` service → **Settings** → **Backups** tab.
2. Enable the **Daily** schedule.
3. Click **Create backup** for a manual one once A6 has finished loading the data.

**Working looks like:** the Backups tab lists a Daily schedule as enabled, and after A6 a manual
backup appears with a non-trivial size.

**If it doesn't:** it is annoying but not fatal — **the laptop's `06_chroma/` remains the
authoritative copy for the whole 10 days.** The Railway volume is a convenience replica. If Railway
loses it, you re-run A5–A6. Nothing unique lives there unless the team ingests new plans through the
bridge, and if they do, see B1.

Two constraints from Railway's docs worth knowing now: *manual backups are limited to 50% of the
volume's total size*, and *wiping a volume deletes all backups*.

## A5. Put an authenticating proxy in front (20 min) — NOT OPTIONAL

> **Self-hosted Chroma 1.x has no authentication of any kind.** Not a setting, not a flag, not an
> env var — the OSS build hardcodes a no-op authenticator. The 0.x `CHROMA_SERVER_AUTHN_*` env-var
> recipe you will find in blogs, cookbooks, and AI answers is **empirically confirmed to do
> nothing** on this image. See decision doc §4.1.

The fix is a second Railway service: **Caddy with basic auth**, holding the only public domain,
forwarding to `chroma.railway.internal` over the private network.

**1. Generate the password hash locally:**

```bash
docker run --rm caddy:2 caddy hash-password --plaintext 'CHOOSE-A-REAL-PASSWORD-HERE'
```

**Working looks like:** one line starting `$2a$14$…`. Copy it.

**2. Create the proxy service:**

- Canvas → **`Cmd/Ctrl + K`** → **"Deploy a Docker image"** → **`caddy:2`**.
- Rename the service to **`proxy`**.
- **Settings → Networking → Generate Domain**, target port **`8000`**. Copy the hostname; it looks
  like `proxy-production-xxxx.up.railway.app`.
- **Variables**, add:

  | Name | Value |
  |---|---|
  | `CADDY_USER` | `csi` |
  | `CADDY_HASH` | the `$2a$14$…` string from step 1 |
  | `CHROMA_UPSTREAM` | `chroma.railway.internal:8000` |

- **Settings → Deploy → Custom Start Command:**

  ```
  sh -c 'printf "{\n  auto_https off\n}\n:8000 {\n  basic_auth {\n    %s %s\n  }\n  reverse_proxy %s\n}\n" "$CADDY_USER" "$CADDY_HASH" "$CHROMA_UPSTREAM" > /etc/caddy/Caddyfile && caddy run --config /etc/caddy/Caddyfile --adapter caddyfile'
  ```

**3. Prove all three cases.** Testing only the success case is how an open service ships:

```bash
HOST=proxy-production-xxxx.up.railway.app     # your domain
echo "no creds:";    curl -s -o /dev/null -w "%{http_code}\n" https://$HOST/api/v2/heartbeat
echo "wrong creds:"; curl -s -o /dev/null -w "%{http_code}\n" -u csi:wrong https://$HOST/api/v2/heartbeat
echo "right creds:"; curl -s -o /dev/null -w "%{http_code}\n" -u csi:YOUR-PASSWORD https://$HOST/api/v2/heartbeat
```

**Working looks like — all three lines, in this order:**

```
no creds:    401
wrong creds: 401
right creds: 200
```

*(This exact sequence was verified locally against `chromadb/chroma:1.5.9` behind `caddy:2` on
2026-08-10.)*

**If it doesn't:**

| What you see | Meaning | Do this |
|---|---|---|
| `no creds: 200` | **STOP.** The corpus is public. | The proxy is not in the path — check that only `proxy` has a public domain and `chroma` has none |
| `right creds: 502` | Caddy cannot reach Chroma | you missed `CHROMA_LISTEN_ADDRESS = ::` in A2.7; add it and redeploy `chroma` |
| `right creds: 502` and the var is set | wrong hostname | it is the *service name* — `railway status` must show the service named `chroma` |
| all three `000`/timeout | no public domain on `proxy` | Settings → Networking → Generate Domain, target port 8000 |

**4. Confirm `chroma` itself is unreachable from outside.** In the console, the `chroma` service's
Networking panel must show **no public domain**. That is the check; there is no URL to curl, and
that is the point.

## A6. Upload the store (5–20 min, bandwidth-bound)

```bash
railway service        # ensure the linked service is: chroma
railway volume files upload /tmp/06_chroma_2026-08-10.tar.gz /06_chroma.tar.gz
railway volume files list /
```

**Working looks like:** the upload completes and `railway volume files list /` shows
`06_chroma.tar.gz` at ~581 MB.

**Estimated wall clock — arithmetic on a measured 581 MB payload, not a measurement:**

| Your upload speed | Transfer |
|---|---|
| 10 Mbps (1.25 MB/s) | 581 ÷ 1.25 = **465 s ≈ 8 min** |
| 20 Mbps (2.5 MB/s) | **232 s ≈ 4 min** |
| 50 Mbps (6.25 MB/s) | **93 s ≈ 1.5 min** |

Check your real uplink first (`networkQuality -v` on macOS) and size your patience off that.

Now extract it in place. Both `tar` and `gzip` are present in the image (verified):

```bash
railway ssh 'tar xzf /data/06_chroma.tar.gz -C /data && rm /data/06_chroma.tar.gz && ls /data'
railway redeploy --yes
```

**Working looks like:** `ls /data` prints `chroma.sqlite3` and six UUID-named directories, and the
tarball is gone. Extraction took **14.8 s** in the local rehearsal.

**If it doesn't:**

| What you see | Meaning | Do this |
|---|---|---|
| `railway ssh` not permitted | SSH not enabled for the service | fall back: `railway volume files upload` the **directory** instead — `railway volume files upload pipelines/plan_reader/06_chroma / --concurrency 32` (uploads the uncompressed 1.72 GB; ~3× longer, no untar needed). Verify with `railway volume files list /` |
| `tar: … No space left` | tarball + extracted exceeds the volume | peak need is 2.3 GB of the 5 GB — if this fires, the volume is not 5 GB. Check the plan |
| `ls /data` shows a nested `06_chroma/` directory | the tarball was built without `-C 06_chroma .` | `railway ssh 'mv /data/06_chroma/* /data/ && rmdir /data/06_chroma'`, or rebuild the tarball per A1 |

## A7. The acceptance test (5 min)

This is the only step whose output is allowed to end Part A.

```bash
cd /Users/t/dev/csi/csi-bid-intelligence
HOST=proxy-production-xxxx.up.railway.app
.venv/bin/python - <<PY
import base64, chromadb
from chromadb.utils import embedding_functions
auth = base64.b64encode(b"csi:YOUR-PASSWORD").decode()
c = chromadb.HttpClient(host="$HOST", port=443, ssl=True,
                        headers={"Authorization": "Basic " + auth})
ef = embedding_functions.SentenceTransformerEmbeddingFunction(model_name="all-MiniLM-L6-v2")
col = c.get_collection("csi_plans", embedding_function=ef)
print("count:", col.count())
r = col.query(query_texts=["bituminous pavement milling quantity"], n_results=3)
for d, m in zip(r["documents"][0], r["metadatas"][0]):
    print("-", m.get("doc_id"), "p." + str(m.get("page")), "|", d[:60].replace("\n", " "))
PY
```

**Working looks like:** `count:` equal to **your A0 `N_CHUNKS`**, then three real plan excerpts with
real `doc_id`s. The local rehearsal produced:

```
count: 76540
- 2023_MARTIN-CO-MN_8436697_NOBID p.190 | **SECTION 32 01 16.13 - ASPHALT PAVEMENT MILLING** …
- 2025_MURRAY-CO-MN_CSAH-2_NOBID p.289 | SECTION 32 01 16 BITUMINOUS MILL & RECLAMATION …
```

**Then redeploy once more and run it again.** Two proofs, not one — the first proves the data
loaded, the second proves it survives a deploy.

```bash
railway redeploy --yes && sleep 45   # then re-run the block above
```

**If it doesn't:**

| What you see | Meaning | Do this |
|---|---|---|
| `count: 0`, or `csi_plans` does not exist | volume not mounted, or files landed outside `/data` | `railway ssh 'ls -la /data'` — if it is empty, A3's proof was skipped or lied. Redo A3, then A6 |
| a count **other than** your A0 number | truncated upload | delete `/data` contents, re-upload, re-verify. Do **not** accept "it returned a number" |
| count is right, `query` errors or returns nothing | the HNSW segment dirs did not come across, or MiniLM is not cached locally | `railway ssh 'ls /data'` must show six UUID dirs; locally run `.venv/bin/python -c "from sentence_transformers import SentenceTransformer; SentenceTransformer('all-MiniLM-L6-v2')"` |
| `401` from Python | header wrong | it is `headers={"Authorization": "Basic <base64 of user:pass>"}` — not `x-chroma-token`, which this server ignores entirely |

**Take the manual Railway backup now** (A4, step 3).

## A8. The code change — two call sites, env-gated (15 min)

The gate is the requirement: **on Aug 17 the bridge disappears by deleting environment variables,
not by reverting a commit.**

`pipelines/plan_reader/01_pipeline/lib.py`, inside `get_collection()`, replacing line 205
(`client = chromadb.PersistentClient(path=str(CHROMA_DIR))`):

```python
    import os
    host = os.environ.get("CHROMA_HOST")
    if host:
        headers = {}
        if os.environ.get("CHROMA_BASIC_AUTH"):          # "user:password"
            import base64
            headers["Authorization"] = "Basic " + base64.b64encode(
                os.environ["CHROMA_BASIC_AUTH"].encode()).decode()
        client = chromadb.HttpClient(
            host=host,
            port=int(os.environ.get("CHROMA_PORT", "443")),
            ssl=os.environ.get("CHROMA_SSL", "1") == "1",
            headers=headers,
        )
    else:
        client = chromadb.PersistentClient(path=str(CHROMA_DIR))
```

Everything below that line stays **byte-for-byte identical** — the
`SentenceTransformerEmbeddingFunction`, the `get_or_create_collection(name=COLLECTION,
embedding_function=ef, metadata={"hnsw:space": "cosine"})`. That binding is what keeps ingest and
query on the same model, and it is why this is a two-line change and not a rewrite. So do
`retriever.py`'s `where` filters, `s2_indexer.py:183`'s `upsert`, `s4_extract_rag`'s `{"doc_id": …}`
scoping, and `plan_reader_bridge.py:51`'s paginated `get`.

**Second call site, easy to miss:** `pipelines/plan_reader/01_pipeline/s2_indexer.py:229` builds its
own `PersistentClient` for the `--reset` branch. Give it the same treatment, or `--reset` drops the
**local** collection while the app reads the **remote** one — a silent no-op that looks like success.

Env vars go in the root `.env` (`$REPO/.env`), beside `ANTHROPIC_API_KEY` and
`SUPABASE_TEAM_DB_URL`:

```
CHROMA_HOST='proxy-production-xxxx.up.railway.app'
CHROMA_PORT='443'
CHROMA_SSL='1'
CHROMA_BASIC_AUTH='csi:YOUR-PASSWORD'
```

`lib.py:53` only reads `MODULE_ROOT / ".env"` for the Anthropic key and otherwise uses `os.environ`,
so for CLI scripts run `set -a; source .env; set +a` first, exactly as `.env.example` documents.

**Working looks like:**

```bash
cd /Users/t/dev/csi/csi-bid-intelligence
set -a; source .env; set +a
.venv/bin/python -c "
import sys,pathlib; sys.path.insert(0,str(pathlib.Path('pipelines/plan_reader/01_pipeline').resolve()))
import lib; print('remote count:', lib.get_collection().count())"

unset CHROMA_HOST
.venv/bin/python -c "
import sys,pathlib; sys.path.insert(0,str(pathlib.Path('pipelines/plan_reader/01_pipeline').resolve()))
import lib; print('local count:', lib.get_collection().count())"
```

Both print your A0 number — the first from Railway, the second from the local directory. **That the
same code produces both is the rollback proof.**

**If it doesn't:** `remote count: 0` with no error means `CHROMA_HOST` was not exported — check
`set -a; source .env; set +a` ran in *this* shell.

## A9. Onboard the team (5 min)

Send each teammate the four `.env` lines and this one-liner:

```bash
cd <their repo>; set -a; source .env; set +a
.venv/bin/python -c "
import sys,pathlib; sys.path.insert(0,str(pathlib.Path('pipelines/plan_reader/01_pipeline').resolve()))
import lib; print(lib.get_collection().count())"
```

**Working looks like:** they print your A0 number. **If it doesn't**, they get `0` or a `ValueError` —
check the password and that they exported the vars.

Tell them two things explicitly:

1. **Their first query downloads the ~80 MB MiniLM model** to their HuggingFace cache. The embedding
   still runs on *their* machine — the server holds only vectors and never sees a model. If they are
   offline it will fail, and that failure is the proof the invariant holds.
2. **The bridge is deleted Aug 17.** Anything they ingest into it that matters must be reported, so
   B1 can pull the volume back down.

## A10. Acceptance checklist for Part A

Do not call this done until every line is a **yes you personally observed**.

- [ ] `railway volume files list /` shows `chroma.sqlite3` and six UUID directories
- [ ] `count:` through the proxy equals A0's `N_CHUNKS`
- [ ] a query returns real plan text with real `doc_id`s
- [ ] the count still matches **after** a forced `railway redeploy`
- [ ] `curl` with **no** credentials returns **401**
- [ ] `curl` with **wrong** credentials returns **401**
- [ ] the `chroma` service has **no** public domain
- [ ] the Backups tab shows a Daily schedule enabled and one manual backup
- [ ] with `CHROMA_HOST` unset, the same code reads the local store and prints the same count
- [ ] at least one teammate has run A9 successfully

---

# PART B — Tear-down, Mon Aug 17

**Do this on the day, not "soon".** An orphaned $5/mo service nobody at CSI remembers owning is
exactly the handoff debt this whole exercise exists to avoid.

## B1. Rescue anything the team added (10 min)

If anyone ingested plans through the bridge, the Railway volume holds chunks the laptop does not.
The formats are identical — verified: a record written through the hosted server was read back by
`PersistentClient` from the same directory, count and document intact.

```bash
railway ssh 'cd /data && tar czf /data/pullback.tar.gz --exclude pullback.tar.gz .'
railway volume files download /pullback.tar.gz /tmp/pullback.tar.gz
mkdir -p /tmp/pullback && tar xzf /tmp/pullback.tar.gz -C /tmp/pullback
.venv/bin/python -c "
import sqlite3; c=sqlite3.connect('/tmp/pullback/chroma.sqlite3')
print('remote embeddings:', c.execute('select count(*) from embeddings').fetchone()[0])"
```

**Working looks like:** a count **≥** your A0 number. If it is **greater**, the remote is now
authoritative — back up the laptop's copy and replace it:

```bash
mv pipelines/plan_reader/06_chroma pipelines/plan_reader/06_chroma.pre-pullback
mv /tmp/pullback pipelines/plan_reader/06_chroma
```
then re-run A0 and confirm the higher count. Keep `.pre-pullback` until Part C passes.

If it **equals** your A0 number, nothing was added; skip ahead.

## B2. Return to local and prove it (5 min)

```bash
# remove the four CHROMA_* lines from $REPO/.env
.venv/bin/python -c "
import sys,pathlib; sys.path.insert(0,str(pathlib.Path('pipelines/plan_reader/01_pipeline').resolve()))
import lib; print('local count:', lib.get_collection().count())"
```

**Working looks like:** the correct count, served from the local directory, with **no code change**.
**If it doesn't**, do not delete anything on Railway yet.

## B3. Delete (5 min)

1. Railway console → `proxy` service → **Settings** → **Delete Service**.
2. `chroma` service → **Settings** → **Delete Service**.
3. Volume → **Delete Volume**. (Reminder from Railway's docs: *"Wiping a volume deletes all
   backups."* That is intended here.)
4. Project → **Settings** → **Delete Project**.
5. Account → **Usage** — cancel Hobby if this project was the only reason for it.
6. Tell teammates to delete the four `CHROMA_*` lines from their `.env`.

## B4. Confirm the bill stops

**Put a calendar reminder for Sept 1**: open the Railway console and confirm no active services and
a $0 projected invoice. A deletion you did not verify is a claim, not an observation.

The env-gate code from A8 can stay in `lib.py` permanently. With no `CHROMA_HOST` set it is inert,
and it leaves the door open for whoever revisits #22 later.

---

# PART C — The handoff install (CSI's app server, Aug 17)

This is the destination and it has not changed: **local `PersistentClient`, zero code change, $0/mo,
no vendor, no account, no card, and CSI's plan corpus never leaves CSI.**

`$SERVER_REPO` = e.g. `/opt/csi-bid-intelligence`.

## C1. Repo and venv

```bash
git clone <repo-url> /opt/csi-bid-intelligence
cd /opt/csi-bid-intelligence
python3 -m venv .venv
./.venv/bin/pip install -r apps/api/requirements.txt
./.venv/bin/pip install -r pipelines/plan_reader/requirements.txt
./.venv/bin/python -c "import chromadb, sentence_transformers, torch; print(chromadb.__version__, torch.__version__)"
```

**Working looks like:** two version numbers, no traceback, and `chromadb` reads **1.5.9** — matching
what wrote the store.

**If it doesn't:** `pip install` dying on `torch` is a known environment issue unrelated to the
vector store (CLAUDE.md rough edge 7 records the same failure on a Windows sandbox). Resolve it
before continuing; nothing below works without `sentence-transformers`. Expect the install to be
**several GB** — `torch` alone dwarfs the 1.7 GB store, so if disk is tight, the vector store is not
your problem.

## C2. Pre-cache the embedding model — while you still have internet

```bash
./.venv/bin/python -c "
from sentence_transformers import SentenceTransformer
SentenceTransformer('all-MiniLM-L6-v2'); print('model cached')"
```

**Working looks like:** `model cached`, and **re-running it prints instantly with no download bars**
— that second run is the proof it is cached, not merely that it worked once. If the server is
firewalled, this must happen now or the first query fails.

## C3. Put the store somewhere a deploy cannot reach

> ### The single most likely way this store dies: `06_chroma/` is gitignored, so `git clean -xdf` — a command deploy scripts genuinely contain — **deletes the entire vector store with no error message.** The app then comes back up, returns HTTP 200, and answers every question with nothing.

So do not keep it inside the repo:

```bash
sudo mkdir -p /var/lib/csi-bid-intelligence
scp /tmp/06_chroma_2026-08-10.tar.gz /tmp/06_chroma_2026-08-10.sha256 user@csi-app-server:/tmp/
# on the server:
cd /tmp && shasum -a 256 -c 06_chroma_2026-08-10.sha256
sudo mkdir -p /var/lib/csi-bid-intelligence/06_chroma
sudo tar xzf /tmp/06_chroma_2026-08-10.tar.gz -C /var/lib/csi-bid-intelligence/06_chroma
ln -s /var/lib/csi-bid-intelligence/06_chroma \
      /opt/csi-bid-intelligence/pipelines/plan_reader/06_chroma
sudo chown -R csi-app:csi-app /var/lib/csi-bid-intelligence/06_chroma
sudo chmod -R o-rwx /var/lib/csi-bid-intelligence/06_chroma
du -sh /var/lib/csi-bid-intelligence/06_chroma
```

**Working looks like:** `06_chroma_2026-08-10.tar.gz: OK` from the checksum, then **1.6G**. If a USB
drive is faster than the LAN, same tarball, same checksum, carry it over.

**If it doesn't:** **a checksum mismatch means stop and re-transfer.** A truncated SQLite file opens
fine and returns a lower count — precisely the quiet wrongness this document is arranged to catch.

`lib.py:52` defines `CHROMA_DIR = MODULE_ROOT / "06_chroma"` and follows the symlink transparently.
**The directory being in the right place is the entire configuration.**

## C4. The acceptance test

```bash
cd /opt/csi-bid-intelligence
sudo -u csi-app ./.venv/bin/python - <<'PY'
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

**Working looks like:** `collection: csi_plans`, `count:` your A0 number, three real excerpts —
**run as the service account**, not as root.

**If it doesn't:**

| What you see | Meaning | Do this |
|---|---|---|
| `count: 0` | Chroma created a *new empty* collection because it did not find the store | `ls /var/lib/csi-bid-intelligence/06_chroma/chroma.sqlite3` — you likely have a nested `06_chroma/06_chroma/` |
| a different count | truncated transfer or a schema migration | re-verify the checksum and re-extract |
| count right, query empty/errors | HNSW dirs missing, or MiniLM not cached | six UUID dirs must be present; re-run C2 |

**Do not proceed past a count that is not your A0 number. A store that opens and answers is not a
store that is complete.**

## C5. The persistence proof

```bash
cd /opt/csi-bid-intelligence
sudo systemctl restart csi-bid-api     # or kill and restart uvicorn
git pull
git status --porcelain --ignored pipelines/plan_reader/06_chroma | head -3
# re-run C4
```

**Working looks like:** the same count before and after, and the `git status` line shows the path as
ignored (`!!`). Then start the app and confirm the chat `search_plans` path returns cited excerpts:

```bash
cd /opt/csi-bid-intelligence
./.venv/bin/python -c "
import sys; sys.path.insert(0, 'apps/api')
from backend import plan_reader_bridge as b
print(len(b.indexed_plans()), 'plans indexed')"
```

**Working looks like:** your A0 `N_DOC_IDS` (213 on 2026-08-10). That number matching is the proof
the backend and the file agree. The path under test is `plan_reader_bridge.py:30 → :35 →
retriever.retrieve`, the same `lib.get_collection()` C4 proved — so if C4 passed and this fails, the
problem is the app, not the store.

## C6. Rollback

Every step is additive; rollback is deletion.

| If this went wrong | Roll back by |
|---|---|
| Store copied but wrong/corrupt | `rm -rf` the directory, re-extract from the tarball, re-run C4 |
| The symlink broke something | `rm` the symlink, `mv` the directory back into `pipelines/plan_reader/`, re-run C4 |
| Everything is broken and the app must be up now | `rm -rf` the store. **The app still runs** — `docs/DATA_ACCESS.md:184` records that the full PDF-drop → report flow works with an empty `06_chroma/`. You lose cross-plan retrieval, not the product |

**Say that last row out loud in the handoff meeting: the vector store is required for good answers,
not for the app to start.** Nothing here can brick the deployment.

## C7. Rebuilding from source instead of copying

Only if the copy is impossible, or when someone finally fixes #58 and #85.

**Prerequisite that is currently unmet — check it first:**

```bash
find pipelines/plan_reader/00_input/plans -name '*.pdf' | wc -l
```

**Working looks like:** a number near 184. **If it prints `1`, stop — you cannot rebuild.** The
source PDFs (~4.5 GB) are in Box, not on the laptop. A rebuild from 1 PDF produces a 1-PDF store and
gives you no error. Also beware CLAUDE.md's note about **two `00_input` directories** (#88).

With the corpus present:

```bash
P=pipelines/plan_reader
./.venv/bin/python $P/01_pipeline/s1_convert.py $P/00_input/plans
./.venv/bin/python $P/01_pipeline/s2_indexer.py $P/00_input/plans --reset --trace
```

`--reset` drops the collection first (`s2_indexer.py:225-232`), which is what fixes #58's `doc_id`
namespace split. **Cost in dollars: $0** — embeddings are local (CLAUDE.md invariant 3).
**Cost in time: the PDF conversion, not the embedding.** MiniLM measured **149 docs/s** on this
laptop → ~8.5 minutes for 76,540 chunks. The old estimate of "hours for the embedding" was wrong;
the hours are in `s1_convert`.

**Working looks like:** a final count **smaller than** your A0 number — #22's audit expects roughly a
third of the size once 42% duplicates and ~15% noise are gone. **A rebuilt store that still reports
~76,540 means `--reset` did not take.**

A rebuild does not fix #58 permanently — `apps/api/backend/report.py:123` still stamps `doc_id` from
the PDF stem, so the split reopens on the next web upload. That is #58's fix, not this document's.

---

# PART D — Backup and restore (Shane, from Aug 17)

The entire operational burden of the recommended option. Two commands.

## D1. What to back up

One directory: `/var/lib/csi-bid-intelligence/06_chroma`, ~1.7 GB — a SQLite database plus HNSW
index files. **It is not in git** (deliberately: derived data, too large). A `git pull` will not
restore it.

## D2. Backup

**Stop the app first.** SQLite tolerates a live copy better than it used to, but the HNSW segment
files are written outside the SQLite transaction, so a hot copy can be internally inconsistent — the
copy succeeds and the restore is subtly wrong. Take the 60 seconds.

```bash
sudo systemctl stop csi-bid-api
STAMP=$(date +%F)
sudo tar czf /backup/06_chroma_$STAMP.tar.gz -C /var/lib/csi-bid-intelligence 06_chroma
sudo shasum -a 256 /backup/06_chroma_$STAMP.tar.gz | sudo tee /backup/06_chroma_$STAMP.sha256
sudo systemctl start csi-bid-api
```

**Working looks like:** a `.tar.gz` of roughly **580–650 MB** (measured compression 2.8×), a
`.sha256` beside it, and the app back up. **A tarball of a few megabytes means the directory was
empty or the path was wrong.** That is why the expected size is quoted here.

**Record the chunk count in a log next to each tarball.** Without it you have nothing to compare
against, and "it printed a number" becomes the success signal — the mistake this project keeps
making.

Weekly is ample; the store only changes when plans are ingested:

```cron
0 2 * * 0 systemctl stop csi-bid-api && tar czf /backup/06_chroma_$(date +\%F).tar.gz -C /var/lib/csi-bid-intelligence 06_chroma && systemctl start csi-bid-api
```

Keep 4 weeks ≈ 2.5 GB.

**Better than the cron, if CSI already backs up `/var/lib`:** do nothing. That is why C3 put it
there. **Confirm it by restoring a test file, not by reading the policy document.**

## D3. Restore

```bash
sudo systemctl stop csi-bid-api
cd /backup && sudo shasum -a 256 -c 06_chroma_<STAMP>.sha256      # must print: OK
sudo rm -rf /var/lib/csi-bid-intelligence/06_chroma
sudo tar xzf /backup/06_chroma_<STAMP>.tar.gz -C /var/lib/csi-bid-intelligence
sudo chown -R csi-app:csi-app /var/lib/csi-bid-intelligence/06_chroma
# VERIFY BEFORE STARTING THE APP
sudo -u csi-app /opt/csi-bid-intelligence/.venv/bin/python -c "
import sys; sys.path.insert(0, '/opt/csi-bid-intelligence/pipelines/plan_reader/01_pipeline')
import lib; print('count:', lib.get_collection().count())"
sudo systemctl start csi-bid-api
```

**Working looks like:** `OK`, then the count recorded in the backup log for that tarball.

## D4. Quarterly restore drill

A backup that has never been restored is a hypothesis.

```bash
mkdir -p /tmp/restore-drill && tar xzf /backup/06_chroma_<latest>.tar.gz -C /tmp/restore-drill
/opt/csi-bid-intelligence/.venv/bin/python -c "
import sqlite3; c=sqlite3.connect('/tmp/restore-drill/06_chroma/chroma.sqlite3')
print('embeddings:', c.execute('select count(*) from embeddings').fetchone()[0])"
rm -rf /tmp/restore-drill
```

**Working looks like:** the recorded count. Five minutes, no downtime, and it turns "we have backups"
into an observation.

## D5. What Shane needs to know, in five lines

1. The vector store is one directory, ~1.7 GB, at `/var/lib/csi-bid-intelligence/06_chroma`.
2. It is not in git and cannot be restored by redeploying. Back it up with the server.
3. If it is lost the app still starts and still processes PDFs — it stops answering questions about
   *other* plans. It can be rebuilt from the plan PDFs (Box) in a few hours at no cash cost.
4. **Never run `git clean -x` in the app directory.** It is gitignored; that command deletes it
   silently.
5. Nothing about it is hosted, metered, or on anyone's credit card. There is no account to inherit.

---

## Appendix — every fact in this document, and how it was verified (2026-08-10)

| Fact | Method |
|---|---|
| Store: 76,540 embeddings, 213 `doc_id`, `csi_plans`, 1,716,394,506 bytes / 31 files | direct `sqlite3` query + `find … -exec stat` |
| `chromadb` installed = 1.5.9 | `pip show chromadb`, `chromadb.__version__` |
| Client embeds 100% client-side; no server-side embedding wire format exists | installed-source read (`CollectionCommon._embed`, `fastapi.py` `_add`/`_query` signatures) **+** live wire capture against a real server |
| Image entrypoint `dumb-init -- chroma run /config.yaml`; `/config.yaml` = `persist_path: "/data"`; 165 MB, single Rust binary, no Python/torch | `docker image inspect` + `docker cp` of `/config.yaml` |
| Image reads a `PersistentClient` directory as-is: `count: 76540`, query 0.14 s | ran `chromadb/chroma:1.5.9` with a copy of `06_chroma` bind-mounted at `/data` |
| Writes through the server round-trip back to `PersistentClient` | added a probe via HTTP, stopped container, reopened locally: `76541`, probe present |
| Memory: **184.6 MiB** serving all chunks through 10 queries | `docker stats --no-stream` |
| Empty volume = HTTP 200 + `[]` collections (the silent failure) | ran the image on an empty `/data` |
| `tar czf` → 608,924,336 bytes in 23 s (2.82×); after `chroma vacuum`, 452,147,921 bytes | measured |
| `tar xzf` inside the container: 14.8 s; `tar`+`gzip` present | full local dress rehearsal, restored + restarted + verified `count: 76540` |
| Records-level copy: 1,209 rec/s loopback, 10,934 bytes/record on the wire (837 MB total) | measured |
| `chroma copy` cannot target a self-hosted server (`--from-local` ⊥ `--to-local`) | ran the command; read `--help` |
| MiniLM re-embed: 149 docs/s | measured on real corpus documents |
| Chroma 1.x has **no** auth; 0.x env vars silently ignored | empirical (401 never returned) **+** source read at tag 1.5.9 (`Arc::new(())`) **+** official 1.0.0 breaking-change note and maintainer statements in #4288 / #5363 |
| Caddy basic-auth in front works: 401 / 401 / 200, Python client via `Authorization: Basic` reads `count: 76540` | ran `caddy:2` + Chroma on a Docker network and tested all three cases |
| `CHROMA_LISTEN_ADDRESS` is honored | positive test (`::` → reachable) **and negative control** (`127.0.0.1` → unreachable), so "ignored" and "working" cannot look alike |
| Railway: scheduled Daily/Weekly/Monthly volume backups, incremental, $0.15/GB/mo; default state undocumented | WebFetch of docs.railway.com **+** raw-markdown corpus grep of `llms-full.txt` |
| Railway: `railway volume files upload/download/list`, directories supported | docs **+** locally installed CLI 5.31.0 `--help` |
| Railway volume caps: Free/Trial 0.5 GB, Hobby 5 GB, Pro 50 GB default | <https://docs.railway.com/volumes/reference> |
| `lib.py:52,205-211`, `s2_indexer.py:229`, `plan_reader_bridge.py`, `DATA_ACCESS.md` all exist at the cited paths | `git ls-files` + reading the cited lines |

**Not verified, stated as such:** whether a Railway *dashboard* volume file browser exists (only the
CLI TUI is documented — irrelevant, the CLI is the recommended path); whether Railway's scheduled
backups are on by default (resolved operationally in A4 by turning them on); whether Docker Hub's
`chromadb/chroma:1.5.9` is byte-identical to a build of the repo's `rust/Dockerfile` (inferred from
an exact entrypoint and config match — but every behavioural claim above was tested against the
published image itself, not against the source).
