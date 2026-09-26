[CmdletBinding()]
param(
    [int]$ApiPort = 8000,
    [int]$WebPort = 5173,
    [string]$DataDir = '',
    [string]$KnowledgeBaseId = '',
    [string]$ExpectedFingerprint = '',
    [string]$ExpectedIndexVersionId = '',
    [switch]$OpenBrowser,
    [ValidateSet('', 'RequestedStop', 'UnexpectedExit')]
    [string]$LifecycleSelfTest = ''
)

$ErrorActionPreference = 'Stop'
$repoRoot = (Resolve-Path (Join-Path $PSScriptRoot '..')).Path
$script:cleaned = $false
$script:backendProcess = $null
$script:frontendProcess = $null
$script:stopRequested = $false
$script:abnormalMessage = $null
$previousApiPort = $env:MINDMATE_API_PORT
$previousDataDir = $env:MINDMATE_DATA_DIR
$previousProviderMode = $env:MINDMATE_PROVIDER_MODE
$previousAllowedOrigins = $env:MINDMATE_ALLOWED_ORIGINS

function Test-LoopbackPortFree {
    param([int]$Port)
    $listener = $null
    try {
        $listener = [System.Net.Sockets.TcpListener]::new([System.Net.IPAddress]::Loopback, $Port)
        $listener.Start()
        return $true
    } catch {
        return $false
    } finally {
        if ($null -ne $listener) {
            $listener.Stop()
        }
    }
}

function Stop-OwnedProcessTree {
    param([int]$ProcessId)
    if ($ProcessId -le 0 -or $ProcessId -eq $PID) {
        return
    }
    $children = @(Get-CimInstance Win32_Process -Filter "ParentProcessId=$ProcessId" -ErrorAction SilentlyContinue)
    foreach ($child in $children) {
        Stop-OwnedProcessTree -ProcessId ([int]$child.ProcessId)
    }
    Stop-Process -Id $ProcessId -Force -ErrorAction SilentlyContinue
}

function Stop-OwnedPortListener {
    param(
        [int]$Port,
        [string]$CommandMatch
    )
    $lines = @(netstat -ano -p tcp | Select-String -Pattern ":$Port\s")
    foreach ($line in $lines) {
        $text = $line.ToString()
        if ($text -notmatch 'LISTENING\s+(\d+)\s*$') {
            continue
        }
        $processId = [int]$Matches[1]
        if ($processId -le 0 -or $processId -eq $PID) {
            continue
        }
        $proc = Get-CimInstance Win32_Process -Filter "ProcessId=$processId" -ErrorAction SilentlyContinue
        $command = if ($null -ne $proc) { [string]$proc.CommandLine } else { '' }
        if ($command -like "*$CommandMatch*") {
            Stop-OwnedProcessTree -ProcessId $processId
        }
    }
}

function Test-OperatorTermination {
    param($ExitCode)
    if ($null -eq $ExitCode) {
        return $false
    }
    # Stop-Process uses TerminateProcess with exit code -1. Other codes stay failures.
    return ($ExitCode -eq -1) -or ($ExitCode -eq 4294967295)
}

function Restore-DemoEnvironment {
    $env:MINDMATE_API_PORT = $previousApiPort
    if ($null -eq $previousDataDir) {
        Remove-Item Env:MINDMATE_DATA_DIR -ErrorAction SilentlyContinue
    } else {
        $env:MINDMATE_DATA_DIR = $previousDataDir
    }
    if ($null -eq $previousProviderMode) {
        Remove-Item Env:MINDMATE_PROVIDER_MODE -ErrorAction SilentlyContinue
    } else {
        $env:MINDMATE_PROVIDER_MODE = $previousProviderMode
    }
    if ($null -eq $previousAllowedOrigins) {
        Remove-Item Env:MINDMATE_ALLOWED_ORIGINS -ErrorAction SilentlyContinue
    } else {
        $env:MINDMATE_ALLOWED_ORIGINS = $previousAllowedOrigins
    }
}

function Stop-StartedServers {
    if ($script:cleaned) {
        return
    }
    $script:cleaned = $true
    if ($null -ne $script:frontendProcess) {
        Stop-OwnedProcessTree -ProcessId $script:frontendProcess.Id
    }
    if ($null -ne $script:backendProcess) {
        Stop-OwnedProcessTree -ProcessId $script:backendProcess.Id
    }
    Stop-OwnedPortListener -Port $ApiPort -CommandMatch 'mindmate.main:app'
    Stop-OwnedPortListener -Port $WebPort -CommandMatch '--port'
    Restore-DemoEnvironment
}

