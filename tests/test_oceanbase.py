"""OceanBase Oracle adapter regressions, including real driver value quoting."""

import asyncio
import os
import socket
import threading
import time
from pathlib import Path
from typing import Any
from unittest.mock import MagicMock

import pyoceanbase
import pytest
import yaml
from pyoceanbase.constants import CLIENT

from db_schema_mcp.config import ConfigManager, DatabaseConfig
from db_schema_mcp.connections.factory import ConnectionFactory
from db_schema_mcp.connections.oceanbase import (
    OceanBaseOracleConnection,
    OracleWireConnection,
)
from db_schema_mcp.tools.exec_query import handle_exec_query
from db_schema_mcp.tools.init_config import SAMPLE_CONFIG


@pytest.fixture
def config() -> DatabaseConfig:
    return DatabaseConfig(
        name="ob", type="oceanbase", host="localhost", user="reader@tenant#cluster",
        password="密码", database="app",
    )


@pytest.fixture
def wire(monkeypatch: pytest.MonkeyPatch) -> tuple[Any, Any]:
    conn = MagicMock()
    conn.open = True
    conn.close.side_effect = lambda: setattr(conn, "open", False)
    control = MagicMock()
    control.fetchone.return_value = ("ob_compatibility_mode", "ORACLE")
    control.__enter__.return_value = control
    data = MagicMock()
    data.__enter__.return_value = data
    conn.cursor.side_effect = lambda *args: control if not args else data
    factory = MagicMock(return_value=conn)
    monkeypatch.setattr("db_schema_mcp.connections.oceanbase.OracleWireConnection", factory)
    conn.control = control
    return factory, data


def test_configuration_and_factory(tmp_path: Path) -> None:
    template = yaml.safe_load(SAMPLE_CONFIG)
    path = tmp_path / "config.yaml"
    path.write_text(yaml.safe_dump(template), encoding="utf-8")
    manager = ConfigManager(str(path))
    cfg = manager.get_connection("oceanbase_oracle")
    assert cfg is not None and cfg.mode == "oracle"
    assert isinstance(ConnectionFactory.create(cfg), OceanBaseOracleConnection)
    template["databases"]["oceanbase_oracle"]["mode"] = "mysql"
    path.write_text(yaml.safe_dump(template), encoding="utf-8")
    with pytest.raises(ValueError, match="只支持"):
        ConfigManager(str(path))


@pytest.mark.parametrize("text", [
    "O'Reilly", "x' OR 1=1 --", "x\\'; DELETE FROM T; --", "中文'\\字符", "a\nb",
])
def test_real_driver_oracle_binding(text: str) -> None:
    # No server: defer_connect exercises the real driver's mogrify/escape path.
    conn = OracleWireConnection(defer_connect=True)
    conn.server_status = 0
    cursor = conn.cursor()
    assert cursor.mogrify("SELECT %s FROM DUAL", [text]) == (
        "SELECT '" + text.replace("'", "''") + "' FROM DUAL"
    )
    assert cursor.mogrify("SELECT %(v)s FROM DUAL", {"v": text}) == (
        "SELECT '" + text.replace("'", "''") + "' FROM DUAL"
    )
    assert not conn.client_flag & CLIENT.MULTI_STATEMENTS
    assert not conn.client_flag & CLIENT.LOCAL_FILES
    conn.close()


def test_packet_budget_rejects_before_read() -> None:
    conn = OracleWireConnection(defer_connect=True)
    with pytest.raises(ValueError, match="4 MiB"):
        conn._read_bytes(4 * 1024 * 1024 + 1)
    conn.close()


def test_real_driver_packet_parser_uses_bounded_reads() -> None:
    conn = OracleWireConnection(defer_connect=True)
    reader, writer = socket.socketpair()
    conn._sock = reader
    conn._rfile = reader.makefile("rb")
    conn._next_seq_id = 0
    try:
        writer.sendall(b"\x04\x00\x00\x00\x03abc")
        assert conn._read_packet().read(4) == b"\x03abc"
        # A hostile peer advertises a huge packet without sending its payload.
        writer.sendall(b"\x01\x00\x40\x01")
        with pytest.raises(ValueError, match="4 MiB"):
            conn._read_packet()
    finally:
        conn.close()
        writer.close()


def test_expired_deadline_rejects_before_network() -> None:
    conn = OracleWireConnection(defer_connect=True)
    conn._deadline = time.monotonic() - 1
    with pytest.raises(TimeoutError):
        conn._read_bytes(1)
    conn.close()


def test_interrupt_wakes_blocked_transport() -> None:
    conn = OracleWireConnection(defer_connect=True)
    reader, writer = socket.socketpair()
    conn._sock = reader
    conn._rfile = reader.makefile("rb")
    started = threading.Event()
    done = threading.Event()

    def read() -> None:
        started.set()
        try:
            conn._read_bytes(1)
        except (pyoceanbase.Error, TimeoutError):
            done.set()

    worker = threading.Thread(target=read, daemon=True)
    worker.start()
    assert started.wait(2)
    conn.interrupt()
    assert done.wait(2)
    worker.join(2)
    if conn.open:
        conn.close()
    writer.close()


