param(
    [Parameter(Mandatory = $true)]
    [string]$BaseSha,

    [Parameter(Mandatory = $true)]
    [string]$HeadSha,

    [Parameter()]
    [string[]]$ChangedFiles
)

$ErrorActionPreference = 'Stop'

function Write-Outputs([bool]$Frontend, [bool]$Backend) {
    if (-not $env:GITHUB_OUTPUT) {
        throw 'GITHUB_OUTPUT must point to the GitHub Actions output file.'
    }

    Add-Content -LiteralPath $env:GITHUB_OUTPUT -Value "frontend=$($Frontend.ToString().ToLowerInvariant())"
    Add-Content -LiteralPath $env:GITHUB_OUTPUT -Value "backend=$($Backend.ToString().ToLowerInvariant())"
}

if (-not $PSBoundParameters.ContainsKey('ChangedFiles')) {
    if (
        [string]::IsNullOrWhiteSpace($BaseSha) -or
        [string]::IsNullOrWhiteSpace($HeadSha) -or
        $BaseSha -match '^0+$' -or
        $HeadSha -match '^0+$'
    ) {
        Write-Outputs -Frontend $true -Backend $true
        exit 0
    }

    $ChangedFiles = @(git diff --name-only --no-renames $BaseSha $HeadSha --)
    if ($LASTEXITCODE -ne 0) {
        Write-Outputs -Frontend $true -Backend $true
        exit 0
    }
}

$runFrontend = $false
$runBackend = $false

foreach ($file in $ChangedFiles) {
    $path = $file.Replace('\', '/')

    if (
        $path -match '(^|/)README\.md$' -or
        $path -match '\.md$' -or
        $path.StartsWith('docs/') -or
        $path.StartsWith('doc/')
    ) {
        if ($path.StartsWith('docs/openapi/')) {
            $runFrontend = $true
            $runBackend = $true
        }
        continue
    }

    if (
        $path.StartsWith('frontend/') -or
        $path.StartsWith('docs/openapi/')
    ) {
        $runFrontend = $true
    }

    if ($path.StartsWith('backend/')) {
        $runBackend = $true
    }

    if (
        $path.StartsWith('.github/workflows/') -or
        $path.StartsWith('scripts/') -or
        -not ($path.StartsWith('frontend/') -or $path.StartsWith('backend/'))
    ) {
        $runFrontend = $true
        $runBackend = $true
    }
}

Write-Outputs -Frontend $runFrontend -Backend $runBackend
