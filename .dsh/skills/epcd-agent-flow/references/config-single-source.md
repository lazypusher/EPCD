# EPCD 配置单一事实源收口方案（待确认，暂不改代码）

> 状态：**设计稿，未落地**。目标：消除 `epcd-config.json` 与 `backend/servers.json` 的定位重叠，
> 让「项目切环境」只改一个地方，并支撑 EPCD 面板「多服务器一键切换」。
> 本轮分支：字段迁移方式待定、面板切换留到下一步。

## 1. 现状诊断（三个真实问题）

| 问题 | 表现 | 后果 |
| --- | --- | --- |
| 连接参数与「项目默认」分裂两文件 | `servers.json` 存连接对象+`pkg`；`epcd-config.json` 存 `ssh`（字符串别名）+`pkg`+`technology`+`workDirRoot` | 靠「`epcd-config.ssh` 的值 == `servers.json` 的 key」的隐式字符串约定耦合，无校验 |
| `pkg` 双份 | 同一段 `/package/...` 抄在两边 | 改一边忘另一边即静默不一致 |
| 面板「一键切换」缺位 | 面板(`epcd_config` 宿主工具)只读写 `epcd-config.json` 的 4 个字符串字段，不读 `servers.json` | 无法在多个 server 间点选切换 |

**各文件当前真实角色：**

- `backend/servers.json`（backend 层）：服务器池，admin 维护。旧格式 `ssh` 为字符串别名；本次已改为
  对象形态 `{host,user,port,identityFile}`，但 **TypeScript 侧 `bridge.ts` 的 `ServerEntry.ssh` 仍是
  `string`，类型已滞后**，需同步。
- `<cwd>/epcd-config.json`（DSH 宿主层）：项目级配置，面板(`/api/epcd-config`)与 `epcd_config` 工具
  读写，字段 `ssh/pkg/technology/workDirRoot` 四字符串，缺字段回落
  `~/.dsh/profiles/epcd/data/epcd-config-defaults.json`。

## 2. 定位原则（收口后）

> **`servers.json` = 「服务器池」唯一事实源**（每台服务器怎么连、EPCD 包根在哪）。
> **`epcd-config.json` = 「项目上下文」唯一事实源**（用哪个 server（按 key）、什么工艺、结果放哪）。
> 二者通过 **key（server 名）** 关联，字段不再重复。

| 归属 | 字段 | 说明 |
| --- | --- | --- |
| `servers.json` 每条目 | `ssh.host/user/port/identityFile`、`pkg` | 连接凭据 + EPCD 包根，admin 维护 |
| `epcd-config.json` | `server`(或沿用 `ssh` 名)、`technology`、`workDirRoot` | 项目「选哪个 server key」+ 工艺 + 工作目录 |

## 3. 待定决策点（影响落地方式）

### 决策 A：`epcd-config.json` 的「服务器选择」字段命名

- **A1（保持 `ssh` 名，语义改为 server key）**：破坏最小，面板字段列表/缓存不用改，但名字仍有歧义（`ssh` 易被误读为连接字符串）。
- **A2（重命名为 `server`）**：语义清晰，但需同步改 `epcd-ui-persist` 的 `CONFIG_FIELDS`/`CONFIG_LABELS`/
  缓存键/历史路径、以及 `epcd_config` MCP 工具的 schema 与 `SKILL.md`。
- 无论 A1/A2，`epcd-config.json` 都**删除重复的 `pkg` 字段**（改由 `servers.json` 条目提供）。

### 决策 B：`pkg` 的回落链

- 删除 `epcd-config.json.pkg` 后，`pkg` 仅存在于 `servers.json`。backend `--server <key>` 已按 key 取
  `pkg`（`cli.py._apply_server` 已实现）；DSH 宿主 `epcd_cli` 工具的 `server` 参数即 key。
  需确认：`epcd_cli` 工具在不传 `server` 时的默认值 = `epcd-config.json.ssh/server` 字段值。

## 4. 落地步骤（后端收口，本轮范围；面板下一步）

1. **`servers.json`**：统一为多条目 + `ssh` 对象（已改 `epcd-primary`，补 `epcd-backup` 示例）。
2. **`bridge.ts`**：`ServerEntry.ssh` 类型从 `string` 改为 `string | {host,user,port,identityFile}`，
   并同步 `loadServers` 的返回（供后续面板渲染下拉）。
3. **`epcd-config.json`**：瘦身为 `{ssh(或server), technology, workDirRoot}`，删 `pkg`；
   同步 `epcd-ui-persist` 的 `CONFIG_FIELDS`（若 A2 则改名）与默认值迁移。
4. **`SKILL.md` + `ssh-troubleshooting.md`**：更新「切环境配哪个文件」的说明。

## 5. 「一键切换」的最终形态（面板，下一步）

- 面板 `epcd_config` 工具 `action=get` 时，额外返回 `servers`（`servers.json` 所有 key 列表）与
  `activeServer`（`epcd-config.ssh` 当前值）。
- 面板渲染「服务器」下拉，选项 = servers key；点选即 `action=set {ssh: <key>}` 写回 `epcd-config.json`。
- 后端与面板此后统一以 `epcd-config.ssh`（或 `server`）为「当前 server key」，去 `servers.json` 取连接参数+`pkg`。

## 6. 边界与风险

- `servers.json` 是 backend 仓库内、admin 维护；`epcd-config.json` 是每项目一份、面板维护。二者都经 git 或
  部署流同步时，需保证「key 一致性」——面板切换到的 key 必须在 `servers.json` 中存在，否则 backend 报
  `unknown server`（退出码 2）。
- 现有 `epcd-config.json` 里 `pkg` 删除后，若有离线/无 `servers.json` 的环境，需保留回落：`epcd_cli`
  工具仍可用 `input.pkg` 显式传（`cli.py --pkg` 已支持），作为兜底。