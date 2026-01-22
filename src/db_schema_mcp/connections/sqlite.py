"""SQLite database connection implementation.

This module provides DatabaseConnection implementation for SQLite databases
using the built-in sqlite3 module.
"""

import re
import sqlite3
from pathlib import Path
from typing import Any

from db_schema_mcp.config import (
    ColumnInfo,
    ConnectionInfo,
    DatabaseConfig,
    ForeignKeyInfo,
    IndexInfo,
    TableDescription,
)
from db_schema_mcp.connections.base import DatabaseConnection


class SQLiteConnection(DatabaseConnection):
    """Database connection implementation for SQLite.

    Uses the built-in sqlite3 module to connect to SQLite database files.
    Queries sqlite_master for table list and uses PRAGMA statements
    for table schema information.
    """

    def __init__(self, config: DatabaseConfig) -> None:
        """Initialize SQLite connection.

        Args:
            config: DatabaseConfig with type='sqlite' and path set.
        """
        super().__init__(config)
        if not config.path:
            msg = "SQLite configuration must include 'path' field"
            raise ValueError(msg)
        self._db_path = Path(config.path).expanduser()

    async def connect(self) -> None:
        """Establish SQLite database connection.

        Raises:
            ConnectionError: If the database file doesn't exist or connection fails.
        """
        try:
            self._connection = sqlite3.connect(str(self._db_path))
            self._connection.row_factory = sqlite3.Row
            self._is_connected = True
        except sqlite3.Error as e:
            msg = f"Failed to connect to SQLite database '{self._db_path}': {e}"
            raise ConnectionError(msg) from e

    async def disconnect(self) -> None:
        """Close SQLite connection."""
        if self._connection:
            self._connection.close()
            self._connection = None
            self._is_connected = False

    async def is_connected(self) -> bool:
        """Check if SQLite connection is active.

        Returns:
            True if connected, False otherwise.
        """
        if not self._connection:
            return False
        try:
            self._connection.execute("SELECT 1")
            return True
        except sqlite3.Error:
            return False

    async def list_tables(self) -> list[str]:
        """Get all table names in the SQLite database.

        Returns:
            List of table names (excluding system tables).

        Raises:
            ConnectionError: If not connected.
        """
        if not self._is_connected:
            msg = "Not connected to database"
            raise ConnectionError(msg)

        cursor = self._connection.execute(
            "SELECT name FROM sqlite_master WHERE type='table' AND name NOT LIKE 'sqlite_%' ORDER BY name"
        )
        return [row[0] for row in cursor.fetchall()]

    async def describe_table(self, table_name: str) -> TableDescription:
        """Get detailed structure information for a SQLite table.

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
        cursor = self._connection.execute(
            "SELECT name FROM sqlite_master WHERE type='table' AND name=?",
            (table_name,)
        )
        if not cursor.fetchone():
            available = await self.list_tables()
            msg = f"Table '{table_name}' not found. Available tables: {', '.join(available)}"
            raise ValueError(msg)

        # Get column information using PRAGMA
        cursor = self._connection.execute(f"PRAGMA table_info('{table_name}')")
        columns: list[ColumnInfo] = []
        primary_keys: list[str] = []

        # Build a map of column comments from CREATE TABLE sql
        column_comments: dict[str, str] = {}
        cursor2 = self._connection.execute(
            "SELECT sql FROM sqlite_master WHERE type='table' AND name=?",
            (table_name,)
        )
        create_table_row = cursor2.fetchone()
        if create_table_row and create_table_row["sql"]:
            # Parse column comments from CREATE TABLE statement
            # SQLite doesn't support native column comments, but we can extract inline comments
            sql = create_table_row["sql"]
            # Match patterns like: column_name TYPE ... -- comment
            # or: column_name TYPE ... /* comment */
            # Use a simpler approach: find all lines with -- or /* */ comments
            lines = sql.split('\n')
            for line in lines:
                # Look for inline comments
                comment = None
                if '--' in line:
                    # Extract everything after -- until end of line
                    parts = line.split('--', 1)
                    if len(parts) == 2:
                        comment = parts[1].strip()
                        # Extract column name from the part before comment
                        col_def = parts[0].strip()
                        # Match column name at the start
                        col_match = re.match(r'^(\w+)\s+', col_def)
                        if col_match:
                            col_name = col_match.group(1)
                            if col_name.upper() not in ('CREATE', 'CONSTRAINT', 'PRIMARY', 'FOREIGN', 'UNIQUE', 'CHECK'):
                                column_comments[col_name] = comment
                elif '/*' in line and '*/' in line:
                    # Extract /* comment */
                    parts = line.split('/*', 1)
                    if len(parts) == 2:
                        comment_parts = parts[1].split('*/', 1)
                        if len(comment_parts) == 2:
                            comment = comment_parts[0].strip()
                            # Extract column name from the part before comment
                            col_def = parts[0].strip()
                            # Match column name at the start
                            col_match = re.match(r'^(\w+)\s+', col_def)
                            if col_match:
                                col_name = col_match.group(1)
                                if col_name.upper() not in ('CREATE', 'CONSTRAINT', 'PRIMARY', 'FOREIGN', 'UNIQUE', 'CHECK'):
                                    column_comments[col_name] = comment

        for row in cursor.fetchall():
            col = ColumnInfo(
                name=row["name"],
                type=row["type"],
                nullable=row["notnull"] == 0,
                default=row["dflt_value"],
                comment=column_comments.get(row["name"]),
            )
            if row["pk"] > 0:
                col.is_primary_key = True
                primary_keys.append(row["name"])
            columns.append(col)

        # Get foreign keys
        cursor = self._connection.execute(f"PRAGMA foreign_key_list('{table_name}')")
        foreign_keys: list[ForeignKeyInfo] = [
            ForeignKeyInfo(
                column=row["from"],
                ref_table=row["table"],
                ref_column=row["to"],
            )
            for row in cursor.fetchall()
        ]

        # Get indexes
        cursor = self._connection.execute(
            "SELECT name, sql FROM sqlite_master WHERE type='index' AND tbl_name=? AND sql IS NOT NULL",
            (table_name,)
        )
        indexes: list[IndexInfo] = []
        for row in cursor.fetchall():
            index_name = row["name"]
            # Parse UNIQUE from CREATE INDEX statement
            sql = row["sql"] or ""
            unique = "UNIQUE" in sql.upper()

            # Get index columns
            cursor2 = self._connection.execute(f"PRAGMA index_info('{index_name}')")
            columns_list = [r["name"] for r in cursor2.fetchall()]

            indexes.append(
                IndexInfo(
                    name=index_name,
                    columns=columns_list,
                    unique=unique,
                )
            )

        return TableDescription(
            table_name=table_name,
            columns=columns,
            primary_keys=primary_keys,
            foreign_keys=foreign_keys,
            indexes=indexes,
        )

    async def get_connection_info(self) -> ConnectionInfo:
        """Get information about this SQLite connection.

        Returns:
            ConnectionInfo with connection details.
        """
        return ConnectionInfo(
            name=self._config.name,
            type="sqlite",
            host=str(self._db_path),
            port=None,
            database=None,
            status="connected" if await self.is_connected() else "disconnected",
        )
