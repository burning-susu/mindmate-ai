[CmdletBinding()]
param(
    [switch]$SkipInstall
)

$ErrorActionPreference = 'Stop'
$repoRoot = Resolve-Path (Join-Path $PSScriptRoot '..')

function Require-Command([string]$Name) {
    if(-not (Get-Command $Name -ErrorAction SilentlyContinue)) {
        throw "Required command is missing: $Name"
    }
}

Require-Command node
Require-Command npm
Require-Command python
Require-Command uv

if(-not $SkipInstall) {
    Push-Location (Join-Path $repoRoot 'frontend')
    npm ci
    Pop-Location

    Push-Location (Join-Path $repoRoot 'backend')
    uv sync --dev
    Pop-Location
}

Write-Host 'MindMate AI development baseline is ready.'
Write-Host 'Use .\scripts\dev.ps1 to start the local frontend and backend.'
