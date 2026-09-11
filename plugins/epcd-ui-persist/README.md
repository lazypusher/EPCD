# EPCD 专用 profile 部署说明

把 EPCD 器件设计做成一个**独立、锁定的专用 Agent**（独立端口、不可切换模式、存储隔离）。

## ⚠️ 命名澄清（务必先读，避免改错副本）

| 名字 | 是什么 | 关系 |
|------|--------|------|
| `epcd-ui-persist` | **本目录的名字**（源码工程 canonical） | 只有这一个物理源码，改了它就改了一切 |
| `epcd-ui-plugin` | **插件真名**（DSH 加载时用的 id + package.json 的 `name`） | 一个身份名，不是独立代码 |

> `persist` = 持久化：指「把原本动态注入的 Cordis 插件 pkg-6 固化成持久插件」这一版的源码。
> 源码目录叫 `epcd-ui-persist`，但打包/发布/加载的统一插件名是 `epcd-ui-plugin`。
> **两者是同一份代码，不是两套实现。**

## 目录布局（单一事实源，软链）

- **唯一源码（canonical）**：`plugins/epcd-ui-persist/lib/{index.js, client.js}` ← 改代码只改这里。
- **DSH 实际加载的插件副本**：`~/.dsh/profiles/epcd/packages/epcd-ui-plugin/lib/`
  与 `~/.dsh/profiles/epcd/node_modules/epcd-ui-plugin/lib/` —— 这两个目录下的
  `index.js`/`client.js` 是**软链（symlink）**，指向 canonical 源码。
- 因此**改 canonical 后无需任何「同步三处」操作**，DSH 加载的始终是同一份物理文件。

## 部署内容（已落地）

`epcd-ui-plugin` 是 EPCD 专用 UI 插件（持久化版，替代原先的动态 Cordis 插件 pkg-6）：

- `lib/index.js` — **宿主工具**：`epcd_status`（TPE 进度条）、`epcd_artifacts`（版图/S2P/GDS/目标值图库）、`epcd_cli`（直调后端）、`epcd_config`（读/写 `epcd-configs.json`）+ `/api/epcd-config` 路由。
- `lib/client.js` — **客户端**：进度条 + 三视图产物图库 + 侧边栏 `[EPCD 配置]` 面板；手写 `window.__ModuleLoader__.load` 包装，只 require 共享外部（react）。
- `package.json` — 双面包：`dsh.client` 声明 client 模块；`exports` 必须显式暴露 `./package.json`（否则 dsh-client-modules 的 `require.resolve('<pkg>/package.json')` 会因 exports 拦截而 404）。

### 四个步骤的落点

| 步骤 | 位置 |
|------|------|
| 1. 插件持久化 | canonical `plugins/epcd-ui-persist/` + 软链到 `~/.dsh/profiles/epcd/packages/epcd-ui-plugin/lib/`（DSH 解析）+ `node_modules/epcd-ui-plugin/lib/`；profile `package.json` 里 `dependencies` 加 `file:./packages/epcd-ui-plugin` |
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

## 维护注意（改代码只改一处，改完重启）

- **改插件代码**：只改 `plugins/epcd-ui-persist/lib/{index.js, client.js}`（canonical）。
  `packages/` 与 `node_modules/` 下的同名文件是软链，会自动指向新内容，**无需再手动同步**。
- **改 `package.json`**：`package.json` 不是软链（三处各有一份，内容一致）。若改了插件名/依赖/
  `exports`，需分别同步三处 `package.json`，再重启。
- **改完重启 profile**：DSH 的 client plugin 是启动时 `window.__ModuleLoader__.load` 载入内存，
  无热重载；必须重启 profile + 刷新浏览器才能看到改动。
- **若日后 `pnpm install` 运行**（如 `dsh plugin add`），`file:./packages/epcd-ui-plugin` 会按
  package.json 重装到 node_modules，可能**覆盖掉软链**（变回实体副本）——届时需重新建立软链：
  `ln -s <canonical>/lib/index.js <...>/lib/index.js`（同理 `client.js`）。
- `~/.dsh/.agent-presets/epcd/` 是 preset 的**唯一源头**（junction 指向它），改 preset 只改这里。
- slogan 隐藏选择器 `.pXSMma_headline` 是编译 hash，锁定的 dsh 版本内稳定；升级 dsh 后若 slogan 复现，需在 `epcd-brand.mjs` 的 `BRAND_CSS` 里更新该 hash。

## 历史教训（为什么上一条那么重要）

曾因改 `plugins/epcd-ui-persist/`（canonical）却没同步到 `packages/epcd-ui-plugin/`（DSH 实际加载），
导致面板改动「看起来不生效」——因为改的是两份独立文件里的错误那一份。已通过软链根治：三处现在
是同一物理文件，从机制上杜绝「改错副本」。