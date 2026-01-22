"""配置管理的测试。"""

import tempfile
from pathlib import Path

import pytest
import yaml

from db_schema_mcp.config import ConfigManager, DatabaseConfig


class TestConfigManager:
    """测试 ConfigManager 的功能。"""

    def test_load_valid_config(self, tmp_path: Path) -> None:
        """测试加载有效的配置文件。"""
        config_data = {
            "databases": {
                "test_sqlite": {
                    "type": "sqlite",
                    "path": "/tmp/test.db",
                },
                "test_postgres": {
                    "type": "postgresql",
                    "host": "localhost",
                    "port": 5432,
                    "user": "postgres",
                    "password": "password",
                    "database": "testdb",
                },
            }
        }

        config_file = tmp_path / "test_config.yaml"
        with open(config_file, "w", encoding="utf-8") as f:
            yaml.dump(config_data, f)

        manager = ConfigManager(str(config_file))
        connections = manager.list_connections()

        assert len(connections) == 2
        assert manager.get_connection("test_sqlite") is not None
        assert manager.get_connection("test_postgres") is not None

    def test_file_not_found(self, tmp_path: Path) -> None:
        """测试配置文件不存在时的错误。"""
        with pytest.raises(FileNotFoundError, match="配置文件未找到"):
            ConfigManager(str(tmp_path / "nonexistent.yaml"))

    def test_missing_databases_key(self, tmp_path: Path) -> None:
        """测试缺少 'databases' 键时的错误。"""
        config_file = tmp_path / "test_config.yaml"
        with open(config_file, "w", encoding="utf-8") as f:
            yaml.dump({"other_key": "value"}, f)

        with pytest.raises(ValueError, match="缺少 'databases' 键"):
            ConfigManager(str(config_file))

    def test_missing_required_fields(self, tmp_path: Path) -> None:
        """测试缺少必填字段时的错误。"""
        config_data = {
            "databases": {
                "test_postgres": {
                    "type": "postgresql",
                    "host": "localhost",
                    # 缺少: user, password, database
                }
            }
        }

        config_file = tmp_path / "test_config.yaml"
        with open(config_file, "w", encoding="utf-8") as f:
            yaml.dump(config_data, f)

        with pytest.raises(ValueError, match="缺少必填字段"):
            ConfigManager(str(config_file))

    def test_unsupported_database_type(self, tmp_path: Path) -> None:
        """测试不支持的数据库类型时的错误。"""
        config_data = {
            "databases": {
                "test_mongo": {
                    "type": "mongodb",
                    "host": "localhost",
                }
            }
        }

        config_file = tmp_path / "test_config.yaml"
        with open(config_file, "w", encoding="utf-8") as f:
            yaml.dump(config_data, f)

        with pytest.raises(ValueError, match="不支持的数据库类型"):
            ConfigManager(str(config_file))

    def test_get_connection_not_found(self, tmp_path: Path) -> None:
        """测试获取不存在的连接。"""
        config_data = {
            "databases": {
                "test": {
                    "type": "sqlite",
                    "path": "/tmp/test.db",
                }
            }
        }

        config_file = tmp_path / "test_config.yaml"
        with open(config_file, "w", encoding="utf-8") as f:
            yaml.dump(config_data, f)

        manager = ConfigManager(str(config_file))
        assert manager.get_connection("nonexistent") is None
