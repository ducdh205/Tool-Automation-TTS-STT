<#
.SYNOPSIS
  Build the portable offline folder: dist\TTS-STT-Tool\ (start it with TTS-STT-Tool.bat)

.DESCRIPTION
  1. Build the web UI (frontend\dist).
  2. Copy two standalone Pythons (3.12 for the tool, 3.14.8 for wyoming) into dist\TTS-STT-Tool\runtime
     and install the locked libraries into them (uv.lock / vendor\wyoming-vietnamese\uv.lock).
  3. Copy the tool source, adb, go-ios + WDA.ipa (iPhone), wyoming source, launch.py and
     TTS-STT-Tool.bat into the folder.
  4. Put every model into dist\TTS-STT-Tool\models (copied from this machine's caches, downloads
     what is missing). models\ and data\ are kept between builds.
  5. Smoke test: start the folder's app offline from a fresh data dir, synthesize + transcribe.
  6. Optional (-Zip): pack the folder (without data\) into dist\TTS-STT-Tool-<version>.zip.

  Needs: uv, Node.js (npm), and the one-time setup from README (vendor\ folders).

.EXAMPLE
  powershell -ExecutionPolicy Bypass -File packaging\build.ps1 -Zip
#>
param(
    [switch]$SkipFrontend,  # reuse the existing frontend\dist
    [switch]$SkipSmokeTest,
    [switch]$Zip            # also make dist\TTS-STT-Tool-<version>.zip
)

$ErrorActionPreference = 'Stop'
$Root = Split-Path -Parent $PSScriptRoot
$Build = Join-Path $Root 'build'  # scratch files (requirements-*.txt)
$Dist = Join-Path $Root 'dist'
$Stage = Join-Path $Dist 'TTS-STT-Tool'
$Wy = Join-Path $Root 'vendor\wyoming-vietnamese'
$Py312 = Join-Path $Stage 'runtime\py312\python.exe'

function Write-Step($msg) { Write-Host "`n==> $msg" -ForegroundColor Cyan }

function Invoke-Native([scriptblock]$Cmd) {
    & $Cmd
    if ($LASTEXITCODE -ne 0) { throw "Lệnh lỗi (mã $LASTEXITCODE): $Cmd" }
}

function Copy-Tree($From, $To, [string[]]$ExcludeDirs = @()) {
    $rc = @($From, $To, '/E', '/NFL', '/NDL', '/NJH', '/NJS', '/NP', '/R:1', '/W:1')
    if ($ExcludeDirs.Count) { $rc += '/XD'; $rc += $ExcludeDirs }
    & robocopy @rc | Out-Null
    if ($LASTEXITCODE -ge 8) { throw "robocopy $From -> $To lỗi (mã $LASTEXITCODE)" }
    $global:LASTEXITCODE = 0
}

