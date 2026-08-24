[CmdletBinding()]
param()

Set-StrictMode -Version Latest
$ErrorActionPreference = "Stop"

$projectRoot = Split-Path -Parent $PSScriptRoot
$pythonPath = Join-Path $projectRoot ".venv\Scripts\python.exe"
$entryPoint = Join-Path $projectRoot "pose_care\__main__.py"
$buildPath = Join-Path $projectRoot "build"
$distPath = Join-Path $projectRoot "dist"

if (-not (Test-Path -LiteralPath $pythonPath -PathType Leaf)) {
    throw "仮想環境がありません。READMEのセットアップ手順を先に実行してください。"
}

# PyInstaller resolves imports relative to the current directory. Always build from the
# repository root so this script behaves the same locally and on GitHub Actions.
Push-Location -LiteralPath $projectRoot
try {
    & $pythonPath -m PyInstaller `
        --noconfirm `
        --clean `
        --windowed `
        --name PoseCare `
        --distpath $distPath `
        --workpath $buildPath `
        --specpath $projectRoot `
        --collect-binaries mediapipe `
        --collect-data pose_care `
        $entryPoint

    if ($LASTEXITCODE -ne 0) {
        throw "PyInstaller failed with exit code $LASTEXITCODE."
    }
}
finally {
    Pop-Location
}

$executablePath = Join-Path $distPath "PoseCare\PoseCare.exe"
if (-not (Test-Path -LiteralPath $executablePath -PathType Leaf)) {
    throw "Build completed without the expected executable: $executablePath"
}

$installDirectory = Join-Path $distPath "PoseCare"
$installManifestName = "PoseCare.install.json"
$installManifestPath = Join-Path $installDirectory $installManifestName
$installDirectoryPrefix = [System.IO.Path]::GetFullPath($installDirectory).TrimEnd('\') + '\'
$relativeFiles = [System.Collections.Generic.List[string]]::new()
$fullPaths = [System.Collections.Generic.Dictionary[string, string]]::new(
    [System.StringComparer]::OrdinalIgnoreCase
)

Get-ChildItem -LiteralPath $installDirectory -Recurse -File -Force | ForEach-Object {
    $fullPath = [System.IO.Path]::GetFullPath($_.FullName)
    if (-not $fullPath.StartsWith($installDirectoryPrefix, [System.StringComparison]::OrdinalIgnoreCase)) {
        throw "Build output escaped the install directory: $fullPath"
    }

    $relativePath = $fullPath.Substring($installDirectoryPrefix.Length).Replace('\', '/')
    if (-not $relativePath.Equals($installManifestName, [System.StringComparison]::OrdinalIgnoreCase)) {
        if ($fullPaths.ContainsKey($relativePath)) {
            throw "Install manifest contains a case-insensitive duplicate path: $relativePath"
        }
        $relativeFiles.Add($relativePath)
        $fullPaths.Add($relativePath, $fullPath)
    }
}

$emptyDirectories = @(
    Get-ChildItem -LiteralPath $installDirectory -Recurse -Directory -Force | Where-Object {
        $null -eq (Get-ChildItem -LiteralPath $_.FullName -Force | Select-Object -First 1)
    }
)
if ($emptyDirectories.Count -gt 0) {
    $emptyDirectoryList = ($emptyDirectories.FullName -join ', ')
    throw "Build output contains directories not owned by any manifest file: $emptyDirectoryList"
}

$relativeFiles.Sort([System.StringComparer]::Ordinal)
$manifestFiles = @(
    foreach ($relativePath in $relativeFiles) {
        $fileHash = (Get-FileHash -LiteralPath $fullPaths[$relativePath] -Algorithm SHA256).Hash.ToLowerInvariant()
        [ordered]@{
            path = $relativePath
            sha256 = $fileHash
        }
    }
)

$installManifest = [ordered]@{
    schema_version = 1
    product = "PoseCare.Desktop"
    # The marker is intentionally excluded because a file cannot contain its own hash.
    # The updater treats the validated list plus PoseCare.install.json as the install root.
    files = $manifestFiles
}
$manifestJson = $installManifest | ConvertTo-Json -Depth 3
[System.IO.File]::WriteAllText(
    $installManifestPath,
    $manifestJson + [Environment]::NewLine,
    [System.Text.UTF8Encoding]::new($false)
)

Write-Host "Build completed: $executablePath"
Write-Host "Install manifest created: $installManifestPath ($($manifestFiles.Count) hashed files)"
