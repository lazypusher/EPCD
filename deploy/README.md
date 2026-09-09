# EPCD 部署指南（形态 A：DSH Agent）

把 EPCD 的 DSH 专用 profile / agent preset / UI 插件部署到目标机器，跑通
「`dsh --profile epcd --port 8091`」这套 Agent 交互形态。

> 本指南只覆盖形态 A（依赖 DeepSeek Harness）。自研 Fastify 平台（形态 B）不在本仓库部署范围。

---

## 依赖清单

| 依赖 | 来源 | 是否入 git |
|------|------|-----------|
| DSH 运行时 | npm 全局 `@deepseek-ai/dsh` + `@linxin666/dsh-ssh` + `dsh-better-sidebar` | —（外部 install） |
| profile | **`plugins/epcd-ui-persist/deploy/`（权威）+ `platform-dsh/profile/`（favicon/pnpm-workspace）** | ✅ 入库 |
| agent preset | `platform-dsh/agent-preset/*` | ✅ 入库 |
| UI 插件 | `plugins/epcd-ui-persist/{package.json,lib/*}` | ✅ 入库 |
| 配置 | `epcd-config.json`（ssh/pkg/technology/workDirRoot） | ✅ 入库（本项目约定） |
| 编排 skill | `.dsh/skills/epcd-agent-flow/` | ✅ 入库 |

> ⚠ **profile 权威源是 `plugins/epcd-ui-persist/deploy/`，不是 `platform-dsh/profile/`。**
> `platform-dsh/profile/cordis.patch.yml` 是旧版：缺 `epcd-ui-plugin` insert 与存储隔离，
> 用它部署出的 profile **没有产物图库/进度条 UI 插件**。完整版在 deploy 目录，
> `install-dsh-agent.ps1` 已按权威源组合复制。

---

## 一键部署（Windows）

```powershell
powershell -ExecutionPolicy Bypass -File .\deploy\install-dsh-agent.ps1
```

脚本会依次：

1. 复制 `platform-dsh/profile/*` → `~/.dsh/profiles/epcd/`
2. 复制 `platform-dsh/agent-preset/*` → `~/.dsh/.agent-presets/epcd/`
3. 同步 UI 插件 `plugins/epcd-ui-persist/` → `packages/epcd-ui-plugin/` + `node_modules/epcd-ui-plugin/`
4. 安装树外依赖 `@linxin666/dsh-ssh`

完成后：

```powershell
# 确认配置（含 ssh 别名 + 内网 pkg 路径）
# 编辑 epcd-config.json 的 ssh/pkg/technology/workDirRoot
dsh --profile epcd --port 8091
```

浏览器打开 `http://127.0.0.1:8091`。

---

## 手动部署（等价步骤，脚本出问题时照此排查）

```powershell
# 1. profile（权威源 = plugins/epcd-ui-persist/deploy/ 完整版）
$p = "$env:USERPROFILE\.dsh\profiles\epcd"
New-Item -ItemType Directory -Force $p | Out-Null
Copy-Item plugins\epcd-ui-persist\deploy\cordis.patch.yml   $p -Force
Copy-Item plugins\epcd-ui-persist\deploy\epcd-brand.mjs     $p -Force
Copy-Item plugins\epcd-ui-persist\deploy\profile-package.json $p\package.json -Force
Copy-Item platform-dsh\profile\epcd-favicon.svg             $p -Force
Copy-Item platform-dsh\profile\pnpm-workspace.yaml          $p -Force
# 2. agent preset
Copy-Item platform-dsh\agent-preset\*   "$env:USERPROFILE\.dsh\.agent-presets\epcd\" -Force -Recurse
# 3. UI 插件（三处同步之 packages + node_modules）
New-Item -ItemType Directory -Force "$p\packages\epcd-ui-plugin","$p\node_modules\epcd-ui-plugin" | Out-Null
Copy-Item plugins\epcd-ui-persist\package.json "$p\packages\epcd-ui-plugin\" -Force
Copy-Item plugins\epcd-ui-persist\lib          "$p\packages\epcd-ui-plugin\" -Recurse -Force
Copy-Item plugins\epcd-ui-persist\package.json "$p\node_modules\epcd-ui-plugin\" -Force
Copy-Item plugins\epcd-ui-persist\lib          "$p\node_modules\epcd-ui-plugin\" -Recurse -Force
# 4. 树外依赖
node "$env:APPDATA\npm\node_modules\@deepseek-ai\dsh\lib\bin.js" plugin --profile epcd add "@linxin666/dsh-ssh"
node "$env:APPDATA\npm\node_modules\@deepseek-ai\dsh\lib\bin.js" plugin --profile epcd add "dsh-better-sidebar"
```

---

## UI 插件「三处同步」约定

改 `plugins/epcd-ui-persist/`（canonical 源）后，需同步三处（`install-dsh-agent.ps1` 已自动化）：

1. `~/.dsh/profiles/epcd/packages/epcd-ui-plugin/`
2. `~/.dsh/profiles/epcd/node_modules/epcd-ui-plugin/`
3. 重启 profile

若日后 `pnpm install` 运行（如 `dsh plugin add`），`file:./packages/epcd-ui-plugin`
会按 package.json 重装到 node_modules，与手工放置一致。

---

## 部署到「本机之外的服务器」注意点

- **形态 A 依赖 DSH 运行时**：目标机必须是能跑 DSH 的桌面/带浏览器环境（DSH 是
  Web GUI + Agent harness）。纯 headless 服务器不适合形态 A。
- **SSH 身份不入库**：`servers.json` / `epcd-config.json` 里的 `ssh` 只是**别名**，
  真正的 Host/User/IdentityFile 在目标机 `~/.ssh/config`，需**每台机器单独部署**
  （含免密私钥）。clone 仓库不会带上这些。
- **绝对路径机器相关**：pkg/technology/workDirRoot 是 Linux 服务器上的绝对路径，
  换服务器需同步改 `epcd-config.json`。
- **换机器要重做三步**：clone 仓库 → 跑 `install-dsh-agent.ps1` → 配 `~/.ssh/config`
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