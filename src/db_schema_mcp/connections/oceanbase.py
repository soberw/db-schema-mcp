"""OceanBase Oracle tenants over the pure Python pyoceanbase driver."""

import asyncio
import math
import re
import select
import socket
import ssl
import threading
import time
from collections.abc import Callable
from typing import Any, TypeVar

import pyoceanbase  # type: ignore[import-untyped]
from pyoceanbase.connections import Connection  # type: ignore[import-untyped]
from pyoceanbase.cursors import SSCursor  # type: ignore[import-untyped]

from db_schema_mcp.config import (
    ColumnInfo,
    ConnectionInfo,
    DatabaseConfig,
    ForeignKeyInfo,
    IndexInfo,
    QueryResult,
    TableDescription,
)
from db_schema_mcp.connections.base import DatabaseConnection

T = TypeVar("T")
QUERY_TIMEOUT = 30
MAX_RESULT_BYTES = 4 * 1024 * 1024


class _CancelableTLSContext:
    """Register the TLS socket before handshaking, so cancellation can wake it."""

    def __init__(self, owner: "OracleWireConnection", context: ssl.SSLContext) -> None:
        self._owner = owner
        self._context = context

    def wrap_socket(self, sock: socket.socket, **kwargs: Any) -> ssl.SSLSocket:
        tls = self._context.wrap_socket(sock, do_handshake_on_connect=False, **kwargs)
        self._owner._sock = tls
        tls.setblocking(False)
        try:
            while True:
                self._owner._check_deadline()
                try:
                    tls.do_handshake()
                    tls.settimeout(max(0.001, self._owner._deadline - time.monotonic()))
                    return tls
                except ssl.SSLWantReadError:
                    select.select([tls], [], [], 0.25)
                except ssl.SSLWantWriteError:
                    select.select([], [tls], [], 0.25)
        except BaseException:
            tls.close()
            raise


class OracleWireConnection(Connection):  # type: ignore[misc]
    """Keep driver value binding consistent with Oracle string literals."""

    def __init__(self, **kwargs: Any) -> None:
        self._stopped = threading.Event()
        self._deadline = time.monotonic() + QUERY_TIMEOUT
        self._packet_bytes = 0
        super().__init__(**kwargs)

    def interrupt(self) -> None:
        """Wake a blocked recv without running DB-API operations in another thread."""
        self._stopped.set()
        sock = getattr(self, "_sock", None)
        if sock is not None:
            try:
                sock.shutdown(socket.SHUT_RDWR)
            except OSError:
                pass

    def _create_ssl_ctx(self, options: Any) -> _CancelableTLSContext:
        return _CancelableTLSContext(self, super()._create_ssl_ctx(options))

    def _check_deadline(self) -> None:
        if self._stopped.is_set() or time.monotonic() >= self._deadline:
            raise TimeoutError("OceanBase 查询已取消或超过 30 秒总时限。")

    def _execute_command(self, command: Any, sql: Any) -> Any:
        self._check_deadline()
        return super()._execute_command(command, sql)

    def _read_packet(self, *args: Any, **kwargs: Any) -> Any:
        self._packet_bytes = 0
        return super()._read_packet(*args, **kwargs)

    def _read_bytes(self, num_bytes: int) -> bytes:
        self._check_deadline()
        # Count packet fragments before allocating or decoding a large row/LOB.
        self._packet_bytes += num_bytes
        if self._packet_bytes > MAX_RESULT_BYTES:
            raise ValueError("OceanBase 单个结果包超过 4 MiB，请缩小字段或查询范围。")
        # Buffered file.read() does not reliably wake on shutdown on Windows.
        # All driver packet reads use this method, so read the socket directly
        # with short polling intervals, including already decrypted TLS bytes.
        chunks: list[bytes] = []
        remaining = num_bytes
        while remaining:
            self._check_deadline()
            sock = self._sock
            sock.settimeout(min(0.25, max(0.001, self._deadline - time.monotonic())))
            try:
                pending = isinstance(sock, ssl.SSLSocket) and sock.pending() > 0
                if not pending and not select.select([sock], [], [], 0.25)[0]:
                    continue
                chunk = sock.recv(min(remaining, 65536))
            except (TimeoutError, ssl.SSLWantReadError):
                continue
            except OSError as exc:
                raise pyoceanbase.OperationalError("OceanBase 网络读取失败。") from exc
            if not chunk:
                raise pyoceanbase.OperationalError("OceanBase 连接已关闭。")
            chunks.append(chunk)
            remaining -= len(chunk)
        self._check_deadline()
        return b"".join(chunks)

    def escape_string(self, value: str) -> str:
        # Oracle does not escape quotes with backslashes, unlike MySQL mode.
        return value.replace("'", "''")

    def close(self) -> None:
        # The driver's result/cursor destructors otherwise attempt to drain an
        # interrupted stream after its socket has already been closed.
        result = getattr(self, "_result", None)
        if result is not None:
            result.unbuffered_active = False
        super().close()


