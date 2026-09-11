# ============================================================================
# EPCD 远程访问一键脚本（本机专用，不进 git —— 已加入 .gitignore）
#
# 三步完成「本机浏览器 → 远程 EPCD」的复现：
#   1. 启动远程 EPCD（若未运行）
#   2. 建 SSH 隧道：本机 127.0.0.1:8092 → 远程 127.0.0.1:8091
#   3. 取最新 token 并打印访问 URL
#
# 用法（本机 PowerShell）：
#   .\epcd-remote-access.ps1            # 启动远程 + 建隧道 + 打印 URL
#   .\epcd-remote-access.ps1 -Stop      # 关闭远程 EPCD + 断开隧道
#   .\epcd-remote-access.ps1 -Url       # 仅取当前 token 打印 URL
# ============================================================================

param(
    [switch]$Stop,
    [switch]$Url
)

$ErrorActionPreference = 'Stop'

# ── 配置 ────────────────────────────────────────────────────────────────────
$Server     = 'eada@192.168.20.109'
$RemotePort = '8091'
$LocalPort  = '8092'

# 远程操作命令（单引号原样传给远程 bash）
$RemoteStart = 'cd ~/epcd && setsid env EPCD_HOST=0.0.0.0 npx @deepseek-ai/dsh --profile epcd --port 8091 --no-open > ~/epcd-dsh.log 2>&1 < /dev/null &'
$RemoteStop  = 'PID=$(pgrep -f "dsh --profile epcd --port 8091" | head -1); [ -n "$PID" ] && kill $PID 2>/dev/null; NPM=$(pgrep -f "npm exec @deepseek-ai/dsh" | head -1); [ -n "$NPM" ] && kill $NPM 2>/dev/null; exit 0'
$RemoteCheck = 'ss -tlnp 2>/dev/null | grep -q ":8091" && echo yes || echo no'
$RemoteToken = 'grep -oE "token=[A-Za-z0-9_-]+" ~/epcd-dsh.log 2>/dev/null | tail -1'

# ── 辅助函数 ────────────────────────────────────────────────────────────────
function Get-RemoteToken { ssh $Server $RemoteToken 2>$null }
function Test-RemoteRunning { (ssh $Server $RemoteCheck 2>$null) -match 'yes' }

function Stop-LocalTunnel {
    Get-Process ssh -ErrorAction SilentlyContinue |
        Where-Object { $_.CommandLine -match "${LocalPort}:127.0.0.1" } |
        ForEach-Object { Stop-Process -Id $_.Id -Force -ErrorAction SilentlyContinue }
}

# ── 关闭远程 ────────────────────────────────────────────────────────────────
if ($Stop) {
    Write-Host '关闭远程 EPCD ...' -ForegroundColor Yellow
    ssh $Server $RemoteStop 2>&1 | Out-Null
    Stop-LocalTunnel
    Write-Host '已关闭远程 EPCD + 断开隧道' -ForegroundColor Green
    exit 0
}

# ── 仅取 URL ────────────────────────────────────────────────────────────────
if ($Url) {
    $token = Get-RemoteToken
    if ($token) { Write-Host "http://127.0.0.1:${LocalPort}/?$token" -ForegroundColor Green }
    else { Write-Host '未取到 token（远程可能未运行）' -ForegroundColor Yellow }
    exit 0
}

# ── 1. 启动远程（若未运行）─────────────────────────────────────────────────
if (Test-RemoteRunning) {
    Write-Host '[1/3] 远程 EPCD 已在运行' -ForegroundColor Cyan
} else {
    Write-Host '[1/3] 启动远程 EPCD ...' -ForegroundColor Cyan
    ssh $Server $RemoteStart 2>&1 | Out-Null
    $ready = $false
    for ($i = 0; $i -lt 20; $i++) {
        Start-Sleep -Seconds 2
        if (Test-RemoteRunning) { $ready = $true; break }
    }
    if (-not $ready) {
        Write-Host '远程 EPCD 启动失败/超时，请查远程 ~/epcd-dsh.log' -ForegroundColor Red
        exit 1
    }
    Write-Host '      远程 EPCD 已启动' -ForegroundColor Green
}

# ── 2. 建 SSH 隧道 ──────────────────────────────────────────────────────────
Write-Host "[2/3] 建 SSH 隧道 127.0.0.1:${LocalPort} -> 远程 ${RemotePort} ..." -ForegroundColor Cyan
Stop-LocalTunnel
Start-Process -FilePath 'ssh' -ArgumentList '-L', "${LocalPort}:127.0.0.1:${RemotePort}", $Server, '-N' -WindowStyle Hidden
Start-Sleep -Seconds 1
Write-Host '      隧道已建' -ForegroundColor Green

# ── 3. 取 token + 打印 URL ─────────────────────────────────────────────────
Write-Host '[3/3] 取 token ...' -ForegroundColor Cyan
Start-Sleep -Seconds 1
$token = Get-RemoteToken
if ($token) {
    Write-Host ''
    Write-Host '复现访问地址：' -ForegroundColor Green
    Write-Host "   http://127.0.0.1:${LocalPort}/?$token" -ForegroundColor White
    Write-Host ''
    Write-Host '首次访问带 ?token= ，DSH 自动签发 cookie 并跳转首页。' -ForegroundColor DarkGray
    Write-Host 'ssh tab / 模型 tab / 设置 因「经隧道=loopback 来源」正常工作。' -ForegroundColor DarkGray
    Write-Host '断开：任务管理器结束 ssh 进程，或运行本脚本 -Stop' -ForegroundColor DarkGray
} else {
    Write-Host '未取到 token，请稍后运行 -Url 重试' -ForegroundColor Yellow
}

# 防止双击运行时窗口闪退
Write-Host ''
Write-Host '按任意键关闭...' -ForegroundColor DarkGray
$null = $Host.UI.RawUI.ReadKey('NoEcho,IncludeKeyDown')