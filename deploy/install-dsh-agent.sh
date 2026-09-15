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

# ── 1. profile：权威源 = epcd-dsh/plugin/deploy/（完整 cordis.patch.yml
#      含 epcd-ui-plugin 挂载 + 存储隔离 + branding + favicon/pnpm-workspace + logo）。
PROFILE_DST="$DSH_HOME/profiles/epcd"
DEPLOY_SRC="$REPO_ROOT/epcd-dsh/plugin/deploy"
mkdir -p "$PROFILE_DST"
cp "$DEPLOY_SRC/cordis.patch.yml"       "$PROFILE_DST/"
cp "$DEPLOY_SRC/epcd-brand.mjs"         "$PROFILE_DST/"
cp "$DEPLOY_SRC/epcd-ui-lock.mjs"       "$PROFILE_DST/"
cp "$DEPLOY_SRC/epcd-workspace.mjs"     "$PROFILE_DST/"
cp "$DEPLOY_SRC/epcd-logo.png"          "$PROFILE_DST/"
cp "$DEPLOY_SRC/profile-package.json"   "$PROFILE_DST/package.json"
cp "$DEPLOY_SRC/epcd-favicon.svg"       "$PROFILE_DST/"
cp "$DEPLOY_SRC/pnpm-workspace.yaml"    "$PROFILE_DST/"
echo "  [1/5] profile -> $PROFILE_DST（完整版 cordis.patch + branding + package.json）"

# ── 2. agent preset（persona + 精简工具集）─────────────────────────────────
PRESET_DST="$DSH_HOME/.agent-presets/epcd"
mkdir -p "$PRESET_DST"
cp -r "$REPO_ROOT/epcd-dsh/agent-preset/." "$PRESET_DST/"
echo "  [2/5] agent preset -> $PRESET_DST"

