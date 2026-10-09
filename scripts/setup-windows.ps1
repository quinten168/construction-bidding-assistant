# Construction Bidding Assistant — one-shot Windows setup.
#
# Run from PowerShell, from inside the cloned repo folder (i.e. after
# `git clone ...` and `cd construction-bidding-assistant` — this script can't do that
# part, since it lives inside the repo it's setting up).
#
#   .\scripts\setup-windows.ps1
#
# What it does, in order: checks for Python/Node/Git and installs any that
# are missing (via winget), creates the Python virtual environment and
# installs backend dependencies, installs frontend dependencies, and copies
# the two .env templates if they don't already exist. It does NOT fill in
# any secret values (ANTHROPIC_API_KEY, SUPABASE_TEAM_DB_URL, ...) — those
# have to be typed in by hand, see docs/SETUP.md §3. It also does not START
# the two servers — see the printed instructions at the end for that.
#
# Safe to re-run: every step below checks first and skips work that's
# already done, so running this twice does not reinstall or reset anything.

$ErrorActionPreference = "Stop"

function Write-Step($msg) { Write-Host "`n== $msg ==" -ForegroundColor Cyan }
function Write-Ok($msg)   { Write-Host "  OK: $msg" -ForegroundColor Green }
function Write-Warn($msg) { Write-Host "  $msg" -ForegroundColor Yellow }

# --- confirm we're actually inside the repo, not just any folder ---------------------------------
if (-not (Test-Path ".\apps\api\requirements.txt")) {
    Write-Host "This doesn't look like the repo root (apps\api\requirements.txt not found)." -ForegroundColor Red
    Write-Host "cd into the construction-bidding-assistant folder first, then re-run this script." -ForegroundColor Red
    exit 1
}

# --- Python ----------------------------------------------------------------------------------------
Write-Step "Python"
$pythonOk = $false
try {
    $verOutput = py -3 --version 2>$null
    if ($verOutput -match "Python 3\.(\d+)") {
        if ([int]$Matches[1] -ge 9) { $pythonOk = $true }
    }
} catch {}

if ($pythonOk) {
    Write-Ok "$verOutput found"
} else {
    Write-Warn "Python 3.9+ not found — installing via winget..."
    winget install -e --id Python.Python.3.12 --accept-source-agreements --accept-package-agreements
    # Refresh PATH in this session so 'py' resolves without reopening the shell.
    $env:Path = [System.Environment]::GetEnvironmentVariable("Path", "Machine") + ";" + `
                [System.Environment]::GetEnvironmentVariable("Path", "User")
}

# --- Node.js (npm comes with it — no separate install) ----------------------------------------------
Write-Step "Node.js"
$nodeOk = $false
try {
    $nodeVer = node --version 2>$null
    if ($nodeVer -match "v(\d+)") {
        if ([int]$Matches[1] -ge 18) { $nodeOk = $true }
    }
} catch {}

if ($nodeOk) {
    Write-Ok "$nodeVer found"
} else {
    Write-Warn "Node.js 18+ not found — installing via winget..."
    winget install -e --id OpenJS.NodeJS.LTS --accept-source-agreements --accept-package-agreements
    $env:Path = [System.Environment]::GetEnvironmentVariable("Path", "Machine") + ";" + `
                [System.Environment]::GetEnvironmentVariable("Path", "User")
}

# --- Git (only relevant if you're running this after a partial/manual clone) -----------------------
Write-Step "Git"
try {
    $gitVer = git --version 2>$null
    Write-Ok "$gitVer found"
} catch {
    Write-Warn "Git not found — installing via winget..."
    winget install -e --id Git.Git --accept-source-agreements --accept-package-agreements
    $env:Path = [System.Environment]::GetEnvironmentVariable("Path", "Machine") + ";" + `
                [System.Environment]::GetEnvironmentVariable("Path", "User")
}

# --- Python virtual environment + backend dependencies ----------------------------------------------
Write-Step "Backend (.venv + pip install)"
if (-not (Test-Path ".\.venv\Scripts\Activate.ps1")) {
    py -3 -m venv .venv
    Write-Ok "Created .venv"
} else {
    Write-Ok ".venv already exists"
}

try {
    .\.venv\Scripts\Activate.ps1
} catch {
    Write-Host @"
  Could not activate .venv — PowerShell is probably blocking script execution.
  Run this once (only needs doing one time, ever, on this machine), then re-run this script:

      Set-ExecutionPolicy -Scope CurrentUser RemoteSigned
"@ -ForegroundColor Red
    exit 1
}

pip install -r apps\api\requirements.txt
Write-Ok "Backend dependencies installed"

# --- Frontend dependencies ---------------------------------------------------------------------------
Write-Step "Frontend (npm install)"
Push-Location apps\web
npm install
Pop-Location
Write-Ok "Frontend dependencies installed"

# --- .env templates (secrets still have to be filled in by hand) -------------------------------------
Write-Step ".env files"
if (-not (Test-Path ".env")) {
    Copy-Item ".env.example" ".env"
    Write-Warn "Created .env — you still need to fill in ANTHROPIC_API_KEY and SUPABASE_TEAM_DB_URL by hand (see docs/SETUP.md 3a). Opening it in Notepad now..."
    Start-Process notepad.exe ".env"
} else {
    Write-Ok ".env already exists — left it alone"
}

if (-not (Test-Path "apps\web\.env.local")) {
    Copy-Item "apps\web\.env.example" "apps\web\.env.local"
    Write-Ok "Created apps\web\.env.local (optional — only needed for the pit-list map, see docs/SETUP.md 3b/4)"
} else {
    Write-Ok "apps\web\.env.local already exists — left it alone"
}

# --- done --------------------------------------------------------------------------------------------
Write-Host "`n=== Setup finished ===" -ForegroundColor Cyan
Write-Host @"
Before running the app:
  1. Finish filling in .env (ANTHROPIC_API_KEY, SUPABASE_TEAM_DB_URL — ask Tobias for the password)
  2. See docs/SETUP.md step 7 to verify it actually works

To run it, open TWO PowerShell windows, both starting from this same folder:

  Window 1 (backend):
    .\.venv\Scripts\Activate.ps1
    cd apps\api
    uvicorn app:app --port 8010

  Window 2 (frontend):
    cd apps\web
    npm run dev

Then open http://localhost:3000 in a browser.
"@ -ForegroundColor White
