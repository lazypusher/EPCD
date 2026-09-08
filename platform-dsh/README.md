# EPCD 专用 Agent 平台（DSH profile）

基于 DeepSeek Harness（DSH）框架裁剪出的 **EPCD 器件设计专用平台**：chat 交互 +
`ask_user_question` 里程碑确认（M1~M4）+ 器件名/路径自动生成，服务器/工艺读全局配置。

启动后是一个独立的 DSH profile，不加载 DSH 的通用装饰（皮肤/插件市场/侧边栏增强/
任务板/git 图/skill 浏览器等），branding 为 EPCD（title/favicon/manifest）。

## 组成

- `profile/` — EPCD profile（`~/.dsh/profiles/epcd` 的内容）
  - bundles = `@deepseek-ai/dsh-base` + `@deepseek-ai/dsh-web-app` + `@linxin666/dsh-ssh`
  - `cordis.patch.yml` — 禁用 telemetry/web 搜索，默认 EPCD preset，注入 branding
  - `epcd-brand.mjs` + `epcd-favicon.svg` — 覆盖 title/favicon/manifest
- `agent-preset/` — EPCD 专用 agent preset（`~/.dsh/.agent-presets/epcd` 的内容）
  - `agent.cordis.yml` — EPCD persona + 精简工具集（pwsh/fs/jobs/skill/goal/plan/compaction/ask-user/todo）
  - 裁剪掉：subagent/fork/workflow/ralph/web（EPCD 不需要多代理与 web 搜索）
- 全局配置：`~/.dsh/epcd-config.json`（ssh 服务器/工艺文件/工作目录根，一次性配置）
- 编排 skill：`.dsh/skills/epcd-agent-flow/`（8 阶段流程，M1~M4 确认）

## 安装

```powershell
# 1. 复制 profile 到 DSH home
Copy-Item platform-dsh\profile\* "$env:USERPROFILE\.dsh\profiles\epcd\" -Force
Copy-Item platform-dsh\agent-preset\* "$env:USERPROFILE\.dsh\.agent-presets\epcd\" -Force

# 2. 安装树外依赖（dsh-ssh，经 dsh plugin 转发 pnpm）
node "$env:APPDATA\npm\node_modules\@deepseek-ai\dsh\lib\bin.js" plugin --profile epcd add "@linxin666/dsh-ssh"

# 3. 全局配置（首次）
#    编辑 $env:USERPROFILE\.dsh\epcd-config.json：
#    { "ssh": "<服务器别名>", "pkg": "<EPCD包根>", "technology": "<工艺文件>", "workDirRoot": "<工作目录根>" }
```

## 启动

```powershell
node "$env:APPDATA\npm\node_modules\@deepseek-ai\dsh\lib\bin.js" --profile epcd --port 3090
```

浏览器打开 `http://127.0.0.1:3090`，直接说「帮我设计一个 2.4GHz L≈10nH、Q>20 的电感」。

## 备注

- `epcd-brand.mjs` 仅在 `epcd` profile 生效，不影响默认 `web` profile 的 DeepSeek branding。
- 回退默认 web profile：`dsh web`（或 `--profile web`）。
- 服务器池（多服务器）在 `backend/servers.json`（`别名 → {ssh, pkg}`），全局配置的 `ssh`/`pkg` 为默认目标。