# ── 3. EPCD UI 插件：软链部署（单一事实源，幂等）────────────────────────────
#     插件采用「单一事实源 + 软链」架构：canonical 在 epcd-dsh/plugin/lib/，
#     而 profile 的 packages/epcd-ui-plugin/lib/ 与 node_modules/epcd-ui-plugin/lib/
#     下的 index.js/client.js 都是软链指向 canonical，改 canonical 即刻生效、无需三处同步。
#     package.json 不是软链，三处各持一份实体（内容一致），此处用 cp 同步。
#     幂等：重复执行不覆盖已有软链、不产生 "same file" 警告、不破坏 pnpm 布局。
PLUGIN_SRC="$REPO_ROOT/epcd-dsh/plugin"
LIB_SRC="$PLUGIN_SRC/lib"
# 把 canonical 的 lib 文件以「软链」镜像到目标目录（幂等：已是正确软链则跳过，否则修正）。
relink_lib() {
  local dst="$1"
  mkdir -p "$dst/lib"
  local f t
  shopt -s nullglob   # canonical 无 .js 时 glob 为空，避免字面量 path 出错
  for f in "$LIB_SRC"/*.js; do
    t="$dst/lib/$(basename "$f")"
    if [ -L "$t" ] && [ "$(readlink -f "$t")" = "$(readlink -f "$f")" ]; then
      continue                        # 已是正确软链，跳过
    fi
    rm -f "$t"                        # 修正错误的软链 / 实体副本
    ln -s "$f" "$t"
  done
  shopt -u nullglob
}
# 两处 DSH 实际加载的位置都镜像为软链（packages = pnpm file: 依赖源，node_modules = 解析落点）
relink_lib "$PROFILE_DST/packages/epcd-ui-plugin"
relink_lib "$PROFILE_DST/node_modules/epcd-ui-plugin"
# package.json 三处实体同步（canonical → packages → node_modules），内容一致
cp "$PLUGIN_SRC/package.json" "$PROFILE_DST/packages/epcd-ui-plugin/package.json"
cp "$PLUGIN_SRC/package.json" "$PROFILE_DST/node_modules/epcd-ui-plugin/package.json"
echo "  [3/5] epcd-ui-plugin -> packages/ 与 node_modules/（lib 软链 + package.json 三处实体同步）"

# ── 3.5 补 @deepseek-ai/dsh-tools 软链（修复 ERR_MODULE_NOT_FOUND）──────────
#     epcd-ui-plugin 的 lib/index.js `import { defineTool } from "@deepseek-ai/dsh-tools"`，
#     而 dsh-tools 只声明为 peerDependency。DSH 模块 fallback 因「该包已存在于 dsh 本体依赖树」
#     而跳过把它软链进 profile 专属 node_modules，导致插件 import 时解析不到。
#     插件 lib 是软链（realpath 落到仓库 canonical），Node 从仓库根路径向上查 node_modules，
#     故只需在仓库根 node_modules 建这一处软链。目标指向 DSH 维护的共享层
#     （profiles/node_modules，随 DSH 版本自动更新），版本始终与 DSH 本体一致。
SHARED_DEP="$DSH_HOME/profiles/node_modules/@deepseek-ai/dsh-tools"
if [ -e "$SHARED_DEP" ]; then
  REPO_LINK="$REPO_ROOT/node_modules/@deepseek-ai"
  mkdir -p "$REPO_LINK"
  ln -sfn "$SHARED_DEP" "$REPO_LINK/dsh-tools"
  echo "  [3.5/5] @deepseek-ai/dsh-tools 软链 -> 共享层（仓库根 node_modules）"
else
  echo "  [3.5/5] 警告：共享层未找到 $SHARED_DEP，跳过软链；若启动仍报 dsh-tools，请先完整安装 dsh。" >&2
fi

# ── 4. 树外依赖（dsh-ssh，经 dsh plugin 转发 pnpm）─────────────────────────
#     注：0.1.5-rc.1 起 DSH 内置右侧 sidebar，无需再装第三方 dsh-better-sidebar。
#     dsh plugin 本质 = 在 profile 目录跑 pnpm add。幂等：若 dsh-ssh 已在 profile
#     node_modules 就绪且 package.json 已声明，则跳过 pnpm（避免重复解析与 supply-chain 校验）。
SSH_PKG_DST="$PROFILE_DST/node_modules/@linxin666/dsh-ssh"
if [ -d "$SSH_PKG_DST" ] && grep -q '"@linxin666/dsh-ssh"' "$PROFILE_DST/package.json" 2>/dev/null; then
  echo "  [4/5] dsh-ssh 已就绪（跳过 pnpm add，幂等）"
elif command -v dsh >/dev/null 2>&1; then
  dsh plugin --profile epcd add "@linxin666/dsh-ssh"
  echo "  [4/5] dsh-ssh 已安装"
elif command -v npx >/dev/null 2>&1; then
  npx @deepseek-ai/dsh plugin --profile epcd add "@linxin666/dsh-ssh"
  echo "  [4/5] dsh-ssh 已安装（经 npx）"
else
  echo "  [4/5] 未找到 dsh / npx 命令，跳过依赖安装。请手动执行：" >&2
  echo "        npx @deepseek-ai/dsh plugin --profile epcd add '@linxin666/dsh-ssh'" >&2
  echo "        （需先确保 pnpm 在 PATH：corepack enable pnpm 或 npm i -g pnpm）" >&2
fi

# ── 5. backend Python 环境（uv sync）─────────────────────────────────────────
#     epcd_cli 工具 spawn backend/.venv 的 python 跑 epcd_agent.cli，需 .venv 就绪。
#     uv 按 uv.lock 建 3.13 环境（服务器系统 Python 3.9 也由 uv 自动下载管理）。
if command -v uv >/dev/null 2>&1; then
  (cd "$REPO_ROOT/backend" && uv sync)
  echo "  [5/5] backend Python 环境已就绪（uv sync）"
else
  echo "  [5/5] 未找到 uv，跳过 backend 环境。请手动执行：" >&2
  echo "        安装 uv：curl -LsSf https://astral.sh/uv/install.sh | sh" >&2
  echo "        然后：cd backend && uv sync" >&2
fi

echo ""
echo "部署完成。"
echo "  下一步（一次性）：编辑/确认 $REPO_ROOT/epcd-configs.json 的 host/port/user/identityFile/pkg/technology/workDirRoot"
echo "  启动（headless 服务器需绑 0.0.0.0，EPCD_WORKSPACE 固定工作区为仓库根）："
echo "    EPCD_HOST=0.0.0.0 EPCD_WORKSPACE=$REPO_ROOT npx @deepseek-ai/dsh --profile epcd --port 8091"
echo ""
echo "  内网访问建议（解决 dsh-ssh loopback-only，SSH tab 直连会 403）："
echo "    sudo bash deploy/setup-nginx.sh    # 安装 Nginx 反代入口（对外 8080）"
echo "    然后用户访问 http://<服务器内网IP>:8080（详见 deploy/README.md 远程访问章节）"