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

import os
import yaml
from pathlib import Path
from typing import Any
from datetime import datetime, date

import aiomysql

# ── 配置文件路径 ────────────────────────────────────────────
# 统一使用 data/settings/db.yaml，测试与生产环境通过文件内容区分。
_CONFIG_NAME = "db.yaml"
CONFIG_PATH = Path(__file__).parent.parent.parent.parent / "data" / "settings" / _CONFIG_NAME

_config: dict[str, Any] | None = None


def _load_config() -> dict[str, Any]:
    """惰性加载数据库配置。支持环境变量覆盖数据库名。"""
    global _config
    if _config is not None:
        return _config
    try:
        with open(CONFIG_PATH, "r", encoding="utf-8") as f:
            _config = yaml.safe_load(f)
        if not _config or "mysql" not in _config:
            raise ValueError(f"{_CONFIG_NAME} 缺少必需的 'mysql' 配置节")
        # 环境变量覆盖数据库名（Docker 部署时使用）
        db_name_override = os.environ.get("DB_NAME", "").strip()
        if db_name_override:
            _config["mysql"]["database"] = db_name_override
        return _config
    except FileNotFoundError:
        raise FileNotFoundError(
            f"数据库配置文件未找到: {CONFIG_PATH}\n"
            f"请确保 {_CONFIG_NAME} 存在。可复制 db.yaml.example 并重命名。"
        ) from None
    except yaml.YAMLError as e:
        raise ValueError(f"数据库配置文件格式错误: {e}") from None


# ── 全局连接池（惰性创建，单例） ─────────────────────────────

_pool: aiomysql.Pool | None = None


async def _create_pool() -> aiomysql.Pool:
    """
    创建 MySQL 连接池。

    如果目标数据库不存在，尝试自动创建（需要 CREATE DATABASE 权限）。
    失败时给出明确的错误信息和修复建议。
    """
    _mysql = _load_config()["mysql"]
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
