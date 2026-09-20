# SecureVault Portable ClamAV Setup (No Admin Required)
# Downloads, extracts, configures and verifies ClamAV inside .clamav/ directory.
# Everything runs sandboxed within the project — zero system-wide changes.

param(
    [switch]$SkipDownload,
    [switch]$UpdateOnly
)

$ErrorActionPreference = 'Stop'
$projectRoot = Split-Path $PSScriptRoot -Parent
$clamDir = Join-Path $projectRoot ".clamav"
$clamBin = Join-Path $clamDir "clamav-1.5.4.win.x64" # extracted folder name
$zipFile = Join-Path $clamDir "clamav.zip"
$downloadUrl = "https://github.com/Cisco-Talos/clamav/releases/download/clamav-1.5.4/clamav-1.5.4.win.x64.zip"

Write-Host ""
Write-Host "============================================" -ForegroundColor Cyan
Write-Host "  SecureVault - Portable ClamAV Setup" -ForegroundColor Cyan
Write-Host "  No admin rights required" -ForegroundColor Gray
Write-Host "============================================" -ForegroundColor Cyan
Write-Host ""

# --- Step 1: Download ---
if (-not $SkipDownload -and -not $UpdateOnly) {
    New-Item -ItemType Directory -Path $clamDir -Force | Out-Null

    if (-not (Test-Path $zipFile)) {
        Write-Host "[1/5] Downloading ClamAV 1.5.4 portable (~50 MB)..." -ForegroundColor Yellow
        try {
            [Net.ServicePointManager]::SecurityProtocol = [Net.SecurityProtocolType]::Tls12
            Invoke-WebRequest -Uri $downloadUrl -OutFile $zipFile -UseBasicParsing
            Write-Host "  Downloaded successfully." -ForegroundColor Green
        } catch {
            Write-Host "  ERROR: Download failed: $_" -ForegroundColor Red
            Write-Host "  Download manually from: $downloadUrl" -ForegroundColor Yellow
            Write-Host "  Place the ZIP at: $zipFile" -ForegroundColor Yellow
            exit 1
        }
    } else {
        Write-Host "[1/5] ClamAV ZIP already downloaded." -ForegroundColor Green
    }
} else {
    Write-Host "[1/5] Skipping download." -ForegroundColor Gray
}

# --- Step 2: Extract ---
if (-not $UpdateOnly) {
    if (-not (Test-Path "$clamBin\clamscan.exe")) {
        Write-Host "[2/5] Extracting ClamAV..." -ForegroundColor Yellow
        try {
            Expand-Archive -Path $zipFile -DestinationPath $clamDir -Force
            # Find the extracted directory
            $extracted = Get-ChildItem -Path $clamDir -Directory -Filter "clamav-*" | Select-Object -First 1
            if ($extracted) {
                $clamBin = $extracted.FullName
            }
            Write-Host "  Extracted to: $clamBin" -ForegroundColor Green
        } catch {
            Write-Host "  ERROR: Extraction failed: $_" -ForegroundColor Red
            exit 1
        }
    } else {
        Write-Host "[2/5] ClamAV already extracted." -ForegroundColor Green
    }
} else {
    Write-Host "[2/5] Skipping extraction." -ForegroundColor Gray
}

# Find actual binary location
if (-not (Test-Path "$clamBin\clamscan.exe")) {
    $extracted = Get-ChildItem -Path $clamDir -Directory -Filter "clamav-*" -Recurse | Select-Object -First 1
    if ($extracted) { $clamBin = $extracted.FullName }
}

$clamscan = Join-Path $clamBin "clamscan.exe"
$freshclam = Join-Path $clamBin "freshclam.exe"
$confFile = Join-Path $clamBin "freshclam.conf"
$dbDir = Join-Path $clamBin "database"

if (-not (Test-Path $clamscan)) {
    Write-Host "ERROR: clamscan.exe not found at $clamscan" -ForegroundColor Red
    Write-Host "Check the extraction path." -ForegroundColor Red
    exit 1
}

Write-Host "  clamscan: $clamscan" -ForegroundColor Gray
Write-Host "  freshclam: $freshclam" -ForegroundColor Gray

# --- Step 3: Configure freshclam ---
Write-Host ""
Write-Host "[3/5] Configuring virus database updates..." -ForegroundColor Yellow

New-Item -ItemType Directory -Path $dbDir -Force | Out-Null

# Create or fix freshclam.conf
$confSample = Join-Path $clamBin "freshclam.conf.sample"
if (Test-Path $confSample) {
    $content = Get-Content $confSample -Raw
    $content = $content -replace '(?m)^Example\s*$', '# Example'
    # Point database to our local directory
    if ($content -notmatch 'DatabaseDirectory') {
        $content += "`nDatabaseDirectory $dbDir`n"
    }
    $content | Set-Content $confFile -Encoding UTF8
    Write-Host "  Created freshclam.conf from sample." -ForegroundColor Green
} elseif (-not (Test-Path $confFile)) {
    @"
# SecureVault portable ClamAV configuration
# No admin rights required - all paths are local
DatabaseMirror database.clamav.net
DatabaseDirectory $dbDir
Checks 12
"@ | Set-Content $confFile -Encoding UTF8
    Write-Host "  Created minimal freshclam.conf." -ForegroundColor Green
} else {
    # Fix existing config
    $content = Get-Content $confFile -Raw
    if ($content -match '(?m)^Example\s*$') {
        $content = $content -replace '(?m)^Example\s*$', '# Example'
        $content | Set-Content $confFile -Encoding UTF8
        Write-Host "  Fixed existing freshclam.conf." -ForegroundColor Green
    } else {
        Write-Host "  freshclam.conf already configured." -ForegroundColor Green
    }
}

