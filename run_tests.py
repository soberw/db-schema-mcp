"""独立的数据库 schema 查询测试脚本。

此脚本可以直接运行，用于测试数据库连接和表结构查询功能，
不需要通过 MCP 协议。
"""

import asyncio
import io
import sys
from pathlib import Path

# 设置 UTF-8 编码输出（兼容 Windows）
if sys.platform == "win32":
    sys.stdout = io.TextIOWrapper(sys.stdout.buffer, encoding="utf-8", errors="replace")
    sys.stderr = io.TextIOWrapper(sys.stderr.buffer, encoding="utf-8", errors="replace")

# 添加 src 目录到 Python 路径
sys.path.insert(0, str(Path(__file__).parent / "src"))

from db_schema_mcp.config import ConfigManager
from db_schema_mcp.connections import ConnectionFactory


async def list_connections(config_manager: ConfigManager, check_status: bool = False) -> None:
    """列出所有已配置的数据库连接。

    Args:
        config_manager: 配置管理器实例。
        check_status: 是否检查连接状态。
    """
    print("\n" + "=" * 60)
    print("📋 已配置的数据库连接")
    print("=" * 60)

    connections = config_manager.list_connections()
    if not connections:
        print("❌ 未找到任何数据库连接配置。")
        return

    for conn_config in connections:
        print(f"\n🔹 连接名称: {conn_config.name}")
        print(f"   类型: {conn_config.type}")
        if conn_config.type == "sqlite":
            print(f"   路径: {conn_config.path}")
        else:
            print(f"   主机: {conn_config.host}:{conn_config.port}")
            print(f"   数据库: {conn_config.database}")
            print(f"   用户: {conn_config.user}")

        if check_status:
            try:
                conn = ConnectionFactory.create(conn_config)
                await conn.connect()
                print(f"   状态: ✅ 连接成功")
                await conn.disconnect()
            except Exception as e:
                print(f"   状态: ❌ 连接失败 - {e}")


async def list_tables(
    config_manager: ConfigManager, connection_name: str, show_details: bool = False
) -> None:
    """列出指定数据库中的所有表。

    Args:
        config_manager: 配置管理器实例。
        connection_name: 数据库连接名称。
        show_details: 是否显示详细信息。
    """
    print("\n" + "=" * 60)
    print(f"📊 数据库 '{connection_name}' 中的表")
    print("=" * 60)

    conn_config = config_manager.get_connection(connection_name)
    if not conn_config:
        available = config_manager.get_connection_names()
        print(f"❌ 连接 '{connection_name}' 未找到。")
        print(f"   可用连接: {', '.join(available)}")
        return

    conn = ConnectionFactory.create(conn_config)
    try:
        await conn.connect()
        tables = await conn.list_tables()

        if not tables:
            print("❌ 数据库中未找到任何表。")
            return

        print(f"\n共找到 {len(tables)} 个表:\n")
        for i, table in enumerate(tables, 1):
            print(f"  {i}. {table}")

        if show_details:
            print("\n" + "-" * 60)
            for table in tables:
                print(f"\n📋 表: {table}")
                desc = await conn.describe_table(table)
                print(f"   列数: {len(desc.columns)}")
                print(f"   主键: {', '.join(desc.primary_keys) if desc.primary_keys else '无'}")
                print(f"   外键: {len(desc.foreign_keys)} 个")
                print(f"   索引: {len(desc.indexes)} 个")

    finally:
        await conn.disconnect()


