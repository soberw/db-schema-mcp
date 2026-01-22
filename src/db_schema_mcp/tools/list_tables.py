"""用于列出数据库中表的 MCP 工具。"""

from db_schema_mcp.config import ConfigManager
from db_schema_mcp.connections import ConnectionFactory


async def handle_list_tables(
    config_manager: ConfigManager,
    connection_name: str,
) -> str:
    """处理 list_tables MCP 工具。

    Args:
        config_manager: ConfigManager 实例。
        connection_name: 数据库连接名称。

    Returns:
        包含表名的格式化字符串。

    Raises:
        ValueError: 如果 connection_name 不存在。
    """
    # 获取连接配置
    conn_config = config_manager.get_connection(connection_name)
    if not conn_config:
        available = config_manager.get_connection_names()
        raise ValueError(
            f"连接 '{connection_name}' 未找到。\n"
            f"可用连接: {', '.join(available)}"
        )

    # 创建连接并列出表
    conn = ConnectionFactory.create(conn_config)
    try:
        await conn.connect()
        tables = await conn.list_tables()

        if not tables:
            return f"数据库 '{connection_name}' 中未找到表。"

        lines = [f"{connection_name} 中的表:\n"]
        for table in tables:
            lines.append(f"- {table}")

        return "\n".join(lines)
    finally:
        await conn.disconnect()
