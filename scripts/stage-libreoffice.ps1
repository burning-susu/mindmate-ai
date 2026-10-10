[CmdletBinding()]
param(
    [Parameter(Mandatory = $true)]
    [string]$SourceDirectory,
    [string]$TargetDirectory = ''
)

$ErrorActionPreference = 'Stop'
$repoRoot = (Resolve-Path (Join-Path $PSScriptRoot '..')).Path
$source = (Resolve-Path -LiteralPath $SourceDirectory).Path
if (-not $TargetDirectory) {
    $TargetDirectory = Join-Path $repoRoot 'build\runtime\libreoffice'
}
$target = [System.IO.Path]::GetFullPath($TargetDirectory)
$buildRoot = Join-Path $repoRoot 'build'
$buildPrefix = $buildRoot.TrimEnd('\') + '\'
if (-not $target.StartsWith($buildPrefix, [System.StringComparison]::OrdinalIgnoreCase)) {
    throw 'LibreOffice staging target must remain inside the repository build directory.'
}

$sourceProgram = Join-Path $source 'program'
$sourceSoffice = Join-Path $sourceProgram 'soffice.exe'
if (-not (Test-Path -LiteralPath $sourceSoffice -PathType Leaf)) {
    throw 'The source directory does not contain program\soffice.exe.'
}

$licenseFiles = @(Get-ChildItem -LiteralPath $source -Recurse -File -ErrorAction Stop |
    Where-Object { $_.Name -match '^(LICENSE|NOTICE|COPYING)' })
if ($licenseFiles.Count -eq 0) {
    throw 'LibreOffice license files were not found; staging is refused.'
}
if (Test-Path -LiteralPath $target) {
    throw "Staging target already exists: $target. Move it aside before replacing it."
}

New-Item -ItemType Directory -Path $target -Force | Out-Null
$sourceItems = Get-ChildItem -LiteralPath $source -Force -ErrorAction Stop
if (-not $sourceItems) {
    throw 'The LibreOffice source directory is empty.'
}
$sourceItems | Copy-Item -Destination $target -Recurse -Force
$stagedSoffice = Join-Path $target 'program\soffice.exe'
if (-not (Test-Path -LiteralPath $stagedSoffice -PathType Leaf)) {
    throw 'The staged LibreOffice runtime is missing program\soffice.exe.'
}
$versionOutput = (& $stagedSoffice --version 2>&1 | Out-String).Trim()
if ($LASTEXITCODE -ne 0 -or $versionOutput -notmatch '^LibreOffice\s+') {
    throw 'Unable to verify the staged LibreOffice version.'
}
$stagedLicenses = @(Get-ChildItem -LiteralPath $target -Recurse -File -ErrorAction Stop |
    Where-Object { $_.Name -match '^(LICENSE|NOTICE|COPYING)' } |
    ForEach-Object { $_.FullName.Substring($target.Length).TrimStart('\') })
$manifest = [ordered]@{
    product = 'LibreOffice'
    version = $versionOutput
    executable = 'program/soffice.exe'
    executable_sha256 = (Get-FileHash -LiteralPath $stagedSoffice -Algorithm SHA256).Hash.ToLowerInvariant()
    license_files = $stagedLicenses
}
$manifest | ConvertTo-Json -Depth 4 | Set-Content -LiteralPath (Join-Path $target 'mindmate-runtime-manifest.json') -Encoding utf8
Write-Host "Staged $versionOutput at $target"
