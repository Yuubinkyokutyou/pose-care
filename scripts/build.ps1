[CmdletBinding()]
param(
    [switch]$SkipInstaller
)

Set-StrictMode -Version Latest
$ErrorActionPreference = "Stop"

$projectRoot = Split-Path -Parent $PSScriptRoot
$pythonPath = Join-Path $projectRoot ".venv\Scripts\python.exe"
$entryPoint = Join-Path $projectRoot "pose_care\__main__.py"
$hookPath = Join-Path $projectRoot "scripts\pyinstaller_hooks"
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
        --additional-hooks-dir $hookPath `
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

if ($SkipInstaller) {
    return
}

$innoCompilerCandidates = @(
    (Get-Command "ISCC.exe" -ErrorAction SilentlyContinue | Select-Object -ExpandProperty Source -ErrorAction SilentlyContinue),
    "${env:ProgramFiles(x86)}\Inno Setup 6\ISCC.exe",
    "$env:ProgramFiles\Inno Setup 6\ISCC.exe",
    "$env:LOCALAPPDATA\Programs\Inno Setup 6\ISCC.exe",
    "$env:LOCALAPPDATA\Programs\Inno Setup 7\ISCC.exe"
) | Where-Object { $_ -and (Test-Path -LiteralPath $_ -PathType Leaf) } | Select-Object -Unique
$innoCompiler = $innoCompilerCandidates | Select-Object -First 1
if (-not $innoCompiler) {
    throw "Inno Setup Compiler (ISCC.exe) がありません。Inno Setupをインストールするか、アプリ本体だけを作る場合は -SkipInstaller を指定してください。"
}

$version = (& $pythonPath -c "import tomllib; print(tomllib.load(open('pyproject.toml', 'rb'))['project']['version'])").Trim()
if ($LASTEXITCODE -ne 0 -or $version -notmatch '^(0|[1-9]\d*)\.(0|[1-9]\d*)\.(0|[1-9]\d*)$') {
    throw "pyproject.tomlから有効なバージョンを読み取れませんでした。"
}

$installerOutput = Join-Path $distPath "installer"
New-Item -ItemType Directory -Path $installerOutput -Force | Out-Null
$previousInstallerVersion = $env:POSE_CARE_INSTALLER_VERSION
$previousInstallerSource = $env:POSE_CARE_INSTALLER_SOURCE
$previousInstallerOutput = $env:POSE_CARE_INSTALLER_OUTPUT
try {
    $env:POSE_CARE_INSTALLER_VERSION = $version
    $env:POSE_CARE_INSTALLER_SOURCE = $installDirectory
    $env:POSE_CARE_INSTALLER_OUTPUT = $installerOutput
    & $innoCompiler (Join-Path $PSScriptRoot "installer.iss")
    if ($LASTEXITCODE -ne 0) {
        throw "Inno Setup failed with exit code $LASTEXITCODE."
    }
}
finally {
    $env:POSE_CARE_INSTALLER_VERSION = $previousInstallerVersion
    $env:POSE_CARE_INSTALLER_SOURCE = $previousInstallerSource
    $env:POSE_CARE_INSTALLER_OUTPUT = $previousInstallerOutput
}

$installerPath = Join-Path $installerOutput "PoseCareSetup-windows-x64.exe"
if (-not (Test-Path -LiteralPath $installerPath -PathType Leaf)) {
    throw "Installer build completed without the expected executable: $installerPath"
}
Write-Host "Installer completed: $installerPath"
