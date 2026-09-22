$ErrorActionPreference = 'Stop'
$repoRoot = Resolve-Path (Join-Path $PSScriptRoot '..')

Push-Location (Join-Path $repoRoot 'frontend')
npm run test
Pop-Location

Push-Location (Join-Path $repoRoot 'backend')
uv run pytest
Pop-Location
