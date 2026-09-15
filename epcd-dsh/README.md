# EPCD 专用 Agent 形态（DSH）

基于 DeepSeek Harness（DSH）框架裁剪出的 **EPCD 器件设计专用平台**：chat 交互 +
`ask_user_question` 里程碑确认（M1~M4）+ 器件名/路径自动生成，服务器/工艺读全局配置。

本目录是「EPCD 的 DSH 形态」唯一的源码/装配源，取代了早期的
`platform-dsh/`（preset + profile）与 `plugins/`（插件实现）两个目录，统一收敛为：

```
epcd-dsh/
├── agent-preset/              # Agent preset：这个 Agent 是什么角色、用什么工具
│   ├── agent.cordis.yml       #   persona + 精简工具集（pwsh/fs/jobs/skill/goal/plan/compaction/ask-user/todo）
│   └── preset.yml             #   显示元数据（名称/描述）
├── plugin/                    # UI 插件实现（canonical，改代码只改这里）
│   ├── lib/index.js           #   宿主工具：epcd_status / epcd_artifacts / epcd_cli / epcd_config
│   ├── lib/client.js          #   客户端：进度条 / 三视图产物图库 / 配置面板
│   ├── package.json           #   name: epcd-ui-plugin（DSH 加载时的插件名）
│   ├── README.md              #   插件维护说明（软链部署 / 三处同步约定）
│   └── deploy/                #   profile 装配源（权威）
│       ├── cordis.patch.yml   # profile patch：禁 telemetry/web搜索、锁 preset、存储隔离、webserver、挂 UI 插件
│       ├── epcd-brand.mjs     # branding：title/favicon/logo + 隐藏 DeepSeek slogan
│       ├── epcd-ui-lock.mjs   # UI 锁定：固定工作区/隐藏预设切换/隐藏思考块/隐藏 dotfile 目录
│       ├── epcd-logo.png      # 左上角品牌 logo（九同方微电子）
│       ├── epcd-favicon.svg   # favicon
│       ├── pnpm-workspace.yaml
│       └── profile-package.json  # → 部署时改名为 package.json（bundle 列表 + 依赖）
```

## 两个层级，别混淆

| | agent preset | profile |
|---|---|---|
| 位置 | `epcd-dsh/agent-preset/` | `epcd-dsh/plugin/deploy/` |
| 部署落点 | `~/.dsh/.agent-presets/epcd/` | `~/.dsh/profiles/epcd/` |
| 决定什么 | 单次会话的 Agent 用什么工具 + persona | 整个进程装哪些插件行（bundle/存储/webserver/UI 插件/branding） |
| 生命周期 | 每次会话按 preset 组装 | 启动 `--profile epcd` 时 mount 一次 |

插件**业务实现**在 `epcd-dsh/plugin/lib/`，`plugin/deploy/` 只负责把它们**挂进 profile**。

## 安装

一键部署（把 profile + preset + 插件软链落地到本机 DSH home）：

```powershell
powershell -ExecutionPolicy Bypass -File .\deploy\install-dsh-agent.ps1   # Windows
# 或
bash deploy/install-dsh-agent.sh                                          # Linux
```

部署脚本会依次：
1. 复制 profile（`epcd-dsh/plugin/deploy/` 全部文件）→ `~/.dsh/profiles/epcd/`
2. 复制 agent preset（`epcd-dsh/agent-preset/`）→ `~/.dsh/.agent-presets/epcd/`
3. 同步 UI 插件（软链到 `~/.dsh/profiles/epcd/{packages,node_modules}/epcd-ui-plugin/`）
4. 安装树外依赖 `@linxin666/dsh-ssh`

## 启动

```powershell
dsh --profile epcd --port 8091
# 或
npx @deepseek-ai/dsh --profile epcd --port 8091
```

浏览器打开 `http://127.0.0.1:8091`，直接说「帮我设计一个 2.4GHz L≈10nH、Q>20 的电感」。

headless 服务器绑局域网：`EPCD_HOST=0.0.0.0 dsh --profile epcd --port 8091`（DSH 自身无
TLS/鉴权，务必套反向代理/防火墙加固），详见 `deploy/README.md`。

## 维护

- **改插件代码**：只改 `epcd-dsh/plugin/lib/{index.js,client.js}`（canonical）。profile 里的
  `packages/` 与 `node_modules/` 是软链指向它，改完重启 profile 即可，无需三处同步。
  详见 `epcd-dsh/plugin/README.md`。
- **改 profile 装配 / branding / UI 锁定**：改 `epcd-dsh/plugin/deploy/` 下的对应文件。
- **改 Agent 角色/工具**：改 `epcd-dsh/agent-preset/agent.cordis.yml`。

## 备注

- `epcd-brand.mjs` / `epcd-ui-lock.mjs` 仅在 `epcd` profile 生效，不影响默认 `web` profile。
- 回退默认 web profile：`dsh web`（或 `--profile web`）。
- 服务器池（多服务器）在 `backend/servers.json`（`别名 → {ssh, pkg}`），全局配置的
  `ssh`/`pkg` 为默认目标。