def test_tls_handshake_cancellation() -> None:
    conn = OracleWireConnection(defer_connect=True)
    reader, writer = socket.socketpair()
    conn._sock = reader
    done = threading.Event()

    def handshake() -> None:
        try:
            conn.ctx.wrap_socket(reader, server_hostname="localhost")
        except (OSError, TimeoutError):
            done.set()

    worker = threading.Thread(target=handshake, daemon=True)
    worker.start()
    try:
        writer.settimeout(2)
        assert writer.recv(4096)  # ClientHello sent; server never answers.
        conn.interrupt()
        assert done.wait(2)
        worker.join(2)
    finally:
        writer.close()
        if conn.open:
            conn.close()


@pytest.mark.asyncio
async def test_probe_defaults_and_cleanup(config: DatabaseConfig, wire: tuple[Any, Any]) -> None:
    factory, _ = wire
    adapter = OceanBaseOracleConnection(config)
    await adapter.connect()
    params = factory.call_args.kwargs
    assert params["port"] == 2881
    assert params["user"] == "reader@tenant#cluster"
    assert params["database"] == "APP"
    assert params["password"] == "密码".encode()
    assert params["read_timeout"] == 30
    conn = factory.return_value
    assert conn.control.execute.call_args_list[-1].args[0] == "START TRANSACTION READ ONLY"
    conn.rollback.assert_called_once()
    conn.close.assert_called_once()


@pytest.mark.asyncio
async def test_wrong_tenant_closes(config: DatabaseConfig, wire: tuple[Any, Any]) -> None:
    factory, _ = wire
    factory.return_value.control.fetchone.return_value = ("ob_compatibility_mode", "MYSQL")
    with pytest.raises(ValueError, match="不是 OceanBase"):
        await OceanBaseOracleConnection(config).connect()
    factory.return_value.close.assert_called_once()
    factory.return_value.rollback.assert_not_called()


@pytest.mark.asyncio
async def test_explicit_port_and_quoted_schema(wire: tuple[Any, Any]) -> None:
    factory, _ = wire
    cfg = DatabaseConfig(name="ob", type="oceanbase", port=2883, database='"MixedSchema"')
    await OceanBaseOracleConnection(cfg).connect()
    assert factory.call_args.kwargs["port"] == 2883
    assert factory.call_args.kwargs["database"] == "MixedSchema"


@pytest.mark.asyncio
async def test_rollback_failure_still_closes(config: DatabaseConfig, wire: tuple[Any, Any]) -> None:
    factory, _ = wire
    factory.return_value.rollback.side_effect = pyoceanbase.OperationalError("rollback failed")
    with pytest.raises(ConnectionError):
        await OceanBaseOracleConnection(config).connect()
    factory.return_value.close.assert_called_once()


def test_cancelled_before_connect_sends_no_sql(config: DatabaseConfig, wire: tuple[Any, Any]) -> None:
    factory, _ = wire
    cancelled = threading.Event()
    cancelled.set()
    with pytest.raises(TimeoutError):
        OceanBaseOracleConnection(config)._run(lambda conn: None, cancelled)
    factory.return_value.connect.assert_not_called()
    factory.return_value.control.execute.assert_not_called()


@pytest.mark.asyncio
async def test_query_binds_and_rolls_back(config: DatabaseConfig, wire: tuple[Any, Any]) -> None:
    factory, cursor = wire
    adapter = OceanBaseOracleConnection(config)
    adapter._is_connected = True
    cursor.description = [("NAME",), ("TOTAL",)]
    cursor.__iter__.return_value = iter([("O'Reilly", 0)])
    result = await adapter.execute_query("SELECT NAME,TOTAL FROM T WHERE NAME=%s -- tail", ["O'Reilly"], 2)
    sql, values = cursor.execute.call_args.args
    assert "\n) WHERE ROWNUM <= 3" in sql
    assert values == ["O'Reilly"]
    assert result.rows == [{"NAME": "O'Reilly", "TOTAL": 0}]
    assert not result.truncated
    factory.return_value.rollback.assert_called_once()
    factory.return_value.close.assert_called_once()


@pytest.mark.asyncio
async def test_stream_truncation_does_not_drain(config: DatabaseConfig, wire: tuple[Any, Any]) -> None:
    factory, cursor = wire
    adapter = OceanBaseOracleConnection(config)
    adapter._is_connected = True
    cursor.description = [("N",)]
    cursor.__iter__.return_value = iter([(1,), (2,), (3,)])
    result = await adapter.execute_query("SELECT 1 FROM DUAL", None, 1)
    assert result.rows == [{"N": 1}] and result.truncated
    cursor.close.assert_not_called()
    factory.return_value.close.assert_called_once()
    factory.return_value.rollback.assert_not_called()


