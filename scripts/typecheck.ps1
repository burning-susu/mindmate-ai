$ErrorActionPreference = 'Stop'
$repoRoot = Resolve-Path (Join-Path $PSScriptRoot '..')

Push-Location (Join-Path $repoRoot 'frontend')
npm run typecheck
Pop-Location

Push-Location (Join-Path $repoRoot 'backend')
uv run pyright
Pop-Location
