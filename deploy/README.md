# EPCD 部署指南（形态 A：DSH Agent）

把 EPCD 的 DSH 专用 profile / agent preset / UI 插件部署到目标机器，跑通
「`npx @deepseek-ai/dsh --profile epcd --port 8091`」这套 Agent 交互形态。

> 本指南只覆盖形态 A（依赖 DeepSeek Harness）。自研 Fastify 平台（形态 B）不在本仓库部署范围。

---

## 依赖清单

| 依赖 | 来源 | 是否入 git |
|------|------|-----------|
| DSH 运行时 | `@deepseek-ai/dsh` 0.1.5-rc.1（内置右侧 sidebar）+ `@linxin666/dsh-ssh` | —（外部 install） |
| profile | **`epcd-dsh/plugin/deploy/`（权威，含 cordis.patch / branding / favicon / pnpm-workspace / logo）** | ✅ 入库 |
| agent preset | `epcd-dsh/agent-preset/*` | ✅ 入库 |
| UI 插件 | `epcd-dsh/plugin/{package.json,lib/*}` | ✅ 入库 |
| 配置 | `epcd-config.json`（ssh/pkg/technology/workDirRoot） | ✅ 入库（本项目约定） |
| 编排 skill | `.dsh/skills/epcd-agent-flow/` | ✅ 入库 |

### DSH 的两种安装形态（本指南里所有命令都给出两种写法）

| 形态 | 安装 | 启动 / 管插件 |
|------|------|--------------|
| **全局安装** | `npm i -g @deepseek-ai/dsh@0.1.5-rc.1` | `dsh --profile epcd ...` / `dsh plugin ...` |
| **npx 免安装** | 无需安装（`npx` 自动缓存） | `npx @deepseek-ai/dsh --profile epcd ...` / `npx @deepseek-ai/dsh plugin ...` |

两条路**等价**，任选其一；混用时本指南已同时列出。需要注意：

- **`dsh plugin add` 本质是在 profile 目录里跑 `pnpm`**（`dsh` 内部转发给 pnpm），所以
  不论走全局还是 npx，**目标机都必须有 `pnpm`**（`corepack enable pnpm` 或
  `npm i -g pnpm`），否则装插件会报「pnpm not found」。
- **npx 陷阱**：若目标机「全局已装了旧版 dsh」，`npx @deepseek-ai/dsh`（不带版本号）
  会**优先复用全局旧版**而不是拉最新——升级后务必先
  `npm i -g @deepseek-ai/dsh@0.1.5-rc.1`，或显式写 `npx @deepseek-ai/dsh@0.1.5-rc.1`。

> ⚠ **profile 权威源只有一个：`epcd-dsh/plugin/deploy/`。**
> 该目录包含完整版 profile 的全部文件（cordis.patch.yml / epcd-brand.mjs /
> epcd-ui-lock.mjs / epcd-logo.png / epcd-favicon.svg / pnpm-workspace.yaml /
> profile-package.json），两个安装脚本（`.ps1` / `.sh`）均从此目录整体复制。
> 旧的 `platform-dsh/profile/` 目录已删除（其中的 cordis.patch.yml / epcd-brand.mjs
> 是缺 UI 插件与存储隔离的历史版本）。

---

## 一键部署

### Windows 本机

```powershell
powershell -ExecutionPolicy Bypass -File .\deploy\install-dsh-agent.ps1
```

### Linux / CentOS 部署服务器

```bash
bash deploy/install-dsh-agent.sh
```

两个脚本对称，都会依次：

1. 复制 profile（权威源 `epcd-dsh/plugin/deploy/` 的 cordis.patch.yml /
   epcd-brand.mjs / epcd-ui-lock.mjs / epcd-logo.png / epcd-favicon.svg /
   pnpm-workspace.yaml / profile-package.json）→ `~/.dsh/profiles/epcd/`
2. 复制 agent preset → `~/.dsh/.agent-presets/epcd/`
3. 同步 UI 插件 → `packages/epcd-ui-plugin/` + `node_modules/epcd-ui-plugin/`（三处同步）
4. 安装树外依赖 `@linxin666/dsh-ssh`（右侧 sidebar 由 DSH 0.1.5 内置，无需第三方）

完成后确认配置并启动：

```powershell
# Windows 本机（全局装了 dsh 用 dsh；未装全局用 npx）
dsh --profile epcd --port 8091
# 或
npx @deepseek-ai/dsh --profile epcd --port 8091
```

```bash
# Linux / CentOS（headless 需绑 0.0.0.0，见下）
dsh --profile epcd --port 8091
# 或
npx @deepseek-ai/dsh --profile epcd --port 8091
```

