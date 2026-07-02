"""db-schema-mcp 的集成测试。"""

import sqlite3
from pathlib import Path

import pytest
import yaml

from db_schema_mcp.config import ConfigManager
from db_schema_mcp.tools.describe_table import handle_describe_table
from db_schema_mcp.tools.exec_query import handle_exec_query
from db_schema_mcp.tools.init_config import handle_init_config
from db_schema_mcp.tools.list_connections import format_connections_list, handle_list_connections
from db_schema_mcp.tools.list_tables import handle_list_tables


class TestIntegration:
    """完整工作流的集成测试。"""

    @pytest.fixture
    def temp_db(self, tmp_path: Path) -> str:
        """创建带有测试数据的临时 SQLite 数据库。"""
        db_path = tmp_path / "test.db"
        conn = sqlite3.connect(str(db_path))
        cursor = conn.cursor()

        cursor.execute("""
            CREATE TABLE products (
                id INTEGER PRIMARY KEY,
                name TEXT NOT NULL,
                price DECIMAL(10,2)
            )
        """)

        cursor.execute("""
            CREATE TABLE inventory (
                id INTEGER PRIMARY KEY,
                product_id INTEGER,
                quantity INTEGER,
                FOREIGN KEY (product_id) REFERENCES products(id)
            )
        """)
        cursor.execute(
            "INSERT INTO products (name, price) VALUES (?, ?)",
            ("Keyboard", 299.99),
        )
        cursor.execute(
            "INSERT INTO products (name, price) VALUES (?, ?)",
            ("Mouse", 99.5),
        )

        conn.commit()
        conn.close()

        return str(db_path)

    @pytest.fixture
    def config_file(self, tmp_path: Path, temp_db: str) -> str:
        """创建测试配置文件。"""
        config_data = {
            "databases": {
                "test_db": {
                    "type": "sqlite",
                    "path": temp_db,
                }
            }
        }

        config_file = tmp_path / "test_config.yaml"
        with open(config_file, "w", encoding="utf-8") as f:
            yaml.dump(config_data, f)

        return str(config_file)

    @pytest.mark.asyncio
    async def test_list_connections(self, config_file: str) -> None:
        """测试列出所有已配置的连接。"""
        manager = ConfigManager(config_file)
        result = await handle_list_connections(manager, check_status=False)

        assert len(result) == 1
        assert result[0]["name"] == "test_db"
        assert result[0]["type"] == "sqlite"

    @pytest.mark.asyncio
    async def test_list_tables(self, config_file: str) -> None:
        """测试列出数据库中的所有表。"""
        manager = ConfigManager(config_file)
        result = await handle_list_tables(manager, "test_db")

        assert "products" in result
        assert "inventory" in result

    @pytest.mark.asyncio
    async def test_describe_table(self, config_file: str) -> None:
        """测试描述表结构。"""
        manager = ConfigManager(config_file)
        result = await handle_describe_table(manager, "test_db", "products")

        assert "products" in result
        assert "id" in result
        assert "name" in result
        assert "price" in result
        assert "主键" in result

    @pytest.mark.asyncio
    async def test_connection_not_found_error(self, config_file: str) -> None:
        """测试连接不存在时的错误。"""
        manager = ConfigManager(config_file)

        with pytest.raises(ValueError, match="连接 'nonexistent' 未找到"):
            await handle_list_tables(manager, "nonexistent")

    @pytest.mark.asyncio
    async def test_table_not_found_error(self, config_file: str) -> None:
        """测试表不存在时的错误。"""
        manager = ConfigManager(config_file)

        with pytest.raises(ValueError, match="表 'nonexistent' 未找到"):
            await handle_describe_table(manager, "test_db", "nonexistent")

    @pytest.mark.asyncio
    async def test_format_connections_list(self, config_file: str) -> None:
        """测试格式化连接列表。"""
        manager = ConfigManager(config_file)
        connections = await handle_list_connections(manager, check_status=False)
        formatted = format_connections_list(connections)

        assert "test_db" in formatted
        assert "sqlite" in formatted

    @pytest.mark.asyncio
    async def test_init_config_generates_yaml(self, tmp_path: Path) -> None:
        """测试 init 工具生成示例配置。"""
        config_path = tmp_path / "db_schema_mcp.yaml"
        manager = ConfigManager(str(config_path), allow_missing=True)

        result = await handle_init_config(manager)

        assert config_path.exists()
        assert "已生成示例配置文件" in result
        assert "databases:" in config_path.read_text(encoding="utf-8")

    @pytest.mark.asyncio
    async def test_init_config_does_not_overwrite(self, tmp_path: Path) -> None:
        """测试 init 默认不覆盖已有文件。"""
        config_path = tmp_path / "db_schema_mcp.yaml"
        config_path.write_text("existing: true\n", encoding="utf-8")
        manager = ConfigManager(None, allow_missing=True)

        result = await handle_init_config(manager, path=str(config_path))

        assert "配置文件已存在" in result
        assert config_path.read_text(encoding="utf-8") == "existing: true\n"

    @pytest.mark.asyncio
    async def test_exec_query(self, config_file: str) -> None:
        """测试 exec_query 执行只读参数化查询。"""
        manager = ConfigManager(config_file)
        result = await handle_exec_query(
            manager,
            connection_name="test_db",
            sql="SELECT name, price FROM products WHERE price > ? ORDER BY price",
            parameters=[100],
            limit=10,
        )

        assert "Keyboard" in result
        assert "Mouse" not in result

    @pytest.mark.asyncio
    async def test_exec_query_rejects_non_query(self, config_file: str) -> None:
        """测试 exec_query 拒绝修改语句。"""
        manager = ConfigManager(config_file)

        with pytest.raises(ValueError, match="只允许"):
            await handle_exec_query(
                manager,
                connection_name="test_db",
                sql="DELETE FROM products",
            )
