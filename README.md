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

### list-connections

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

### list-tables

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

### describe-table

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

## 安全性

- 所有数据库操作在本地执行
- 没有数据传输到外部服务
- 数据库凭证存储在本地配置文件中
- 仅访问元数据（表结构），不访问实际数据

## 开发

### 搭建开发环境

```bash
# 克隆仓库
git clone https://github.com/soberw/db-schema-mcp.git
cd db-schema-mcp

# 以可编辑模式安装
uv pip install -e ".[dev]"
```

### 运行测试

#### 1. 单元测试

使用 pytest 运行单元测试：

```bash
# 运行所有测试
pytest

# 运行测试并显示覆盖率
pytest --cov=db_schema_mcp --cov-report=html

# 运行特定测试文件
pytest tests/test_config.py

# 运行测试并显示详细输出
pytest -v
```

#### 2. 集成测试

使用 `run_tests.py` 进行集成测试：

```bash
# 1. 首先创建测试配置文件
cp config.example.yaml tests/test_config.yaml

# 2. 编辑 tests/test_config.yaml，配置数据库连接

# 3. 创建测试数据库和表
python run_tests.py setup

# 4. 列出所有数据库连接
python run_tests.py list

# 5. 列出指定数据库的表
python run_tests.py tables <连接名>

# 6. 查看表结构
python run_tests.py desc <连接名> <表名>

# 7. 进入交互模式
python run_tests.py interactive
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
mypy src/

# 格式化代码
ruff check src/ --fix

# 仅检查不修改
ruff check src/
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
uv pip install -e ".[dev]"
```
