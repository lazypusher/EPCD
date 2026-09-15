#!/usr/bin/env bash
# ============================================================================
# EPCD DSH Agent —— Nginx 反向代理入口（方案 A：单一端口 loopback 收敛）
#
# 解决 dsh-ssh 的 loopback-only fence 导致的「内网直连 DSH 时 SSH tab 报
# forbidden」问题：用 Nginx 在服务器本机做单一入口（对外 8080），把请求
# proxy_pass 到 127.0.0.1:8091，并对 /api/dsh-ssh/ 路由改写 Host 为 loopback，
# 从而无需每个用户手动开 SSH 隧道。
#
# 用法（在部署服务器上、仓库根目录执行）：
#   sudo bash deploy/setup-nginx.sh
#
# 前置：
#   - 已按 install-dsh-agent.sh 部署好 profile
#   - DSH 以 `EPCD_HOST=0.0.0.0 npx @deepseek-ai/dsh --profile epcd --port 8091` 启动
#   - 本脚本会尝试安装 nginx（yum/dnf/apt 自动探测），需 root/sudo
#
# 幂等：重复执行只覆盖站点配置并 reload，不重复安装已存在的 nginx。
#
# 注意：DSH 上游固定为本机 127.0.0.1:8091（loopback fence 要求），仅对外端口
#   （EPCD_NGINX_PORT，默认 8080）可调。若 DSH 端口不是 8091，请同步改
#   deploy/nginx/epcd-agent.conf 里两处 8091。
# ============================================================================

set -euo pipefail

REPO_ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
CONF_SRC="$REPO_ROOT/deploy/nginx/epcd-agent.conf"
CONF_DST="/etc/nginx/conf.d/epcd-agent.conf"
LISTEN_PORT="${EPCD_NGINX_PORT:-8080}"

echo "== EPCD Nginx 反代入口部署 =="
echo "  对外端口: $LISTEN_PORT"
echo "  上游 DSH: http://127.0.0.1:8091（固定，见脚本头注释）"
echo "  配置源:   $CONF_SRC"

# ── 1. 安装 nginx（若未装）───────────────────────────────────────────────
if command -v nginx >/dev/null 2>&1; then
  echo "  [1/3] nginx 已安装：$(nginx -v 2>&1)"
else
  echo "  [1/3] 未找到 nginx，尝试安装…"
  if command -v dnf >/dev/null 2>&1; then
    dnf install -y nginx
  elif command -v yum >/dev/null 2>&1; then
    yum install -y nginx
  elif command -v apt-get >/dev/null 2>&1; then
    apt-get update && apt-get install -y nginx
  else
    echo "  [1/3] 错误：无法识别包管理器（尝试 dnf/yum/apt-get）。请手动安装 nginx 后重跑。" >&2
    exit 1
  fi
  echo "  [1/3] nginx 已安装：$(nginx -v 2>&1)"
fi

# ── 2. 写入站点配置（幂等覆盖；只替换对外 listen 端口）───────────────────
mkdir -p /etc/nginx/conf.d
sed "s/listen 8080;/listen ${LISTEN_PORT};/" "$CONF_SRC" > "$CONF_DST"
echo "  [2/3] 站点配置已写入 $CONF_DST"

# ── 3. 校验并 reload（失败则不中断 nginx 现有服务）───────────────────────
if nginx -t 2>/dev/null; then
  if systemctl is-active --quiet nginx 2>/dev/null; then
    systemctl reload nginx
    echo "  [3/3] nginx reload 完成"
  else
    systemctl enable --now nginx 2>/dev/null || nginx
    echo "  [3/3] nginx 已启动"
  fi
else
  echo "  [3/3] 错误：nginx -t 校验失败，配置未生效，请检查 $CONF_DST" >&2
  exit 1
fi

echo ""
echo "部署完成。"
echo "  现在用户访问：http://<服务器内网IP>:${LISTEN_PORT}"
echo "  （SSH tab / 页面鉴权均已通过 loopback fence + LAN 信任，无需手动 SSH 隧道）"
echo "  安全提醒：仍建议在 Nginx 层加 TLS/来源限制，DSH 自身不带鉴权与 TLS。"