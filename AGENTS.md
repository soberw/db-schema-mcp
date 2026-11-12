# 项目指引

- Python 3.12+，使用 uv 执行 Python、测试和打包。
- `src/db_schema_mcp/config.py` 管理 YAML 和数据模型。
- `src/db_schema_mcp/connections/` 管理数据库适配器，`factory.py` 注册类型；
  `oceanbase.py` 使用纯 Python pyoceanbase 连接 OceanBase Oracle 租户。
- `src/db_schema_mcp/tools/` 包含 init、连接/表结构工具和只读 exec_query。
- `tests/test_oceanbase.py` 验证适配器；真实租户测试显式通过环境变量启用。
- 新数据库应同步 README、config.example.yaml 和 init_config.py 的模板。
- `tasks/` 为独立 Git 账本，禁止混入业务仓库提交。
- 验证使用 `uv run --extra dev pytest tests/ -q`、
  `uv run --extra dev ruff check src tests` 和 `uv run --extra dev mypy src/`。
