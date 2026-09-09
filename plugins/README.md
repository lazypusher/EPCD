# EPCD UI 动态插件（进度条 + 产物图库 + 三视图）

`epcd-ui-plugin.host.js` + `epcd-ui-plugin.client.js` 是 EPCD 前端增强的
**动态 Cordis 插件**源码（同一份代码已在会话内跑通并验证）。

- 宿主（host）：注册 `epcd_status`（TPE 进度）与 `epcd_artifacts`（产物图库）两个工具。
- 客户端（client）：为这两个工具注册 `tool.call.toolview` 卡片，并隐藏首页 DeepSeek 标语。
  - `epcd_status` → 进度条 + 每轮 cost 迷你柱
  - `epcd_artifacts` → 图库；`preview_top/iso/side` 三张版图自动合并成「俯视/轴测/侧视」切换

## 每次新会话如何挂载（boot）

动态插件定义只存在于当前进程、不跨重启。新会话启动后，若工具 `epcd_status` /
`epcd_artifacts` 不存在，按下面两步挂载（`{{cwd}}` = 本仓库根目录）：

1. `cordis_define`（`kind:"new"`，`idPrefix:"epcdui"`）：`code.host` = 读
   `plugins/epcd-ui-plugin.host.js` 的**函数体**，`code.client` = 读
   `plugins/epcd-ui-plugin.client.js` 的**函数体**（两个文件各自 `return {…}` 结尾，
   不含外层的 import/导出）。
2. `cordis_run`（`mode:"run"`）激活返回的 `pluginId`/`packageId`；弹出授权时请用户批准
   （勾「始终允许」/双勾则后续版本免批）。

> 挂载后 `epcd_status`/`epcd_artifacts` 会出现在工具目录里，后续轮询/交付按
> `epcd-agent-flow` skill 调用即可。

## 架构说明（为什么不是「写进 preset」）

- **preset（`agent.cordis.yml`）只组合宿主侧**：工具、persona、prompt。它没有客户端 UI 面。
- **`tool.call.toolview` 是共享 Web shell 的客户端槽位**，不是 per-preset 的。要在重启后
  原生常驻（零手动挂载），需要把它做成 Web shell 的客户端插件包并重建 `apps/web`，
  这会影响**所有**预设的共享界面，且需要重建+刷新验证——是 DSH 壳层开发，不是 preset 编写。

因此当前交付是「动态插件 + 本目录持久源码 + 每会话 boot 一键重挂载」。
如需**原生常驻**（不用每次挂载），再做：宿主工具放 preset/宿主组合、客户端卡片进
Web shell 并重建。可作为后续独立任务。