async def describe_table(
    config_manager: ConfigManager, connection_name: str, table_name: str
) -> None:
    """获取指定表的详细结构信息。

    Args:
        config_manager: 配置管理器实例。
        connection_name: 数据库连接名称。
        table_name: 表名。
    """
    print("\n" + "=" * 60)
    print(f"📋 表 '{table_name}' 的详细结构")
    print("=" * 60)

    conn_config = config_manager.get_connection(connection_name)
    if not conn_config:
        available = config_manager.get_connection_names()
        print(f"❌ 连接 '{connection_name}' 未找到。")
        print(f"   可用连接: {', '.join(available)}")
        return

    conn = ConnectionFactory.create(conn_config)
    try:
        await conn.connect()
        table_desc = await conn.describe_table(table_name)

        print(f"\n📌 表名: {table_desc.table_name}")

        # 列信息
        if table_desc.columns:
            print(f"\n📝 列信息 ({len(table_desc.columns)} 列):")
            print("\n{:<20} {:<15} {:<8} {:<12} {:<8} {:<20}".format("列名", "类型", "可空", "默认值", "主键", "注释"))
            print("-" * 90)
            for col in table_desc.columns:
                pk = "✓" if col.is_primary_key else ""
                default = col.default or ""
                nullable = "YES" if col.nullable else "NO"
                comment = col.comment or ""
                print(
                    "{:<20} {:<15} {:<8} {:<12} {:<8} {:<20}".format(
                        col.name, col.type, nullable, str(default)[:12], pk, comment
                    )
                )

        # 主键
        if table_desc.primary_keys:
            print(f"\n🔑 主键: {', '.join(table_desc.primary_keys)}")

        # 外键
        if table_desc.foreign_keys:
            print(f"\n🔗 外键 ({len(table_desc.foreign_keys)} 个):")
            for fk in table_desc.foreign_keys:
                print(f"   • {fk.column} → {fk.ref_table}.{fk.ref_column}")

        # 索引
        if table_desc.indexes:
            print(f"\n📇 索引 ({len(table_desc.indexes)} 个):")
            for idx in table_desc.indexes:
                unique = " [唯一]" if idx.unique else ""
                print(f"   • {idx.name}{unique}: {', '.join(idx.columns)}")

    finally:
        await conn.disconnect()


async def interactive_mode(config_manager: ConfigManager) -> None:
    """交互式模式，允许用户输入命令进行查询。

    Args:
        config_manager: 配置管理器实例。
    """
    print("\n" + "=" * 60)
    print("🚀 交互式数据库 Schema 查询工具")
    print("=" * 60)
    print("\n可用命令:")
    print("  list                    - 列出所有数据库连接")
    print("  tables <连接名>         - 列出指定数据库的所有表")
    print("  desc <连接名> <表名>    - 显示表的详细结构")
    print("  check                   - 检查所有连接状态")
    print("  quit / exit             - 退出程序")

    while True:
        try:
            command = input("\n🔍 输入命令> ").strip()
            if not command:
                continue

            parts = command.split()
            cmd = parts[0].lower()

            if cmd in ["quit", "exit", "q"]:
                print("👋 再见!")
                break

            elif cmd == "list":
                await list_connections(config_manager)

            elif cmd == "check":
                await list_connections(config_manager, check_status=True)

            elif cmd == "tables":
                if len(parts) < 2:
                    print("❌ 用法: tables <连接名>")
                    continue
                await list_tables(config_manager, parts[1])

            elif cmd == "desc":
                if len(parts) < 3:
                    print("❌ 用法: desc <连接名> <表名>")
                    continue
                await describe_table(config_manager, parts[1], parts[2])

            else:
                print(f"❌ 未知命令: {cmd}")
                print("   输入 'quit' 退出程序")

        except KeyboardInterrupt:
            print("\n👋 再见!")
            break
        except Exception as e:
            print(f"❌ 错误: {e}")


