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
$sourceConsole = Join-Path $sourceProgram 'soffice.com'
if (-not (Test-Path -LiteralPath $sourceSoffice -PathType Leaf) -or -not (Test-Path -LiteralPath $sourceConsole -PathType Leaf)) {
    throw 'The source directory must contain program\soffice.com and soffice.exe.'
}

$licenseFiles = @(Get-ChildItem -LiteralPath $source -Recurse -File -ErrorAction Stop |
    Where-Object { $_.Name -match '^(LICENSE|NOTICE|COPYING)' })
if ($licenseFiles.Count -eq 0) {
    throw 'LibreOffice license files were not found; staging is refused.'
}
if (Test-Path -LiteralPath $target) {
    $sourceInventory = @(Get-ChildItem -LiteralPath $source -Recurse -File -ErrorAction Stop |
        ForEach-Object { $_.FullName.Substring($source.Length).TrimStart('\') + '|' + $_.Length } |
        Sort-Object)
    $targetInventory = @(Get-ChildItem -LiteralPath $target -Recurse -File -ErrorAction Stop |
        Where-Object { $_.Name -ne 'mindmate-runtime-manifest.json' } |
        ForEach-Object { $_.FullName.Substring($target.Length).TrimStart('\') + '|' + $_.Length } |
        Sort-Object)
    if ($sourceInventory.Count -ne $targetInventory.Count -or (Compare-Object $sourceInventory $targetInventory)) {
        throw "Staging target already exists and does not match the source runtime: $target"
    }
    $stagedSoffice = Join-Path $target 'program\soffice.exe'
    $sourceHash = (Get-FileHash -LiteralPath $sourceSoffice -Algorithm SHA256).Hash
    $stagedHash = (Get-FileHash -LiteralPath $stagedSoffice -Algorithm SHA256).Hash
    if ($sourceHash -ne $stagedHash) {
        throw 'The staged LibreOffice executable hash does not match the source.'
    }
} else {
    New-Item -ItemType Directory -Path $target -Force | Out-Null
    $sourceItems = Get-ChildItem -LiteralPath $source -Force -ErrorAction Stop
    if (-not $sourceItems) {
        throw 'The LibreOffice source directory is empty.'
    }
    $sourceItems | Copy-Item -Destination $target -Recurse -Force
}
$stagedSoffice = Join-Path $target 'program\soffice.exe'
$stagedConsole = Join-Path $target 'program\soffice.com'
if (-not (Test-Path -LiteralPath $stagedSoffice -PathType Leaf) -or -not (Test-Path -LiteralPath $stagedConsole -PathType Leaf)) {
    throw 'The staged LibreOffice runtime is missing program\soffice.com or soffice.exe.'
}
$versionOutput = (& $stagedConsole --version 2>&1 | Out-String).Trim()
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
