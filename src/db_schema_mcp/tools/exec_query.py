"""用于执行只读 SQL 查询的 MCP 工具。"""

import json
import re
from collections.abc import Mapping, Sequence
from datetime import date, datetime
from decimal import Decimal
from typing import Any

from db_schema_mcp.config import ConfigManager, QueryResult
from db_schema_mcp.connections import ConnectionFactory

DEFAULT_LIMIT = 100
MAX_LIMIT = 1000
MAX_CELL_LENGTH = 300

ALLOWED_START_KEYWORDS = {"SELECT", "WITH"}
FORBIDDEN_KEYWORDS = {
    "ALTER",
    "ANALYZE",
    "ATTACH",
    "CALL",
    "COMMIT",
    "COPY",
    "CREATE",
    "DELETE",
    "DETACH",
    "DROP",
    "EXEC",
    "EXECUTE",
    "GRANT",
    "INSERT",
    "LOAD",
    "LOCK",
    "MERGE",
    "PRAGMA",
    "REINDEX",
    "RENAME",
    "REPLACE",
    "RESET",
    "REVOKE",
    "ROLLBACK",
    "SAVEPOINT",
    "SET",
    "TRUNCATE",
    "UNLOAD",
    "UPDATE",
    "UPSERT",
    "VACUUM",
}


def _mask_sql_literals_and_comments(sql: str) -> str:
    """Mask SQL literals/comments while preserving token positions."""
    result: list[str] = []
    i = 0
    length = len(sql)

    while i < length:
        char = sql[i]
        next_char = sql[i + 1] if i + 1 < length else ""

        if char == "-" and next_char == "-":
            result.extend("  ")
            i += 2
            while i < length and sql[i] not in "\r\n":
                result.append(" ")
                i += 1
            continue

        if char == "/" and next_char == "*":
            result.extend("  ")
            i += 2
            while i < length:
                if sql[i] == "*" and i + 1 < length and sql[i + 1] == "/":
                    result.extend("  ")
                    i += 2
                    break
                result.append(" ")
                i += 1
            continue

        if char in {"'", '"', "`"}:
            quote = char
            result.append(" ")
            i += 1
            while i < length:
                result.append(" ")
                if sql[i] == quote:
                    if i + 1 < length and sql[i + 1] == quote:
                        result.append(" ")
                        i += 2
                        continue
                    i += 1
                    break
                if sql[i] == "\\" and i + 1 < length:
                    result.append(" ")
                    i += 2
                    continue
                i += 1
            continue

        if char == "$":
            match = re.match(r"\$[A-Za-z_][A-Za-z0-9_]*\$|\$\$", sql[i:])
            if match:
                delimiter = match.group(0)
                result.extend(" " * len(delimiter))
                i += len(delimiter)
                end = sql.find(delimiter, i)
                if end == -1:
                    result.extend(" " * (length - i))
                    break
                result.extend(" " * (end - i + len(delimiter)))
                i = end + len(delimiter)
                continue

        result.append(char)
        i += 1

    return "".join(result)


def _without_optional_trailing_semicolon(sql: str) -> str:
    stripped = sql.strip()
    if stripped.endswith(";"):
        return stripped[:-1].strip()
    return stripped


def validate_read_only_query(sql: str) -> str:
    """校验 SQL 是否为单条只读查询，并返回去除末尾分号后的 SQL。"""
    normalized_sql = _without_optional_trailing_semicolon(sql)
    if not normalized_sql:
        raise ValueError("SQL 不能为空。")

    masked = _mask_sql_literals_and_comments(normalized_sql)
    if ";" in masked:
        raise ValueError("exec_query 只允许执行单条查询语句，不能包含多条 SQL。")

    first_token_match = re.search(r"\b([A-Za-z_][A-Za-z0-9_]*)\b", masked)
    if not first_token_match:
        raise ValueError("无法识别 SQL 起始关键字。")

    first_token = first_token_match.group(1).upper()
    if first_token not in ALLOWED_START_KEYWORDS:
        allowed = ", ".join(sorted(ALLOWED_START_KEYWORDS))
        raise ValueError(f"exec_query 只允许 {allowed} 开头的只读查询。")

    upper_masked = masked.upper()
    for keyword in FORBIDDEN_KEYWORDS:
        if re.search(rf"\b{keyword}\b", upper_masked):
            raise ValueError(
                f"exec_query 检测到非只读关键字 `{keyword}`，已拒绝执行。"
            )

    if re.search(r"\bINTO\b", upper_masked):
        raise ValueError("exec_query 不允许 SELECT INTO / INTO OUTFILE 等写入型查询。")

    if re.search(r"\bFOR\s+(UPDATE|SHARE|NO\s+KEY\s+UPDATE|KEY\s+SHARE)\b", upper_masked):
        raise ValueError("exec_query 不允许带行锁的 SELECT ... FOR UPDATE/SHARE 查询。")

    return normalized_sql


