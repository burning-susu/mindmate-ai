[CmdletBinding()]
param(
    [int]$ApiPort = 8000,
    [int]$WebPort = 5173,
    [string]$BrowserUrl = '',
    [string]$LogDir = '',
    [string]$ExpectedModelFingerprint = '',
    [string]$ReadyKnowledgeBaseId = ''
)

$ErrorActionPreference = 'Stop'
$repoRoot = (Resolve-Path (Join-Path $PSScriptRoot '..')).Path
$python = Join-Path $repoRoot 'backend/.venv/Scripts/python.exe'
$vite = Join-Path $repoRoot 'frontend/node_modules/vite/bin/vite.js'
if (-not (Test-Path -LiteralPath $python) -or -not (Test-Path -LiteralPath $vite)) {
    throw '缺少后端虚拟环境或前端依赖；请先运行 .\scripts\bootstrap.ps1。'
}
if ($ApiPort -eq $WebPort -or $ApiPort -lt 1 -or $ApiPort -gt 65535 -or $WebPort -lt 1 -or $WebPort -gt 65535) {
    throw 'API/Web 端口必须是两个不同的有效端口。'
}
foreach ($port in @($ApiPort, $WebPort)) {
    $listener = [System.Net.Sockets.TcpListener]::new([System.Net.IPAddress]::Loopback, $port)
    try { $listener.Start() } catch { throw "回环端口 $port 已被占用；请停止占用服务或指定其他端口。" } finally { $listener.Stop() }
}

$node = (Get-Command node -ErrorAction Stop).Source
$previousApiPort = $env:MINDMATE_API_PORT
$previousAllowedOrigins = $env:MINDMATE_ALLOWED_ORIGINS
$env:MINDMATE_API_PORT = "$ApiPort"
$env:MINDMATE_ALLOWED_ORIGINS = '["http://127.0.0.1:' + $WebPort + '"]'
$backend = $null
$frontend = $null
try {
    $backendArgs = @{
        FilePath = $python
        ArgumentList = @('-m', 'uvicorn', 'mindmate.main:app', '--host', '127.0.0.1', '--port', "$ApiPort")
        WorkingDirectory = (Join-Path $repoRoot 'backend')
        PassThru = $true
        WindowStyle = 'Hidden'
    }
    $frontendArgs = @{
        FilePath = $node
        ArgumentList = @('node_modules/vite/bin/vite.js', '--host', '127.0.0.1', '--port', "$WebPort", '--strictPort')
        WorkingDirectory = (Join-Path $repoRoot 'frontend')
        PassThru = $true
        WindowStyle = 'Hidden'
    }
    if ($LogDir) {
        New-Item -ItemType Directory -Path $LogDir -Force | Out-Null
        $backendArgs.RedirectStandardOutput = Join-Path $LogDir 'api.stdout.log'
        $backendArgs.RedirectStandardError = Join-Path $LogDir 'api.stderr.log'
        $frontendArgs.RedirectStandardOutput = Join-Path $LogDir 'web.stdout.log'
        $frontendArgs.RedirectStandardError = Join-Path $LogDir 'web.stderr.log'
    }
    $backend = Start-Process @backendArgs
    $frontend = Start-Process @frontendArgs
    $deadline = (Get-Date).AddSeconds(30)
    while ((Get-Date) -lt $deadline) {
        if ($backend.HasExited -or $frontend.HasExited) { throw '本地服务启动失败；请检查 evidence/*.stderr.log。' }
        try {
            $api = Invoke-RestMethod -Uri "http://127.0.0.1:$ApiPort/api/v1/health" -TimeoutSec 2
            $web = Invoke-WebRequest -Uri "http://127.0.0.1:$WebPort/" -TimeoutSec 2 -UseBasicParsing
            if ($api.status -eq 'ok' -and $web.StatusCode -eq 200) { break }
        } catch { Start-Sleep -Milliseconds 300 }
    }
    if ((Get-Date) -ge $deadline) { throw '30 秒内本地服务未就绪；请检查 evidence/*.stderr.log。' }
    if ($ExpectedModelFingerprint) {
        $model = Invoke-RestMethod -Uri "http://127.0.0.1:$ApiPort/api/v1/embedding-model" -TimeoutSec 10
        if ($model.state -ne 'READY' -or $model.artifact_fingerprint -ne $ExpectedModelFingerprint) {
            throw "运行中模型未达到固定 READY：$($model.state) / $($model.error_code)"
        }
    }
    if ($ReadyKnowledgeBaseId) {
        $knowledgeBase = Invoke-RestMethod -Uri "http://127.0.0.1:$ApiPort/api/v1/knowledge-bases/$ReadyKnowledgeBaseId" -TimeoutSec 10
        if ($knowledgeBase.status -ne 'READY') { throw "运行中知识库未达到 READY：$($knowledgeBase.status)" }
    }
    Write-Host "API: http://127.0.0.1:$ApiPort  Web: http://127.0.0.1:$WebPort"
    if ($BrowserUrl) {
        Write-Host "演示页面: $BrowserUrl"
        Start-Process $BrowserUrl
    }
    Write-Host '按 Ctrl+C 停止本次启动的两个服务。'
    while (-not $backend.HasExited -and -not $frontend.HasExited) { Start-Sleep -Seconds 1 }
    throw '本地服务意外退出；请检查启动日志。'
} finally {
    foreach ($process in @($frontend, $backend)) {
        if ($process -and -not $process.HasExited) { Stop-Process -Id $process.Id -Force }
    }
    $env:MINDMATE_API_PORT = $previousApiPort
    $env:MINDMATE_ALLOWED_ORIGINS = $previousAllowedOrigins
}
