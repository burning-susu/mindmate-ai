[CmdletBinding()]
param(
    [string]$DataDir = '',
    [int]$ApiPort = 8001,
    [int]$WebPort = 5174
)

$ErrorActionPreference = 'Stop'
$repoRoot = (Resolve-Path (Join-Path $PSScriptRoot '..')).Path
if (-not $DataDir) {
    $DataDir = Join-Path $env:TEMP 'mindmate-ai-stage36-job-demo'
}

$resolvedDataDir = [System.IO.Path]::GetFullPath($DataDir)
$defaultUserData = [System.IO.Path]::GetFullPath((Join-Path $env:LOCALAPPDATA 'MindMateAI'))
if ($resolvedDataDir -eq $defaultUserData) {
    throw "拒绝使用默认用户数据目录 $defaultUserData。请使用独立的演示目录。"
}

Write-Host "演示数据目录：$resolvedDataDir"
Write-Host "该目录位于 TEMP 时可能被系统清理。清理后脚本只在空目录或带本批所有权标记的目录中重新准备，不会清空其他数据。"
Write-Host "Embedding 使用已校验的固定本地 ONNX 缓存；生成端固定为 Mock Provider，不调用真实 DeepSeek。"

$python = Join-Path $repoRoot 'backend\.venv\Scripts\python.exe'
if (-not (Test-Path -LiteralPath $python)) {
    throw "未找到 backend\.venv\Scripts\python.exe。请先运行 .\scripts\bootstrap.ps1。不会下载模型。"
}

$prepare = Join-Path $repoRoot 'backend\scripts\prepare_stage5_fixed_ready.py'
& $python $prepare --data-dir $resolvedDataDir
if ($LASTEXITCODE -ne 0) {
    throw "固定资料准备失败。演示未启动。请检查固定模型缓存 backend\model-cache\manager-validation 是否为 READY；脚本不会下载模型或切换 Provider。"
}

$reportPath = Join-Path $resolvedDataDir 'stage5-fixed-ready-report.json'
if (-not (Test-Path -LiteralPath $reportPath)) {
    throw "准备脚本未写出 stage5-fixed-ready-report.json。"
}
$report = [System.IO.File]::ReadAllText($reportPath) | ConvertFrom-Json
if ($report.provider_mode -ne 'mock' -or $report.deepseek_called) {
    throw "准备报告不是 Mock Provider，已停止。不会使用真实 Key。"
}
if ($report.real_model.state -ne 'READY') {
    throw "准备报告中的模型不是 READY。未启动演示，也未下载模型。"
}
$primary = $report.knowledge_bases.primary
if ($primary.status -ne 'READY' -or $primary.version_status -ne 'READY') {
    throw "固定主库不是 READY。未启动演示。"
}
if (-not $primary.knowledge_base_id -or -not $primary.index_version_id) {
    throw "准备报告缺少主库 ID 或索引版本。"
}

Write-Host "主库 $($primary.knowledge_base_id) 索引 $($primary.index_version_id) 已 READY。"
Write-Host "重复准备计数：files=$($report.idempotency.counts.files) knowledge_bases=$($report.idempotency.counts.knowledge_bases) tasks=$($report.idempotency.counts.tasks)。任务数会随演示问答增加，不表示样本被重复导入。"

& (Join-Path $PSScriptRoot 'dev.ps1') `
    -ApiPort $ApiPort `
    -WebPort $WebPort `
    -DataDir $resolvedDataDir `
    -KnowledgeBaseId $primary.knowledge_base_id `
    -ExpectedFingerprint $report.real_model.artifact_fingerprint `
    -ExpectedIndexVersionId $primary.index_version_id `
    -OpenBrowser
