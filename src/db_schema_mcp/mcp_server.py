"""db-schema-mcp 的 MCP 服务器实现。

本模块提供主 MCP 服务器，处理与 MCP 客户端的通信，
并将工具调用路由到相应的处理器。
"""

from typing import Any

import mcp.server.stdio
import mcp.types as types
from mcp.server import Server

from db_schema_mcp.config import ConfigManager
from db_schema_mcp.tools.describe_table import handle_describe_table
from db_schema_mcp.tools.exec_query import handle_exec_query
from db_schema_mcp.tools.init_config import handle_init_config
from db_schema_mcp.tools.list_connections import (
    format_connections_list,
    handle_list_connections,
)
from db_schema_mcp.tools.list_tables import handle_list_tables


class MCPServer:
    """用于数据库表结构操作的 MCP 服务器。

    此服务器提供五个工具:
    - init: 生成示例 YAML 配置文件
    - list_connections: 列出所有已配置的数据库连接
    - list_tables: 列出数据库中的表
    - describe_table: 获取表结构详细信息
    - exec_query: 执行只读 SQL 查询
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
            arguments = arguments or {}
            try:
                if name == "init":
                    result = await handle_init_config(
                        self._config_manager,
                        path=arguments.get("path"),
                        overwrite=arguments.get("overwrite", False),
                    )
                    return [types.TextContent(type="text", text=result)]

                elif name == "list_connections":
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

                elif name == "exec_query":
                    connection_name = arguments.get("connection_name")
                    sql = arguments.get("sql")
                    if not connection_name or not sql:
                        return [
                            types.TextContent(
                                type="text",
                                text="错误: 需要 'connection_name' 和 'sql' 参数。",
                            )
                        ]
                    result = await handle_exec_query(
                        self._config_manager,
                        connection_name=connection_name,
                        sql=sql,
                        parameters=arguments.get("parameters"),
                        limit=arguments.get("limit"),
                        response_format=arguments.get("response_format", "markdown"),
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
                    name="init",
                    description=(
                        "生成 db-schema-mcp 示例 YAML 配置文件。"
                        "当 MCP 启动时没有配置文件，可先调用此工具创建配置模板。"
                    ),
                    inputSchema={
                        "type": "object",
                        "properties": {
                            "path": {
                                "type": "string",
                                "description": (
                                    "配置文件输出路径。未提供时使用 CLI 的 --config 路径；"
                                    "若也没有 --config，工具会提示用户提供路径。"
                                ),
                            },
                            "overwrite": {
                                "type": "boolean",
                                "description": "是否覆盖已存在的配置文件",
                                "default": False,
                            },
                        },
                    },
                    annotations=types.ToolAnnotations(
                        title="生成示例配置",
                        readOnlyHint=False,
                        destructiveHint=False,
                        idempotentHint=True,
                        openWorldHint=False,
                    ),
                ),
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
                    annotations=types.ToolAnnotations(
                        title="列出数据库连接",
                        readOnlyHint=True,
                        destructiveHint=False,
                        idempotentHint=True,
                        openWorldHint=False,
                    ),
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
                    annotations=types.ToolAnnotations(
                        title="列出数据库表",
                        readOnlyHint=True,
                        destructiveHint=False,
                        idempotentHint=True,
                        openWorldHint=True,
                    ),
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
                    annotations=types.ToolAnnotations(
                        title="描述表结构",
                        readOnlyHint=True,
                        destructiveHint=False,
                        idempotentHint=True,
                        openWorldHint=True,
                    ),
                ),
                types.Tool(
                    name="exec_query",
                    description=(
                        "执行只读 SQL 查询并返回结果。仅允许单条 SELECT/WITH 查询；"
                        "禁止 INSERT、UPDATE、DELETE、DDL、多语句和 SELECT INTO。"
                        "如需动态值，请使用 parameters 参数绑定，避免拼接 SQL。"
                    ),
                    inputSchema={
                        "type": "object",
                        "properties": {
                            "connection_name": {
                                "type": "string",
                                "description": "数据库连接名称",
                            },
                            "sql": {
                                "type": "string",
                                "description": "只读 SQL 查询，必须以 SELECT 或 WITH 开头",
                            },
                            "parameters": {
                                "description": (
                                    "参数化查询绑定值。可传数组或对象；不要把外部输入拼接进 SQL。"
                                ),
                                "oneOf": [
                                    {"type": "array"},
                                    {"type": "object"},
                                    {"type": "null"},
                                ],
                            },
                            "limit": {
                                "type": "integer",
                                "description": "最大返回行数，默认 100，最大 1000",
                                "minimum": 1,
                                "maximum": 1000,
                                "default": 100,
                            },
                            "response_format": {
                                "type": "string",
                                "description": "返回格式：markdown 或 json",
                                "enum": ["markdown", "json"],
                                "default": "markdown",
                            },
                        },
                        "required": ["connection_name", "sql"],
                    },
                    annotations=types.ToolAnnotations(
                        title="执行只读查询",
                        readOnlyHint=True,
                        destructiveHint=False,
                        idempotentHint=True,
                        openWorldHint=True,
                    ),
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
