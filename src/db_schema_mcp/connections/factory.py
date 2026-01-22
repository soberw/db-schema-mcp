"""数据库连接工厂。

本模块提供根据配置类型创建数据库连接实例的工厂。
"""

from typing import Any

from db_schema_mcp.config import DatabaseConfig
from db_schema_mcp.connections.base import DatabaseConnection
from db_schema_mcp.connections.mysql import MySQLConnection
from db_schema_mcp.connections.oracle import OracleConnection
from db_schema_mcp.connections.postgres import PostgresConnection
from db_schema_mcp.connections.sqlite import SQLiteConnection


class ConnectionFactory:
    """用于创建数据库连接实例的工厂。

    此工厂根据配置中的数据库类型创建相应的连接类。

    支持的数据库类型:
    - sqlite
    - postgresql
    - mysql
    - oracle
    """

    _drivers: dict[str, type[DatabaseConnection]] = {
        "sqlite": SQLiteConnection,
        "postgresql": PostgresConnection,
        "mysql": MySQLConnection,
        "oracle": OracleConnection,
    }

    @classmethod
    def create(cls, config: DatabaseConfig) -> DatabaseConnection:
        """根据配置创建数据库连接实例。

        Args:
            config: 包含连接参数的 DatabaseConfig。

        Returns:
            指定数据库类型的 DatabaseConnection 实例。

        Raises:
            ValueError: 如果数据库类型不支持。
        """
        db_type = config.type.lower()

        if db_type not in cls._drivers:
            supported = ", ".join(cls._drivers.keys())
            msg = (
                f"不支持的数据库类型: '{config.type}'\n"
                f"支持的类型: {supported}"
            )
            raise ValueError(msg)

        driver_class = cls._drivers[db_type]
        return driver_class(config)

    @classmethod
    def register_driver(cls, db_type: str, driver_class: type[DatabaseConnection]) -> None:
        """注册自定义数据库驱动。

        Args:
            db_type: 数据库类型标识符 (例如 'oracle')。
            driver_class: DatabaseConnection 子类。
        """
        cls._drivers[db_type.lower()] = driver_class

    @classmethod
    def supported_types(cls) -> list[str]:
        """获取支持的数据库类型列表。

        Returns:
            数据库类型标识符列表。
        """
        return list(cls._drivers.keys())
