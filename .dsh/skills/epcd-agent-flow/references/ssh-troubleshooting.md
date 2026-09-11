# EPCD 本机 SSH 连接解耦与故障排查（运维参考）

> 背景：backend 的 `EpcdCli`（`backend/src/epcd_agent/cli_client.py`）用**本机 `ssh` 二进制**
> 远程执行 `epcd-cli`。连接方式不再是「读本机 `~/.ssh/config` 里的 Host 别名」，而是
> **平台无关的显式连接**（见 §1），因此在 Windows / Linux、以及 home 目录只读的容器环境里
> 行为一致、且不依赖本机 ssh 配置路径。

## 1. 连接方式（当前实现，`backend/src/epcd_agent/cli.py`）

服务器的连接信息来自 `backend/servers.json`（项目内、随工程走，不是本机 `~/.ssh/config`）。
`ssh` 字段支持两种形态，由 `_apply_server` 自动判别：

### 形态 A：显式连接（推荐，平台无关）

```json
"servers": {
  "epcd-primary": {
    "ssh": { "host": "192.168.20.243", "user": "zhubo", "port": 22,
             "identityFile": "~/.ssh/id_rsa_epcdB" },
    "pkg": "/package/..."
  }
}
```

`ssh` 是**对象**时：连接参数全部用 `-o HostName=/-o User=/.../-i` 显式传给 ssh，且 `-F` 指向
EPCD 在 **OS 临时目录**（`tempfile.gettempdir()`，Linux 是 `/tmp`、Windows 是 `%TEMP%`）下
维护的空 config 文件。这样 ssh **既不读系统 `/etc/ssh/ssh_config*`，也不读用户 `~/.ssh/config`**，
彻底与本机 ssh 配置路径解耦。

生成的 ssh 前缀形如（`build_argv_prefix`）：

```
ssh -F /tmp/epcd-inline-ssh-config -o BatchMode=yes \
    -o HostName=192.168.20.243 -o User=zhubo -o Port=22 -i ~/.ssh/id_rsa_epcdB \
    epcd-primary source <pkg>/user.bashrc.ePCD >/dev/null 2>&1; ... epcd-cli
```

> 末尾的 `epcd-primary` 只是 ssh 语法要求的「目标」占位（会被 `-o HostName=` 覆盖），
> 它用 **server 名本身**，不承担别名解析作用。`identityFile` 里的 `~` 由
> `os.path.expanduser` 跨平台展开（Windows 读 `USERPROFILE`）。

### 形态 B：别名（legacy 回退，兼容旧配置）

```json
"epcd-primary": { "ssh": "epcd-primary", "pkg": "/package/..." }
```

`ssh` 是**字符串**时：回退为「`-o BatchMode=yes <别名>` + 让 ssh 自己读本机 config 解析别名」的
旧行为。仅用于未迁移的老环境；新配置一律建议用形态 A。

## 2. 为什么必须 `-F` + 显式传参（而不是只 `-o`）

OpenSSH 在**解析任何 `-o` 选项之前**就会读系统 `ssh_config`（含 `ssh_config.d/*`）。
若系统 config 属主异常（如 `nobody`），即便把连接参数用 `-o` 全给了，ssh 也会先 fatal，
stdout 为空、报 `Bad owner or permissions on <文件>`。

`-F <file>` 是唯一能让 ssh **跳过系统 config** 的开关，且要求 `<file>` 已存在。因此：

- 不能用只读的 `~/.ssh/`（home 可能只读，也无法跨平台保证路径）；
- 用 temp 目录（`gettempdir()`）放空 config 文件，既跨平台又一定可写。

## 3. 典型症状与定位

- `ENVELOPE_PARSE_ERROR: empty stdout: no envelope`（退出码 1）：本机 ssh 没产出 stdout。
- 手动复现 `ssh -o BatchMode=yes <别名> 'echo OK'` 返回 exit 255、stderr 报
  `Bad owner or permissions on /etc/ssh/ssh_config.d/...`。
- DSH 的 `ssh_exec` / `ssh_list` 工具**正常**（它们用自己的连接库，不走本机 ssh 二进制）。

## 4. 自检清单（新环境 onboarding 前跑一遍）

```bash
# 1) servers.json 用显式 ssh 对象（推荐），字段齐全
cat backend/servers.json

# 2) 本机 ssh 直连验证（显式参数 + temp 空 config，等价于 backend 实际行为）
CFG=$(mktemp); : > "$CFG"
ssh -F "$CFG" -o BatchMode=yes \
    -o HostName=192.168.20.243 -o User=zhubo -i ~/.ssh/id_rsa_epcdB \
    epcd-primary 'whoami; which epcd-cli'

# 3) 后台回环：backend 任意轻量工具应返回 ok
cd <repo>/backend && printf '{}' | \
  .venv/bin/python -m epcd_agent.cli --server epcd-primary \
    --db epcd-agent-session.sqlite3 --session probe epcd_health
```

第 3 步若报 `ENVELOPE_PARSE_ERROR: empty stdout`，回到 §2 定位（先确认 temp 目录可写、identityFile 存在）；
若返回 `no project in session store`，说明 ssh 已通、只是该 session 还没建工程（正常）。