# --- Step 4: Update virus database ---
Write-Host ""
Write-Host "[4/5] Updating virus signatures (first run may take 2-5 minutes)..." -ForegroundColor Yellow

$freshclamArgs = @("--config-file=$confFile", "--datadir=$dbDir")
try {
    $proc = Start-Process -FilePath $freshclam -ArgumentList $freshclamArgs -NoNewWindow -Wait -PassThru -RedirectStandardOutput "$clamDir\freshclam-stdout.log" -RedirectStandardError "$clamDir\freshclam-stderr.log" 2>$null
    $freshOutput = Get-Content "$clamDir\freshclam-stdout.log" -ErrorAction SilentlyContinue
    $freshErr = Get-Content "$clamDir\freshclam-stderr.log" -ErrorAction SilentlyContinue

    if ($freshOutput) {
        foreach ($line in $freshOutput) {
            if ($line -match "updated|is up to date|downloaded") {
                Write-Host "  $line" -ForegroundColor Green
            }
        }
    }

    $dbFiles = Get-ChildItem -Path $dbDir -Include "main.cvd","main.cld","daily.cvd","daily.cld" -Recurse -ErrorAction SilentlyContinue
    if ($dbFiles.Count -eq 0) {
        # Also check clamBin root for database files
        $dbFiles = Get-ChildItem -Path $clamBin -Include "main.cvd","main.cld","daily.cvd","daily.cld" -Recurse -ErrorAction SilentlyContinue
    }

    if ($dbFiles.Count -gt 0) {
        Write-Host "  Virus database ready: $($dbFiles.Name -join ', ')" -ForegroundColor Green
    } else {
        Write-Host "  WARNING: No virus database files found." -ForegroundColor Red
        Write-Host "  ClamAV will not detect threats without signatures." -ForegroundColor Red
        Write-Host "  Check: $clamDir\freshclam-stderr.log" -ForegroundColor Yellow
    }
} catch {
    Write-Host "  WARNING: freshclam failed: $_" -ForegroundColor Yellow
}

# --- Step 5: Verify with EICAR test ---
Write-Host ""
Write-Host "[5/5] Running verification scan..." -ForegroundColor Yellow

$testDir = Join-Path $clamDir "test-files"
New-Item -ItemType Directory -Path $testDir -Force | Out-Null

# EICAR standard antivirus test string
$eicar = 'X5O!P%@AP[4\PZX54(P^)7CC)7}$EICAR-STANDARD-ANTIVIRUS-TEST-FILE!$H+H*'
$eicarFile = Join-Path $testDir "eicar.com"
$cleanFile = Join-Path $testDir "clean.txt"

[System.IO.File]::WriteAllText($eicarFile, $eicar)
[System.IO.File]::WriteAllText($cleanFile, "This is a clean test file.")

# Scan malicious file
$dbFlag = "--database=$dbDir"
$scanArgs = @("--no-summary", $dbFlag, $eicarFile)
$malResult = Start-Process -FilePath $clamscan -ArgumentList $scanArgs -NoNewWindow -Wait -PassThru -RedirectStandardOutput "$clamDir\scan-mal.log" 2>$null
$malExit = $malResult.ExitCode
$malOutput = Get-Content "$clamDir\scan-mal.log" -ErrorAction SilentlyContinue

# Scan clean file
$scanArgs2 = @("--no-summary", $dbFlag, $cleanFile)
$cleanResult = Start-Process -FilePath $clamscan -ArgumentList $scanArgs2 -NoNewWindow -Wait -PassThru -RedirectStandardOutput "$clamDir\scan-clean.log" 2>$null
$cleanExit = $cleanResult.ExitCode

# Cleanup test files
Remove-Item -Path $testDir -Recurse -Force -ErrorAction SilentlyContinue
Remove-Item "$clamDir\scan-mal.log","$clamDir\scan-clean.log" -Force -ErrorAction SilentlyContinue

Write-Host ""
if ($malExit -eq 1 -and $cleanExit -eq 0) {
    Write-Host "  EICAR test:  DETECTED (exit 1)  - CORRECT" -ForegroundColor Green
    Write-Host "  Clean file:  PASSED   (exit 0)  - CORRECT" -ForegroundColor Green
    Write-Host ""
    Write-Host "  ClamAV is fully working!" -ForegroundColor Green
} elseif ($malExit -eq 1) {
    Write-Host "  EICAR test:  DETECTED (exit 1)  - CORRECT" -ForegroundColor Green
    Write-Host "  Clean file:  exit $cleanExit (expected 0)" -ForegroundColor Yellow
} else {
    Write-Host "  EICAR test:  exit $malExit (expected 1)" -ForegroundColor Red
    Write-Host "  Virus database may be missing or incomplete." -ForegroundColor Red
    if ($malOutput) { Write-Host "  Output: $malOutput" -ForegroundColor Gray }
}

# --- Print startup instructions ---
Write-Host ""
Write-Host "============================================" -ForegroundColor Cyan
Write-Host "  Ready! Start SecureVault with ClamAV:" -ForegroundColor Cyan
Write-Host "============================================" -ForegroundColor Cyan
Write-Host ""
Write-Host "  `$env:CLAMSCAN_PATH = '$clamscan'" -ForegroundColor White
Write-Host "  `$env:REQUIRE_SCAN = '1'" -ForegroundColor White
Write-Host "  .\.venv\Scripts\python.exe run.py" -ForegroundColor White
Write-Host ""
Write-Host "  Or let SecureVault auto-detect ClamAV" -ForegroundColor Gray
Write-Host "  (auto-detection checks common paths)." -ForegroundColor Gray
Write-Host ""
Write-Host "  Health check: http://127.0.0.1:5000/health" -ForegroundColor Gray
Write-Host ""
