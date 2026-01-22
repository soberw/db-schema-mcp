"""db-schema-mcp 的配置和数据模型。

本模块定义了用于数据库配置和表结构表示的所有数据结构。
"""

from dataclasses import dataclass, field
from pathlib import Path
from typing import Any

import yaml


# ============================================================================
# 数据库配置模型
# ============================================================================


@dataclass(frozen=True)
class DatabaseConfig:
    """单个数据库连接的配置。

    Attributes:
        name: 用于引用此配置的连接名称。
        type: 数据库类型 (sqlite, postgresql, mysql, oracle)。
        host: 数据库主机地址 (SQLite 为 None)。
        port: 数据库端口号 (SQLite 为 None)。
        user: 数据库用户名 (SQLite 为 None)。
        password: 数据库密码 (SQLite 为 None)。
        database: 数据库名称 (SQLite 为 None)。
        path: SQLite 数据库文件路径 (仅 SQLite 使用)。
        ssl: SSL/TLS 配置字典。
        sslmode: PostgreSQL 的 SSL 模式 (disable, allow, prefer, require, verify-ca, verify-full)。
    """

    name: str
    type: str
    host: str | None = None
    port: int | None = None
    user: str | None = None
    password: str | None = None
    database: str | None = None
    path: str | None = None
    ssl: dict[str, Any] | None = None
    sslmode: str | None = None


@dataclass
class ConnectionInfo:
    """数据库连接的信息。

    Attributes:
        name: 连接名称。
        type: 数据库类型。
        host: 主机地址或 SQLite 的文件路径。
        port: 端口号 (SQLite 为 None)。
        database: 数据库名称。
        status: 连接状态 (connected, failed, disconnected)。
        error: 连接失败时的错误信息。
    """

    name: str
    type: str
    host: str | None
    port: int | None
    database: str | None
    status: str
    error: str | None = None


# ============================================================================
# 表结构模型
# ============================================================================


@dataclass
class ColumnInfo:
    """表列的信息。

    Attributes:
        name: 列名。
        type: 数据类型。
        nullable: 列是否可包含 NULL 值。
        default: 默认值。
        comment: 列的注释/描述。
        is_primary_key: 此列是否为主键。
    """

    name: str
    type: str
    nullable: bool
    default: str | None = None
    comment: str | None = None
    is_primary_key: bool = False


@dataclass
class ForeignKeyInfo:
    """外键约束的信息。

    Attributes:
        column: 此表中的列名。
        ref_table: 引用的表名。
        ref_column: 引用的列名。
    """

    column: str
    ref_table: str
    ref_column: str


@dataclass
class IndexInfo:
    """索引的信息。

    Attributes:
        name: 索引名称。
        columns: 索引中的列名列表。
        unique: 是否为唯一索引。
    """

    name: str
    columns: list[str]
    unique: bool


@dataclass
class TableDescription:
    """数据库表的完整描述。

    Attributes:
        table_name: 表名。
        columns: 列信息列表。
        primary_keys: 主键列名列表。
        foreign_keys: 外键约束列表。
        indexes: 索引列表。
        comment: 表的注释/描述。
    """

    table_name: str
    columns: list[ColumnInfo]
    primary_keys: list[str] = field(default_factory=list)
    foreign_keys: list[ForeignKeyInfo] = field(default_factory=list)
    indexes: list[IndexInfo] = field(default_factory=list)
    comment: str | None = None


# ============================================================================
# 配置管理器
# ============================================================================


