$ErrorActionPreference = "Stop"
$projectRoot = Split-Path -Parent $PSScriptRoot
$pythonPath = Join-Path $projectRoot ".venv\Scripts\python.exe"

if (-not (Test-Path -LiteralPath $pythonPath)) {
    Write-Error "仮想環境がありません。READMEのセットアップ手順を先に実行してください。"
}

& $pythonPath -m PyInstaller `
    --noconfirm `
    --clean `
    --windowed `
    --name PoseCare `
    --collect-binaries mediapipe `
    --collect-data pose_care `
    (Join-Path $projectRoot "pose_care\__main__.py")
