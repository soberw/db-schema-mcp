"""Oracle database connection implementation.

This module provides DatabaseConnection implementation for Oracle
using the cx_Oracle (python-oracledb) driver.
"""

from typing import Any

import oracledb

from db_schema_mcp.config import (
    ColumnInfo,
    ConnectionInfo,
    DatabaseConfig,
    ForeignKeyInfo,
    IndexInfo,
    TableDescription,
)
from db_schema_mcp.connections.base import DatabaseConnection


class OracleConnection(DatabaseConnection):
    """Database connection implementation for Oracle.

    Uses python-oracledb (successor to cx_Oracle) to connect to
    Oracle databases and queries ALL_TABLES, ALL_TAB_COLUMNS,
    ALL_CONSTRAINTS for metadata.
    """

    def __init__(self, config: DatabaseConfig) -> None:
        """Initialize Oracle connection.

        Args:
            config: DatabaseConfig with type='oracle'.
        """
        super().__init__(config)
        self._pool: oracledb.ConnectionPool | None = None

    async def connect(self) -> None:
        """Establish Oracle database connection.

        Raises:
            ConnectionError: If connection fails.
        """
        try:
            # Build connection parameters
            user = self._config.user
            password = self._config.password
            host = self._config.host
            port = self._config.port or 1521
            service_name = self._config.database

            # Create DSN string
            dsn = f"{host}:{port}/{service_name}"

            # Create connection pool
            self._pool = oracledb.create_pool(
                user=user,
                password=password,
                dsn=dsn,
                min=1,
                max=1,
                increment=0,
            )

            # Test connection
            with self._pool.acquire() as conn:
                cursor = conn.cursor()
                cursor.execute("SELECT 1 FROM dual")
                cursor.fetchone()

            self._is_connected = True
        except oracledb.Error as e:
            msg = f"Failed to connect to Oracle database '{self._config.database}': {e}"
            raise ConnectionError(msg) from e

    async def disconnect(self) -> None:
        """Close Oracle connection pool."""
        if self._pool:
            self._pool.close()
            self._pool = None
            self._is_connected = False

    async def is_connected(self) -> bool:
        """Check if Oracle connection is active.

        Returns:
            True if connected, False otherwise.
        """
        if not self._pool:
            return False
        try:
            with self._pool.acquire() as conn:
                cursor = conn.cursor()
                cursor.execute("SELECT 1 FROM dual")
                cursor.fetchone()
            return True
        except oracledb.Error:
            return False

    async def list_tables(self) -> list[str]:
        """Get all table names in the Oracle database.

        Returns:
            List of table names (user's tables only).

        Raises:
            ConnectionError: If not connected.
        """
        if not self._is_connected or not self._pool:
            msg = "Not connected to database"
            raise ConnectionError(msg)

        query = """
            SELECT table_name
            FROM user_tables
            ORDER BY table_name
        """

        with self._pool.acquire() as conn:
            cursor = conn.cursor()
            cursor.execute(query)
            return [row[0] for row in cursor]

    async def describe_table(self, table_name: str) -> TableDescription:
        """Get detailed structure information for an Oracle table.

        Args:
            table_name: The name of the table (uppercase for Oracle).

        Returns:
            TableDescription with complete schema information.

        Raises:
            ConnectionError: If not connected.
            ValueError: If table doesn't exist.
        """
        if not self._is_connected or not self._pool:
            msg = "Not connected to database"
            raise ConnectionError(msg)

        # Oracle table names are uppercase by default
        table_upper = table_name.upper()

        # Check if table exists
        check_query = """
            SELECT table_name
            FROM user_tables
            WHERE table_name = :1
        """

        with self._pool.acquire() as conn:
            cursor = conn.cursor()
            cursor.execute(check_query, [table_upper])
            table_exists = cursor.fetchone()

        # 检查表是否在连接释放后进行，避免连接池死锁
        if not table_exists:
            available = await self.list_tables()
            msg = f"Table '{table_name}' not found. Available tables: {', '.join(available)}"
            raise ValueError(msg)

        # Get column information
        columns_query = """
            SELECT
                utc.column_name,
                utc.data_type,
                utc.nullable,
                utc.data_default,
                CASE
                    WHEN pk.column_name IS NOT NULL THEN 1
                    ELSE 0
                END AS is_primary_key,
                ucc.comments
            FROM user_tab_columns utc
            LEFT JOIN (
                SELECT cols.column_name
                FROM user_constraints cons
                JOIN user_cons_columns cols
                    ON cons.constraint_name = cols.constraint_name
                WHERE cons.table_name = :tb_name
                    AND cons.constraint_type = 'P'
            ) pk ON pk.column_name = utc.column_name
            LEFT JOIN user_col_comments ucc
                ON ucc.table_name = utc.table_name
                AND ucc.column_name = utc.column_name
            WHERE utc.table_name = :tb_name
            ORDER BY utc.column_id
        """

        with self._pool.acquire() as conn:
            cursor = conn.cursor()
            cursor.execute(columns_query, {"tb_name": table_upper})
            rows = cursor.fetchall()

            columns: list[ColumnInfo] = []
            primary_keys: list[str] = []

            for row in rows:
                col = ColumnInfo(
                    name=row[0].lower(),
                    type=row[1],
                    nullable=row[2] == "Y",
                    default=str(row[3]) if row[3] else None,
                    comment=row[5],
                )
                if row[4]:
                    col.is_primary_key = True
                    primary_keys.append(row[0].lower())
                columns.append(col)

        # Get foreign keys
        fk_query = """
            SELECT
                ucc1.column_name,
                uc2.table_name AS referenced_table,
                ucc2.column_name AS referenced_column
            FROM user_constraints uc1
            JOIN user_cons_columns ucc1
                ON uc1.constraint_name = ucc1.constraint_name
            JOIN user_constraints uc2
                ON uc1.r_constraint_name = uc2.constraint_name
            JOIN user_cons_columns ucc2
                ON uc2.constraint_name = ucc2.constraint_name
                AND ucc2.position = ucc1.position
            WHERE uc1.constraint_type = 'R'
                AND uc1.table_name = :tb_name
        """

        with self._pool.acquire() as conn:
            cursor = conn.cursor()
            cursor.execute(fk_query, {"tb_name": table_upper})
            foreign_keys: list[ForeignKeyInfo] = [
                ForeignKeyInfo(
                    column=row[0].lower(),
                    ref_table=row[1].lower(),
                    ref_column=row[2].lower(),
                )
                for row in cursor
            ]

        # Get indexes
        idx_query = """
            SELECT
                uic.index_name,
                uic.column_name,
                ui.uniqueness
            FROM user_ind_columns uic
            JOIN user_indexes ui
                ON uic.index_name = ui.index_name
            WHERE uic.table_name = :tb_name
                AND NOT EXISTS (
                    SELECT 1
                    FROM user_constraints
                    WHERE constraint_name = ui.index_name
                        AND constraint_type = 'P'
                )
            ORDER BY uic.index_name, uic.column_position
        """

        with self._pool.acquire() as conn:
            cursor = conn.cursor()
            cursor.execute(idx_query, {"tb_name": table_upper})
            rows = cursor.fetchall()

            # Group by index name
            index_map: dict[str, dict[str, Any]] = {}
            for row in rows:
                idx_name = row[0].lower()
                if idx_name not in index_map:
                    index_map[idx_name] = {"columns": [], "unique": row[2] == "UNIQUE"}
                index_map[idx_name]["columns"].append(row[1].lower())

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
        """Get information about this Oracle connection.

        Returns:
            ConnectionInfo with connection details.
        """
        return ConnectionInfo(
            name=self._config.name,
            type="oracle",
            host=self._config.host,
            port=self._config.port or 1521,
            database=self._config.database,
            status="connected" if await self.is_connected() else "disconnected",
        )