class OceanBaseOracleConnection(DatabaseConnection):
    """Short-lived, read-only connections; no native client or JVM required."""

    def __init__(self, config: DatabaseConfig) -> None:
        super().__init__(config)
        if config.mode != "oracle":
            raise ValueError("OceanBase 当前只支持 Oracle 兼容模式。")
        schema = config.database or ""
        self._schema = schema[1:-1].replace('""', '"') if (
            schema.startswith('"') and schema.endswith('"')
        ) else schema.upper()

    def _run(
        self, operation: Callable[[Any], T], stopped: threading.Event | None = None,
        active: list[Any] | None = None,
    ) -> T:
        """Own the complete socket lifecycle in one worker, including cancellation cleanup."""
        conn = OracleWireConnection(
            host=self._config.host,
            port=self._config.port or 2881,
            user=self._config.user,
            password=(self._config.password or "").encode("utf-8"),
            database=self._schema,
            charset="utf8mb4",
            autocommit=True,
            local_infile=False,
            connect_timeout=10,
            read_timeout=QUERY_TIMEOUT,
            write_timeout=QUERY_TIMEOUT,
            ssl=self._config.ssl,
            defer_connect=True,
        )
        if active is not None:
            active.append(conn)
        timer = threading.Timer(QUERY_TIMEOUT, conn.interrupt)
        timer.daemon = True
        try:
            if stopped is not None and stopped.is_set():
                raise TimeoutError("OceanBase 查询已取消。")
            timer.start()
            conn.connect()
            with conn.cursor() as cursor:
                cursor.execute("SHOW VARIABLES LIKE 'ob_compatibility_mode'")
                mode = cursor.fetchone()
                if not mode or str(mode[1]).upper() != "ORACLE":
                    raise ValueError("目标连接不是 OceanBase Oracle 兼容租户。")
                cursor.execute("SET ob_query_timeout = 30000000")
                cursor.execute("START TRANSACTION READ ONLY")
            try:
                return operation(conn)
            finally:
                # Truncated streaming reads close the socket instead of draining it.
                if conn.open:
                    conn.rollback()
        finally:
            timer.cancel()
            if conn.open:
                conn.close()

    async def _worker(self, operation: Callable[[Any], T]) -> T:
        stopped = threading.Event()
        active: list[Any] = []
        try:
            return await asyncio.to_thread(self._run, operation, stopped, active)
        except asyncio.CancelledError:
            stopped.set()
            # Only transport shutdown crosses threads; rollback/close stay in _run.
            if active:
                active[0].interrupt()
            raise

    async def connect(self) -> None:
        try:
            await self._worker(lambda conn: None)
            self._is_connected = True
        except pyoceanbase.Error as exc:
            raise ConnectionError("OceanBase 连接失败，请检查地址、租户账号及 schema。") from exc

    async def disconnect(self) -> None:
        # Physical connections belong to the worker and always close in _run.
        self._is_connected = False

    async def is_connected(self) -> bool:
        if not self._is_connected:
            return False
        try:
            await self._worker(lambda conn: None)
            return True
        except (pyoceanbase.Error, ValueError, TimeoutError):
            return False

    async def _call(self, operation: Callable[[Any], T]) -> T:
        if not self._is_connected:
            raise ConnectionError("未连接 OceanBase。")
        return await self._worker(operation)

    async def list_tables(self) -> list[str]:
        def read(conn: Any) -> list[str]:
            with conn.cursor() as cursor:
                cursor.execute(
                    "SELECT TABLE_NAME FROM ALL_TABLES WHERE OWNER = %s ORDER BY TABLE_NAME",
                    (self._schema,),
                )
                return [str(row[0]) for row in cursor.fetchall()]
        return await self._call(read)

    async def describe_table(self, table_name: str) -> TableDescription:
        def read(conn: Any) -> TableDescription:
            with conn.cursor() as cursor:
                # Match exact quoted names first, then ordinary Oracle uppercase names.
                cursor.execute(
                    "SELECT TABLE_NAME FROM ALL_TABLES WHERE OWNER = %s "
                    "AND TABLE_NAME IN (%s, %s) ORDER BY TABLE_NAME",
                    (self._schema, table_name, table_name.upper()),
                )
                names = [row[0] for row in cursor.fetchall()]
                name = table_name if table_name in names else (names[0] if names else None)
                if name is None:
                    raise ValueError(f"表 '{table_name}' 未找到。")
                params = (self._schema, name)
                cursor.execute(
                    "SELECT COMMENTS FROM ALL_TAB_COMMENTS WHERE OWNER = %s AND TABLE_NAME = %s",
                    params,
                )
                comment = cursor.fetchone()
                cursor.execute(
                    "SELECT c.COLUMN_NAME, c.DATA_TYPE, c.NULLABLE, c.DATA_DEFAULT, "
                    "cc.COMMENTS FROM ALL_TAB_COLUMNS c LEFT JOIN ALL_COL_COMMENTS cc "
                    "ON cc.OWNER = c.OWNER AND cc.TABLE_NAME = c.TABLE_NAME "
                    "AND cc.COLUMN_NAME = c.COLUMN_NAME "
                    "WHERE c.OWNER = %s AND c.TABLE_NAME = %s ORDER BY c.COLUMN_ID",
                    params,
                )
                columns = [ColumnInfo(
                    name=row[0], type=row[1], nullable=row[2] == "Y",
                    default=None if row[3] is None else str(row[3]), comment=row[4],
                ) for row in cursor.fetchall()]
                cursor.execute(
                    "SELECT cc.COLUMN_NAME FROM ALL_CONSTRAINTS c JOIN ALL_CONS_COLUMNS cc "
                    "ON cc.OWNER = c.OWNER AND cc.CONSTRAINT_NAME = c.CONSTRAINT_NAME "
                    "WHERE c.OWNER = %s AND c.TABLE_NAME = %s AND c.CONSTRAINT_TYPE = 'P' "
                    "ORDER BY cc.POSITION", params,
                )
                primary_keys = [row[0] for row in cursor.fetchall()]
                for column in columns:
                    column.is_primary_key = column.name in primary_keys
                cursor.execute(
                    "SELECT cc.COLUMN_NAME, r.TABLE_NAME, rc.COLUMN_NAME "
                    "FROM ALL_CONSTRAINTS c JOIN ALL_CONS_COLUMNS cc "
                    "ON cc.OWNER = c.OWNER AND cc.CONSTRAINT_NAME = c.CONSTRAINT_NAME "
                    "JOIN ALL_CONSTRAINTS r ON r.OWNER = c.R_OWNER "
                    "AND r.CONSTRAINT_NAME = c.R_CONSTRAINT_NAME "
                    "JOIN ALL_CONS_COLUMNS rc ON rc.OWNER = r.OWNER "
                    "AND rc.CONSTRAINT_NAME = r.CONSTRAINT_NAME AND rc.POSITION = cc.POSITION "
                    "WHERE c.OWNER = %s AND c.TABLE_NAME = %s AND c.CONSTRAINT_TYPE = 'R' "
                    "ORDER BY c.CONSTRAINT_NAME, cc.POSITION", params,
                )
                foreign_keys = [ForeignKeyInfo(*row) for row in cursor.fetchall()]
                cursor.execute(
                    "SELECT i.INDEX_NAME, ic.COLUMN_NAME, i.UNIQUENESS "
                    "FROM ALL_INDEXES i JOIN ALL_IND_COLUMNS ic "
                    "ON ic.INDEX_OWNER = i.OWNER AND ic.INDEX_NAME = i.INDEX_NAME "
                    "AND ic.TABLE_OWNER = i.TABLE_OWNER AND ic.TABLE_NAME = i.TABLE_NAME "
                    "WHERE i.TABLE_OWNER = %s AND i.TABLE_NAME = %s "
                    "AND NOT EXISTS (SELECT 1 FROM ALL_CONSTRAINTS pk "
                    "WHERE pk.OWNER = i.TABLE_OWNER AND pk.TABLE_NAME = i.TABLE_NAME "
                    "AND pk.CONSTRAINT_TYPE = 'P' AND pk.INDEX_NAME = i.INDEX_NAME) "
                    "ORDER BY i.INDEX_NAME, ic.COLUMN_POSITION", params,
                )
                indexes: dict[str, IndexInfo] = {}
                for idx_name, col_name, uniqueness in cursor.fetchall():
                    if idx_name not in indexes:
                        indexes[idx_name] = IndexInfo(idx_name, [], uniqueness == "UNIQUE")
                    indexes[idx_name].columns.append(col_name)
                return TableDescription(
                    name, columns, primary_keys, foreign_keys, list(indexes.values()),
                    comment[0] if comment else None,
                )
        return await self._call(read)

    async def execute_query(
        self, sql: str, parameters: list[Any] | dict[str, Any] | None, limit: int,
    ) -> QueryResult:
        # Import lazily: tool modules import the connection factory themselves.
        from db_schema_mcp.tools.exec_query import validate_read_only_query

        sql = validate_read_only_query(sql)
        if type(limit) is not int or not 1 <= limit <= 1000:
            raise ValueError("limit 必须在 1 到 1000 之间。")
        values = parameters.values() if isinstance(parameters, dict) else (parameters or [])
        for value in values:
            if type(value) not in (str, int, float, type(None)) or (
                isinstance(value, float) and not math.isfinite(value)
            ):
                raise ValueError("OceanBase parameters 仅支持字符串、数字和 null。")
        # Reject executable comments and sequence mutation in Oracle SELECTs.
        if "/*!" in sql or "/*M!" in sql.upper():
            raise ValueError("OceanBase 不允许可执行注释。")
        if re.search(r"\bNEXTVAL\b", sql, re.IGNORECASE):
            raise ValueError("OceanBase 只读查询不允许 NEXTVAL。")

        def read(conn: Any) -> QueryResult:
            cursor = conn.cursor(SSCursor)
            try:
                # The only interpolated value is a validated bounded integer.
                cursor.execute(
                    f"SELECT * FROM (\n{sql}\n) WHERE ROWNUM <= {limit + 1}", parameters,
                )
                columns = [col[0] for col in cursor.description]
                if len(set(columns)) != len(columns):
                    raise ValueError("查询列名重复，请使用不同的 AS 别名。")
                rows: list[dict[str, Any]] = []
                size = 0
                truncated = False
                for row in cursor:
                    size += sum(len(str(value).encode("utf-8")) for value in row)
                    if len(rows) >= limit or size > MAX_RESULT_BYTES:
                        truncated = True
                        # close() on SSCursor otherwise drains the unread result.
                        conn.close()
                        break
                    rows.append(dict(zip(columns, row, strict=True)))
                return QueryResult(columns, rows, len(rows), truncated)
            except BaseException:
                if conn.open:
                    conn.close()
                raise
            finally:
                if conn.open:
                    cursor.close()
                else:
                    cursor.connection = None
        return await self._call(read)

    async def get_connection_info(self) -> ConnectionInfo:
        return ConnectionInfo(
            self._config.name, "oceanbase", self._config.host,
            self._config.port or 2881, self._schema,
            "connected" if await self.is_connected() else "disconnected",
        )
