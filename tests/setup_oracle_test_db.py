"""创建测试用 Oracle 数据库和测试数据。

运行前需要：
1. 确保 Oracle 数据库正在运行
2. 配置 tests/test_config.yaml 中的 Oracle 连接信息
3. 确保有创建表和插入数据的权限

注意: Oracle Express Edition (XE) 默认服务名通常是 XE 或 XEPDB1
Oracle 免费开发者版默认服务名通常是 FREEPDB1
"""

import asyncio
import sys
from pathlib import Path

# 添加 src 目录到 Python 路径
sys.path.insert(0, str(Path(__file__).parent.parent / "src"))

import oracledb
from yaml import safe_load

CONFIG_PATH = "./tests/test_config.yaml"


async def create_oracle_tables(
    host: str, port: int, user: str, password: str, database: str
) -> None:
    """创建 Oracle 测试表结构和数据。

    Args:
        host: Oracle 主机地址。
        port: Oracle 端口。
        user: Oracle 用户名。
        password: Oracle 密码。
        database: Oracle 服务名或 SID。
    """
    # 构建连接字符串
    dsn = f"{host}:{port}/{database}"
    print(f"🔗 连接中: {dsn}")

    # 创建连接
    conn = oracledb.connect(user=user, password=password, dsn=dsn)
    cursor = conn.cursor()

    try:
        # 检查连接
        cursor.execute("SELECT * FROM global_name")
        db_name = cursor.fetchone()[0]
        print(f"✅ 已连接到数据库: {db_name}")

        # 删除已存在的表（按依赖关系逆序）
        tables_to_drop = ["order_items", "orders", "products", "users"]
        for table in tables_to_drop:
            try:
                cursor.execute(f"DROP TABLE {table} CASCADE CONSTRAINTS PURGE")
                print(f"🗑️  已删除旧表: {table}")
            except oracledb.DatabaseError:
                pass  # 表不存在

        # 创建用户表
        cursor.execute("""
            CREATE TABLE users (
                id NUMBER(10) GENERATED ALWAYS AS IDENTITY PRIMARY KEY,
                username VARCHAR2(50) NOT NULL UNIQUE,
                email VARCHAR2(100) NOT NULL,
                age NUMBER(3),
                created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                is_active NUMBER(1) DEFAULT 1
            )
        """)
        print("✅ 已创建表: users")

        # 创建订单表
        cursor.execute("""
            CREATE TABLE orders (
                id NUMBER(10) GENERATED ALWAYS AS IDENTITY PRIMARY KEY,
                user_id NUMBER(10) NOT NULL,
                order_date TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                total_amount NUMBER(10, 2),
                status VARCHAR2(20) DEFAULT 'pending',
                CONSTRAINT fk_orders_user FOREIGN KEY (user_id) REFERENCES users(id)
            )
        """)
        print("✅ 已创建表: orders")

        # 创建产品表
        cursor.execute("""
            CREATE TABLE products (
                id NUMBER(10) GENERATED ALWAYS AS IDENTITY PRIMARY KEY,
                name VARCHAR2(100) NOT NULL,
                description CLOB,
                price NUMBER(10, 2),
                stock_quantity NUMBER(10) DEFAULT 0,
                category VARCHAR2(50)
            )
        """)
        print("✅ 已创建表: products")

        # 创建订单项表
        cursor.execute("""
            CREATE TABLE order_items (
                id NUMBER(10) GENERATED ALWAYS AS IDENTITY PRIMARY KEY,
                order_id NUMBER(10) NOT NULL,
                product_id NUMBER(10) NOT NULL,
                quantity NUMBER(10) NOT NULL,
                unit_price NUMBER(10, 2) NOT NULL,
                CONSTRAINT fk_items_order FOREIGN KEY (order_id) REFERENCES orders(id),
                CONSTRAINT fk_items_product FOREIGN KEY (product_id) REFERENCES products(id)
            )
        """)
        print("✅ 已创建表: order_items")

        # 创建索引
        cursor.execute("CREATE INDEX idx_users_username ON users(username)")
        cursor.execute("CREATE INDEX idx_users_email ON users(email)")
        cursor.execute("CREATE INDEX idx_orders_user_id ON orders(user_id)")
        cursor.execute("CREATE INDEX idx_orders_date ON orders(order_date)")
        cursor.execute("CREATE INDEX idx_products_category ON products(category)")
        print("✅ 已创建索引")

        # 插入测试数据 - 用户
        users_data = [
            ("alice", "alice@example.com", 28, 1),
            ("bob", "bob@example.com", 35, 1),
            ("charlie", "charlie@example.com", 22, 0),
        ]
        cursor.executemany(
            "INSERT INTO users (username, email, age, is_active) VALUES (:1, :2, :3, :4)",
            users_data,
        )
        print("✅ 已插入用户测试数据")

        # 插入测试数据 - 产品
        products_data = [
            ("笔记本电脑", "高性能笔记本电脑", 5999.99, 50, "电子产品"),
            ("无线鼠标", "人体工学无线鼠标", 99.99, 200, "电子产品"),
            ("机械键盘", "青轴机械键盘", 399.99, 100, "电子产品"),
            ("显示器", "27寸4K显示器", 2999.99, 30, "电子产品"),
        ]
        cursor.executemany(
            "INSERT INTO products (name, description, price, stock_quantity, category) VALUES (:1, :2, :3, :4, :5)",
            products_data,
        )
        print("✅ 已插入产品测试数据")

        # 插入测试数据 - 订单
        orders_data = [
            (1, 6099.98, "completed"),
            (2, 99.99, "pending"),
            (1, 399.99, "shipped"),
        ]
        cursor.executemany(
            "INSERT INTO orders (user_id, total_amount, status) VALUES (:1, :2, :3)",
            orders_data,
        )
        print("✅ 已插入订单测试数据")

        # 提交所有更改
        conn.commit()

        # 查询并显示表信息
        cursor.execute("""
            SELECT table_name FROM user_tables
            ORDER BY table_name
        """)
        tables = [row[0] for row in cursor.fetchall()]

        print("\n" + "=" * 60)
        print(f"🎉 Oracle 测试表创建完成!")
        print("=" * 60)
        print(f"📊 数据库: {db_name}")
        print(f"📍 主机: {host}:{port}")
        print(f"\n已创建以下表:")
        for table in tables:
            cursor.execute(f"SELECT COUNT(*) FROM {table}")
            count = cursor.fetchone()[0]
            print(f"   - {table} ({count} 条记录)")

    finally:
        cursor.close()
        conn.close()


