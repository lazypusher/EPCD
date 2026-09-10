#!/usr/bin/env bash
# ============================================================================
# EPCD 形态 A（DSH Agent）一键部署脚本 —— Linux / CentOS 版
#
# 与 deploy/install-dsh-agent.ps1（Windows）对称：把仓库里的 EPCD profile /
# agent preset / UI 插件复制到本机 DSH home，并安装树外依赖。
#
# 前置条件：
#   - 已全局安装 DeepSeek Harness（`dsh` 命令在 PATH 可用）
#   - 已 clone 本仓库（脚本相对仓库根定位源文件）
#   - Linux（含 CentOS 7）+ bash；DSH home 按 ~/.dsh
#
# 用法（仓库根目录执行）：
#   bash deploy/install-dsh-agent.sh
# ============================================================================

set -euo pipefail

REPO_ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
DSH_HOME="${DSH_HOME:-$HOME/.dsh}"

echo "== EPCD 形态 A 部署（Linux）=="
echo "  仓库根: $REPO_ROOT"
echo "  DSH home: $DSH_HOME"

# ── 1. profile：权威源 = plugins/epcd-ui-persist/deploy/（完整 cordis.patch.yml
#      含 epcd-ui-plugin 挂载 + 存储隔离 + branding）+ platform-dsh/profile/ 的
#      favicon 与 pnpm-workspace（deploy 目录缺这两份）。
#      注：platform-dsh/profile/cordis.patch.yml 是旧版（缺 epcd-ui-plugin insert
#      与存储隔离），不要用它。
PROFILE_DST="$DSH_HOME/profiles/epcd"
DEPLOY_SRC="$REPO_ROOT/plugins/epcd-ui-persist/deploy"
PFP_SRC="$REPO_ROOT/platform-dsh/profile"
mkdir -p "$PROFILE_DST"
cp "$DEPLOY_SRC/cordis.patch.yml"       "$PROFILE_DST/"
cp "$DEPLOY_SRC/epcd-brand.mjs"         "$PROFILE_DST/"
cp "$DEPLOY_SRC/profile-package.json"   "$PROFILE_DST/package.json"
cp "$PFP_SRC/epcd-favicon.svg"          "$PROFILE_DST/"
cp "$PFP_SRC/pnpm-workspace.yaml"       "$PROFILE_DST/"
echo "  [1/4] profile -> $PROFILE_DST（完整版 cordis.patch + branding + package.json）"

# ── 2. agent preset（persona + 精简工具集）─────────────────────────────────
PRESET_DST="$DSH_HOME/.agent-presets/epcd"
mkdir -p "$PRESET_DST"
cp -r "$REPO_ROOT/platform-dsh/agent-preset/." "$PRESET_DST/"
echo "  [2/4] agent preset -> $PRESET_DST"

# ── 3. EPCD UI 插件（三处同步：packages 源 + node_modules + package.json）───
PLUGIN_SRC="$REPO_ROOT/plugins/epcd-ui-persist"
PKG_DST="$PROFILE_DST/packages/epcd-ui-plugin"
NM_DST="$PROFILE_DST/node_modules/epcd-ui-plugin"
mkdir -p "$PKG_DST" "$NM_DST"
cp "$PLUGIN_SRC/package.json" "$PKG_DST/"
cp -r "$PLUGIN_SRC/lib"        "$PKG_DST/"
cp "$PLUGIN_SRC/package.json" "$NM_DST/"
cp -r "$PLUGIN_SRC/lib"        "$NM_DST/"
echo "  [3/4] epcd-ui-plugin -> packages/ 与 node_modules/（三处同步完成两处）"

# ── 4. 树外依赖（dsh-ssh，经 dsh plugin 转发 pnpm）─────────────────────────
#     注：0.1.5-rc.1 起 DSH 内置右侧 sidebar，无需再装第三方 dsh-better-sidebar。
if command -v dsh >/dev/null 2>&1; then
  dsh plugin --profile epcd add "@linxin666/dsh-ssh"
  echo "  [4/4] dsh-ssh 已安装"
else
  echo "  [4/4] 未找到 dsh 命令，跳过依赖安装。请手动执行：" >&2
  echo "        dsh plugin --profile epcd add '@linxin666/dsh-ssh'" >&2
fi

echo ""
echo "部署完成。"
echo "  下一步（一次性）：编辑/确认 $REPO_ROOT/epcd-config.json 的 ssh/pkg/technology/workDirRoot"
echo "  启动（headless 服务器需绑 0.0.0.0，见 deploy/README.md）：dsh --profile epcd --port 8091"
echo "  浏览器（局域网）：http://<服务器IP>:8091"