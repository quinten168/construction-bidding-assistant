# Setup Guide — Getting a Fresh Clone Running

For anyone receiving this repo who has not run it before — including someone with **nothing**
installed on their computer yet. Follow these steps in order; each one notes what breaks if you
skip it.

## 0. Install Git (the one thing you need before you can even download this repo)

Everything else in §0 can be installed automatically later (§2a, Windows) — but you need Git first
just to get the repo onto your computer at all.

**Windows**: open PowerShell and run:
```powershell
winget install -e --id Git.Git --accept-source-agreements --accept-package-agreements
```
If that fails with `winget: The term 'winget' is not recognized...`, winget itself isn't available
on this machine (older Windows build, or it's missing the "App Installer" component) — instead,
download and run the installer from [git-scm.com/downloads](https://git-scm.com/downloads),
accepting the default options.

**macOS**: usually already installed. Open Terminal and run `git --version` — if you see a version
number, skip ahead. If not: `brew install git` (install [Homebrew](https://brew.sh) first if you
don't have it — paste the command on that page into Terminal).

After installing, **close and reopen your terminal window** — this is the step people forget, and
the new tool won't be found until you do.

## 1. Get repo access

The repo is **private** (`Tobias-V-Knight/csi-bid-intelligence`). You cannot clone it until
someone with admin access adds your GitHub account as a collaborator (Settings → Collaborators on
GitHub, or ask Tobias directly).

## 2. Clone it

```bash
git clone https://github.com/Tobias-V-Knight/csi-bid-intelligence.git
cd csi-bid-intelligence
```

## 2a. Windows — one script does the rest of §0 and §5/§6 for you (recommended)

Everything below this box (Python, Node.js, the Python virtual environment, backend dependencies,
frontend dependencies, and the two `.env` template files) can be done in one step:

```powershell
powershell -ExecutionPolicy Bypass -File .\scripts\setup-windows.ps1
```

`-ExecutionPolicy Bypass` is required **for this one invocation only** — Windows blocks `.ps1`
scripts from running by default, and this flag says "allow just this one, just this once" without
changing any permanent setting on your machine. You'll see it check each tool, install whatever's
missing via `winget`, set up the Python virtual environment, install both sets of dependencies, and
create `.env` / `apps\web\.env.local` from their templates (it opens `.env` in Notepad for you at
the end — that's your cue to fill in the real secret values, §3 below).

It's safe to run more than once — every step checks first and skips anything already done.

If you'd rather do each piece by hand instead (or you're on macOS, which this script doesn't
cover), continue reading from §0's table below and follow §3 through §6 in order.

**Check what you already have first** — open a terminal (macOS: Terminal.app or iTerm; Windows:
PowerShell) and run:

```bash
python3 --version
node --version
npm --version
```

If both print a version number, skip to §3. Anything that says "command not found" needs
installing — **Windows first**, since that's what most of you are on:

| Tool | Version needed | Windows | macOS |
| --- | --- | --- | --- |
| **Python** | 3.9 or newer | `winget install -e --id Python.Python.3.12` — or download from [python.org/downloads](https://www.python.org/downloads/) and **check the box "Add python.exe to PATH"** during install, this is the step people miss | `brew install python3` |
| **Node.js** (this also installs `npm` — no separate install) | 18 or newer | `winget install -e --id OpenJS.NodeJS.LTS` — or download the **LTS** installer from [nodejs.org](https://nodejs.org) | `brew install node` |
| **A text editor** | — | [VS Code](https://code.visualstudio.com) (free) — recommended: it shows hidden files like `.env` by default, unlike Windows Explorer/Finder | Same — VS Code |

After installing anything from this table by hand, **close and reopen your terminal window** (the
new tool won't be found until you do), then re-run the `--version` commands above to confirm.

> **If a `--version` command still fails after installing and reopening the terminal**: the tool was
> installed but your terminal doesn't know where to find it (a "PATH" problem). This is the single
> most common setup snag and is worth asking a technical contact for five minutes of help with,
> rather than debugging alone.

## 3. Set up secrets (`.env` files)

If you ran the Windows script in §2a, both files below already exist — this section is about
**what to type into them**, not creating them.

Two `.env` files, three keys total. See `docs/DATA_ACCESS.md` / `docs/DATA_ACCESS_SCRATCH.md` for
more detail than this summary if needed.

> **`.env` files are "hidden files" — this is expected, not an error.** Any file whose name starts
> with a `.` is hidden by default in macOS Finder / Windows Explorer, so after running the `cp`
> command below, don't expect to *see* the new file in a normal file browser window. To confirm it
> was actually created, either run `ls -la .env` in the terminal (it should print a file size and
> date, not "No such file or directory"), or open the folder in VS Code, which shows these files by
> default.

### 3a. Repo root — `.env` (required)

Already created for you if you ran the §2a script. Otherwise:

```bash
cp .env.example .env
```

Fill in:

| Key | Required? | What it's for | Where to get it |
| --- | --- | --- | --- |
| `ANTHROPIC_API_KEY` | **Required** | Powers the chat agent and both PDF extraction passes. Nothing that touches an LLM works without it. | Anthropic Console |
| `SUPABASE_TEAM_DB_URL` | **Required** | Postgres DSN for the `csi_team` login (Supabase `scratch` schema) — read/write for the bid-results/pit-list/competitor-registry admin pages and the live competitor-prediction path. Without it the competitor cascade has no data source and prediction fails outright. | Ask Tobias for the password — the connection string format is already in `.env.example`, only the password is missing. |
| `GOOGLE_GEOCODING_API_KEY` | Optional | Server-side reverse-geocode call (turns a plan's computed lat/long into a city name for `project_natural_key`). Unset just skips this step (no city, no error) — see §4 below. | See §4 below. |

`apps/api/.env` also exists but is for API-specific overrides only (model name, retrieval `k`,
etc.) — do **not** put `SUPABASE_TEAM_DB_URL` there too; the backend warns at startup if it finds
two copies that could drift.

### 3b. `apps/web/.env.local` (optional — only for the pit-list map)

Already created for you if you ran the §2a script. Otherwise:

```bash
cp apps/web/.env.example apps/web/.env.local
```

Fill in `NEXT_PUBLIC_GOOGLE_MAPS_API_KEY` — see §4. If you skip this file entirely, everything
except the pit-list page's map view still works; that page shows a "missing API key" placeholder
instead of erroring.

## 4. (Optional) Get the two Google API keys

These are two **separate** keys — `.env.example` warns not to reuse one value for both, since one
is public (shipped to the browser) and one is server-side-only.

1. Open [console.cloud.google.com](https://console.cloud.google.com), create or pick a project.
2. Enable **Maps JavaScript API** and **Geocoding API** for that project.
3. Create two API keys (APIs & Services → Credentials → Create Credentials → API Key):
   - One for `NEXT_PUBLIC_GOOGLE_MAPS_API_KEY` (`apps/web/.env.local`) — restrict it by **HTTP
     referrer** (e.g. `http://localhost:3000/*`) since it's exposed in the browser.
   - One for `GOOGLE_GEOCODING_API_KEY` (repo-root `.env`) — no referrer restriction needed, it's
     only called server-side.

Both are optional. Skipping them degrades map/city-lookup features only — the core PDF-upload,
extraction, and competitor-prediction path does not need either one.

## 5. Install and run the backend (FastAPI, port 8010)

If you ran the §2a script, the virtual environment and dependencies are already installed — skip
straight to the last line.

**macOS / Linux:**
```bash
python -m venv .venv && source .venv/bin/activate
pip install -r apps/api/requirements.txt
cd apps/api && uvicorn app:app --port 8010
```

**Windows (PowerShell)** — note the different activation command and path separators:
```powershell
py -3 -m venv .venv
.\.venv\Scripts\Activate.ps1
pip install -r apps\api\requirements.txt
cd apps\api
uvicorn app:app --port 8010
```

Success looks like `Uvicorn running on http://127.0.0.1:8010` in the terminal, and
`http://localhost:8010/docs` loading the FastAPI docs page in a browser.

## 6. Install and run the frontend (Next.js, port 3000)

In a **second** terminal window, from the repo root (leave the backend from §5 running in the
first one):

If you ran the §2a script, dependencies are already installed — you only need `npm run dev`.

```bash
cd apps/web
npm install
npm run dev
```

(Same command on Windows — no differences here.)

Open `http://localhost:3000`. The frontend proxies API calls to `http://127.0.0.1:8010` by
default; override with `BIDINTEL_API_URL` if the backend runs somewhere else.

## 6a. Seed the vector corpus (required for chat over past plans)

**A fresh clone has an EMPTY vector store, and that fails silently.** The app starts, reports
run, and new PDFs process fine — but chat cannot answer questions about any plan ingested on a
different machine, because `pipelines/plan_reader/06_chroma/` is gitignored.

The prebuilt corpus (68,572 chunks across 199 plans) ships as a **GitHub Release asset**, not a
committed file — GitHub rejects files over 100 MB, and a regenerated ~500 MB binary would bloat
git history permanently. **It does NOT come down with `git clone`.** You have to fetch it.

```powershell
.\scripts\fetch-corpus.ps1
```

That uses the GitHub CLI if it is installed and signed in. The repo is private, so if `gh` is
absent the script prints the release URL and stops — download the zip in a browser while signed
in to GitHub, then re-run:

```powershell
.\scripts\fetch-corpus.ps1 -ZipPath "$env:USERPROFILE\Downloads\06_chroma_corpus_199plans.zip"
```

Release page:
<https://github.com/Tobias-V-Knight/csi-bid-intelligence/releases/tag/chroma-corpus-2026-07-14>

The script installs to `pipelines/plan_reader/06_chroma/` and verifies by reading the collection
back — expect **68572**. A count of `0` means it landed in the wrong place. Restart the backend
afterwards. Chat additionally needs `ANTHROPIC_API_KEY`.

On macOS/Linux, or if you would rather do it by hand: download the zip, extract it, and place the
resulting `06_chroma` folder at `pipelines/plan_reader/06_chroma`.

## 7. Verify it actually works

Drop a bid-proposal PDF into the chat UI at `http://localhost:3000`. If extraction runs and you
reach the human-in-the-loop verification step, both required keys from §3a are working.

## Two things that are gitignored on purpose — don't file a bug for these


| Missing thing                                                                                                | What actually happens                                                                                                                                                                                                                                                                                                                                                                                                  |
| ------------------------------------------------------------------------------------------------------------ | ---------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------- |
| `pipelines/ci_model/03_training/outputs/ranking_predictions.csv` (~94 MB, gitignored — too large to commit) | The competitor-prediction cascade's tier-1 subprocess (fresh reports for projects already in the client's historical corpus) can't run. Every plan falls through to tier 3 instead — a **live prediction** computed from that plan's own data against Postgres. This is not an error and not stale data — it's just the less-detailed of two real prediction tiers. To recover the file, see `pipelines/ci_model/README.md`. |
| `pipelines/plan_reader/06_chroma/` (the vector index — grows with usage, not pre-built) | It auto-creates itself, so new PDFs you upload are searchable immediately. **But it starts EMPTY, so chat cannot answer questions about plans ingested on another machine.** Seed it with the prebuilt corpus — see §6a. This is the one gitignored thing that needs an explicit step. |

## If something doesn't start

See the root [`README.md`](../README.md)'s "Fresh-clone gotcha" section and
[`docs/ARCHITECTURE.md`](ARCHITECTURE.md) for the full system reference. For agent/AI-assisted
sessions working in this repo, start with [`CLAUDE.md`](../CLAUDE.md) instead — it documents
known rough edges that look like bugs but aren't.
