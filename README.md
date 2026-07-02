# db-schema-mcp

一个用于查询数据库表结构的 Model Context Protocol (MCP) 服务器。该服务器允许 AI 助手（如 Claude Code、Cursor 等）通过标准化协议访问多种数据库类型的表结构信息。

## 功能特性

- **多数据库支持**: SQLite、PostgreSQL、MySQL、Oracle
- **本地执行**: 所有数据库操作在本地运行，数据绝不上传
- **MCP 协议兼容**: 可无缝集成到任何支持 MCP 的 AI 客户端
- **灵活配置**: 通过 YAML 配置文件管理多个数据库连接

## 安装

### 使用 uv（推荐）

```bash
uvx db-schema-mcp --config /path/to/your/db_config.yaml

# 如果还没有配置文件，也可以先启动后通过 init 工具生成示例配置
uvx db-schema-mcp
```

### 使用 pip

```bash
pip install db-schema-mcp
db-schema-mcp --config /path/to/your/db_config.yaml
```

## 配置

创建 YAML 配置文件（例如 `db_config.yaml`）：

```yaml
databases:
  # MySQL 配置
  mysql_production:
    type: mysql
    host: localhost
    port: 3306
    user: your_username
    password: your_password
    database: production_db
    # 可选: SSL 配置
    ssl: true
    ssl_ca: /path/to/ca.pem
    ssl_cert: /path/to/cert.pem
    ssl_key: /path/to/key.pem

  # PostgreSQL 配置
  postgres_analytics:
    type: postgresql
    host: localhost
    port: 5432
    user: postgres
    password: your_password
    database: analytics_db
    # 可选: SSL 配置
    sslmode: require

  # SQLite 配置
  sqlite_local:
    type: sqlite
    path: /path/to/your/database.db
```

### MCP 客户端配置

将以下配置添加到您的 MCP 客户端配置（例如 Claude Desktop 的 `claude_desktop_config.json`）：

```json
{
  "mcpServers": {
    "db-schema": {
      "command": "uvx",
      "args": [
        "db-schema-mcp",
        "--config", "/path/to/your/db_config.yaml"
      ]
    }
  }
}
```

## 可用工具

### init

生成示例 YAML 配置文件。适用于首次使用、还没有配置文件的场景。

**参数:**
- `path` (可选): 配置文件输出路径。未提供时优先使用启动命令中的 `--config` 路径
- `overwrite` (可选): 是否覆盖已有文件，默认 `false`

**示例:**
```
您: 请初始化 db-schema-mcp 配置文件，存到 ./db_schema_mcp.yaml
AI: 已生成示例配置文件: ./db_schema_mcp.yaml
```

### list_connections

列出所有已配置的数据库连接。

**参数:**
- `check_status` (可选): 验证连接可用性

**示例:**
```
您: 我有哪些可用的数据库连接？
AI: 以下是您配置的连接：
1. mysql_production - MySQL @ localhost:3306
2. postgres_analytics - PostgreSQL @ localhost:5432
3. sqlite_local - SQLite @ /path/to/database.db
```

### list_tables

列出指定数据库中的所有表。

**参数:**
- `connection_name` (必需): 数据库连接名称

**示例:**
```
您: 列出 analytics 数据库中的所有表
AI: postgres_analytics 中的表如下：
- customers（客户）
- products（产品）
- orders（订单）
- inventory（库存）
- order_items（订单明细）
```

### describe_table

获取指定表的详细结构信息。

**参数:**
- `connection_name` (必需): 数据库连接名称
- `table_name` (必需): 表名

**示例:**
```
您: customers 表的结构是什么样的？
AI: customers 表有以下结构：

| 字段名 | 类型 | 是否可为空 | 默认值 | 说明 |
|--------|------|------------|--------|------|
| id | INTEGER | NO | | 主键 |
| name | VARCHAR(255) | NO | | 客户姓名 |
| email | VARCHAR(255) | YES | NULL | 电子邮箱 |
| registration_date | DATE | NO | | 注册日期 |
| status | VARCHAR(50) | YES | 'active' | 客户状态 |
```

### exec_query

