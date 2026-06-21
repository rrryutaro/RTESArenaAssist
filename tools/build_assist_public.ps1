param(
    [string]$Python = "python",
    [switch]$SkipInstall,
    [switch]$OneDir,           # 指定で onedir（補助系統）。既定は onefile（主系統・単一exe）。
    [switch]$NoGate            # 公開前混入検査をスキップ（非推奨・デバッグ用）
)

# 公開ビルド（資産非同梱）。
# RTESArenaAssist-public.spec を使い、dist-public/build-public へ隔離出力する
# （dev ビルドの dist/ と混ざらない）。ビルド後に公開前混入検査を -PublicGate 相当で
# 実行し、Arena 由来データの混入（DENY）を検出したらビルドを失敗にする。

$ErrorActionPreference = "Stop"

$RepoRoot = Resolve-Path -LiteralPath (Join-Path $PSScriptRoot "..")
Set-Location -LiteralPath $RepoRoot

$VenvPython = Join-Path $RepoRoot ".venv\Scripts\python.exe"
if (-not (Test-Path -LiteralPath $VenvPython)) {
    & $Python -m venv ".venv"
}
if (-not $SkipInstall) {
    & $VenvPython -m pip install --upgrade pip
    & $VenvPython -m pip install -r "requirements-build-assist.txt"
}

if ($OneDir) { $env:RTESA_ONEFILE = "0" } else { $env:RTESA_ONEFILE = "1" }

$DistPath = Join-Path $RepoRoot "dist-public"
$WorkPath = Join-Path $RepoRoot "build-public"

& $VenvPython -m PyInstaller --clean --noconfirm `
    --distpath $DistPath --workpath $WorkPath `
    "RTESArenaAssist-public.spec"

# --- 公開前混入検査（安全柵・DENY でビルド失敗） ---------------------------
if (-not $NoGate) {
    Write-Host ""
    Write-Host "=== 公開前混入検査（公開ビルド・安全柵） ===" -ForegroundColor Cyan
    & $VenvPython "tools\check_public_build.py" `
        --spec "RTESArenaAssist-public.spec" `
        --build-dir (Join-Path $WorkPath "RTESArenaAssist-public") `
        --dist $DistPath
    $GateExit = $LASTEXITCODE
    if ($GateExit -ne 0) {
        throw "公開前混入検査に失敗（Arena 由来データの混入を検出）。exit=$GateExit"
    }
    Write-Host "公開前混入検査: 合格（Arena 由来データの混入なし）" -ForegroundColor Green
}

Write-Host ""
Write-Host "公開ビルド出力: $DistPath" -ForegroundColor Green
