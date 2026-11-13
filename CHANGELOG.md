# 变动说明

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
