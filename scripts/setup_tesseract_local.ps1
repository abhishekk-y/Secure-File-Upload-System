$ErrorActionPreference = 'Stop'

$root = (Resolve-Path (Join-Path $PSScriptRoot '..')).Path
$runtime = Join-Path $root '.runtime'
$installerDir = Join-Path $runtime 'installers'
$stage = Join-Path $runtime 'tesseract-stage'
$install = Join-Path $runtime 'tesseract'
$installer = Join-Path $installerDir 'tesseract-5.5.3.20260724-x64.exe'
$model = Join-Path $runtime 'eng.traineddata'
$installerUrl = 'https://github.com/tesseract-ocr/tesseract/releases/download/5.5.3/tesseract-ocr-w64-setup-5.5.3.20260724.exe'
$modelUrl = 'https://raw.githubusercontent.com/tesseract-ocr/tessdata_fast/main/eng.traineddata'
$expectedInstallerHash = 'BEE9E3434BD94FD65387D9BE28CD467A41F61B1275383B55B0F59A1331270AE4'
$expectedModelHash = '7D4322BD2A7749724879683FC3912CB542F19906C83BCC1A52132556427170B2'

if (Test-Path (Join-Path $install 'tesseract.exe')) {
    Write-Host "Tesseract already exists at $install. Remove that local runtime manually only if you intend to replace it."
    exit 0
}
if (Test-Path $stage) { throw "Staging directory already exists: $stage" }

$sevenZip = (Get-Command '7z.exe' -ErrorAction SilentlyContinue).Source
if (-not $sevenZip) {
    $candidates = @(
        (Join-Path $env:ProgramFiles '7-Zip\7z.exe'),
        (Join-Path ${env:ProgramFiles(x86)} '7-Zip\7z.exe'),
        'C:\ProgramData\chocolatey\tools\7z.exe'
    )
    $sevenZip = $candidates | Where-Object { Test-Path -LiteralPath $_ } | Select-Object -First 1
}
if (-not $sevenZip) { throw '7-Zip command-line tool was not found. Install 7-Zip, then rerun this script.' }

New-Item -ItemType Directory -Force -Path $installerDir | Out-Null
Invoke-WebRequest -Uri $installerUrl -OutFile $installer
$actualInstallerHash = (Get-FileHash -LiteralPath $installer -Algorithm SHA256).Hash
if ($actualInstallerHash -ne $expectedInstallerHash) { throw 'Tesseract installer SHA-256 did not match the pinned release hash.' }

New-Item -ItemType Directory -Force -Path $stage | Out-Null
& $sevenZip x $installer "-o$stage" -y
if ($LASTEXITCODE -ne 0 -or -not (Test-Path (Join-Path $stage 'tesseract.exe'))) {
    throw 'Could not extract the Tesseract payload into the project-local staging directory.'
}

$stageData = Join-Path $stage 'tessdata'
New-Item -ItemType Directory -Force -Path $stageData | Out-Null
Invoke-WebRequest -Uri $modelUrl -OutFile $model
$actualModelHash = (Get-FileHash -LiteralPath $model -Algorithm SHA256).Hash
if ($actualModelHash -ne $expectedModelHash) { throw 'English trained-data SHA-256 did not match the pinned model hash.' }
Move-Item -LiteralPath $model -Destination (Join-Path $stageData 'eng.traineddata')

$version = & (Join-Path $stage 'tesseract.exe') --version
if ($LASTEXITCODE -ne 0) { throw 'The extracted Tesseract executable failed its version check.' }
$languageOutput = & (Join-Path $stage 'tesseract.exe') --list-langs --tessdata-dir $stageData 2>&1
if ($LASTEXITCODE -ne 0 -or ($languageOutput -join "`n") -notmatch '\beng\b') {
    throw 'Tesseract could not load the pinned English trained data.'
}

Move-Item -LiteralPath $stage -Destination $install
Write-Host ($version | Select-Object -First 1)
Write-Host 'Installed locally at .runtime/tesseract with English data. No global PATH or system install was changed.'
