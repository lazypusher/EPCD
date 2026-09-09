# EPCD 专用 profile 部署说明

把 EPCD 器件设计做成一个**独立、锁定的专用 Agent**（独立端口、不可切换模式、存储隔离）。

## 部署内容（已落地）

`epcd-ui-plugin` 是 EPCD 专用 UI 插件（持久化版，替代原先的动态 Cordis 插件 pkg-6）：

- `lib/index.js` — **宿主工具**：`epcd_status`（TPE 进度条数据）、`epcd_artifacts`（版图/S2P/GDS/目标值图库，PNG→base64 二进制安全）。
- `lib/client.js` — **客户端 toolview**：进度条 + 三视图（俯视/轴测/侧视）产物图库；手写 `window.__ModuleLoader__.load` 包装，只 require 共享外部（react）。
- `package.json` — 双面包：`dsh.client` 声明 client 模块；`exports` 必须显式暴露 `./package.json`（否则 dsh-client-modules 的 `require.resolve('<pkg>/package.json')` 会因 exports 拦截而 404）。

### 四个步骤的落点

| 步骤 | 位置 |
|------|------|
| 1. 插件持久化 | `~/.dsh/profiles/epcd/packages/epcd-ui-plugin/`（源）+ `node_modules/epcd-ui-plugin/`（手工放置，立即可解析）；profile `package.json` 里 `dependencies` 加 `file:./packages/epcd-ui-plugin` |
| 2. 锁定 preset | `~/.dsh/profiles/epcd/cordis.patch.yml` → `agent-presets.config`: `default: epcd` + `roots:[profile/presets]` + `includeUserRoot:false`；`presets/epcd` 是指向 `~/.dsh/.agent-presets/epcd` 的 **junction**（单一来源，无拷贝漂移） |
| 3. 清除 settings 覆盖 | `~/.dsh/settings.yaml` 已删除 `agent-presets.default: standard`（该覆盖曾把 epcd 拉回 standard） |
| 4. 存储隔离 | `cordis.patch.yml` → `session-persistence-jsonl.root` + `storage-json.root` 指向 `profiles/epcd/data/{sessions,storages}`（workspace 记录存于 storageDomain，随 storage-json 一并隔离） |

## 独立启动

```powershell
# PowerShell 用 .cmd shim（.ps1 受执行策略限制）
cmd /c "dsh --profile epcd --port 8091"
# 或直接
dsh.cmd --profile epcd --port 8091
```

启动后：`http://127.0.0.1:8091`（仅 EPCD 模式，名录只有 epcd，无 slogan/logo）。

## 维护注意

- `~/.dsh/.agent-presets/epcd/` 是 preset 的**唯一源头**（junction 指向它），改 preset 只改这里。
- 改插件后，需同步三处 `package.json`/`lib/*`：本目录（canonical）、`~/.dsh/profiles/epcd/packages/epcd-ui-plugin/`、`~/.dsh/profiles/epcd/node_modules/epcd-ui-plugin/`，然后重启 profile。
- 若日后 `pnpm install` 运行（如 `dsh plugin add`），`file:./packages/epcd-ui-plugin` 会按 package.json 重装到 node_modules，与手工放置一致。
- slogan 隐藏选择器 `.pXSMma_headline` 是编译 hash，锁定的 dsh 版本内稳定；升级 dsh 后若 slogan 复现，需在 `epcd-brand.mjs` 的 `BRAND_CSS` 里更新该 hash。