# ============================================================================
# EPCD 形态 A（DSH Agent）一键部署脚本
#
# 把仓库里的 EPCD profile / agent preset / UI 插件复制到本机 DSH home，
# 并安装树外依赖（dsh-ssh / epcd-ui-plugin）。
#
# 前置条件：
#   - 已全局安装 DeepSeek Harness（`dsh` 命令可用）
#   - 已 clone 本仓库（脚本会相对仓库根定位源文件）
#   - Windows + PowerShell（DSH home 按 $env:USERPROFILE\.dsh）
#
# 用法（仓库根目录执行）：
#   powershell -ExecutionPolicy Bypass -File .\deploy\install-dsh-agent.ps1
# ============================================================================

$ErrorActionPreference = 'Stop'

$RepoRoot = Split-Path -Parent (Split-Path -Parent $PSScriptRoot)
$DshHome  = Join-Path $env:USERPROFILE '.dsh'

Write-Host "== EPCD 形态 A 部署 ==" -ForegroundColor Cyan
Write-Host "  仓库根: $RepoRoot"
Write-Host "  DSH home: $DshHome"

# ── 1. profile：权威源 = plugins/epcd-ui-persist/deploy/（完整 cordis.patch.yml
#     含 epcd-ui-plugin 挂载 + 存储隔离 + branding）+ platform-dsh/profile/ 的
#     favicon 与 pnpm-workspace（deploy 目录缺这两份）。
#     注：platform-dsh/profile/cordis.patch.yml 是旧版（缺 epcd-ui-plugin insert
#     与存储隔离），不要用它——否则部署出的 profile 没有 UI 插件。
$ProfileDst = Join-Path $DshHome 'profiles\epcd'
$DeploySrc  = Join-Path $RepoRoot 'plugins\epcd-ui-persist\deploy'
$PfpSrc     = Join-Path $RepoRoot 'platform-dsh\profile'
New-Item -ItemType Directory -Force -Path $ProfileDst | Out-Null
# 完整版 cordis.patch.yml / epcd-brand.mjs（覆盖旧版）
Copy-Item (Join-Path $DeploySrc 'cordis.patch.yml') $ProfileDst -Force
Copy-Item (Join-Path $DeploySrc 'epcd-brand.mjs')   $ProfileDst -Force
# profile-package.json 改名为 package.json（含 epcd-ui-plugin + dsh-ssh 依赖）
Copy-Item (Join-Path $DeploySrc 'profile-package.json') (Join-Path $ProfileDst 'package.json') -Force
# favicon + pnpm-workspace（deploy 目录没有，从 platform-dsh/profile 补）
Copy-Item (Join-Path $PfpSrc 'epcd-favicon.svg')    $ProfileDst -Force
Copy-Item (Join-Path $PfpSrc 'pnpm-workspace.yaml') $ProfileDst -Force
Write-Host "  [1/4] profile -> $ProfileDst（完整版 cordis.patch + branding + package.json）"

# ── 2. agent preset（persona + 精简工具集）─────────────────────────────────
$PresetSrc = Join-Path $RepoRoot 'platform-dsh\agent-preset'
$PresetDst = Join-Path $DshHome '.agent-presets\epcd'
New-Item -ItemType Directory -Force -Path $PresetDst | Out-Null
Copy-Item (Join-Path $PresetSrc '*') $PresetDst -Force -Recurse
Write-Host "  [2/4] agent preset -> $PresetDst"

# ── 3. EPCD UI 插件（三处同步：packages 源 + node_modules + package.json）──
#     canonical 源在 plugins/epcd-ui-persist/（lib/* + package.json）
$PluginSrc = Join-Path $RepoRoot 'plugins\epcd-ui-persist'
$PkgDst    = Join-Path $ProfileDst 'packages\epcd-ui-plugin'
$NmDst     = Join-Path $ProfileDst 'node_modules\epcd-ui-plugin'
New-Item -ItemType Directory -Force -Path $PkgDst | Out-Null
New-Item -ItemType Directory -Force -Path $NmDst  | Out-Null
Copy-Item (Join-Path $PluginSrc 'package.json') $PkgDst -Force
Copy-Item (Join-Path $PluginSrc 'lib') $PkgDst -Force -Recurse
# node_modules 侧只需解析用（与 packages 一侧保持一致）
Copy-Item (Join-Path $PluginSrc 'package.json') $NmDst -Force
Copy-Item (Join-Path $PluginSrc 'lib') $NmDst -Force -Recurse
Write-Host "  [3/4] epcd-ui-plugin -> packages/ 与 node_modules/（三处同步完成两处）"

# ── 4. 树外依赖（dsh-ssh，经 dsh plugin 转发 pnpm）────────────────────────
#     注：0.1.5-rc.1 起 DSH 内置右侧 sidebar，无需再装第三方 dsh-better-sidebar。
#     定位 dsh bin：优先 APPDATA 默认路径，其次 npm 全局前缀。
$DshBin = $null
$Candidate1 = Join-Path $env:APPDATA 'npm\node_modules\@deepseek-ai\dsh\lib\bin.js'
if (Test-Path $Candidate1) {
    $DshBin = $Candidate1
} else {
    $GlobalPrefix = npm prefix -g 2>$null
    if ($GlobalPrefix) {
        $Candidate2 = Join-Path $GlobalPrefix 'node_modules\@deepseek-ai\dsh\lib\bin.js'
        if (Test-Path $Candidate2) { $DshBin = $Candidate2 }
    }
}
if (-not $DshBin) {
    Write-Warning "  [4/4] 未找到 dsh bin.js，跳过依赖安装。请手动执行："
    Write-Warning "        npx @deepseek-ai/dsh plugin --profile epcd add '@linxin666/dsh-ssh'"
    Write-Warning "        （需先确保 pnpm 在 PATH）"
} else {
    node $DshBin plugin --profile epcd add "@linxin666/dsh-ssh"
    Write-Host "  [4/4] dsh-ssh 已安装"
}

Write-Host ""
Write-Host "部署完成。" -ForegroundColor Green
Write-Host "  下一步（一次性）：编辑/确认 $RepoRoot\epcd-config.json 的 ssh/pkg/technology/workDirRoot"
Write-Host "  启动：npx @deepseek-ai/dsh --profile epcd --port 8091  （headless 服务器加 EPCD_HOST=0.0.0.0 前缀）"
Write-Host "  浏览器：http://127.0.0.1:8091"