async def setup_all_databases() -> None:
    """一键创建所有已配置数据库的测试数据。"""
    print("\n" + "=" * 60)
    print("🔧 创建所有数据库测试数据")
    print("=" * 60)

    # 1. 创建 SQLite 测试数据库
    print("\n📦 创建 SQLite 测试数据库...")
    sqlite_script = Path(__file__).parent / "tests" / "setup_test_db.py"
    if sqlite_script.exists():
        import subprocess
        result = subprocess.run([sys.executable, str(sqlite_script)], capture_output=True)
        if result.returncode == 0:
            print(result.stdout.decode())
        else:
            print(f"❌ SQLite 创建失败: {result.stderr.decode()}")
    else:
        print(f"❌ 未找到 SQLite 创建脚本: {sqlite_script}")

    # 2. 创建 MySQL 测试数据库（如果配置了）
    print("\n📦 检查 MySQL 配置...")
    mysql_script = Path(__file__).parent / "tests" / "setup_mysql_test_db.py"
    if mysql_script.exists():
        import subprocess
        result = subprocess.run([sys.executable, str(mysql_script)], capture_output=True)
        if result.returncode == 0:
            print(result.stdout.decode())
        else:
            # MySQL 可能未配置，显示警告但不报错
            stderr = result.stderr.decode()
            if "未在配置文件中找到 MySQL 配置" in stderr:
                print("⚠️  未配置 MySQL，跳过")
            else:
                print(f"❌ MySQL 创建失败: {stderr}")

    # 3. 创建 Oracle 测试表（如果配置了）
    print("\n📦 检查 Oracle 配置...")
    oracle_script = Path(__file__).parent / "tests" / "setup_oracle_test_db.py"
    if oracle_script.exists():
        import subprocess
        result = subprocess.run([sys.executable, str(oracle_script)], capture_output=True)
        if result.returncode == 0:
            print(result.stdout.decode())
        else:
            # Oracle 可能未配置，显示警告但不报错
            stderr = result.stderr.decode()
            if "未在配置文件中找到 Oracle 配置" in stderr:
                print("⚠️  未配置 Oracle，跳过")
            else:
                print(f"❌ Oracle 创建失败: {stderr}")

    print("\n" + "=" * 60)
    print("✅ 测试数据创建完成!")
    print("=" * 60)


async def main() -> None:
    """主函数。"""
    # 默认配置文件路径
    config_path = "./tests/test_config.yaml"

    # 解析命令行参数
    if len(sys.argv) >= 2 and sys.argv[1].lower() in ["setup", "init"]:
        await setup_all_databases()
        return

    # 检查配置文件是否存在
    if not Path(config_path).exists():
        print(f"❌ 配置文件未找到: {config_path}")
        print("\n请先创建配置文件，可以复制示例文件:")
        print("  cp config.example.yaml tests/test_config.yaml")
        print("\n然后编辑 tests/test_config.yaml 配置数据库连接")
        return

    try:
        config_manager = ConfigManager(config_path)
    except Exception as e:
        print(f"❌ 加载配置文件失败: {e}")
        return

    # 解析命令行参数
    if len(sys.argv) < 2:
        # 无参数时进入交互模式
        await interactive_mode(config_manager)
        return

    command = sys.argv[1].lower()

    if command == "list":
        check = "--check" in sys.argv or "-c" in sys.argv
        await list_connections(config_manager, check_status=check)

    elif command == "tables":
        if len(sys.argv) < 3:
            print("用法: python run_tests.py tables <连接名>")
            return
        details = "--details" in sys.argv or "-d" in sys.argv
        await list_tables(config_manager, sys.argv[2], show_details=details)

    elif command == "desc":
        if len(sys.argv) < 4:
            print("用法: python run_tests.py desc <连接名> <表名>")
            return
        await describe_table(config_manager, sys.argv[2], sys.argv[3])

    elif command == "interactive" or command == "i":
        await interactive_mode(config_manager)

    else:
        print(f"❌ 未知命令: {command}")
        print("\n用法:")
        print("  python run_tests.py setup                   # 创建所有测试数据库")
        print("  python run_tests.py list [--check]          # 列出所有连接")
        print("  python run_tests.py tables <连接名>         # 列出表")
        print("  python run_tests.py desc <连接名> <表名>    # 显示表结构")
        print("  python run_tests.py interactive             # 交互模式")


if __name__ == "__main__":
    asyncio.run(main())