@pytest.mark.asyncio
async def test_read_error_closes(config: DatabaseConfig, wire: tuple[Any, Any]) -> None:
    factory, cursor = wire
    adapter = OceanBaseOracleConnection(config)
    adapter._is_connected = True
    cursor.execute.side_effect = pyoceanbase.OperationalError("timed out")
    with pytest.raises(pyoceanbase.OperationalError):
        await adapter.execute_query("SELECT 1 FROM DUAL", None, 10)
    factory.return_value.close.assert_called_once()
    cursor.close.assert_not_called()


@pytest.mark.asyncio
@pytest.mark.parametrize("sql,parameters", [
    ("DELETE FROM T", None), ("SELECT 1; DROP TABLE T", None),
    ("SELECT S.NEXTVAL FROM DUAL", None), ("SELECT * FROM T FOR UPDATE", None),
    ("SELECT 1 /*! INTO T */ FROM DUAL", None),
    ("SELECT %s FROM DUAL", [["nested"]]),
])
async def test_rejects_before_connect(
    config: DatabaseConfig, wire: tuple[Any, Any], sql: str, parameters: Any,
) -> None:
    factory, _ = wire
    adapter = OceanBaseOracleConnection(config)
    adapter._is_connected = True
    with pytest.raises(ValueError):
        await adapter.execute_query(sql, parameters, 10)
    factory.assert_not_called()


@pytest.mark.asyncio
async def test_metadata_schema_and_key_order(config: DatabaseConfig, wire: tuple[Any, Any]) -> None:
    factory, _ = wire
    adapter = OceanBaseOracleConnection(config)
    adapter._is_connected = True
    control = factory.return_value.control
    control.fetchall.side_effect = [
        [("ORDERS",)],
        [("ID", "NUMBER", "N", "0", "id"), ("TENANT_ID", "NUMBER", "N", None, None)],
        [("TENANT_ID",), ("ID",)],
        [("TENANT_ID", "TENANTS", "ID")],
        [("IDX", "TENANT_ID", "UNIQUE"), ("IDX", "ID", "UNIQUE")],
    ]
    control.fetchone.side_effect = [("ob_compatibility_mode", "ORACLE"), ("orders",)]
    result = await adapter.describe_table("orders")
    assert result.table_name == "ORDERS" and result.comment == "orders"
    assert result.columns[0].default == "0" and result.columns[0].is_primary_key
    assert result.primary_keys == ["TENANT_ID", "ID"]
    assert result.foreign_keys[0].ref_table == "TENANTS"
    assert result.indexes[0].columns == ["TENANT_ID", "ID"]
    metadata_calls = control.execute.call_args_list[3:]
    assert all(call.args[1][0] == "APP" for call in metadata_calls)


@pytest.mark.asyncio
async def test_cancelled_worker_closes_its_connection(config: DatabaseConfig, wire: tuple[Any, Any]) -> None:
    factory, cursor = wire
    adapter = OceanBaseOracleConnection(config)
    adapter._is_connected = True
    entered = threading.Event()
    release = threading.Event()
    closed = threading.Event()

    def execute(*args: Any) -> None:
        entered.set()
        assert release.wait(5)
        raise pyoceanbase.OperationalError("cancelled request completed")

    def close() -> None:
        factory.return_value.open = False
        closed.set()

    cursor.execute.side_effect = execute
    factory.return_value.close.side_effect = close
    factory.return_value.interrupt.side_effect = release.set
    task = asyncio.create_task(adapter.execute_query("SELECT 1 FROM DUAL", None, 1))
    assert await asyncio.to_thread(entered.wait, 5)
    task.cancel()
    with pytest.raises(asyncio.CancelledError):
        await task
    await adapter.disconnect()
    release.set()
    assert await asyncio.to_thread(closed.wait, 5)


@pytest.mark.asyncio
async def test_real_oceanbase_read_only(tmp_path: Path) -> None:
    """Opt-in test: only reads an explicitly supplied test tenant."""
    required = ["OCEANBASE_HOST", "OCEANBASE_USER", "OCEANBASE_PASSWORD", "OCEANBASE_DATABASE"]
    if not all(key in os.environ for key in required):
        pytest.skip("OceanBase Oracle 测试租户未配置")
    cfg = {"databases": {"ob": {
        "type": "oceanbase", "host": os.environ[required[0]],
        "user": os.environ[required[1]], "password": os.environ[required[2]],
        "database": os.environ[required[3]], "port": int(os.getenv("OCEANBASE_PORT", "2881")),
    }}}
    path = tmp_path / "ob.yaml"
    path.write_text(yaml.safe_dump(cfg), encoding="utf-8")
    result = await handle_exec_query(
        ConfigManager(str(path)), "ob", "SELECT %s AS VALUE FROM DUAL", ["O'Reilly\\test"],
        response_format="json",
    )
    assert "O'Reilly" in result
