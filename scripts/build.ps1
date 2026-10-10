[CmdletBinding()]
param([string]$LibreOfficeHome = '')

$ErrorActionPreference = 'Stop'
$repoRoot = Resolve-Path (Join-Path $PSScriptRoot '..')

if ($LibreOfficeHome) {
    & (Join-Path $PSScriptRoot 'stage-libreoffice.ps1') -SourceDirectory $LibreOfficeHome
}

Push-Location (Join-Path $repoRoot 'frontend')
npm run build
Pop-Location

Push-Location (Join-Path $repoRoot 'backend')
uv run python -m compileall -q src
Pop-Location
