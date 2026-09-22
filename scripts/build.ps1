$ErrorActionPreference = 'Stop'
$repoRoot = Resolve-Path (Join-Path $PSScriptRoot '..')

Push-Location (Join-Path $repoRoot 'frontend')
npm run build
Pop-Location

Push-Location (Join-Path $repoRoot 'backend')
uv run python -m compileall -q src
Pop-Location
