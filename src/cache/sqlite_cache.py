"""
SQLite 持久化缓存
用于存储 API 响应数据，避免重复请求

自动清理机制：
- 启动时清理过期缓存
- 每 100 次 get() 调用时清理一次
- 过期数据读取时立即删除
"""

import sqlite3
import json
import time
import os
from typing import Any, Dict, Optional
from src.utils.logger import get_logger

logger = get_logger(__name__)


class SQLiteCache:
    """SQLite 缓存管理器"""

    def __init__(self, db_path: str = "./data/cache/financial_cache.db", ttl_hours: int = 24):
        self.db_path = db_path
        self.ttl_seconds = ttl_hours * 3600
        self._get_count = 0  # get() 调用计数器
        self._init_db()
        self.clear_expired()  # 启动时清理过期缓存

    def _init_db(self):
        """初始化数据库表"""
        os.makedirs(os.path.dirname(self.db_path), exist_ok=True)
        conn = sqlite3.connect(self.db_path)
        try:
            conn.execute("""
                CREATE TABLE IF NOT EXISTS cache (
                    key TEXT PRIMARY KEY,
                    value TEXT NOT NULL,
                    created_at REAL NOT NULL,
                    expires_at REAL NOT NULL,
                    metadata TEXT
                )
            """)
            conn.execute("""
                CREATE INDEX IF NOT EXISTS idx_expires_at ON cache(expires_at)
            """)
            conn.commit()
        finally:
            conn.close()

    def get(self, key: str) -> Optional[Any]:
        """获取缓存值，过期返回 None"""
        self._get_count += 1

        # 每 100 次调用清理一次过期缓存
        if self._get_count % 100 == 0:
            self.clear_expired()

        conn = sqlite3.connect(self.db_path)
        try:
            cursor = conn.execute(
                "SELECT value, expires_at FROM cache WHERE key = ?", (key,)
            )
            row = cursor.fetchone()
            if row is None:
                return None

            value_str, expires_at = row
            if time.time() > expires_at:
                conn.execute("DELETE FROM cache WHERE key = ?", (key,))
                conn.commit()
                logger.debug(f"缓存过期: {key}")
                return None

            logger.debug(f"缓存命中: {key}")
            return json.loads(value_str)
        finally:
            conn.close()

    def set(self, key: str, value: Any, metadata: Optional[Dict] = None, ttl_seconds: int = None):
        """设置缓存值，支持自定义 TTL"""
        now = time.time()
        expires_at = now + (ttl_seconds or self.ttl_seconds)
        value_str = json.dumps(value, ensure_ascii=False, default=str)
        metadata_str = json.dumps(metadata, ensure_ascii=False) if metadata else None

        conn = sqlite3.connect(self.db_path)
        try:
            conn.execute(
                """INSERT OR REPLACE INTO cache (key, value, created_at, expires_at, metadata)
                   VALUES (?, ?, ?, ?, ?)""",
                (key, value_str, now, expires_at, metadata_str),
            )
            conn.commit()
            logger.debug(f"缓存写入: {key}")
        finally:
            conn.close()

    def delete(self, key: str):
        """删除缓存"""
        conn = sqlite3.connect(self.db_path)
        try:
            conn.execute("DELETE FROM cache WHERE key = ?", (key,))
            conn.commit()
        finally:
            conn.close()

    def clear_expired(self):
        """清理所有过期缓存"""
        conn = sqlite3.connect(self.db_path)
        try:
            cursor = conn.execute(
                "DELETE FROM cache WHERE expires_at < ?", (time.time(),)
            )
            conn.commit()
            count = cursor.rowcount
            if count > 0:
                logger.info(f"自动清理 {count} 条过期缓存")
        finally:
            conn.close()

    def clear_all(self):
        """清空所有缓存"""
        conn = sqlite3.connect(self.db_path)
        try:
            conn.execute("DELETE FROM cache")
            conn.commit()
            logger.info("已清空所有缓存")
        finally:
            conn.close()

    def get_stats(self) -> Dict[str, Any]:
        """获取缓存统计"""
        conn = sqlite3.connect(self.db_path)
        try:
            total = conn.execute("SELECT COUNT(*) FROM cache").fetchone()[0]
            expired = conn.execute(
                "SELECT COUNT(*) FROM cache WHERE expires_at < ?", (time.time(),)
            ).fetchone()[0]
            # 获取数据库文件大小
            db_size = os.path.getsize(self.db_path) if os.path.exists(self.db_path) else 0
            return {
                "total": total,
                "expired": expired,
                "active": total - expired,
                "db_size_mb": round(db_size / 1024 / 1024, 2),
            }
        finally:
            conn.close()


# 全局缓存实例
_cache: Optional[SQLiteCache] = None


def get_cache(db_path: str = None) -> SQLiteCache:
    """获取全局缓存实例"""
    global _cache
    if _cache is None:
        from src.config import get_config
        config = get_config()
        path = db_path or config.cache.sqlite_db_path
        _cache = SQLiteCache(db_path=path, ttl_hours=config.cache.cache_ttl_hours)
    return _cache
