"""用于列出数据库连接的 MCP 工具。"""

from typing import Any

from db_schema_mcp.config import ConfigManager, ConnectionInfo
from db_schema_mcp.connections import ConnectionFactory


async def handle_list_connections(
    config_manager: ConfigManager,
    check_status: bool = False,
) -> list[dict[str, Any]]:
    """处理 list_connections MCP 工具。

    Args:
        config_manager: ConfigManager 实例。
        check_status: 如果为 True，验证每个连接的可用性。

    Returns:
        连接信息字典列表。
    """
    connections = config_manager.list_connections()
    result: list[dict[str, Any]] = []

    for conn_config in connections:
        if check_status:
            # 尝试连接并验证状态
            try:
                conn = ConnectionFactory.create(conn_config)
                await conn.connect()
                info = await conn.get_connection_info()
                await conn.disconnect()
                result.append({
                    "name": info.name,
                    "type": info.type,
                    "host": info.host,
                    "port": info.port,
                    "database": info.database,
                    "status": info.status,
                })
            except Exception as e:
                result.append({
                    "name": conn_config.name,
                    "type": conn_config.type,
                    "host": conn_config.host or conn_config.path,
                    "port": conn_config.port,
                    "database": conn_config.database,
                    "status": "failed",
                    "error": str(e),
                })
        else:
            # 仅返回配置信息，不进行连接
            result.append({
                "name": conn_config.name,
                "type": conn_config.type,
                "host": conn_config.host or conn_config.path,
                "port": conn_config.port,
                "database": conn_config.database,
                "status": "disconnected",
            })

    return result


def format_connections_list(connections: list[dict[str, Any]]) -> str:
    """格式化连接列表用于显示。

    Args:
        connections: 连接信息字典列表。

    Returns:
        用于显示的格式化字符串。
    """
    if not connections:
        return "未配置数据库连接。"

    lines = ["可用的数据库连接:\n"]
    for i, conn in enumerate(connections, 1):
        status_emoji = "✅" if conn["status"] == "connected" else "❌" if conn["status"] == "failed" else "ℹ️"
        lines.append(f"{i}. {status_emoji} **{conn['name']}**")
        lines.append(f"   - 类型: {conn['type']}")

        if conn["type"] == "sqlite":
            lines.append(f"   - 路径: {conn['host']}")
        else:
            lines.append(f"   - 主机: {conn['host']}")
            if conn.get("port"):
                lines.append(f"   - 端口: {conn['port']}")
            lines.append(f"   - 数据库: {conn['database']}")

        if conn.get("error"):
            lines.append(f"   - 错误: {conn['error']}")
        elif conn["status"] == "disconnected":
            lines.append(f"   - 状态: 未检查")
        else:
            lines.append(f"   - 状态: {conn['status']}")
        lines.append("")

    return "\n".join(lines)
