"""数据库连接配置。

密码等敏感信息从环境变量读取,不写进代码。本地开发时:
    1. cp .env.example .env
    2. 编辑 .env 填入真实密码

本模块是整个项目唯一的数据库入口:ETL 与分析脚本都从这里拿 engine。
"""
import os

from dotenv import load_dotenv
from sqlalchemy import create_engine

PROJECT_ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))

# 显式指定 .env 路径。不用裸 load_dotenv():它靠当前工作目录向上查找,
# 从别的目录运行脚本时会静默失效,最后报出一个看不懂的认证错误。
load_dotenv(os.path.join(PROJECT_ROOT, ".env"))


def _get_secret(name):
    """读取必填的环境变量,缺失时给出可操作的报错。"""
    value = os.getenv(name)
    if not value:
        raise RuntimeError(
            f"环境变量 {name} 未设置。请复制 .env.example 为 .env 并填入数据库密码:\n"
            f"    cp .env.example .env"
        )
    return value


DB_CONFIG = {
    "host": os.getenv("MYSQL_HOST", "127.0.0.1"),
    "port": int(os.getenv("MYSQL_PORT", "3306")),
    "user": os.getenv("MYSQL_USER", "root"),
    "database": "olist",
    "charset": "utf8mb4",
}


def get_engine():
    """创建 SQLAlchemy engine。

    密码在这里才读取(而不是模块导入时),这样缺少密码时的报错
    能带上一句清楚的提示,而不是 create_engine 抛出的 Access denied。
    """
    return create_engine(
        f"mysql+pymysql://{DB_CONFIG['user']}:{_get_secret('MYSQL_PASSWORD')}"
        f"@{DB_CONFIG['host']}:{DB_CONFIG['port']}/{DB_CONFIG['database']}"
        f"?charset={DB_CONFIG['charset']}"
    )
