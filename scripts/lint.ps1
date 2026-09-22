$ErrorActionPreference = 'Stop'
$repoRoot = Resolve-Path (Join-Path $PSScriptRoot '..')

Push-Location (Join-Path $repoRoot 'frontend')
npm run lint
Pop-Location

Push-Location (Join-Path $repoRoot 'backend')
uv run ruff check src tests
Pop-Location
