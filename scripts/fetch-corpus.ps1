<#
.SYNOPSIS
    Downloads and installs the prebuilt ChromaDB vector corpus for the plan reader.

.DESCRIPTION
    pipelines/plan_reader/06_chroma/ is gitignored: it is generated data that changes on
    every PDF ingest, and it is ~1.5 GB. So a fresh `git clone` starts with NO vector store,
    and chat cannot answer questions about previously-ingested plans.

    That failure is SILENT. The app starts, reports run, and PDFs process normally -- only
    retrieval over the back catalogue comes back empty. This script is how you avoid it.

    The corpus ships as a GitHub Release asset rather than a committed file, because GitHub
    rejects files over 100 MB and because a regenerated half-gigabyte binary would bloat git
    history permanently.

.PARAMETER ZipPath
    Path to an already-downloaded corpus zip. Use this when the automatic download is not
    available (see NOTES) and you fetched the file through a browser instead.

.PARAMETER Force
    Replace an existing 06_chroma directory. Without this, a populated store is left alone.

.EXAMPLE
    .\scripts\fetch-corpus.ps1
    Downloads via the GitHub CLI if it is installed and authenticated.

.EXAMPLE
    .\scripts\fetch-corpus.ps1 -ZipPath "$env:USERPROFILE\Downloads\06_chroma_corpus_199plans.zip"
    Installs a zip you already downloaded in a browser.

.NOTES
    The repository is PRIVATE, so the release asset cannot be fetched with a plain web request.
    Either the GitHub CLI (`gh`) must be installed and signed in, or you download the zip in a
    browser while signed in to GitHub and pass -ZipPath.

    Windows Server 2016 note: PowerShell 5.1 defaults to TLS 1.0, which GitHub refuses. This
    script sets TLS 1.2 for its own session.
#>
[CmdletBinding()]
param(
    [string]$ZipPath,
    [switch]$Force
)

$ErrorActionPreference = "Stop"
[Net.ServicePointManager]::SecurityProtocol = [Net.SecurityProtocolType]::Tls12

$RELEASE_TAG = "chroma-corpus-2026-07-14"
$REPO        = "Tobias-V-Knight/csi-bid-intelligence"
$ASSET       = "06_chroma_corpus_199plans.zip"
$EXPECTED    = 68572   # embeddings in collection csi_plans for this snapshot

function Write-Step { param($m) Write-Host "`n=== $m ===" -ForegroundColor Cyan }
function Write-Ok   { param($m) Write-Host "  OK   $m" -ForegroundColor Green }
function Write-Warn { param($m) Write-Host "  WARN $m" -ForegroundColor Yellow }
function Write-Err  { param($m) Write-Host "  FAIL $m" -ForegroundColor Red }

# --- locate the repo, from this script's own location (not the caller's cwd) ---------------
$RepoRoot = Split-Path -Parent (Split-Path -Parent $MyInvocation.MyCommand.Path)
$Target   = Join-Path $RepoRoot "pipelines\plan_reader\06_chroma"
$PlanDir  = Split-Path -Parent $Target

if (-not (Test-Path $PlanDir)) {
    Write-Err "Not a csi-bid-intelligence checkout: $PlanDir does not exist."
    Write-Host "  Run this from the repo, e.g. .\scripts\fetch-corpus.ps1"
    exit 1
}

Write-Step "Target"
Write-Host "  $Target"

# --- refuse to clobber a populated store unless asked ---------------------------------------
if (Test-Path $Target) {
    $existing = Get-ChildItem $Target -Recurse -File -ErrorAction SilentlyContinue |
                Measure-Object -Property Length -Sum
    $mb = [math]::Round(($existing.Sum / 1MB), 1)
    if ($existing.Count -gt 0 -and -not $Force) {
        Write-Warn "A vector store already exists here ($($existing.Count) files, $mb MB)."
        Write-Host "  Leaving it alone. Re-run with -Force to replace it." -ForegroundColor Yellow
        exit 0
    }
    if ($Force) {
        Write-Warn "Replacing existing store ($mb MB) because -Force was given."
        Remove-Item $Target -Recurse -Force
    }
}

