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

$RepoRoot = Split-Path -Parent $PSScriptRoot
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

# ── 3. EPCD UI 插件：复制部署（免管理员，幂等）──────────────────────────────
#     插件 canonical 在 plugins/epcd-ui-persist/lib/，DSH 实际加载的两处
#     packages/epcd-ui-plugin/lib/ 与 node_modules/epcd-ui-plugin/lib/ 都复制到位。
#     说明：Windows 创建 SymbolicLink 需要管理员或开发者模式（普通用户报
#     "需要管理员权限"）；这里改用 Copy-Item 覆盖 lib/*.js，与脚本其余复制步骤一致。
#     改插件后重跑本脚本即可同步（三处 lib 一致）。
$PluginSrc = Join-Path $RepoRoot 'plugins\epcd-ui-persist'
$LibSrc    = Join-Path $PluginSrc 'lib'
function Copy-EpcdLib {
    param([string]$Dst)
    New-Item -ItemType Directory -Force -Path (Join-Path $Dst 'lib') | Out-Null
    Get-ChildItem -Path $LibSrc -Filter '*.js' -File | ForEach-Object {
        $target = Join-Path $Dst ('lib\' + $_.Name)
        # 目标若是旧软链/硬链/实体，一律先删再复制成全新实体，保证内容与 canonical 一致
        Remove-Item $target -Force -Recurse -ErrorAction SilentlyContinue
        Copy-Item $_.FullName $target -Force
    }
}
# 两处 DSH 实际加载的位置都复制到位（packages = pnpm file: 依赖源，node_modules = 解析落点）
Copy-EpcdLib (Join-Path $ProfileDst 'packages\epcd-ui-plugin')
Copy-EpcdLib (Join-Path $ProfileDst 'node_modules\epcd-ui-plugin')
# package.json 三处实体同步（canonical → packages → node_modules），内容一致
Copy-Item (Join-Path $PluginSrc 'package.json') (Join-Path $ProfileDst 'packages\epcd-ui-plugin\package.json') -Force
Copy-Item (Join-Path $PluginSrc 'package.json') (Join-Path $ProfileDst 'node_modules\epcd-ui-plugin\package.json') -Force
Write-Host "  [3/4] epcd-ui-plugin -> packages/ 与 node_modules/（lib 复制 + package.json 三处同步）"

# ── 3.5 补 @deepseek-ai/dsh-tools junction（修复 ERR_MODULE_NOT_FOUND）───────
#     epcd-ui-plugin 的 lib/index.js `import { defineTool } from "@deepseek-ai/dsh-tools"`，
#     而 dsh-tools 只声明为 peerDependency，DSH 模块 fallback 不把它放进 profile node_modules。
#     这里在仓库根 node_modules 建一个「目录 junction」指向 DSH 共享层：
#     目录 junction 无需管理员（symbolic link 才需要），效果等同软链且随 DSH 版本自动更新。
$SharedDep = Join-Path $DshHome 'profiles\node_modules\@deepseek-ai\dsh-tools'
if (Test-Path $SharedDep) {
    $RepoLink = Join-Path $RepoRoot 'node_modules\@deepseek-ai'
    New-Item -ItemType Directory -Force -Path $RepoLink | Out-Null
    $RepoLinkTarget = Join-Path $RepoLink 'dsh-tools'
    # 幂等且安全：已是正确 junction 则跳过；旧的 symlink/残留用 rmdir 只删链接本身（不跟进删共享层内容）
    $existing = Get-Item $RepoLinkTarget -ErrorAction SilentlyContinue
    if ($existing -and $existing.LinkType -ne 'Junction') {
        cmd /c rmdir "`"$RepoLinkTarget`"" 2>$null | Out-Null
    }
    if (-not (Test-Path $RepoLinkTarget)) {
        New-Item -ItemType Junction -Path $RepoLinkTarget -Target $SharedDep | Out-Null
    }
    Write-Host "  [3.5/4] @deepseek-ai/dsh-tools junction -> 共享层（仓库根 node_modules）"
} else {
    Write-Warning "  [3.5/4] 共享层未找到 $SharedDep，跳过；若启动仍报 dsh-tools，请先完整安装 dsh。"
}

# ── 4. 树外依赖（dsh-ssh，经 dsh plugin 转发 pnpm）────────────────────────
#     注：0.1.5-rc.1 起 DSH 内置右侧 sidebar，无需再装第三方 dsh-better-sidebar。
#     幂等：若 dsh-ssh 已在 profile node_modules 就绪且 package.json 已声明，则跳过 pnpm。
$SshPkgDst = Join-Path $ProfileDst 'node_modules\@linxin666\dsh-ssh'
$ProfilePkgJson = Join-Path $ProfileDst 'package.json'
$SshDeclared = (Test-Path $ProfilePkgJson) -and ((Get-Content $ProfilePkgJson -Raw) -match '"@linxin666/dsh-ssh"')
if ((Test-Path $SshPkgDst) -and $SshDeclared) {
    Write-Host "  [4/4] dsh-ssh 已就绪（跳过 pnpm add，幂等）"
} else {
    # 定位 dsh bin：优先 APPDATA 默认路径，其次 npm 全局前缀。
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
}

Write-Host ""
Write-Host "部署完成。" -ForegroundColor Green
Write-Host "  下一步（一次性）：编辑/确认 $RepoRoot\epcd-configs.json 的 host/port/user/identityFile/pkg/technology/workDirRoot"
Write-Host "  启动：npx @deepseek-ai/dsh --profile epcd --port 8091  （headless 服务器加 EPCD_HOST=0.0.0.0 前缀）"
Write-Host "  浏览器：http://127.0.0.1:8091"