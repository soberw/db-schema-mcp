"""exec_query 安全校验测试。"""

import pytest

from db_schema_mcp.tools.exec_query import validate_read_only_query


class TestExecQueryValidation:
    """测试只读 SQL 校验。"""

    def test_allows_select(self) -> None:
        """允许普通 SELECT。"""
        assert validate_read_only_query("SELECT * FROM users;") == "SELECT * FROM users"

    def test_allows_with_query(self) -> None:
        """允许只读 WITH 查询。"""
        sql = "WITH active_users AS (SELECT * FROM users) SELECT * FROM active_users"
        assert validate_read_only_query(sql) == sql

    def test_rejects_multiple_statements(self) -> None:
        """拒绝多语句。"""
        with pytest.raises(ValueError, match="单条查询"):
            validate_read_only_query("SELECT * FROM users; SELECT * FROM orders")

    def test_rejects_forbidden_keyword(self) -> None:
        """拒绝修改语句。"""
        with pytest.raises(ValueError, match="非只读关键字"):
            validate_read_only_query("WITH deleted AS (DELETE FROM users RETURNING *) SELECT * FROM deleted")

    def test_ignores_keywords_inside_string_literals(self) -> None:
        """字符串字面量中的危险词不应误伤。"""
        sql = "SELECT 'DELETE FROM users' AS sample_text"
        assert validate_read_only_query(sql) == sql

    def test_rejects_select_into(self) -> None:
        """拒绝 SELECT INTO 类写入查询。"""
        with pytest.raises(ValueError, match="SELECT INTO"):
            validate_read_only_query("SELECT * INTO backup_users FROM users")
