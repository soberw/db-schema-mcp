"""创建测试用 MySQL 数据库和测试数据。

运行前需要：
1. 确保 MySQL 服务正在运行
2. 配置 tests/test_config.yaml 中的 MySQL 连接信息
3. 确保有创建数据库的权限
"""

import asyncio
import sys
from pathlib import Path

# 添加 src 目录到 Python 路径
sys.path.insert(0, str(Path(__file__).parent.parent / "src"))

import aiomysql
from yaml import safe_load

CONFIG_PATH = "./tests/test_config.yaml"
DB_NAME = "test_db"


async def create_mysql_database(
    host: str, port: int, user: str, password: str, database: str = DB_NAME
) -> None:
    """创建 MySQL 测试数据库和表结构。

    Args:
        host: MySQL 主机地址。
        port: MySQL 端口。
        user: MySQL 用户名。
        password: MySQL 密码。
        database: 数据库名称。
    """
    # 首先连接到 MySQL 服务器创建数据库
    conn = await aiomysql.connect(
        host=host, port=port, user=user, password=password, autocommit=True
    )
    cursor = await conn.cursor()

    try:
        # 删除已存在的测试数据库
        await cursor.execute(f"DROP DATABASE IF EXISTS `{database}`")
        print(f"🗑️  已删除旧数据库 (如果存在): {database}")

        # 创建新数据库
        await cursor.execute(f"CREATE DATABASE `{database}` CHARACTER SET utf8mb4 COLLATE utf8mb4_unicode_ci")
        print(f"✅ 已创建数据库: {database}")

        # 切换到新数据库
        await cursor.execute(f"USE `{database}`")

        # 创建用户表
        await cursor.execute("""
            CREATE TABLE users (
                id INT AUTO_INCREMENT PRIMARY KEY,
                username VARCHAR(50) NOT NULL UNIQUE,
                email VARCHAR(100) NOT NULL,
                age INT,
                created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                is_active TINYINT(1) DEFAULT 1,
                INDEX idx_username (username),
                INDEX idx_email (email)
            ) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4
        """)
        print("✅ 已创建表: users")

        # 创建订单表
        await cursor.execute("""
            CREATE TABLE orders (
                id INT AUTO_INCREMENT PRIMARY KEY,
                user_id INT NOT NULL,
                order_date TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                total_amount DECIMAL(10, 2),
                status VARCHAR(20) DEFAULT 'pending',
                FOREIGN KEY (user_id) REFERENCES users(id) ON DELETE CASCADE,
                INDEX idx_user_id (user_id),
                INDEX idx_order_date (order_date)
            ) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4
        """)
        print("✅ 已创建表: orders")

        # 创建产品表
        await cursor.execute("""
            CREATE TABLE products (
                id INT AUTO_INCREMENT PRIMARY KEY,
                name VARCHAR(100) NOT NULL,
                description TEXT,
                price DECIMAL(10, 2),
                stock_quantity INT DEFAULT 0,
                category VARCHAR(50),
                INDEX idx_category (category)
            ) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4
        """)
        print("✅ 已创建表: products")

        # 创建订单项表
        await cursor.execute("""
            CREATE TABLE order_items (
                id INT AUTO_INCREMENT PRIMARY KEY,
                order_id INT NOT NULL,
                product_id INT NOT NULL,
                quantity INT NOT NULL,
                unit_price DECIMAL(10, 2) NOT NULL,
                FOREIGN KEY (order_id) REFERENCES orders(id) ON DELETE CASCADE,
                FOREIGN KEY (product_id) REFERENCES products(id),
                INDEX idx_order_id (order_id),
                INDEX idx_product_id (product_id)
            ) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4
        """)
        print("✅ 已创建表: order_items")

        # 插入测试数据 - 用户
        await cursor.executemany(
            "INSERT INTO users (username, email, age, is_active) VALUES (%s, %s, %s, %s)",
            [
                ("alice", "alice@example.com", 28, 1),
                ("bob", "bob@example.com", 35, 1),
                ("charlie", "charlie@example.com", 22, 0),
            ],
        )
        print("✅ 已插入用户测试数据")

        # 插入测试数据 - 产品
        await cursor.executemany(
            "INSERT INTO products (name, description, price, stock_quantity, category) VALUES (%s, %s, %s, %s, %s)",
            [
                ("笔记本电脑", "高性能笔记本电脑", 5999.99, 50, "电子产品"),
                ("无线鼠标", "人体工学无线鼠标", 99.99, 200, "电子产品"),
                ("机械键盘", "青轴机械键盘", 399.99, 100, "电子产品"),
                ("显示器", "27寸4K显示器", 2999.99, 30, "电子产品"),
            ],
        )
        print("✅ 已插入产品测试数据")

        # 插入测试数据 - 订单
        await cursor.executemany(
            "INSERT INTO orders (user_id, total_amount, status) VALUES (%s, %s, %s)",
            [
                (1, 6099.98, "completed"),
                (2, 99.99, "pending"),
                (1, 399.99, "shipped"),
            ],
        )
        print("✅ 已插入订单测试数据")

        print("\n" + "=" * 60)
        print(f"🎉 MySQL 测试数据库创建完成!")
        print("=" * 60)
        print(f"📊 数据库: {database}")
        print(f"📍 主机: {host}:{port}")
        print(f"\n包含以下表:")
        print(f"   - users (用户表)")
        print(f"   - orders (订单表)")
        print(f"   - products (产品表)")
        print(f"   - order_items (订单项表)")

    finally:
        await cursor.close()
        conn.close()


