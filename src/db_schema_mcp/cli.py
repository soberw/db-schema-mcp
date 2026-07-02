"""db-schema-mcp 的命令行界面。"""

import argparse
import asyncio
import sys
from pathlib import Path

from db_schema_mcp._version import get_version
from db_schema_mcp.config import ConfigManager
from db_schema_mcp.mcp_server import MCPServer


def parse_args() -> argparse.Namespace:
    """解析命令行参数。"""
    parser = argparse.ArgumentParser(
        description="db-schema-mcp: 数据库表结构 MCP 服务器",
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog="""
示例:
  db-schema-mcp --config /path/to/db_config.yaml
  db-schema-mcp --config ./config.yaml
  db-schema-mcp

未提供或找不到 --config 时，服务仍会启动，可先通过 init 工具生成示例配置。
""",
    )
    parser.add_argument(
        "--config",
        type=str,
        required=False,
        help="数据库配置 YAML 文件的路径",
    )
    parser.add_argument(
        "--version",
        action="version",
        version=f"%(prog)s {get_version()}",
    )
    return parser.parse_args()


def resolve_config_path(config_path: str | None) -> Path | None:
    """解析配置文件路径。

    配置文件允许不存在，以便 MCP 启动后通过 init 工具生成。
    """
    if not config_path:
        return None

    path = Path(config_path).expanduser().resolve()
    if path.exists() and not path.is_file():
        sys.stderr.write(f"错误: 配置路径不是文件: {path}\n")
        sys.exit(1)
    return path


async def main_async() -> None:
    """异步主入口点。"""
    args = parse_args()
    config_path = resolve_config_path(args.config)
    if config_path is None:
        sys.stderr.write("未提供配置文件路径。可通过 init 工具生成示例配置。\n")
    elif not config_path.exists():
        sys.stderr.write(
            f"配置文件暂不存在: {config_path}\n"
            "MCP 服务将以空配置启动，可通过 init 工具生成示例配置。\n"
        )

    try:
        config_manager = ConfigManager(
            str(config_path) if config_path else None,
            allow_missing=True,
        )
    except Exception as e:
        sys.stderr.write(f"加载配置出错: {e}\n")
        sys.stderr.write("请检查 YAML 格式后重试。\n")
        sys.exit(1)

    server = MCPServer(config_manager)
    await server.start()


def main() -> None:
    """CLI 的主入口点。"""
    try:
        asyncio.run(main_async())
    except KeyboardInterrupt:
        sys.stderr.write("\n正在优雅关闭...\n")
        sys.exit(0)
    except Exception as e:
        sys.stderr.write(f"错误: {e}\n")
        sys.exit(1)


if __name__ == "__main__":
    main()
