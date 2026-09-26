# Build: tests -> exe (PyInstaller) -> portable zip -> installer (Inno Setup).
# Usage:  powershell -ExecutionPolicy Bypass -File build.ps1   [-SkipTests]
# ASCII only on purpose: Windows PowerShell 5.1 reads BOM-less .ps1 files as ANSI.
param([switch]$SkipTests)

$ErrorActionPreference = "Stop"
Set-Location $PSScriptRoot
$root = $PSScriptRoot

# Everything runs in the project's own .venv, never in the global Python.
$py = "$root\.venv\Scripts\python.exe"
if (-not (Test-Path $py)) {
    Write-Host "Creating .venv" -ForegroundColor Cyan
    py -3 -m venv "$root\.venv"
    if ($LASTEXITCODE) { python -m venv "$root\.venv" }
    if ($LASTEXITCODE) { throw "venv failed" }
}
& $py -m pip install --disable-pip-version-check -q -r "$root\requirements-dev.txt"
if ($LASTEXITCODE) { throw "pip install failed" }

$version = (& $py -c "import wheelscript; print(wheelscript.__version__)").Trim()
Write-Host "WheelScript $version" -ForegroundColor Cyan

if (-not $SkipTests) {
    & $py -m pytest -p no:cacheprovider
    if ($LASTEXITCODE) { throw "Tests failed" }
}

if (-not (Test-Path "$root\assets\icon.ico")) { & $py tools\make_icon.py }

# Input is SDL 2.28.4 via PySDL2; pysdl2-dll also carries SDL2_image/mixer/ttf, but only
# SDL2.dll is needed. It goes where sdl2dll.get_dllpath() looks: _internal\sdl2dll\dll.
$sdlDll = (& $py -c "import os, sdl2dll; print(os.path.join(sdl2dll.get_dllpath(), 'SDL2.dll'))").Trim()
if (-not (Test-Path $sdlDll)) { throw "SDL2.dll not found: $sdlDll (pip install pysdl2-dll)" }

& $py -m PyInstaller --noconfirm --clean --windowed --name WheelScript `
    --icon "$root\assets\icon.ico" `
    --add-data "$root\assets\icon.ico;assets" `
    --add-binary "$sdlDll;sdl2dll/dll" `
    --collect-all vgamepad `
    --exclude-module pygame `
    --exclude-module numpy --exclude-module hypothesis --exclude-module pytest `
    --exclude-module tkinter --exclude-module _tkinter `
    --exclude-module PySide6.QtNetwork --exclude-module PySide6.QtQml --exclude-module PySide6.QtQuick `
    --exclude-module PySide6.QtSql --exclude-module PySide6.QtOpenGL --exclude-module PySide6.QtPdf `
    --exclude-module PySide6.QtSvg --exclude-module PySide6.QtDBus `
    --distpath "$root\dist" --workpath "$root\build\pyi" --specpath "$root\build" `
    "$root\run.py"
if ($LASTEXITCODE) { throw "PyInstaller failed" }
if (-not (Test-Path "$root\dist\WheelScript\_internal\sdl2dll\dll\SDL2.dll")) { throw "SDL2.dll is missing from the build" }
if (Test-Path "$root\dist\WheelScript\_internal\pygame") { throw "pygame got into the build" }

# Selftest of the built exe: input service without a window for 2 s, SDL + devices into a file.
# Paused mapping, no hotkey, no profile: it presses nothing and does not rumble.
$selftest = "$root\build\selftest.txt"
Remove-Item -Force -ErrorAction SilentlyContinue $selftest
$p = Start-Process -FilePath "$root\dist\WheelScript\WheelScript.exe" -ArgumentList "--selftest", "`"$selftest`"" -Wait -PassThru
if (Test-Path $selftest) { Get-Content -Encoding UTF8 $selftest | Select-Object -First 12 | Write-Host }
if ($p.ExitCode -ne 0) { throw "Selftest failed (exit $($p.ExitCode)), see $selftest" }

# Software OpenGL fallback is never used by Qt Widgets; keep only Russian Qt texts.
$qt = "$root\dist\WheelScript\_internal\PySide6"
Remove-Item -Force -ErrorAction SilentlyContinue "$qt\opengl32sw.dll"
if (Test-Path "$qt\translations") {
    Get-ChildItem "$qt\translations" -File | Where-Object { $_.Name -notlike "qtbase_ru*.qm" } | Remove-Item -Force
}

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