# Zip $SrcDir (as a top-level folder inside the zip), skipping $SrcDir\<ExcludeTop> and __pycache__.
# .NET ZipArchive streams each file and writes zip64 when needed; Compress-Archive breaks on files
# over 2 GB and Windows' tar.exe crashes (0xC0000005) on this folder.
function New-Zip($SrcDir, $ZipPath, [string[]]$ExcludeTop = @()) {
    Add-Type -AssemblyName System.IO.Compression, System.IO.Compression.FileSystem
    $src = (Get-Item $SrcDir).FullName.TrimEnd('\')
    $name = Split-Path $src -Leaf
    if (Test-Path $ZipPath) { Remove-Item $ZipPath -Force }
    $zip = [System.IO.Compression.ZipFile]::Open($ZipPath, 'Create')
    try {
        foreach ($f in Get-ChildItem $src -Recurse -File -Force) {
            $rel = $f.FullName.Substring($src.Length + 1)
            if ($rel -match '(^|\\)__pycache__\\') { continue }
            if ($ExcludeTop | Where-Object { $rel -like "$_\*" }) { continue }
            $entry = "$name/" + $rel.Replace('\', '/')
            [void][System.IO.Compression.ZipFileExtensions]::CreateEntryFromFile($zip, $f.FullName, $entry, 'Optimal')
        }
    } catch {
        $zip.Dispose(); $zip = $null
        Remove-Item $ZipPath -Force -ErrorAction SilentlyContinue
        throw
    } finally {
        if ($zip) { $zip.Dispose() }
    }
}

function New-Runtime($Version, $Dest, $ProjectDir, [string[]]$ExtraArgs = @(), [switch]$NoCheck) {
    Write-Step "Python $Version -> $Dest"
    Invoke-Native { uv python install $Version }
    # --system: ignore any .venv, we want the standalone interpreter itself (it is relocatable).
    $ErrorActionPreference = 'Continue'  # PS 5.1 turns any native stderr line into an error
    $py = (& uv python find --managed-python --system --no-project $Version 2>$null | Select-Object -Last 1)
    $ErrorActionPreference = 'Stop'
    if ($LASTEXITCODE -ne 0 -or -not $py -or -not (Test-Path $py.Trim())) { throw "Không tìm thấy Python $Version do uv quản lý" }
    Copy-Tree (Split-Path $py.Trim()) $Dest @('__pycache__')
    Remove-Item (Join-Path $Dest 'Lib\EXTERNALLY-MANAGED') -ErrorAction SilentlyContinue

    $req = Join-Path $Build "requirements-$Version.txt"
    $python = Join-Path $Dest 'python.exe'
    Invoke-Native { uv export --project $ProjectDir --frozen --no-dev --no-emit-project --no-hashes --no-header -q -o $req }
    Invoke-Native { uv pip install --python $python --break-system-packages --no-deps -r $req @ExtraArgs }
    # wyoming's uv.lock drops some zerotts deps on purpose (exclude-dependencies): skip the check there.
    if (-not $NoCheck) { Invoke-Native { uv pip check --python $python } }

    # Entry-point .exe files hard-code this machine's paths; the app never uses them.
    Remove-Item (Join-Path $Dest 'Scripts') -Recurse -Force -ErrorAction SilentlyContinue
    # App-local MSVC runtime: onnxruntime & co. need msvcp140.dll, absent on some clean Windows.
    foreach ($dll in 'msvcp140.dll', 'msvcp140_1.dll', 'msvcp140_2.dll', 'vcruntime140.dll', 'vcruntime140_1.dll', 'concrt140.dll') {
        $src = Join-Path $env:WINDIR "System32\$dll"
        if ((Test-Path $src) -and -not (Test-Path (Join-Path $Dest $dll))) { Copy-Item $src $Dest }
    }
}

# --- checks -------------------------------------------------------------------------------
foreach ($p in @("$Wy\pyproject.toml", "$Wy\wyoming_vietnamese", "$Root\vendor\platform-tools\adb.exe",
                  "$Root\vendor\go-ios\ios.exe", "$Root\vendor\go-ios\wintun.dll", "$Root\vendor\wda\WDA.ipa")) {
    if (-not (Test-Path $p)) { throw "Thiếu $p — làm bước cài đặt một lần trong README trước" }
}
if (-not (Get-Command uv -ErrorAction SilentlyContinue)) { throw 'Thiếu uv (https://docs.astral.sh/uv/)' }
$Version = (Select-String -Path "$Root\pyproject.toml" -Pattern '^version\s*=\s*"([^"]+)"').Matches[0].Groups[1].Value
Write-Host "TTS-STT Tool $Version"
$env:PYTHONIOENCODING = 'utf-8'
Remove-Item Env:PYTHONPATH, Env:VIRTUAL_ENV -ErrorAction SilentlyContinue

# --- 1. web UI ----------------------------------------------------------------------------
if (-not $SkipFrontend) {
    Write-Step 'Build giao diện'
    Push-Location (Join-Path $Root 'frontend')
    try { Invoke-Native { npm ci --no-audit --no-fund }; Invoke-Native { npm run build } } finally { Pop-Location }
}
if (-not (Test-Path "$Root\frontend\dist\index.html")) { throw 'Thiếu frontend\dist — bỏ -SkipFrontend' }

# --- 2. clean stage (models are kept: they are big and rarely change) ----------------------
Write-Step "Dọn $Stage (giữ models, data)"
New-Item -ItemType Directory -Force $Stage | Out-Null
foreach ($d in 'runtime', 'backend', 'frontend', 'vendor', 'ios', 'launch.py', 'TTS-STT-Tool.bat', 'HUONG-DAN-IPHONE.txt') {
    $p = Join-Path $Stage $d
    if (Test-Path $p) { Remove-Item $p -Recurse -Force }
}
# Models from an older build layout (build\stage): move them instead of downloading again.
$oldModels = Join-Path $Build 'stage\models'
if ((Test-Path $oldModels) -and -not (Test-Path "$Stage\models")) { Move-Item $oldModels "$Stage\models" }

# --- 3. runtimes ----------------------------------------------------------------------------
New-Runtime '3.12' (Join-Path $Stage 'runtime\py312') $Root
# iPhone: "Kết nối iPhone" runs pymobiledevice3 from this runtime (python -m pymobiledevice3).
Invoke-Native { & $Py312 -m pymobiledevice3 version }
New-Runtime '3.14.8' (Join-Path $Stage 'runtime\py314') $Wy @('--find-links', 'https://k2-fsa.github.io/icefall/piper_phonemize.html') -NoCheck

# --- 4. app files ---------------------------------------------------------------------------
Write-Step 'Copy mã nguồn, giao diện, adb, go-ios, wyoming'
Copy-Tree "$Root\backend\tts_stt_tool" "$Stage\backend\tts_stt_tool" @('__pycache__')
Copy-Tree "$Root\frontend\dist" "$Stage\frontend\dist"
Copy-Tree "$Root\vendor\platform-tools" "$Stage\vendor\platform-tools"
# go-ios: only the program + its tunnel driver (selfIdentity.plist is this machine's pairing identity).
New-Item -ItemType Directory -Force "$Stage\vendor\go-ios", "$Stage\ios" | Out-Null
Copy-Item "$Root\vendor\go-ios\ios.exe", "$Root\vendor\go-ios\wintun.dll" "$Stage\vendor\go-ios"
Copy-Item "$Root\vendor\wda\WDA.ipa" "$Stage\ios\WDA.ipa"
Copy-Item "$PSScriptRoot\HUONG-DAN-IPHONE.txt" "$Stage\HUONG-DAN-IPHONE.txt"
Copy-Tree "$Wy\wyoming_vietnamese" "$Stage\vendor\wyoming-vietnamese\wyoming_vietnamese" @('__pycache__')
Copy-Item "$Wy\LICENSE" "$Stage\vendor\wyoming-vietnamese\LICENSE"
Copy-Item "$PSScriptRoot\launch.py" "$Stage\launch.py"
Copy-Item "$PSScriptRoot\TTS-STT-Tool.bat" "$Stage\TTS-STT-Tool.bat"

# --- 5. models ------------------------------------------------------------------------------
Write-Step 'Model (VieNeu + wyoming)'
$hub = Join-Path $Stage 'models\hf\hub'
if (-not (Test-Path $hub)) {
    $localHub = if ($env:HF_HOME) { Join-Path $env:HF_HOME 'hub' } else { Join-Path $env:USERPROFILE '.cache\huggingface\hub' }
    foreach ($repo in 'models--pnnbao-ump--VieNeu-TTS-v3-Turbo', 'models--OpenMOSS-Team--MOSS-Audio-Tokenizer-Nano-ONNX') {
        if (Test-Path "$localHub\$repo") { Copy-Tree "$localHub\$repo" "$hub\$repo" }
    }
}
$wyModels = Join-Path $Stage 'models\wyoming'
if (-not (Test-Path $wyModels)) {
    foreach ($sub in 'models', 'cache\hub', 'cache\nghitts') {
        $src = Join-Path $Root "data\wyoming\$sub"
        if (Test-Path $src) { Copy-Tree $src "$wyModels\$sub" }
    }
}
Invoke-Native { & $Py312 "$PSScriptRoot\prefetch_models.py" $Stage }

# --- 6. smoke test --------------------------------------------------------------------------
if (-not $SkipSmokeTest) {
    Write-Step 'Smoke test offline'
    Invoke-Native { & $Py312 "$PSScriptRoot\smoke_test.py" $Stage }
}

$sizeGb = (Get-ChildItem $Stage -Exclude 'data' | Get-ChildItem -Recurse -File | Measure-Object Length -Sum).Sum / 1GB
Write-Host ('Xong: {0} ({1:N2} GB) — chạy TTS-STT-Tool.bat' -f $Stage, $sizeGb) -ForegroundColor Green

# --- 7. zip (optional) ----------------------------------------------------------------------
if ($Zip) {
    Write-Step 'Nén zip'
    $zipPath = Join-Path $Dist "TTS-STT-Tool-$Version.zip"
    New-Zip $Stage $zipPath @('data')
    Write-Host ('Xong: {0} ({1:N2} GB)' -f $zipPath, ((Get-Item $zipPath).Length / 1GB)) -ForegroundColor Green
}
