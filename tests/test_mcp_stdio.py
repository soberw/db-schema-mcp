"""Exercise the installed server over real MCP stdio, including SDK dispatch."""

import json
import sqlite3
import sys
from datetime import timedelta
from importlib.metadata import requires, version
from pathlib import Path

import pytest
import yaml
from mcp import ClientSession, StdioServerParameters, types
from mcp.client.stdio import stdio_client
from packaging.requirements import Requirement


def test_installed_metadata_limits_sdk_major_version() -> None:
    """Check the installed artifact's constraint, rather than the source lockfile."""
    requirements = [Requirement(item) for item in requires("db-schema-mcp") or []]
    sdk = next(item for item in requirements if item.name == "mcp")
    assert "1.25.0" in sdk.specifier
    assert "0.9.0" not in sdk.specifier
    assert "2.0.0" not in sdk.specifier
    assert "2.3.0" not in sdk.specifier
    assert version("mcp") in sdk.specifier


@pytest.mark.asyncio
@pytest.mark.parametrize("configured", [False, True])
async def test_installed_server_stdio(tmp_path: Path, configured: bool) -> None:
    """Catch SDK changes that imports and direct tool-handler tests miss."""
    args = ["-m", "db_schema_mcp.cli"]
    if configured:
        database = tmp_path / "test.db"
        with sqlite3.connect(database) as conn:
            conn.execute("CREATE TABLE products (id INTEGER PRIMARY KEY, name TEXT)")
            conn.execute("INSERT INTO products VALUES (1, ?)", ("O'Reilly",))
        config = tmp_path / "config.yaml"
        config.write_text(yaml.safe_dump({"databases": {
            "test": {"type": "sqlite", "path": str(database)},
        }}), encoding="utf-8")
        args.extend(["--config", str(config)])

    server = StdioServerParameters(
        command=sys.executable, args=args, cwd=tmp_path,
        env={"PYTHONUTF8": "1"},
    )
    async with stdio_client(server) as (read, write):
        async with ClientSession(read, write, read_timeout_seconds=timedelta(seconds=15)) as session:
            initialized = await session.initialize()
            assert initialized.serverInfo.name == "db-schema-mcp"
            tools = await session.list_tools()
            assert {tool.name for tool in tools.tools} == {
                "init", "list_connections", "list_tables", "describe_table", "exec_query",
            }
            connections = await session.call_tool("list_connections", {})
            assert not connections.isError
            if not configured:
                target = tmp_path / "generated.yaml"
                result = await session.call_tool("init", {"path": str(target)})
                assert not result.isError and target.exists()
                assert "databases" in yaml.safe_load(target.read_text(encoding="utf-8"))
                return
            listed = await session.call_tool("list_tables", {"connection_name": "test"})
            assert not listed.isError
            assert any(isinstance(item, types.TextContent) and "products" in item.text
                       for item in listed.content)
            described = await session.call_tool("describe_table", {
                "connection_name": "test", "table_name": "products",
            })
            assert not described.isError
            result = await session.call_tool("exec_query", {
                "connection_name": "test",
                "sql": "SELECT name FROM products WHERE id = ?",
                "parameters": [1], "response_format": "json",
            })
            assert not result.isError
            assert isinstance(result.content[0], types.TextContent)
            assert json.loads(result.content[0].text)["rows"] == [{"name": "O'Reilly"}]