function Invoke-LifecycleSelfTest {
    param([string]$Mode)
    $decoy = Start-Process -FilePath 'powershell.exe' -ArgumentList @(
        '-NoProfile', '-Command', 'Start-Sleep -Seconds 60'
    ) -WindowStyle Hidden -PassThru
    try {
        if ($Mode -eq 'RequestedStop') {
            $owned = Start-Process -FilePath 'powershell.exe' -ArgumentList @(
                '-NoProfile', '-Command', 'Start-Sleep -Seconds 60'
            ) -WindowStyle Hidden -PassThru
            Stop-Process -Id $owned.Id -Force
            $owned.WaitForExit()
            $owned.Refresh()
            if (-not (Test-OperatorTermination $owned.ExitCode)) {
                throw "本批进程的 Stop-Process 退出码 $($owned.ExitCode) 不能当成正常停止。"
            }
            Stop-OwnedProcessTree -ProcessId $owned.Id
        } else {
            $owned = Start-Process -FilePath 'powershell.exe' -ArgumentList @(
                '-NoProfile', '-Command', 'exit 1'
            ) -WindowStyle Hidden -PassThru -Wait
            $owned.Refresh()
            if (Test-OperatorTermination $owned.ExitCode) {
                throw "退出码 $($owned.ExitCode) 不应视为操作者停止。"
            }
        }
        if ($decoy.HasExited) {
            throw "无关进程被清理，pid=$($decoy.Id)。"
        }
        $busy = netstat -ano -p tcp | Select-String -Pattern ':8000\s+.*LISTENING|:5173\s+.*LISTENING'
        if ($busy) {
            throw "自测占用了受保护端口。"
        }
    } finally {
        if (-not $decoy.HasExited) {
            Stop-Process -Id $decoy.Id -Force -ErrorAction SilentlyContinue
        }
    }
    if ($Mode -eq 'UnexpectedExit') {
        exit 1
    }
    Write-Host "正常停止分类通过，未结束无关进程。"
    exit 0
}

if ($LifecycleSelfTest) {
    Invoke-LifecycleSelfTest -Mode $LifecycleSelfTest
}

if (-not (Test-LoopbackPortFree -Port $ApiPort)) {
    throw "回环端口 $ApiPort 已被占用。脚本不会改用其他端口，请先停止占用进程后重试。"
}
if (-not (Test-LoopbackPortFree -Port $WebPort)) {
    throw "回环端口 $WebPort 已被占用。脚本不会改用其他端口，请先停止占用进程后重试。"
}

$python = Join-Path $repoRoot 'backend\.venv\Scripts\python.exe'
if (-not (Test-Path -LiteralPath $python)) {
    throw "未找到 backend\.venv\Scripts\python.exe。请先运行 .\scripts\bootstrap.ps1。脚本不会下载模型，也不会改用系统 Python。"
}

$env:MINDMATE_API_PORT = "$ApiPort"
$env:MINDMATE_PROVIDER_MODE = 'mock'
$env:MINDMATE_ALLOWED_ORIGINS = '["http://127.0.0.1:' + $WebPort + '","http://localhost:' + $WebPort + '"]'
if ($DataDir) {
    $env:MINDMATE_DATA_DIR = (Resolve-Path -LiteralPath $DataDir).Path
}

