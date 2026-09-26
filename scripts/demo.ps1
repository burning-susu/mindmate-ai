[CmdletBinding()]
param(
    [string]$DataDir = (Join-Path $env:TEMP 'mindmate-ai-stage36-job-demo'),
    [int]$ApiPort = 8001,
    [int]$WebPort = 5174,
    [switch]$NoBrowser
)

$ErrorActionPreference = 'Stop'
$repoRoot = (Resolve-Path (Join-Path $PSScriptRoot '..')).Path
$python = Join-Path $repoRoot 'backend/.venv/Scripts/python.exe'
if (-not (Test-Path -LiteralPath $python)) { throw '缺少后端虚拟环境；请先运行 .\scripts\bootstrap.ps1。' }
$resolvedDataDir = [System.IO.Path]::GetFullPath($DataDir)
$prepare = Join-Path $repoRoot 'backend/scripts/prepare_stage5_fixed_ready.py'

Write-Host "准备独立 Demo 数据：$resolvedDataDir"
Push-Location (Join-Path $repoRoot 'backend')
try {
    & $python $prepare --data-dir $resolvedDataDir | Out-Null
    if ($LASTEXITCODE -ne 0) { throw '固定资料或模型准备失败；未启动演示服务。' }
} finally { Pop-Location }

$reportPath = Join-Path $resolvedDataDir 'stage5-fixed-ready-report.json'
$report = Get-Content -Raw -Encoding UTF8 -LiteralPath $reportPath | ConvertFrom-Json
if ($report.real_model.state -ne 'READY' -or $report.knowledge_bases.primary.status -ne 'READY' -or -not $report.knowledge_bases.primary.index_version_id) {
    throw '模型或主库索引未达到 READY；未启动演示服务。'
}
$marker = Join-Path $resolvedDataDir '.mindmate-stage5-fixed-ready-owner'
if (-not (Test-Path -LiteralPath $marker)) { throw 'Demo 数据所有权标记缺失；拒绝启动。' }
$previousDataDir = $env:MINDMATE_DATA_DIR
$previousProviderMode = $env:MINDMATE_PROVIDER_MODE
$env:MINDMATE_DATA_DIR = $resolvedDataDir
$env:MINDMATE_PROVIDER_MODE = 'mock'
$url = "http://127.0.0.1:$WebPort/knowledge-bases/$($report.knowledge_bases.primary.knowledge_base_id)"
Write-Host "固定主库索引 READY：$($report.knowledge_bases.primary.index_version_id)"
Write-Host '生成端使用 Mock Provider；Embedding 使用已校验的本地 ONNX。'
try {
    $devArgs = @{
        ApiPort = $ApiPort
        WebPort = $WebPort
        LogDir = (Join-Path $resolvedDataDir 'evidence')
        ExpectedModelFingerprint = $report.real_model.artifact_fingerprint
        ReadyKnowledgeBaseId = $report.knowledge_bases.primary.knowledge_base_id
    }
    if (-not $NoBrowser) { $devArgs.BrowserUrl = $url }
    & (Join-Path $PSScriptRoot 'dev.ps1') @devArgs
} finally {
    $env:MINDMATE_DATA_DIR = $previousDataDir
    $env:MINDMATE_PROVIDER_MODE = $previousProviderMode
}
