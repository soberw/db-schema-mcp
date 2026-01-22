"""用于描述表结构的 MCP 工具。"""

from db_schema_mcp.config import ConfigManager
from db_schema_mcp.connections import ConnectionFactory


async def handle_describe_table(
    config_manager: ConfigManager,
    connection_name: str,
    table_name: str,
) -> str:
    """处理 describe_table MCP 工具。

    Args:
        config_manager: ConfigManager 实例。
        connection_name: 数据库连接名称。
        table_name: 表名。

    Returns:
        包含表结构的格式化字符串。

    Raises:
        ValueError: 如果 connection_name 不存在或表未找到。
    """
    # 获取连接配置
    conn_config = config_manager.get_connection(connection_name)
    if not conn_config:
        available = config_manager.get_connection_names()
        raise ValueError(
            f"连接 '{connection_name}' 未找到。\n"
            f"可用连接: {', '.join(available)}"
        )

    # 创建连接并描述表
    conn = ConnectionFactory.create(conn_config)
    try:
        await conn.connect()
        table_desc = await conn.describe_table(table_name)

        lines = [f"## 表: {table_desc.table_name}\n"]

        # 列信息
        if table_desc.columns:
            lines.append("### 列:")
            lines.append("| 列名 | 类型 | 可空 | 默认值 | 主键 | 注释 |")
            lines.append("|------|------|------|--------|------|------|")
            for col in table_desc.columns:
                pk = "✓" if col.is_primary_key else ""
                default = col.default or ""
                nullable = "YES" if col.nullable else "NO"
                comment = col.comment or ""
                lines.append(f"| {col.name} | {col.type} | {nullable} | {default} | {pk} | {comment} |")
            lines.append("")

        # 主键
        if table_desc.primary_keys:
            lines.append(f"**主键:** {', '.join(table_desc.primary_keys)}\n")

        # 外键
        if table_desc.foreign_keys:
            lines.append("**外键:**")
            for fk in table_desc.foreign_keys:
                lines.append(f"  - {fk.column} → {fk.ref_table}.{fk.ref_column}")
            lines.append("")

        # 索引
        if table_desc.indexes:
            lines.append("**索引:**")
            for idx in table_desc.indexes:
                unique = "(唯一)" if idx.unique else ""
                lines.append(f"  - {idx.name} {unique}: {', '.join(idx.columns)}")
            lines.append("")

        return "\n".join(lines)
    finally:
        await conn.disconnect()