执行只读 SQL 查询并返回结果。此工具只允许单条 `SELECT` 或 `WITH` 查询，会拒绝 `INSERT`、`UPDATE`、`DELETE`、DDL、多语句、`SELECT INTO`、`FOR UPDATE` 等非只读或可能产生副作用的 SQL。

**参数:**
- `connection_name` (必需): 数据库连接名称
- `sql` (必需): 只读 SQL 查询
- `parameters` (可选): 参数绑定值，数组或对象。请使用它传入动态值，避免拼接 SQL。占位符写法遵循对应数据库驱动（例如 SQLite `?`、MySQL/PostgreSQL `%s`、Oracle `:name` 或 `:1`）
- `limit` (可选): 最大返回行数，默认 100，最大 1000
- `response_format` (可选): `markdown` 或 `json`，默认 `markdown`

**示例:**
```
您: 查询订单金额超过 1000 的客户，最多 20 条
AI 调用:
exec_query({
  "connection_name": "mysql_production",
  "sql": "SELECT customer_id, total FROM orders WHERE total > %s ORDER BY total DESC",
  "parameters": [1000],
  "limit": 20
})
```

## 安全性

- 所有数据库操作在本地执行
- 没有数据传输到外部服务
- 数据库凭证存储在本地配置文件中
- 表结构工具仅访问元数据
- `exec_query` 仅允许只读查询，并支持参数绑定以避免 SQL 拼接

## 开发

### 搭建开发环境

```bash
# 克隆仓库
git clone https://github.com/soberw/db-schema-mcp.git
cd db-schema-mcp

# 安装开发依赖
uv sync --extra dev
```

### 运行测试

#### 1. 单元测试

使用 pytest 运行单元测试：

```bash
# 运行所有测试
uv run --extra dev pytest

# 运行测试并显示覆盖率
uv run --extra dev pytest --cov=db_schema_mcp --cov-report=html

# 运行特定测试文件
uv run --extra dev pytest tests/test_config.py

# 运行测试并显示详细输出
uv run --extra dev pytest -v
```

#### 2. 集成测试

使用 `run_tests.py` 进行集成测试：

```bash
# 1. 首先创建测试配置文件
cp config.example.yaml tests/test_config.yaml

# 2. 编辑 tests/test_config.yaml，配置数据库连接

# 3. 创建测试数据库和表
uv run python run_tests.py setup

# 4. 列出所有数据库连接
uv run python run_tests.py list

# 5. 列出指定数据库的表
uv run python run_tests.py tables <连接名>

# 6. 查看表结构
uv run python run_tests.py desc <连接名> <表名>

# 7. 进入交互模式
uv run python run_tests.py interactive
```

交互模式可用命令：
- `list` - 列出所有数据库连接
- `check` - 检查所有连接状态
- `tables <连接名>` - 列出表
- `desc <连接名> <表名>` - 显示表结构
- `quit` 或 `exit` - 退出

#### 3. 代码质量检查

```bash
# 运行类型检查
uv run --extra dev mypy src/

# 格式化代码
uv run --extra dev ruff check src/ --fix

# 仅检查不修改
uv run --extra dev ruff check src/
```

### 数据库支持

| 数据库 | 驱动 | 状态 |
|--------|------|------|
| SQLite | sqlite3 (内置) | ✅ 完全支持 |
| PostgreSQL | psycopg3 | ✅ 完全支持 |
| MySQL | aiomysql | ✅ 完全支持 |
| Oracle | oracledb | ✅ 支持 |

## 许可证

MIT 许可证 - 详见 LICENSE 文件。

## 贡献

欢迎贡献！请随时提交 Pull Request。

## 故障排查

### 连接错误

如果遇到连接错误：
1. 验证配置文件路径是否正确
2. 检查数据库凭证和主机/端口设置
3. 确保数据库可从您的机器访问
4. 查看错误消息了解具体详情

### SSL/TLS 问题

对于需要 SSL 的数据库：
- 在 YAML 配置中包含 SSL 配置
- 确保证书文件可访问
- 验证 SSL 模式设置与数据库要求匹配

### 缺少依赖

如果遇到导入错误：
```bash
pip install --upgrade db-schema-mcp
```

或用于开发：
```bash
uv sync --extra dev
```
