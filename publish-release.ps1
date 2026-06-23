[CmdletBinding()]
param(
    [string]$Version = "",
    [string]$OutputDir = "release",
    [switch]$SkipTests
)

$ErrorActionPreference = "Stop"

$RepoRoot = Split-Path -Parent $MyInvocation.MyCommand.Path
Set-Location $RepoRoot

function Assert-UnderPath {
    param(
        [Parameter(Mandatory = $true)]
        [string]$Path,
        [Parameter(Mandatory = $true)]
        [string]$Parent
    )

    $fullParent = [System.IO.Path]::GetFullPath($Parent).TrimEnd("\", "/")
    $fullPath = [System.IO.Path]::GetFullPath($Path).TrimEnd("\", "/")
    $prefix = "$fullParent$([System.IO.Path]::DirectorySeparatorChar)"

    if ($fullPath -ne $fullParent -and -not $fullPath.StartsWith($prefix, [System.StringComparison]::OrdinalIgnoreCase)) {
        throw "Refusing to write outside target directory: $fullPath"
    }
}

function Copy-Directory {
    param(
        [Parameter(Mandatory = $true)]
        [string]$Source,
        [Parameter(Mandatory = $true)]
        [string]$Destination,
        [string[]]$ExcludeDirectories = @(),
        [string[]]$ExcludeFiles = @()
    )

    New-Item -ItemType Directory -Path $Destination -Force | Out-Null

    Get-ChildItem -LiteralPath $Source -Force | ForEach-Object {
        if ($_.PSIsContainer -and $ExcludeDirectories -contains $_.Name) {
            return
        }
        if (-not $_.PSIsContainer -and $ExcludeFiles -contains $_.Name) {
            return
        }

        $target = Join-Path $Destination $_.Name
        if ($_.PSIsContainer) {
            Copy-Directory `
                -Source $_.FullName `
                -Destination $target `
                -ExcludeDirectories $ExcludeDirectories `
                -ExcludeFiles $ExcludeFiles
        }
        else {
            Copy-Item -LiteralPath $_.FullName -Destination $target -Force
        }
    }
}

if (-not $Version) {
    $pyproject = Get-Content -LiteralPath (Join-Path $RepoRoot "pyproject.toml") -Raw -Encoding UTF8
    if ($pyproject -notmatch '(?m)^version\s*=\s*"([^"]+)"') {
        throw "Cannot find project version in pyproject.toml"
    }
    $Version = $Matches[1]
}

$python = Join-Path $RepoRoot ".venv\Scripts\python.exe"
if (-not (Test-Path -LiteralPath $python)) {
    $python = "python.exe"
}

if (-not $SkipTests) {
    Write-Host "Running tests..."
    & $python -m pytest tests -q -p no:cacheprovider
    if ($LASTEXITCODE -ne 0) {
        throw "Tests failed. Release was not created."
    }
}

$releaseRoot = Join-Path $RepoRoot $OutputDir
$packageName = "DocumentToMarkdown-v$Version"
$packageDir = Join-Path $releaseRoot $packageName
$zipPath = Join-Path $releaseRoot "$packageName.zip"

Assert-UnderPath -Path $releaseRoot -Parent $RepoRoot
Assert-UnderPath -Path $packageDir -Parent $releaseRoot
Assert-UnderPath -Path $zipPath -Parent $releaseRoot

New-Item -ItemType Directory -Path $releaseRoot -Force | Out-Null

if (Test-Path -LiteralPath $packageDir) {
    Remove-Item -LiteralPath $packageDir -Recurse -Force
}
if (Test-Path -LiteralPath $zipPath) {
    Remove-Item -LiteralPath $zipPath -Force
}

New-Item -ItemType Directory -Path $packageDir -Force | Out-Null

$rootFiles = @(
    "README.md",
    "pyproject.toml",
    ".env.example",
    ".dockerignore",
    "Dockerfile",
    "Dockerfile.local-models",
    "docker-compose.yml"
)

foreach ($file in $rootFiles) {
    Copy-Item `
        -LiteralPath (Join-Path $RepoRoot $file) `
        -Destination (Join-Path $packageDir $file) `
        -Force
}

Copy-Directory `
    -Source (Join-Path $RepoRoot "app") `
    -Destination (Join-Path $packageDir "app") `
    -ExcludeDirectories @("__pycache__")

Copy-Directory `
    -Source (Join-Path $RepoRoot "docs") `
    -Destination (Join-Path $packageDir "docs")

Copy-Directory `
    -Source (Join-Path $RepoRoot "tests") `
    -Destination (Join-Path $packageDir "tests") `
    -ExcludeDirectories @("__pycache__", "_tmp") `
    -ExcludeFiles @("*.pyc")

$gitCommit = ""
$gitStatus = @()
try {
    $gitCommit = (& git rev-parse HEAD).Trim()
    $gitStatus = @(& git status --short)
}
catch {
    $gitCommit = ""
    $gitStatus = @()
}

$manifest = [ordered]@{
    name = "DocumentToMarkdown"
    version = $Version
    package = $packageName
    created_at = (Get-Date).ToUniversalTime().ToString("o")
    git_commit = $gitCommit
    git_status = $gitStatus
    included = @(
        "app/",
        "docs/",
        "tests/",
        "README.md",
        "pyproject.toml",
        ".env.example",
        ".dockerignore",
        "Dockerfile",
        "Dockerfile.local-models",
        "docker-compose.yml"
    )
    excluded = @(
        ".venv/",
        "data/",
        "release/",
        "tests/_tmp/",
        "__pycache__/",
        "*.egg-info/"
    )
}

$manifestPath = Join-Path $packageDir "release-manifest.json"
$manifest | ConvertTo-Json -Depth 4 | Set-Content -LiteralPath $manifestPath -Encoding UTF8

Compress-Archive -LiteralPath $packageDir -DestinationPath $zipPath -Force

Write-Host "Release created:"
Write-Host "  Directory: $packageDir"
Write-Host "  Archive:   $zipPath"
