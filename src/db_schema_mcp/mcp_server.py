"""db-schema-mcp 的 MCP 服务器实现。

本模块提供主 MCP 服务器，处理与 MCP 客户端的通信，
并将工具调用路由到相应的处理器。
"""

import asyncio
from typing import Any

import mcp.server.stdio
import mcp.types as types
from mcp.server import Server

from db_schema_mcp.config import ConfigManager
from db_schema_mcp.tools.describe_table import handle_describe_table
from db_schema_mcp.tools.list_connections import (
    format_connections_list,
    handle_list_connections,
)
from db_schema_mcp.tools.list_tables import handle_list_tables


class MCPServer:
    """用于数据库表结构操作的 MCP 服务器。

    此服务器提供三个工具:
    - list_connections: 列出所有已配置的数据库连接
    - list_tables: 列出数据库中的表
    - describe_table: 获取表结构详细信息
    """

    def __init__(self, config_manager: ConfigManager) -> None:
        """初始化 MCP 服务器。

        Args:
            config_manager: 用于数据库配置的 ConfigManager 实例。
        """
        self._config_manager = config_manager
        self._app = Server("db-schema-mcp")
        self._setup_tools()

    def _setup_tools(self) -> None:
        """注册所有 MCP 工具。"""

        @self._app.call_tool()
        async def call_tool(
            name: str, arguments: dict[str, Any]
        ) -> list[types.TextContent]:
            """处理工具调用。"""
            try:
                if name == "list_connections":
                    check_status = arguments.get("check_status", False)
                    connections = await handle_list_connections(
                        self._config_manager, check_status
                    )
                    result = format_connections_list(connections)
                    return [types.TextContent(type="text", text=result)]

                elif name == "list_tables":
                    connection_name = arguments.get("connection_name")
                    if not connection_name:
                        return [
                            types.TextContent(
                                type="text",
                                text="错误: 需要 'connection_name' 参数。",
                            )
                        ]
                    result = await handle_list_tables(self._config_manager, connection_name)
                    return [types.TextContent(type="text", text=result)]

                elif name == "describe_table":
                    connection_name = arguments.get("connection_name")
                    table_name = arguments.get("table_name")
                    if not connection_name or not table_name:
                        return [
                            types.TextContent(
                                type="text",
                                text="错误: 需要 'connection_name' 和 'table_name' 参数。",
                            )
                        ]
                    result = await handle_describe_table(
                        self._config_manager, connection_name, table_name
                    )
                    return [types.TextContent(type="text", text=result)]

                else:
                    return [
                        types.TextContent(
                            type="text", text=f"错误: 未知的工具 '{name}'"
                        )
                    ]
            except Exception as e:
                return [types.TextContent(type="text", text=f"错误: {e}")]

        @self._app.list_tools()
        async def list_tools() -> list[types.Tool]:
            """列出可用工具。"""
            return [
                types.Tool(
                    name="list_connections",
                    description="列出所有已配置的数据库连接。可选择验证连接可用性。",
                    inputSchema={
                        "type": "object",
                        "properties": {
                            "check_status": {
                                "type": "boolean",
                                "description": "验证连接可用性（会增加响应时间）",
                                "default": False,
                            }
                        },
                    },
                ),
                types.Tool(
                    name="list_tables",
                    description="列出指定数据库中的所有表。",
                    inputSchema={
                        "type": "object",
                        "properties": {
                            "connection_name": {
                                "type": "string",
                                "description": "数据库连接名称",
                            }
                        },
                        "required": ["connection_name"],
                    },
                ),
                types.Tool(
                    name="describe_table",
                    description="获取指定表的详细结构信息。",
                    inputSchema={
                        "type": "object",
                        "properties": {
                            "connection_name": {
                                "type": "string",
                                "description": "数据库连接名称",
                            },
                            "table_name": {
                                "type": "string",
                                "description": "表名",
                            },
                        },
                        "required": ["connection_name", "table_name"],
                    },
                ),
            ]

    async def start(self) -> None:
        """启动 MCP 服务器。

        此方法使用 stdio 传输运行服务器。
        """
        async with mcp.server.stdio.stdio_server() as (read_stream, write_stream):
            await self._app.run(
                read_stream,
                write_stream,
                self._app.create_initialization_options(),
            )
