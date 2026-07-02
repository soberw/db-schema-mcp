"""CLI 参数处理测试。"""

from pathlib import Path

from db_schema_mcp.cli import resolve_config_path


def test_resolve_config_path_without_config() -> None:
    """未提供 --config 时返回 None。"""
    assert resolve_config_path(None) is None


def test_resolve_config_path_allows_missing_file(tmp_path: Path) -> None:
    """配置文件不存在时仍返回目标路径，便于 init 工具生成。"""
    config_path = tmp_path / "db_schema_mcp.yaml"

    assert resolve_config_path(str(config_path)) == config_path.resolve()
