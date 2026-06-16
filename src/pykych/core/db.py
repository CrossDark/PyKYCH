"""
核心数据库模块 — MySQL 连接管理与表初始化。

此模块提供统一的数据库连接管理：
    - 读取 data/settings/db.yaml 配置
    - 惰性创建连接池（单例模式）
    - 自动创建数据库（如不存在）
    - 应用启动时建表和迁移
    - 应用关闭时释放连接池

用法:
    from pykych.core.db import get_sys_pool, get_md_pool, get_wk_pool
    from pykych.core.db import init_tables, close_pools, row_to_dict
"""

import yaml
from pathlib import Path
from typing import Any
from datetime import datetime, date

import aiomysql

# ── 配置文件路径 ────────────────────────────────────────────

CONFIG_PATH = Path(__file__).parent.parent.parent.parent / "data" / "settings" / "db.yaml"

with open(CONFIG_PATH, "r", encoding="utf-8") as f:
    _config: dict[str, Any] = yaml.safe_load(f)

_mysql = _config["mysql"]


# ── 全局连接池（惰性创建，单例） ─────────────────────────────

_pool: aiomysql.Pool | None = None


async def _create_pool() -> aiomysql.Pool:
    """
    创建 MySQL 连接池。

    如果目标数据库不存在，尝试自动创建（需要 CREATE DATABASE 权限）。
    失败时给出明确的错误信息和修复建议。
    """
    pool_cfg = _mysql.get("pool", {})
    db_name = _mysql["database"]

    async def _connect(db: str) -> aiomysql.Pool:
        return await aiomysql.create_pool(
            host=_mysql["host"],
            port=_mysql.get("port", 3306),
            user=_mysql["user"],
            password=_mysql["password"],
            db=db,
            charset=_mysql.get("charset", "utf8mb4"),
            minsize=pool_cfg.get("minsize", 2),
            maxsize=pool_cfg.get("maxsize", 10),
            pool_recycle=pool_cfg.get("pool_recycle", 3600),
            autocommit=True,
        )

    # 尝试直接连接目标数据库
    try:
        return await _connect(db_name)
    except Exception as e:
        err_msg = str(e)
        if "1049" not in err_msg and "Unknown database" not in err_msg:
            raise

    # 数据库不存在，尝试创建
    try:
        temp_conn = await aiomysql.connect(
            host=_mysql["host"],
            port=_mysql.get("port", 3306),
            user=_mysql["user"],
            password=_mysql["password"],
            charset=_mysql.get("charset", "utf8mb4"),
            autocommit=True,
        )
        try:
            async with temp_conn.cursor() as cur:
                await cur.execute(
                    f"CREATE DATABASE IF NOT EXISTS `{db_name}` "
                    "CHARACTER SET utf8mb4 COLLATE utf8mb4_unicode_ci"
                )
        finally:
            temp_conn.close()
    except Exception as e:
        raise RuntimeError(
            f"数据库 '{db_name}' 不存在且无法自动创建（权限不足）。\n"
            f"请在 MySQL 中手动执行: CREATE DATABASE IF NOT EXISTS `{db_name}` "
            "CHARACTER SET utf8mb4 COLLATE utf8mb4_unicode_ci;\n"
            f"原始错误: {e}"
        ) from e

    return await _connect(db_name)


async def _get_pool() -> aiomysql.Pool:
    """获取统一数据库连接池（惰性创建）。"""
    global _pool
    if _pool is None:
        _pool = await _create_pool()
    return _pool


# ── 兼容别名（所有文章类型共用同一数据库） ──────────────────


async def get_md_pool() -> aiomysql.Pool:
    """获取 Markdown 文章连接池（指向统一 pykych 数据库）。"""
    return await _get_pool()


async def get_wk_pool() -> aiomysql.Pool:
    """获取 Wikidot 页面连接池（指向统一 pykych 数据库）。"""
    return await _get_pool()


async def get_sys_pool() -> aiomysql.Pool:
    """获取系统管理连接池（指向统一 pykych 数据库）。"""
    return await _get_pool()


async def close_pools() -> None:
    """关闭连接池（应用关闭时调用）。"""
    global _pool
    if _pool:
        _pool.close()
        await _pool.wait_closed()
    _pool = None


# ── 工具函数 ────────────────────────────────────────────────


def row_to_dict(row: tuple, cursor: aiomysql.Cursor) -> dict:
    """
    将数据库查询结果行转为字典。

    datetime/date 对象自动转为 ISO 8601 字符串。

    参数:
        row:    查询结果元组
        cursor: aiomysql 游标对象（用于获取列名）

    返回:
        字典，键为列名，值为对应的 Python 对象
    """
    cols = [desc[0] for desc in cursor.description]
    result = {}
    for col, val in zip(cols, row):
        if isinstance(val, (datetime, date)):
            result[col] = val.isoformat()
        else:
            result[col] = val
    return result
