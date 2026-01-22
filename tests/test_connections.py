"""数据库连接实现的测试。"""

import sqlite3
import tempfile
from pathlib import Path

import pytest

from db_schema_mcp.config import DatabaseConfig
from db_schema_mcp.connections.sqlite import SQLiteConnection


class TestSQLiteConnection:
    """测试 SQLite 连接实现。"""

    @pytest.fixture
    def temp_db(self, tmp_path: Path) -> str:
        """创建带有测试数据的临时 SQLite 数据库。"""
        db_path = tmp_path / "test.db"
        conn = sqlite3.connect(str(db_path))
        cursor = conn.cursor()

        # 创建测试表 - 带有内联注释
        cursor.execute("""
            CREATE TABLE customers (
                id INTEGER PRIMARY KEY, -- 主键 ID
                name TEXT NOT NULL, -- 客户姓名
                email TEXT /* 电子邮箱地址 */
            )
        """)

        cursor.execute("""
            CREATE TABLE orders (
                id INTEGER PRIMARY KEY,
                customer_id INTEGER,
                total DECIMAL(10,2),
                FOREIGN KEY (customer_id) REFERENCES customers(id)
            )
        """)

        cursor.execute("CREATE INDEX idx_customers_email ON customers(email)")

        conn.commit()
        conn.close()

        return str(db_path)

    @pytest.fixture
    def sqlite_config(self, temp_db: str) -> DatabaseConfig:
        """创建 SQLite 数据库配置。"""
        return DatabaseConfig(
            name="test_sqlite",
            type="sqlite",
            path=temp_db,
        )

    @pytest.mark.asyncio
    async def test_connect(self, sqlite_config: DatabaseConfig) -> None:
        """测试连接到 SQLite 数据库。"""
        conn = SQLiteConnection(sqlite_config)
        await conn.connect()
        assert await conn.is_connected() is True
        await conn.disconnect()

    @pytest.mark.asyncio
    async def test_list_tables(self, sqlite_config: DatabaseConfig) -> None:
        """测试列出数据库中的所有表。"""
        conn = SQLiteConnection(sqlite_config)
        await conn.connect()
        tables = await conn.list_tables()
        await conn.disconnect()

        assert "customers" in tables
        assert "orders" in tables
        assert len(tables) == 2

    @pytest.mark.asyncio
    async def test_describe_table(self, sqlite_config: DatabaseConfig) -> None:
        """测试描述表结构。"""
        conn = SQLiteConnection(sqlite_config)
        await conn.connect()
        desc = await conn.describe_table("customers")
        await conn.disconnect()

        assert desc.table_name == "customers"
        assert len(desc.columns) == 3
        assert desc.columns[0].name == "id"
        assert desc.columns[0].is_primary_key is True
        assert "id" in desc.primary_keys
        assert len(desc.indexes) > 0

    @pytest.mark.asyncio
    async def test_foreign_keys(self, sqlite_config: DatabaseConfig) -> None:
        """测试外键检测。"""
        conn = SQLiteConnection(sqlite_config)
        await conn.connect()
        desc = await conn.describe_table("orders")
        await conn.disconnect()

        assert len(desc.foreign_keys) == 1
        fk = desc.foreign_keys[0]
        assert fk.column == "customer_id"
        assert fk.ref_table == "customers"
        assert fk.ref_column == "id"

    @pytest.mark.asyncio
    async def test_table_not_found(self, sqlite_config: DatabaseConfig) -> None:
        """测试表不存在时的错误。"""
        conn = SQLiteConnection(sqlite_config)
        await conn.connect()

        with pytest.raises(ValueError, match="表 'nonexistent' 未找到"):
            await conn.describe_table("nonexistent")

        await conn.disconnect()

    @pytest.mark.asyncio
    async def test_get_connection_info(self, sqlite_config: DatabaseConfig) -> None:
        """测试获取连接信息。"""
        conn = SQLiteConnection(sqlite_config)
        await conn.connect()
        info = await conn.get_connection_info()
        await conn.disconnect()

        assert info.name == "test_sqlite"
        assert info.type == "sqlite"
        assert info.status == "connected"

    @pytest.mark.asyncio
    async def test_column_comments(self, sqlite_config: DatabaseConfig) -> None:
        """测试列注释功能。"""
        conn = SQLiteConnection(sqlite_config)
        await conn.connect()
        desc = await conn.describe_table("customers")
        await conn.disconnect()

        # 验证列注释被正确解析
        assert desc.columns[0].comment is not None  # id 列有注释
        assert "主键" in desc.columns[0].comment or "ID" in desc.columns[0].comment
        assert desc.columns[1].comment is not None  # name 列有注释
        assert "客户" in desc.columns[1].comment or "姓名" in desc.columns[1].comment
        assert desc.columns[2].comment is not None  # email 列有注释
        assert "邮箱" in desc.columns[2].comment or "email" in desc.columns[2].comment.lower()