def load_mysql_config() -> dict | None:
    """从配置文件加载 MySQL 连接信息。

    Returns:
        包含 MySQL 连接信息的字典，如果未配置则返回 None。
    """
    config_file = Path(CONFIG_PATH)
    if not config_file.exists():
        print(f"❌ 配置文件未找到: {CONFIG_PATH}")
        return None

    with open(config_file, encoding="utf-8") as f:
        config = safe_load(f)

    databases = config.get("databases", {})
    mysql_configs = {k: v for k, v in databases.items() if v.get("type") == "mysql"}

    if not mysql_configs:
        print("❌ 未在配置文件中找到 MySQL 配置")
        print(f"请在 {CONFIG_PATH} 中添加 MySQL 配置:")
        print("""
  mysql_test:
    type: mysql
    host: localhost
    port: 3306
    user: root
    password: your_password
    database: test_db
        """)
        return None

    # 返回第一个找到的 MySQL 配置
    name, conn_config = next(iter(mysql_configs.items()))
    return {
        "name": name,
        "host": conn_config.get("host"),
        "port": conn_config.get("port", 3306),
        "user": conn_config.get("user"),
        "password": conn_config.get("password"),
        "database": conn_config.get("database", DB_NAME),
    }


async def main() -> None:
    """主函数。"""
    print("=" * 60)
    print("🔧 MySQL 测试数据库创建工具")
    print("=" * 60)

    mysql_config = load_mysql_config()
    if not mysql_config:
        return

    print(f"\n📋 从配置文件读取到 MySQL 连接: {mysql_config['name']}")
    print(f"   主机: {mysql_config['host']}:{mysql_config['port']}")
    print(f"   用户: {mysql_config['user']}")
    print(f"   数据库: {mysql_config['database']}")

    confirm = input("\n⚠️  这将删除并重新创建数据库，确认继续? (yes/no): ")
    if confirm.lower() != "yes":
        print("❌ 操作已取消")
        return

    try:
        await create_mysql_database(
            host=mysql_config["host"],
            port=mysql_config["port"],
            user=mysql_config["user"],
            password=mysql_config["password"],
            database=mysql_config["database"],
        )
    except Exception as e:
        print(f"\n❌ 创建数据库失败: {e}")
        print("\n请检查:")
        print("  1. MySQL 服务是否正在运行")
        print("  2. 连接信息是否正确")
        print("  3. 用户是否有创建数据库的权限")


if __name__ == "__main__":
    asyncio.run(main())
