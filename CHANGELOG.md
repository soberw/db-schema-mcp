# 变动说明

## 1.2.1 - 2026-11-13

### 修复

- 将发布依赖从 `mcp>=0.9.0` 修正为 `mcp>=1.25.0,<2`，防止新安装解析到不兼容的 MCP SDK v2。
- 修复 SDK 2.3.0 下启动出现 `'Server' object has no attribute 'call_tool'` 的问题；继续使用已经验证的 SDK v1 接口。
- SDK 约束写入 wheel 元数据，用户安装无需依赖开发环境的 `uv.lock`。

### 回归保护

- 新增真实 stdio 子进程测试，覆盖 initialize、五个工具发现、无配置初始化以及 SQLite 表结构和参数查询。
- CI 在 Python 3.12/3.13 上从 wheel 安装，分别验证 MCP SDK 1.25.0 和最新允许的 v1 版本。
- 发布工作流上传 PyPI 前验证 wheel 依赖元数据和 stdio 握手，失败时中止上传。

### 验证

- 已复现 SDK 2.3.0 启动失败，并验证 SDK 1.25.0 和 1.30.0 下 wheel 安装与回归通过。
- 本地测试 64 项通过，1 项需要真实数据库配置的测试跳过；ruff、mypy 和构建通过。

### 升级

```bash
uvx --refresh db-schema-mcp@1.2.1 --config /path/to/db_config.yaml
# 已使用 uv tool 安装时：
uv tool upgrade db-schema-mcp
```

升级本地安装后需要重新启动 MCP 连接，正在运行的旧进程不会自动切换 SDK。

## 1.2.0 - 2026-11-13

### 新增

- 支持 OceanBase Oracle 兼容模式，使用 `type: oceanbase`，`mode` 默认为 `oracle`。
- 默认安装纯 Python 驱动 `pyoceanbase==1.1.0`，无需 OBCI、Oracle Instant Client 或 Java。
- 支持连接检查、按 schema 列出表、读取字段/注释/主外键/索引以及 `exec_query` 查询。
- 配置示例和 `init` 模板加入 OceanBase Oracle 连接；支持 OBServer 直连地址和 ODP 地址，用户名原样传递。

### 查询保护

- OceanBase 查询使用数据库只读事务，成功后回滚；异常或截断时关闭连接。
- Oracle 字符串使用单引号加倍转义，支持 `%s` 和 `%(name)s` 标量参数绑定。
- 查询最多返回 1000 行，使用服务端行数限制、4 MiB 结果预算和收包上限。
- 增加 30 秒网络操作总时限和取消处理，覆盖 Windows 阻塞读取及 TLS 握手。
- 禁止本地文件导入、多语句能力、可执行注释及 `NEXTVAL`。账号仍应采用最小权限。

### 验证

- 本地回归：61 项通过，1 项需显式配置真实租户的测试跳过；ruff 和 mypy 通过。
- 独立审查完成，并验证 wheel 隔离安装自动携带驱动。
- 真实 ODP Oracle 租户只读测试通过：登录/schema 识别、219 张表列表、代表性表结构、特殊字符参数绑定和结果截断。
- 本次未执行写入测试，未核实数据库具体版本；真实直连和 TLS 部署未验证。

### 使用示例

```yaml
databases:
  ob_oracle:
    type: oceanbase
    host: your-odp-host
    port: 2883
    user: "app_user@tenant#cluster"
    password: your_password
    database: APP_USER
```
