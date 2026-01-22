"""db-schema-mcp 的命令行界面。"""

import argparse
import asyncio
import sys
from pathlib import Path

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
""",
    )
    parser.add_argument(
        "--config",
        type=str,
        required=True,
        help="数据库配置 YAML 文件的路径",
    )
    parser.add_argument(
        "--version",
        action="version",
        version="%(prog)s 0.1.0",
    )
    return parser.parse_args()


def validate_config_path(config_path: str) -> Path:
    """验证配置文件存在且可读。"""
    path = Path(config_path).expanduser().resolve()
    if not path.exists():
        sys.stderr.write(f"错误: 配置文件未找到: {path}\n")
        sys.stderr.write("请检查路径后重试。\n")
        sys.exit(1)
    if not path.is_file():
        sys.stderr.write(f"错误: 配置路径不是文件: {path}\n")
        sys.exit(1)
    return path


async def main_async() -> None:
    """异步主入口点。"""
    args = parse_args()
    config_path = validate_config_path(args.config)

    try:
        config_manager = ConfigManager(str(config_path))
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
