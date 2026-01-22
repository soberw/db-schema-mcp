"""PostgreSQL database connection implementation.

This module provides DatabaseConnection implementation for PostgreSQL
using the psycopg3 driver.
"""

import asyncio
from typing import Any

import psycopg
from psycopg import sql

from db_schema_mcp.config import (
    ColumnInfo,
    ConnectionInfo,
    DatabaseConfig,
    ForeignKeyInfo,
    IndexInfo,
    TableDescription,
)
from db_schema_mcp.connections.base import DatabaseConnection


class PostgresConnection(DatabaseConnection):
    """Database connection implementation for PostgreSQL.

    Uses psycopg3 to connect to PostgreSQL databases and queries
    information_schema for metadata.
    """

    def __init__(self, config: DatabaseConfig) -> None:
        """Initialize PostgreSQL connection.

        Args:
            config: DatabaseConfig with type='postgresql'.
        """
        super().__init__(config)
        self._connect_lock = asyncio.Lock()

    async def connect(self) -> None:
        """Establish PostgreSQL database connection.

        Raises:
            ConnectionError: If connection fails.
        """
        try:
            # Build connection parameters
            conn_params = {
                "host": self._config.host,
                "port": self._config.port or 5432,
                "user": self._config.user,
                "password": self._config.password,
                "dbname": self._config.database,
            }

            # Add SSL mode if specified
            if self._config.sslmode:
                conn_params["sslmode"] = self._config.sslmode

            self._connection = await psycopg.AsyncConnection.connect(**conn_params)
            self._is_connected = True
        except psycopg.Error as e:
            msg = f"Failed to connect to PostgreSQL database '{self._config.database}': {e}"
            raise ConnectionError(msg) from e

    async def disconnect(self) -> None:
        """Close PostgreSQL connection."""
        if self._connection:
            await self._connection.close()
            self._connection = None
            self._is_connected = False

    async def is_connected(self) -> bool:
        """Check if PostgreSQL connection is active.

        Returns:
            True if connected, False otherwise.
        """
        if not self._connection:
            return False
        try:
            async with self._connection.cursor() as cursor:
                await cursor.execute("SELECT 1")
            return True
        except psycopg.Error:
            return False

    async def list_tables(self) -> list[str]:
        """Get all table names in the PostgreSQL database.

        Returns:
            List of table names (user tables only, excluding system tables).

        Raises:
            ConnectionError: If not connected.
        """
        if not self._is_connected:
            msg = "Not connected to database"
            raise ConnectionError(msg)

        query = """
            SELECT table_name
            FROM information_schema.tables
            WHERE table_schema = 'public'
                AND table_type = 'BASE TABLE'
            ORDER BY table_name
        """

        async with self._connection.cursor() as cursor:
            await cursor.execute(query)
            return [row[0] for row in await cursor.fetchall()]

    async def describe_table(self, table_name: str) -> TableDescription:
        """Get detailed structure information for a PostgreSQL table.

        Args:
            table_name: The name of the table.

        Returns:
            TableDescription with complete schema information.

        Raises:
            ConnectionError: If not connected.
            ValueError: If table doesn't exist.
        """
        if not self._is_connected:
            msg = "Not connected to database"
            raise ConnectionError(msg)

        # Check if table exists
        query = """
            SELECT table_name
            FROM information_schema.tables
            WHERE table_schema = 'public' AND table_name = %s
        """
        async with self._connection.cursor() as cursor:
            await cursor.execute(query, (table_name,))
            if not await cursor.fetchone():
                available = await self.list_tables()
                msg = f"Table '{table_name}' not found. Available tables: {', '.join(available)}"
                raise ValueError(msg)

        # Get column information
        columns_query = """
            SELECT
                c.column_name,
                c.data_type,
                c.is_nullable,
                c.column_default,
                CASE WHEN pk.column_name IS NOT NULL THEN TRUE ELSE FALSE END AS is_primary_key,
                pgd.description
            FROM information_schema.columns c
            LEFT JOIN (
                SELECT ku.column_name
                FROM information_schema.table_constraints tc
                JOIN information_schema.key_column_usage ku
                    ON tc.constraint_name = ku.constraint_name
                WHERE tc.table_schema = 'public'
                    AND tc.table_name = %s
                    AND tc.constraint_type = 'PRIMARY KEY'
            ) pk ON pk.column_name = c.column_name
            LEFT JOIN pg_catalog.pg_description pgd
                ON pgd.objoid = (
                    SELECT oid FROM pg_class
                    WHERE relname = %s AND relnamespace = (
                        SELECT oid FROM pg_namespace WHERE nspname = 'public'
                    )
                )
                AND pgd.objsubid = c.ordinal_position
            WHERE c.table_schema = 'public'
                AND c.table_name = %s
            ORDER BY c.ordinal_position
        """

        async with self._connection.cursor() as cursor:
            await cursor.execute(columns_query, (table_name, table_name, table_name))
            rows = await cursor.fetchall()

            columns: list[ColumnInfo] = []
            primary_keys: list[str] = []

            for row in rows:
                col = ColumnInfo(
                    name=row[0],
                    type=row[1],
                    nullable=row[2] == "YES",
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
                kcu.column_name,
                ccu.table_name AS foreign_table_name,
                ccu.column_name AS foreign_column_name
            FROM information_schema.table_constraints AS tc
            JOIN information_schema.key_column_usage AS kcu
                ON tc.constraint_name = kcu.constraint_name
            JOIN information_schema.constraint_column_usage AS ccu
                ON ccu.constraint_name = tc.constraint_name
            WHERE tc.constraint_type = 'FOREIGN KEY'
                AND tc.table_schema = 'public'
                AND tc.table_name = %s
        """

        async with self._connection.cursor() as cursor:
            await cursor.execute(fk_query, (table_name,))
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
                i.relname as index_name,
                a.attname as column_name,
                ix.indisunique as is_unique
            FROM pg_class t
            JOIN pg_index ix ON t.oid = ix.indrelid
            JOIN pg_class i ON i.oid = ix.indexrelid
            JOIN pg_attribute a ON a.attrelid = t.oid AND a.attnum = ANY(ix.indkey)
            JOIN pg_namespace n ON n.oid = t.relnamespace
            WHERE n.nspname = 'public'
                AND t.relname = %s
                AND NOT ix.indisprimary
            ORDER BY i.relname, a.attnum
        """

        async with self._connection.cursor() as cursor:
            await cursor.execute(idx_query, (table_name,))
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
        """Get information about this PostgreSQL connection.

        Returns:
            ConnectionInfo with connection details.
        """
        return ConnectionInfo(
            name=self._config.name,
            type="postgresql",
            host=self._config.host,
            port=self._config.port or 5432,
            database=self._config.database,
            status="connected" if await self.is_connected() else "disconnected",
        )