def load_oracle_config() -> dict | None:
    """从配置文件加载 Oracle 连接信息。

    Returns:
        包含 Oracle 连接信息的字典，如果未配置则返回 None。
    """
    config_file = Path(CONFIG_PATH)
    if not config_file.exists():
        print(f"❌ 配置文件未找到: {CONFIG_PATH}")
        return None

    with open(config_file, encoding="utf-8") as f:
        config = safe_load(f)

    databases = config.get("databases", {})
    oracle_configs = {k: v for k, v in databases.items() if v.get("type") == "oracle"}

    if not oracle_configs:
        print("❌ 未在配置文件中找到 Oracle 配置")
        print(f"请在 {CONFIG_PATH} 中添加 Oracle 配置:")
        print("""
  oracle_test:
    type: oracle
    host: localhost
    port: 1521
    user: system
    password: your_password
    database: XE  # 或 XEPDB1, FREEPDB1 等
        """)
        print("\n常见 Oracle 服务名:")
        print("  - Oracle XE: XE 或 XEPDB1")
        print("  - Oracle 23c Free: FREEPDB1")
        print("  - Oracle 标准版: ORCL 或自定义服务名")
        return None

    # 返回第一个找到的 Oracle 配置
    name, conn_config = next(iter(oracle_configs.items()))
    return {
        "name": name,
        "host": conn_config.get("host"),
        "port": conn_config.get("port", 1521),
        "user": conn_config.get("user"),
        "password": conn_config.get("password"),
        "database": conn_config.get("database"),
    }


async def main() -> None:
    """主函数。"""
    print("=" * 60)
    print("🔧 Oracle 测试数据库创建工具")
    print("=" * 60)

    oracle_config = load_oracle_config()
    if not oracle_config:
        return

    print(f"\n📋 从配置文件读取到 Oracle 连接: {oracle_config['name']}")
    print(f"   主机: {oracle_config['host']}:{oracle_config['port']}")
    print(f"   用户: {oracle_config['user']}")
    print(f"   服务名: {oracle_config['database']}")

    confirm = input("\n⚠️  这将删除并重新创建测试表，确认继续? (yes/no): ")
    if confirm.lower() != "yes":
        print("❌ 操作已取消")
        return

    try:
        await create_oracle_tables(
            host=oracle_config["host"],
            port=oracle_config["port"],
            user=oracle_config["user"],
            password=oracle_config["password"],
            database=oracle_config["database"],
        )
    except Exception as e:
        print(f"\n❌ 创建测试表失败: {e}")
        print("\n请检查:")
        print("  1. Oracle 数据库是否正在运行")
        print("  2. 连接信息是否正确")
        print("  3. 用户是否有创建表的权限")
        print("  4. 服务名/SID 是否正确")


if __name__ == "__main__":
    asyncio.run(main())
