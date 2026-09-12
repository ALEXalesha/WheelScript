# Build: tests -> exe (PyInstaller) -> portable zip -> installer (Inno Setup).
# Usage:  powershell -ExecutionPolicy Bypass -File build.ps1   [-SkipTests]
# ASCII only on purpose: Windows PowerShell 5.1 reads BOM-less .ps1 files as ANSI.
param([switch]$SkipTests)

$ErrorActionPreference = "Stop"
Set-Location $PSScriptRoot
$root = $PSScriptRoot

$version = (python -c "import wheelscript; print(wheelscript.__version__)").Trim()
Write-Host "WheelScript $version" -ForegroundColor Cyan

if (-not $SkipTests) {
    python -m pytest
    if ($LASTEXITCODE) { throw "Tests failed" }
}

if (-not (Test-Path "$root\assets\icon.ico")) { python tools\make_icon.py }

python -m PyInstaller --noconfirm --clean --windowed --name WheelScript `
    --icon "$root\assets\icon.ico" `
    --add-data "$root\assets\icon.ico;assets" `
    --exclude-module numpy --exclude-module hypothesis --exclude-module pytest `
    --distpath "$root\dist" --workpath "$root\build\pyi" --specpath "$root\build" `
    "$root\run.py"
if ($LASTEXITCODE) { throw "PyInstaller failed" }

New-Item -ItemType Directory -Force "$root\release" | Out-Null

# Portable = same build + portable.ini next to the exe (settings go to .\data).
$portable = "$root\build\portable"
if (Test-Path $portable) { Remove-Item -Recurse -Force $portable }
New-Item -ItemType Directory -Force $portable | Out-Null
Copy-Item -Recurse "$root\dist\WheelScript" $portable
Set-Content -Encoding ASCII "$portable\WheelScript\portable.ini" "Portable mode: settings are stored in the data folder next to WheelScript.exe."
$zip = "$root\release\WheelScript-$version-portable.zip"
if (Test-Path $zip) { Remove-Item $zip }
Compress-Archive -Path "$portable\WheelScript" -DestinationPath $zip
Write-Host "Portable: $zip" -ForegroundColor Green

$iscc = @(
    "$env:LOCALAPPDATA\Programs\Inno Setup 6\ISCC.exe",
    "${env:ProgramFiles(x86)}\Inno Setup 6\ISCC.exe",
    "$env:ProgramFiles\Inno Setup 6\ISCC.exe"
) | Where-Object { Test-Path $_ } | Select-Object -First 1
if (-not $iscc) {
    $cmd = Get-Command iscc -ErrorAction SilentlyContinue
    if ($cmd) { $iscc = $cmd.Source }
}
if (-not $iscc) {
    Write-Warning "Inno Setup 6 not found, installer skipped (winget install JRSoftware.InnoSetup)."
    exit 0
}
& $iscc /Q "/DAppVersion=$version" "/DSourceDir=$root\dist\WheelScript" "$root\installer\WheelScript.iss"
if ($LASTEXITCODE) { throw "Inno Setup failed" }
Write-Host "Setup: $root\release\WheelScript-$version-setup.exe" -ForegroundColor Green
