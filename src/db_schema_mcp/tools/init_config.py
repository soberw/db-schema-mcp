"""用于生成示例配置文件的 MCP 工具。"""

from pathlib import Path

from db_schema_mcp.config import ConfigManager

SAMPLE_CONFIG = """# db-schema-mcp 配置示例
# 请保留需要的连接并删除不使用的示例项。

databases:
  sqlite_local:
    type: sqlite
    path: /path/to/your/database.db

  postgres_local:
    type: postgresql
    host: localhost
    port: 5432
    user: postgres
    password: your_password
    database: your_database
    # sslmode: require

  mysql_local:
    type: mysql
    host: localhost
    port: 3306
    user: your_username
    password: your_password
    database: your_database
    # ssl:
    #   charset: utf8mb4

  oracle_local:
    type: oracle
    host: localhost
    port: 1521
    user: your_username
    password: your_password
    database: ORCL
"""


def _resolve_output_path(config_manager: ConfigManager, path: str | None) -> Path | None:
    target: Path | None
    if path and path.strip():
        target = Path(path).expanduser()
    else:
        target = config_manager.config_path

    if target is None:
        return None

    target = target.resolve()
    if target.exists() and target.is_dir():
        return target / "db_schema_mcp.yaml"
    return target


async def handle_init_config(
    config_manager: ConfigManager,
    path: str | None = None,
    overwrite: bool = False,
) -> str:
    """生成示例 YAML 配置文件。

    Args:
        config_manager: 当前配置管理器。
        path: 可选输出路径。未提供时优先使用 CLI 的 --config 路径。
        overwrite: 是否覆盖已存在文件。

    Returns:
        操作结果文本。
    """
    output_path = _resolve_output_path(config_manager, path)
    if output_path is None:
        return (
            "请提供配置文件存放路径，例如调用 init 时传入 "
            "`path: \"./db_schema_mcp.yaml\"`。"
        )

    if output_path.exists() and not overwrite:
        return (
            f"配置文件已存在: {output_path}\n"
            "未覆盖已有文件。如确认要覆盖，请传入 `overwrite: true`。"
        )

    output_path.parent.mkdir(parents=True, exist_ok=True)
    output_path.write_text(SAMPLE_CONFIG, encoding="utf-8")

    return (
        f"已生成示例配置文件: {output_path}\n"
        "请编辑其中的数据库连接信息，然后使用 "
        f"`db-schema-mcp --config \"{output_path}\"` 启动 MCP 服务。"
    )