# --- obtain the zip -------------------------------------------------------------------------
Write-Step "Corpus archive"
$TempZip = $null

if ($ZipPath) {
    if (-not (Test-Path $ZipPath)) { Write-Err "No such file: $ZipPath"; exit 1 }
    $ZipPath = (Resolve-Path $ZipPath).Path
    Write-Ok "Using local archive: $ZipPath"
}
else {
    $gh = Get-Command gh -ErrorAction SilentlyContinue
    if ($gh) {
        Write-Host "  GitHub CLI found - downloading $ASSET ..."
        $TempZip = Join-Path $env:TEMP "csi-corpus-$(Get-Random)"
        New-Item -ItemType Directory -Path $TempZip -Force | Out-Null
        & gh release download $RELEASE_TAG --repo $REPO --pattern $ASSET --dir $TempZip
        if ($LASTEXITCODE -ne 0) {
            Write-Err "gh release download failed (are you signed in? run: gh auth login)"
            exit 1
        }
        $ZipPath = (Join-Path $TempZip $ASSET)
        Write-Ok "Downloaded"
    }
    else {
        Write-Err "GitHub CLI (gh) not found, and this repository is private."
        Write-Host ""
        Write-Host "  Download the corpus manually, then re-run with -ZipPath:" -ForegroundColor Yellow
        Write-Host ""
        Write-Host "    1. Open this in a browser, signed in to GitHub:"
        Write-Host "       https://github.com/$REPO/releases/tag/$RELEASE_TAG" -ForegroundColor White
        Write-Host "    2. Download $ASSET (about 526 MB)"
        Write-Host "    3. Re-run:"
        Write-Host "       .\scripts\fetch-corpus.ps1 -ZipPath `"`$env:USERPROFILE\Downloads\$ASSET`"" -ForegroundColor White
        Write-Host ""
        exit 1
    }
}

# --- extract --------------------------------------------------------------------------------
Write-Step "Extracting"
$Staging = Join-Path $env:TEMP "csi-corpus-extract-$(Get-Random)"
New-Item -ItemType Directory -Path $Staging -Force | Out-Null
try {
    Expand-Archive -Path $ZipPath -DestinationPath $Staging -Force

    # the archive contains a top-level 06_chroma/ folder; tolerate its absence just in case
    $src = Join-Path $Staging "06_chroma"
    if (-not (Test-Path $src)) { $src = $Staging }

    Move-Item -Path $src -Destination $Target -Force
    Write-Ok "Installed to $Target"
}
finally {
    Remove-Item $Staging -Recurse -Force -ErrorAction SilentlyContinue
    if ($TempZip) { Remove-Item $TempZip -Recurse -Force -ErrorAction SilentlyContinue }
}

# --- verify by actually reading the store, not by trusting the copy -------------------------
Write-Step "Verifying"
$venvPy = Join-Path $RepoRoot ".venv\Scripts\python.exe"
if (Test-Path $venvPy) {
    $probe = @"
import chromadb
c = chromadb.PersistentClient(path=r'$Target')
print(c.get_collection('csi_plans').count())
"@
    try {
        $count = & $venvPy -c $probe 2>$null
        if ($count -match '^\d+$') {
            if ([int]$count -eq $EXPECTED) { Write-Ok "$count embeddings (expected $EXPECTED)" }
            elseif ([int]$count -gt 0)     { Write-Warn "$count embeddings, expected $EXPECTED - store differs from the published snapshot" }
            else                           { Write-Err "0 embeddings - the store is empty, something went wrong" ; exit 1 }
        } else {
            Write-Warn "Could not read a count back. Check manually."
        }
    } catch {
        Write-Warn "Verification could not run: $_"
    }
} else {
    Write-Warn "No .venv found, skipping verification. Create the venv, then check with:"
    Write-Host "    .venv\Scripts\python.exe -c `"import chromadb; print(chromadb.PersistentClient(path=r'$Target').get_collection('csi_plans').count())`""
}

Write-Host "`nDone. Restart the backend to pick up the corpus." -ForegroundColor Green
Write-Host "Note: chat also requires ANTHROPIC_API_KEY in the root .env`n"
