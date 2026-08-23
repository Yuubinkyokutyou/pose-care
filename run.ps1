$ErrorActionPreference = "Stop"
$pythonPath = Join-Path $PSScriptRoot ".venv\Scripts\pythonw.exe"

if (-not (Test-Path -LiteralPath $pythonPath)) {
    Write-Error "仮想環境がありません。READMEのセットアップ手順を先に実行してください。"
}

Start-Process -FilePath $pythonPath -ArgumentList "-m", "pose_care" -WorkingDirectory $PSScriptRoot -WindowStyle Hidden
