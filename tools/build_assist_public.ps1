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

# --- 翻訳内容ゲート（公開対象言語・仕様082） --------------------------------
# 成果物への Arena 由来データ混入検査（check_public_build）とは別責務。
# 公開対象言語の翻訳内容違反（略号localize/テンプレ内コード/クラス・種族名不整合/
# プレースホルダ破損/日本語残り/空等）を PyInstaller 実行前に検出する。
if (-not $NoGate) {
    Write-Host ""
    Write-Host "=== 翻訳内容ゲート（公開対象言語・仕様082） ===" -ForegroundColor Cyan
    & $VenvPython "tools\check_language_content.py"
    $ContentExit = $LASTEXITCODE
    if ($ContentExit -ne 0) {
        throw "翻訳内容ゲートに失敗（公開対象言語の翻訳内容違反）。exit=$ContentExit"
    }
    Write-Host "翻訳内容ゲート: 合格（公開対象言語 0 violation）" -ForegroundColor Green
}

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
