"""MySQL database connection implementation.

This module provides DatabaseConnection implementation for MySQL
using the aiomysql driver.
"""

import asyncio
from typing import Any

import aiomysql

from db_schema_mcp.config import (
    ColumnInfo,
    ConnectionInfo,
    DatabaseConfig,
    ForeignKeyInfo,
    IndexInfo,
    TableDescription,
)
from db_schema_mcp.connections.base import DatabaseConnection


class MySQLConnection(DatabaseConnection):
    """Database connection implementation for MySQL.

    Uses aiomysql to connect to MySQL databases and queries
    information_schema for metadata.
    """

    def __init__(self, config: DatabaseConfig) -> None:
        """Initialize MySQL connection.

        Args:
            config: DatabaseConfig with type='mysql'.
        """
        super().__init__(config)
        self._pool: aiomysql.Pool | None = None

    async def connect(self) -> None:
        """Establish MySQL database connection.

        Raises:
            ConnectionError: If connection fails.
        """
        try:
            self._pool = await aiomysql.create_pool(
                host=self._config.host,
                port=self._config.port or 3306,
                user=self._config.user,
                password=self._config.password,
                db=self._config.database,
                charset=self._config.ssl.get("charset", "utf8mb4") if self._config.ssl else "utf8mb4",
                autocommit=True,
            )
            self._is_connected = True
        except aiomysql.Error as e:
            msg = f"Failed to connect to MySQL database '{self._config.database}': {e}"
            raise ConnectionError(msg) from e

    async def disconnect(self) -> None:
        """Close MySQL connection pool."""
        if self._pool:
            self._pool.close()
            await self._pool.wait_closed()
            self._pool = None
            self._is_connected = False

    async def is_connected(self) -> bool:
        """Check if MySQL connection is active.

        Returns:
            True if connected, False otherwise.
        """
        if not self._pool:
            return False
        try:
            async with self._pool.acquire() as conn:
                async with conn.cursor() as cursor:
                    await cursor.execute("SELECT 1")
            return True
        except aiomysql.Error:
            return False

    async def list_tables(self) -> list[str]:
        """Get all table names in the MySQL database.

        Returns:
            List of table names.

        Raises:
            ConnectionError: If not connected.
        """
        if not self._is_connected or not self._pool:
            msg = "Not connected to database"
            raise ConnectionError(msg)

        query = """
            SELECT table_name
            FROM information_schema.tables
            WHERE table_schema = %s
                AND table_type = 'BASE TABLE'
            ORDER BY table_name
        """

        async with self._pool.acquire() as conn:
            async with conn.cursor() as cursor:
                await cursor.execute(query, (self._config.database,))
                return [row[0] for row in await cursor.fetchall()]

    async def describe_table(self, table_name: str) -> TableDescription:
        """Get detailed structure information for a MySQL table.

        Args:
            table_name: The name of the table.

        Returns:
            TableDescription with complete schema information.

        Raises:
            ConnectionError: If not connected.
            ValueError: If table doesn't exist.
        """
        if not self._is_connected or not self._pool:
            msg = "Not connected to database"
            raise ConnectionError(msg)

        # Check if table exists
        check_query = """
            SELECT table_name
            FROM information_schema.tables
            WHERE table_schema = %s AND table_name = %s
        """

        async with self._pool.acquire() as conn:
            async with conn.cursor() as cursor:
                await cursor.execute(check_query, (self._config.database, table_name))
                if not await cursor.fetchone():
                    available = await self.list_tables()
                    msg = f"Table '{table_name}' not found. Available tables: {', '.join(available)}"
                    raise ValueError(msg)

        # Get column information
        columns_query = """
            SELECT
                c.column_name,
                c.data_type,
                CASE
                    WHEN c.is_nullable = 'YES' THEN TRUE
                    ELSE FALSE
                END AS nullable,
                c.column_default,
                CASE
                    WHEN c.column_key = 'PRI' THEN TRUE
                    ELSE FALSE
                END AS is_primary_key,
                c.column_comment
            FROM information_schema.columns c
            WHERE c.table_schema = %s AND c.table_name = %s
            ORDER BY c.ordinal_position
        """

        async with self._pool.acquire() as conn:
            async with conn.cursor() as cursor:
                await cursor.execute(columns_query, (self._config.database, table_name))
                rows = await cursor.fetchall()

                columns: list[ColumnInfo] = []
                primary_keys: list[str] = []

                for row in rows:
                    col = ColumnInfo(
                        name=row[0],
                        type=row[1],
                        nullable=row[2],
                        default=row[3],
                        comment=row[5],
                    )
                    if row[4]:
                        col.is_primary_key = True
                        primary_keys.append(row[0])
                    columns.append(col)

        # Get foreign keys
        fk_query = """
            SELECT
                column_name,
                referenced_table_name,
                referenced_column_name
            FROM information_schema.key_column_usage
            WHERE table_schema = %s
                AND table_name = %s
                AND referenced_table_name IS NOT NULL
        """

        async with self._pool.acquire() as conn:
            async with conn.cursor() as cursor:
                await cursor.execute(fk_query, (self._config.database, table_name))
                foreign_keys: list[ForeignKeyInfo] = [
                    ForeignKeyInfo(
                        column=row[0],
                        ref_table=row[1],
                        ref_column=row[2],
                    )
                    for row in await cursor.fetchall()
                ]

        # Get indexes
        idx_query = """
            SELECT
                index_name,
                column_name,
                NOT non_unique AS is_unique
            FROM information_schema.statistics
            WHERE table_schema = %s
                AND table_name = %s
                AND index_name != 'PRIMARY'
            ORDER BY index_name, seq_in_index
        """

        async with self._pool.acquire() as conn:
            async with conn.cursor() as cursor:
                await cursor.execute(idx_query, (self._config.database, table_name))
                rows = await cursor.fetchall()

                # Group by index name
                index_map: dict[str, dict[str, Any]] = {}
                for row in rows:
                    idx_name = row[0]
                    if idx_name not in index_map:
                        index_map[idx_name] = {"columns": [], "unique": row[2]}
                    index_map[idx_name]["columns"].append(row[1])

                indexes: list[IndexInfo] = [
                    IndexInfo(
                        name=name,
                        columns=data["columns"],
                        unique=data["unique"],
                    )
                    for name, data in index_map.items()
                ]

        return TableDescription(
            table_name=table_name,
            columns=columns,
            primary_keys=primary_keys,
            foreign_keys=foreign_keys,
            indexes=indexes,
        )

    async def get_connection_info(self) -> ConnectionInfo:
        """Get information about this MySQL connection.

        Returns:
            ConnectionInfo with connection details.
        """
        return ConnectionInfo(
            name=self._config.name,
            type="mysql",
            host=self._config.host,
            port=self._config.port or 3306,
            database=self._config.database,
            status="connected" if await self.is_connected() else "disconnected",
        )