class ConfigManager:
    """管理从 YAML 文件加载数据库配置。

    此类处理从 YAML 文件加载、解析和验证数据库配置。

    Attributes:
        _config_path: 配置文件的路径。
        _connections: 按名称索引的数据库配置字典。
    """

    # 每种数据库类型的必填字段
    _REQUIRED_FIELDS: dict[str, set[str]] = {
        "sqlite": {"type", "path"},
        "postgresql": {"type", "host", "user", "password", "database"},
        "mysql": {"type", "host", "user", "password", "database"},
        "oracle": {"type", "host", "user", "password", "database"},
    }

    def __init__(self, config_path: str) -> None:
        """初始化配置管理器。

        Args:
            config_path: YAML 配置文件的路径。

        Raises:
            FileNotFoundError: 如果配置文件不存在。
            ValueError: 如果 YAML 格式无效或缺少必填字段。
        """
        self._config_path = Path(config_path).expanduser().resolve()

        if not self._config_path.exists():
            raise FileNotFoundError(
                f"配置文件未找到: {self._config_path}\n"
                f"请检查路径后重试。"
            )

        self._connections: dict[str, DatabaseConfig] = {}
        self._load_config()

    def _load_config(self) -> None:
        """加载并解析 YAML 配置文件。

        Raises:
            ValueError: 如果 YAML 格式无效或缺少必填字段。
        """
        try:
            with open(self._config_path, encoding="utf-8") as f:
                data = yaml.safe_load(f)
        except yaml.YAMLError as e:
            raise ValueError(
                f"{self._config_path} 中的 YAML 格式无效: {e}\n"
                f"请检查 YAML 语法后重试。"
            ) from e

        if not isinstance(data, dict):
            raise ValueError(
                f"配置文件根级别必须包含字典。\n"
                f"期望格式: databases:\n  connection_name:\n    type: ...\n"
            )

        databases = data.get("databases")
        if not isinstance(databases, dict):
            raise ValueError(
                f"配置文件中缺少 'databases' 键。\n"
                f"请确保配置包含 'databases:' 部分。"
            )

        if not databases:
            raise ValueError(
                f"'databases' 部分未定义数据库连接。\n"
                f"请至少添加一个数据库连接。"
            )

        for name, db_config in databases.items():
            if not isinstance(db_config, dict):
                raise ValueError(
                    f"'{name}' 的数据库配置必须是字典。\n"
                    f"请检查 '{name}' 连接的格式。"
                )
            self._parse_connection(name, db_config)

    def _parse_connection(self, name: str, config: dict[str, Any]) -> None:
        """解析单个数据库连接配置。

        Args:
            name: 连接名称。
            config: 配置字典。

        Raises:
            ValueError: 如果缺少必填字段或数据库类型不支持。
        """
        db_type = config.get("type", "").lower()

        if not db_type:
            raise ValueError(
                f"连接 '{name}' 缺少 'type' 字段。\n"
                f"支持的类型: {', '.join(self._REQUIRED_FIELDS.keys())}"
            )

        if db_type not in self._REQUIRED_FIELDS:
            raise ValueError(
                f"连接 '{name}' 的数据库类型 '{db_type}' 不支持。\n"
                f"支持的类型: {', '.join(self._REQUIRED_FIELDS.keys())}"
            )

        # 检查必填字段
        required = self._REQUIRED_FIELDS[db_type]
        missing = required - set(config.keys())
        if missing:
            raise ValueError(
                f"{db_type} 连接 '{name}' 缺少必填字段: {', '.join(missing)}\n"
                f"{db_type} 的必填字段: {', '.join(required)}"
            )

        # 创建 DatabaseConfig
        self._connections[name] = DatabaseConfig(
            name=name,
            type=db_type,
            host=config.get("host"),
            port=config.get("port"),
            user=config.get("user"),
            password=config.get("password"),
            database=config.get("database"),
            path=config.get("path"),
            ssl=config.get("ssl"),
            sslmode=config.get("sslmode"),
        )

    def get_connection(self, name: str) -> DatabaseConfig | None:
        """根据名称获取数据库配置。

        Args:
            name: 连接名称。

        Returns:
            如果找到则返回 DatabaseConfig，否则返回 None。
        """
        return self._connections.get(name)

    def list_connections(self) -> list[DatabaseConfig]:
        """列出所有数据库配置。

        Returns:
            所有 DatabaseConfig 对象的列表。
        """
        return list(self._connections.values())

    def get_connection_names(self) -> list[str]:
        """获取所有连接名称。

        Returns:
            连接名称列表。
        """
        return list(self._connections.keys())
