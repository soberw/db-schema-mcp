"""创建测试用 SQLite 数据库和测试数据。"""

import io
import sqlite3
import sys
from pathlib import Path

# 设置 UTF-8 编码输出（兼容 Windows）
if sys.platform == "win32":
    sys.stdout = io.TextIOWrapper(sys.stdout.buffer, encoding="utf-8", errors="replace")
    sys.stderr = io.TextIOWrapper(sys.stderr.buffer, encoding="utf-8", errors="replace")


def create_test_database(db_path: str = "./tests/test_data.db") -> None:
    """创建一个包含测试表和数据的 SQLite 数据库。

    Args:
        db_path: 数据库文件路径。
    """
    db_file = Path(db_path)
    db_file.parent.mkdir(parents=True, exist_ok=True)

    conn = sqlite3.connect(db_path)
    cursor = conn.cursor()

    # 创建用户表
    cursor.execute("""
        CREATE TABLE IF NOT EXISTS users (
            id INTEGER PRIMARY KEY AUTOINCREMENT,  -- 用户唯一标识 ID
            username VARCHAR(50) NOT NULL UNIQUE,  -- 用户名，登录用
            email VARCHAR(100) NOT NULL,           -- 用户邮箱地址
            age INTEGER,                            -- 用户年龄
            created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,  -- 账户创建时间
            is_active BOOLEAN DEFAULT 1            /* 账户是否激活，1-激活，0-未激活 */
        )
    """)

    # 创建订单表
    cursor.execute("""
        CREATE TABLE IF NOT EXISTS orders (
            id INTEGER PRIMARY KEY AUTOINCREMENT,  -- 订单唯一标识
            user_id INTEGER NOT NULL,              -- 下单用户 ID
            order_date TIMESTAMP DEFAULT CURRENT_TIMESTAMP,  -- 下单时间
            total_amount DECIMAL(10, 2),           /* 订单总金额（元） */
            status VARCHAR(20) DEFAULT 'pending',  /* 订单状态：pending-待处理，paid-已支付，shipped-已发货，completed-已完成 */
            FOREIGN KEY (user_id) REFERENCES users(id)
        )
    """)

    # 创建产品表
    cursor.execute("""
        CREATE TABLE IF NOT EXISTS products (
            id INTEGER PRIMARY KEY AUTOINCREMENT,  -- 产品唯一标识
            name VARCHAR(100) NOT NULL,            /* 产品名称 */
            description TEXT,                       -- 产品详细描述
            price DECIMAL(10, 2),                  /* 单价（元） */
            stock_quantity INTEGER DEFAULT 0,      -- 库存数量
            category VARCHAR(50)                    /* 产品分类 */
        )
    """)

    # 创建订单项表
    cursor.execute("""
        CREATE TABLE IF NOT EXISTS order_items (
            id INTEGER PRIMARY KEY AUTOINCREMENT,  -- 订单项唯一标识
            order_id INTEGER NOT NULL,             /* 所属订单 ID */
            product_id INTEGER NOT NULL,           -- 产品 ID
            quantity INTEGER NOT NULL,             /* 购买数量 */
            unit_price DECIMAL(10, 2) NOT NULL,    /* 下单时的单价 */
            FOREIGN KEY (order_id) REFERENCES orders(id),
            FOREIGN KEY (product_id) REFERENCES products(id)
        )
    """)

    # 创建索引
    cursor.execute("""
        CREATE INDEX IF NOT EXISTS idx_users_username ON users(username)
    """)
    cursor.execute("""
        CREATE INDEX IF NOT EXISTS idx_users_email ON users(email)
    """)
    cursor.execute("""
        CREATE INDEX IF NOT EXISTS idx_orders_user_id ON orders(user_id)
    """)
    cursor.execute("""
        CREATE INDEX IF NOT EXISTS idx_orders_date ON orders(order_date)
    """)

    # 插入测试数据
    cursor.executemany(
        "INSERT OR IGNORE INTO users (username, email, age, is_active) VALUES (?, ?, ?, ?)",
        [
            ("alice", "alice@example.com", 28, 1),
            ("bob", "bob@example.com", 35, 1),
            ("charlie", "charlie@example.com", 22, 0),
        ],
    )

    cursor.executemany(
        "INSERT OR IGNORE INTO products (name, description, price, stock_quantity, category) VALUES (?, ?, ?, ?, ?)",
        [
            ("笔记本电脑", "高性能笔记本电脑", 5999.99, 50, "电子产品"),
            ("无线鼠标", "人体工学无线鼠标", 99.99, 200, "电子产品"),
            ("机械键盘", "青轴机械键盘", 399.99, 100, "电子产品"),
            ("显示器", "27寸4K显示器", 2999.99, 30, "电子产品"),
        ],
    )

    conn.commit()
    conn.close()

    print(f"✅ 测试数据库已创建: {db_file.absolute()}")
    print("📊 包含以下表:")
    print("   - users (用户表)")
    print("   - orders (订单表)")
    print("   - products (产品表)")
    print("   - order_items (订单项表)")


if __name__ == "__main__":
    create_test_database()
