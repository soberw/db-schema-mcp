"""
db-schema-mcp: 用于数据库表结构操作的 Model Context Protocol 服务器。

本包提供用于从多种数据库类型（包括 SQLite、PostgreSQL、MySQL 和 Oracle）
查询表结构的 MCP 工具。
"""

__version__ = "0.1.0"

from db_schema_mcp.config import ConfigManager, DatabaseConfig
from db_schema_mcp.mcp_server import MCPServer

__all__ = [
    "__version__",
    "ConfigManager",
    "DatabaseConfig",
    "MCPServer",
]