def _validate_parameters(parameters: Any) -> list[Any] | dict[str, Any] | None:
    if parameters is None:
        return None
    if isinstance(parameters, Mapping):
        return dict(parameters)
    if isinstance(parameters, Sequence) and not isinstance(parameters, str | bytes | bytearray):
        return list(parameters)
    raise ValueError("parameters 必须是数组、对象或 null。请使用参数绑定避免拼接 SQL。")


def _validate_limit(limit: Any) -> int:
    if limit is None:
        return DEFAULT_LIMIT
    if not isinstance(limit, int) or isinstance(limit, bool):
        raise ValueError("limit 必须是整数。")
    if limit < 1 or limit > MAX_LIMIT:
        raise ValueError(f"limit 必须在 1 到 {MAX_LIMIT} 之间。")
    return limit


def _json_safe(value: Any) -> Any:
    if value is None or isinstance(value, str | int | float | bool):
        return value
    if isinstance(value, Decimal):
        return str(value)
    if isinstance(value, datetime | date):
        return value.isoformat()
    if isinstance(value, bytes | bytearray | memoryview):
        return f"<bytes {len(value)}>"
    return str(value)


def _format_cell(value: Any) -> str:
    safe_value = _json_safe(value)
    text = "NULL" if safe_value is None else str(safe_value)
    text = text.replace("\r", " ").replace("\n", " ").replace("|", "\\|")
    if len(text) > MAX_CELL_LENGTH:
        return text[:MAX_CELL_LENGTH] + "..."
    return text


def format_query_result(
    connection_name: str,
    result: QueryResult,
    response_format: str,
) -> str:
    """格式化查询结果。"""
    if response_format == "json":
        payload = {
            "connection_name": connection_name,
            "columns": result.columns,
            "row_count": result.row_count,
            "truncated": result.truncated,
            "rows": [
                {column: _json_safe(row.get(column)) for column in result.columns}
                for row in result.rows
            ],
        }
        return json.dumps(payload, ensure_ascii=False, indent=2)

    lines = [
        f"## 查询结果: {connection_name}",
        "",
        f"- 返回行数: {result.row_count}",
        f"- 是否截断: {'是' if result.truncated else '否'}",
        "",
    ]

    if not result.columns:
        lines.append("查询未返回列。")
        return "\n".join(lines)

    if not result.rows:
        lines.append("查询成功，但没有返回数据行。")
        lines.append(f"列: {', '.join(result.columns)}")
        return "\n".join(lines)

    header = "| " + " | ".join(result.columns) + " |"
    separator = "| " + " | ".join(["---"] * len(result.columns)) + " |"
    lines.extend([header, separator])
    for row in result.rows:
        values = [_format_cell(row.get(column)) for column in result.columns]
        lines.append("| " + " | ".join(values) + " |")

    if result.truncated:
        lines.extend(["", "结果已按 limit 截断，请提高筛选条件或调整 limit。"])

    return "\n".join(lines)


async def handle_exec_query(
    config_manager: ConfigManager,
    connection_name: str,
    sql: str,
    parameters: Any = None,
    limit: Any = None,
    response_format: str = "markdown",
) -> str:
    """处理 exec_query MCP 工具。"""
    conn_config = config_manager.get_connection(connection_name)
    if not conn_config:
        available = config_manager.get_connection_names()
        raise ValueError(
            f"连接 '{connection_name}' 未找到。\n"
            f"可用连接: {', '.join(available) if available else '无'}"
        )

    if response_format not in {"markdown", "json"}:
        raise ValueError("response_format 必须是 'markdown' 或 'json'。")

    safe_sql = validate_read_only_query(sql)
    safe_parameters = _validate_parameters(parameters)
    safe_limit = _validate_limit(limit)

    conn = ConnectionFactory.create(conn_config)
    try:
        await conn.connect()
        result = await conn.execute_query(safe_sql, safe_parameters, safe_limit)
        return format_query_result(connection_name, result, response_format)
    finally:
        await conn.disconnect()