浏览器打开 `http://127.0.0.1:8091`（本机）或 `http://<服务器IP>:8091`（局域网）。

---

## headless 服务器：局域网访问（绑 0.0.0.0）

**DSH 的 `--host 0.0.0.0` 命令行 flag 会被 `dsh-web-app` 出于安全拒绝**（源码明确
reject：`--host 0.0.0.0 is intentionally not supported yet for safety`）。正确做法是
在 profile 的 `cordis.patch.yml` 里覆盖 `dsh-host-webserver` 的 `config.host`，用
**环境变量 `EPCD_HOST`** 控制（默认回落 `127.0.0.1`）：

- **不设 `EPCD_HOST`**（默认）→ `127.0.0.1`，仅回环，本机开发用（安全）。
- **设 `EPCD_HOST=0.0.0.0`** → 监听所有网卡，局域网其他主机可访问。

```bash
# CentOS 部署服务器：绑定所有网卡供局域网访问
EPCD_HOST=0.0.0.0 dsh --profile epcd --port 8091
# 或（未装全局 dsh 时）
EPCD_HOST=0.0.0.0 npx @deepseek-ai/dsh --profile epcd --port 8091

# 或写进 systemd unit / 启动脚本的 Environment
```

> ⚠ **安全警告**：DSH 本身**不带 TLS、鉴权或来源策略**。绑 `0.0.0.0` 等于把「可执行
> 任意代码的 agent harness」暴露到网络，务必套一层反向代理（Nginx/Caddy，加 HTTPS +
> 认证）或至少用防火墙限制来源网段，绝不能裸奔在公网。

> ⚠ **为什么不能直接局域网访问 ssh tab**：`@linxin666/dsh-ssh` 的 `/api/dsh-ssh/*`
> 端点带 **loopback-only trust fence**（源码 `loopback.ts`：要求请求 `remoteAddress`
> 是 127.0.0.1），因为 SSH 面板能在远程服务器执行任意命令。从局域网 IP 直接访问会
> 报 `forbidden: loopback-only`，模型 tab 报 `settings are unavailable`。**正确做法是
> 走 SSH 隧道**，让请求来源变成 loopback。

---

## 远程访问（SSH 隧道 + token，完整可用）

三步走通「本机浏览器 → 远程 EPCD」，且 ssh tab / 模型 tab / 设置都能正常用：

**① 服务器端启动**（登录部署服务器后）：

```bash
cd ~/epcd && EPCD_HOST=0.0.0.0 npx @deepseek-ai/dsh --profile epcd --port 8091 --no-open
```

启动后终端会打印一行，记下 `token=XXXX` 那段（每次启动都变）。

**② 本机建 SSH 隧道**（另开一个窗口，保持运行）：

```bash
ssh -L 8092:127.0.0.1:8091 eada@192.168.20.109 -N
```

（把本机 8092 映射到远程 127.0.0.1:8091；经隧道后远程看到的请求来源是 loopback，绕开 loopback-only fence）

**③ 本机浏览器访问**（把 `XXXX` 换成第①步的 token）：

```
http://127.0.0.1:8092/?token=XXXX
```

首次带 `?token=` 访问，DSH 校验后自动签发 cookie 并跳转首页。

> 注：本机 8092 是隧道端口，用 8092 而非 8091 是为了避开本机可能已在跑的本地 EPCD。

---

## 手动部署（等价步骤，脚本出问题时照此排查）

### Windows

```powershell
$p = "$env:USERPROFILE\.dsh\profiles\epcd"
New-Item -ItemType Directory -Force $p | Out-Null
Copy-Item epcd-dsh\plugin\deploy\cordis.patch.yml   $p -Force
Copy-Item epcd-dsh\plugin\deploy\epcd-brand.mjs     $p -Force
Copy-Item epcd-dsh\plugin\deploy\epcd-ui-lock.mjs   $p -Force
Copy-Item epcd-dsh\plugin\deploy\epcd-logo.png      $p -Force
Copy-Item epcd-dsh\plugin\deploy\profile-package.json $p\package.json -Force
Copy-Item epcd-dsh\plugin\deploy\epcd-favicon.svg   $p -Force
Copy-Item epcd-dsh\plugin\deploy\pnpm-workspace.yaml $p -Force
Copy-Item epcd-dsh\agent-preset\*   "$env:USERPROFILE\.dsh\.agent-presets\epcd\" -Force -Recurse
New-Item -ItemType Directory -Force "$p\packages\epcd-ui-plugin","$p\node_modules\epcd-ui-plugin" | Out-Null
Copy-Item epcd-dsh\plugin\package.json "$p\packages\epcd-ui-plugin\" -Force
Copy-Item epcd-dsh\plugin\lib          "$p\packages\epcd-ui-plugin\" -Recurse -Force
Copy-Item epcd-dsh\plugin\package.json "$p\node_modules\epcd-ui-plugin\" -Force
Copy-Item epcd-dsh\plugin\lib          "$p\node_modules\epcd-ui-plugin\" -Recurse -Force
node "$env:APPDATA\npm\node_modules\@deepseek-ai\dsh\lib\bin.js" plugin --profile epcd add "@linxin666/dsh-ssh"
```

