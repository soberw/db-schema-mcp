"""数据库连接的抽象基类。

本模块定义了所有数据库连接实现必须遵循的接口。
"""

import abc
from typing import Any

from db_schema_mcp.config import ConnectionInfo, TableDescription


class DatabaseConnection(abc.ABC):
    """数据库连接的抽象基类。

    所有特定数据库的连接实现（SQLite、PostgreSQL、MySQL、Oracle）
    必须继承此类并实现所有抽象方法。

    连接生命周期为:
    1. 使用 DatabaseConfig 创建实例
    2. 调用 connect() 建立连接
    3. 调用 list_tables()、describe_table() 等方法
    4. 完成后调用 disconnect()
    """

    def __init__(self, config: Any) -> None:
        """初始化数据库连接。

        Args:
            config: 包含连接参数的 DatabaseConfig 实例。
        """
        self._config = config
        self._connection: Any = None
        self._is_connected: bool = False

    @abc.abstractmethod
    async def connect(self) -> None:
        """建立数据库连接。

        Raises:
            ConnectionError: 如果连接失败。
        """

    @abc.abstractmethod
    async def disconnect(self) -> None:
        """关闭数据库连接。

        此方法应该可以安全地多次调用。
        """

    @abc.abstractmethod
    async def is_connected(self) -> bool:
        """检查数据库连接是否处于活动状态。

        Returns:
            如果已连接则返回 True，否则返回 False。
        """

    @abc.abstractmethod
    async def list_tables(self) -> list[str]:
        """获取数据库中的所有表名。

        Returns:
            表名列表。

        Raises:
            ConnectionError: 如果未连接。
        """

    @abc.abstractmethod
    async def describe_table(self, table_name: str) -> TableDescription:
        """获取表的详细结构信息。

        Args:
            table_name: 表名。

        Returns:
            包含完整模式信息的 TableDescription。

        Raises:
            ConnectionError: 如果未连接。
            ValueError: 如果表不存在。
        """

    @abc.abstractmethod
    async def get_connection_info(self) -> ConnectionInfo:
        """获取此连接的信息。

        Returns:
            包含连接详细信息的 ConnectionInfo。
        """

    async def __aenter__(self) -> "DatabaseConnection":
        """异步上下文管理器入口。"""
        await self.connect()
        return self

    async def __aexit__(self, exc_type: Any, exc_val: Any, exc_tb: Any) -> None:
        """异步上下文管理器出口。"""
        await self.disconnect()