try {
    $script:backendProcess = Start-Process -FilePath $python -ArgumentList @(
        '-m', 'uvicorn', 'mindmate.main:app',
        '--host', '127.0.0.1',
        '--port', "$ApiPort"
    ) -WorkingDirectory (Join-Path $repoRoot 'backend') -PassThru -WindowStyle Hidden

    $healthDeadline = (Get-Date).AddSeconds(40)
    $healthy = $false
    while ((Get-Date) -lt $healthDeadline) {
        if ($script:backendProcess.HasExited) {
            throw "后端进程已退出，退出码 $($script:backendProcess.ExitCode)。未切换端口或 Provider。"
        }
        try {
            $health = Invoke-RestMethod -Uri "http://127.0.0.1:$ApiPort/api/v1/health" -TimeoutSec 2
            if ($health.status -eq 'ok') {
                $healthy = $true
                break
            }
        } catch {
            Start-Sleep -Milliseconds 300
        }
    }
    if (-not $healthy) {
        throw "后端在 http://127.0.0.1:$ApiPort 未在 40 秒内就绪。"
    }

    if ($KnowledgeBaseId) {
        $readyDeadline = (Get-Date).AddSeconds(60)
        $modelReady = $false
        $indexReady = $false
        while ((Get-Date) -lt $readyDeadline) {
            $model = Invoke-RestMethod -Uri "http://127.0.0.1:$ApiPort/api/v1/embedding-model" -TimeoutSec 5
            if ($model.state -in @('MISSING', 'MISSING_OFFLINE', 'FAILED', 'CORRUPT')) {
                throw "运行中的 Embedding 模型不可用：state=$($model.state) error=$($model.error_code)。未下载模型，也未切换模型。"
            }
            $fingerprintMatches = (-not $ExpectedFingerprint) -or ($model.artifact_fingerprint -eq $ExpectedFingerprint)
            if ($model.state -eq 'READY' -and $fingerprintMatches) {
                $modelReady = $true
            }
            $index = Invoke-RestMethod -Uri "http://127.0.0.1:$ApiPort/api/v1/knowledge-bases/$KnowledgeBaseId/index-status" -TimeoutSec 5
            $versionMatches = (-not $ExpectedIndexVersionId) -or ($index.active_index_version_id -eq $ExpectedIndexVersionId)
            if ($index.status -eq 'READY' -and $index.active_index_version_status -eq 'READY' -and $versionMatches) {
                $indexReady = $true
            }
            if ($modelReady -and $indexReady) {
                break
            }
            Start-Sleep -Milliseconds 400
        }
        if (-not $modelReady -or -not $indexReady) {
            throw "演示启动前未确认模型 READY 与知识库 READY。modelReady=$modelReady indexReady=$indexReady。未重建不受控数据。"
        }
        Write-Host "运行中模型指纹已核对，知识库 $KnowledgeBaseId 为 READY。"
    }

    $npm = (Get-Command npm.cmd -ErrorAction SilentlyContinue)
    if (-not $npm) {
        $npm = Get-Command npm -ErrorAction Stop
    }
    $script:frontendProcess = Start-Process -FilePath $npm.Source -ArgumentList @(
        'run', 'dev', '--', '--host', '127.0.0.1', '--port', "$WebPort", '--strictPort'
    ) -WorkingDirectory (Join-Path $repoRoot 'frontend') -PassThru -WindowStyle Hidden

    $webDeadline = (Get-Date).AddSeconds(40)
    $webReady = $false
    while ((Get-Date) -lt $webDeadline) {
        if ($script:frontendProcess.HasExited) {
            throw "前端进程已退出，退出码 $($script:frontendProcess.ExitCode)。"
        }
        try {
            $web = Invoke-WebRequest -Uri "http://127.0.0.1:$WebPort/" -TimeoutSec 2 -UseBasicParsing
            if ($web.StatusCode -ge 200 -and $web.StatusCode -lt 500) {
                $webReady = $true
                break
            }
        } catch {
            Start-Sleep -Milliseconds 300
        }
    }
    if (-not $webReady) {
        throw "前端在 http://127.0.0.1:$WebPort 未在 40 秒内就绪。"
    }

    $pageUrl = "http://127.0.0.1:$WebPort/"
    if ($KnowledgeBaseId) {
        $pageUrl = "http://127.0.0.1:$WebPort/knowledge-bases/$KnowledgeBaseId"
    }
    Write-Host "API  http://127.0.0.1:$ApiPort"
    Write-Host "Web  $pageUrl"
    Write-Host "Provider 固定为 Mock。按 Ctrl+C，或结束本次启动的后端/前端进程，即正常停止。"
    Write-Host "Stop-Process 产生的退出码 -1 视为正常停止；其他退出码仍视为失败。不会结束系统浏览器，也不会清理其他端口。"
    if ($OpenBrowser) {
        Start-Process $pageUrl
    }
    $script:consoleCancel = $false
    try {
        [Console]::TreatControlCAsInput = $true
        $script:consoleCancel = $true
    } catch {
        $script:consoleCancel = $false
    }
    while (-not $script:backendProcess.HasExited -and -not $script:frontendProcess.HasExited) {
        if ($script:consoleCancel) {
            try {
                if ([Console]::KeyAvailable) {
                    $key = [Console]::ReadKey($true)
                    $ctrl = ($key.Modifiers -band [ConsoleModifiers]::Control) -eq [ConsoleModifiers]::Control
                    if ($ctrl -and $key.Key -eq [ConsoleKey]::C) {
                        $script:stopRequested = $true
                        break
                    }
                }
            } catch {
                $script:consoleCancel = $false
            }
        }
        Start-Sleep -Milliseconds 500
    }
    if (-not $script:stopRequested) {
        $script:backendProcess.Refresh()
        $script:frontendProcess.Refresh()
        $backendCode = if ($script:backendProcess.HasExited) { $script:backendProcess.ExitCode } else { $null }
        $frontendCode = if ($script:frontendProcess.HasExited) { $script:frontendProcess.ExitCode } else { $null }
        if ((Test-OperatorTermination $backendCode) -or (Test-OperatorTermination $frontendCode)) {
            $script:stopRequested = $true
        } elseif ($null -ne $backendCode) {
            $script:abnormalMessage = "后端已退出，退出码 $backendCode。"
        } elseif ($null -ne $frontendCode) {
            $script:abnormalMessage = "前端已退出，退出码 $frontendCode。"
        }
    }
} catch [System.Management.Automation.PipelineStoppedException] {
    $script:stopRequested = $true
    $script:abnormalMessage = $null
} finally {
    Stop-StartedServers
}
if ($script:abnormalMessage) {
    throw $script:abnormalMessage
}
if ($script:stopRequested) {
    Write-Host "已正常停止本次启动的后端和前端。"
}