### Linux

```bash
p="$HOME/.dsh/profiles/epcd"
mkdir -p "$p" "$HOME/.dsh/.agent-presets/epcd" "$p/packages/epcd-ui-plugin" "$p/node_modules/epcd-ui-plugin"
cp epcd-dsh/plugin/deploy/cordis.patch.yml       "$p/"
cp epcd-dsh/plugin/deploy/epcd-brand.mjs         "$p/"
cp epcd-dsh/plugin/deploy/epcd-ui-lock.mjs       "$p/"
cp epcd-dsh/plugin/deploy/epcd-logo.png          "$p/"
cp epcd-dsh/plugin/deploy/profile-package.json   "$p/package.json"
cp epcd-dsh/plugin/deploy/epcd-favicon.svg       "$p/"
cp epcd-dsh/plugin/deploy/pnpm-workspace.yaml    "$p/"
cp -r epcd-dsh/agent-preset/.  "$HOME/.dsh/.agent-presets/epcd/"
cp epcd-dsh/plugin/package.json "$p/packages/epcd-ui-plugin/"
cp -r epcd-dsh/plugin/lib       "$p/packages/epcd-ui-plugin/"
cp epcd-dsh/plugin/package.json "$p/node_modules/epcd-ui-plugin/"
cp -r epcd-dsh/plugin/lib       "$p/node_modules/epcd-ui-plugin/"
dsh plugin --profile epcd add "@linxin666/dsh-ssh"
# 或（未装全局 dsh 时；本质是在 profile 目录跑 pnpm，故需 pnpm 在 PATH）
npx @deepseek-ai/dsh plugin --profile epcd add "@linxin666/dsh-ssh"
```

---

## UI 插件「三处同步」约定

改 `epcd-dsh/plugin/`（canonical 源）后，需同步三处（两个安装脚本已自动化）：

1. `~/.dsh/profiles/epcd/packages/epcd-ui-plugin/`
2. `~/.dsh/profiles/epcd/node_modules/epcd-ui-plugin/`
3. 重启 profile

若日后 `pnpm install` 运行（如 `dsh plugin add`），`file:./packages/epcd-ui-plugin`
会按 package.json 重装到 node_modules，与手工放置一致。

---

## 部署到「本机之外的服务器」注意点

- **形态 A 依赖 DSH 运行时**：目标机需能跑 DSH（Node 20+）。headless 服务器可用
  （DSH 是 Web GUI，headless 只是不自动开浏览器），但需按上文绑 `0.0.0.0` + 加固。
- **SSH 身份不入库**：`servers.json` / `epcd-config.json` 里的 `ssh` 只是**别名**，
  真正的 Host/User/IdentityFile 在目标机 `~/.ssh/config`，需**每台机器单独部署**
  （含免密私钥）。`epcd-agent` 后端还会 ssh 到真正的 EDA 服务器跑 epcd-cli，那条
  SSH 通道同样要配好免密。
- **绝对路径机器相关**：pkg/technology/workDirRoot 是 Linux 服务器上的绝对路径，
  换服务器需同步改 `epcd-config.json`。
- **换机器重做三步**：clone 仓库 → 跑安装脚本（`.ps1` 或 `.sh`）→ 配 `~/.ssh/config`
  与 `epcd-config.json`。

---

## 关键约定（必读）

1. **配置入 git**：本项目约定 `epcd-config.json` 与 `backend/servers.json` **均入 git**。
   这两份文件里的 ssh 别名 / pkg 路径是「仓库公共事实」；改服务器池要改仓库、
   再在各机器 pull。
2. **SSH 私钥永不入 git**：`~/.ssh/config`、IdentityFile、免密私钥是每机一份的
   敏感凭证，绝不进仓库。
3. **slogan 隐藏 hash**（`epcd-brand.mjs` 的 `BRAND_CSS`）：若升级 dsh 后 slogan
   复现，需更新 `epcd-brand.mjs` 里的编译 hash（见 `README` 维护注意）。
4. **0.0.0.0 默认关闭**：`EPCD_HOST` 不设时回落 `127.0.0.1`；只有部署服务器显式设
   `EPCD_HOST=0.0.0.0` 才向局域网开放，且必须配反向代理/防火墙加固。