"""SQLite 社交雷达动态记录与去重模块."""

import os
import sqlite3
from typing import Optional, Dict, Any, List
from datetime import datetime
from loguru import logger


class RadarStorage:
    """本地 SQLite 数据库管理，用于已爬取动态去重与历史记录."""

    def __init__(self, db_path: str = "data/social_radar.db"):
        self.db_path = db_path
        os.makedirs(os.path.dirname(os.path.abspath(db_path)), exist_ok=True)
        self._init_db()

    def _get_connection(self) -> sqlite3.Connection:
        conn = sqlite3.connect(self.db_path, timeout=20.0)
        conn.row_factory = sqlite3.Row
        return conn

    def _init_db(self):
        """初始化数据表."""
        with self._get_connection() as conn:
            cur = conn.cursor()
            cur.execute("""
            CREATE TABLE IF NOT EXISTS processed_items (
                item_id TEXT PRIMARY KEY,     -- 动态/回答唯一标识
                platform TEXT NOT NULL,       -- 'zhihu', 'x_twitter'
                item_type TEXT NOT NULL,       -- 'moment', 'question_answer', 'tweet'
                title TEXT,
                author TEXT,
                url TEXT,
                value_score INTEGER DEFAULT 0,
                is_notified INTEGER DEFAULT 0,
                core_insight TEXT,
                created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
            )
            """)
            cur.execute("""
            CREATE TABLE IF NOT EXISTS radar_chat_history (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                item_id TEXT NOT NULL,
                from_user TEXT,
                role TEXT NOT NULL,
                content TEXT NOT NULL,
                created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
            )
            """)
            cur.execute("CREATE INDEX IF NOT EXISTS idx_radar_platform ON processed_items(platform)")
            cur.execute("CREATE INDEX IF NOT EXISTS idx_radar_score ON processed_items(value_score)")
            cur.execute("CREATE INDEX IF NOT EXISTS idx_radar_created ON processed_items(created_at)")
            cur.execute("CREATE INDEX IF NOT EXISTS idx_radar_chat_id ON radar_chat_history(item_id)")
            conn.commit()
            logger.debug(f"[Storage] SQLite 数据库就绪: {self.db_path}")

    def is_processed(self, item_id: str) -> bool:
        """检查条目是否已处理过."""
        if not item_id:
            return False
        with self._get_connection() as conn:
            cur = conn.cursor()
            cur.execute("SELECT 1 FROM processed_items WHERE item_id = ?", (item_id,))
            return cur.fetchone() is not None

    def record_item(
        self,
        item_id: str,
        platform: str,
        item_type: str,
        title: str,
        author: str,
        url: str,
        value_score: int,
        is_notified: bool,
        core_insight: str = ""
    ):
        """记录已处理的动态."""
        with self._get_connection() as conn:
            cur = conn.cursor()
            cur.execute("""
            INSERT OR REPLACE INTO processed_items
            (item_id, platform, item_type, title, author, url, value_score, is_notified, core_insight, created_at)
            VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
            """, (
                item_id,
                platform,
                item_type,
                title,
                author,
                url,
                value_score,
                1 if is_notified else 0,
                core_insight,
                datetime.now().strftime("%Y-%m-%d %H:%M:%S")
            ))
            conn.commit()
    def add_chat_message(self, item_id: str, from_user: str, role: str, content: str):
        """记录动态追问历史."""
        with self._get_connection() as conn:
            cur = conn.cursor()
            cur.execute("""
            INSERT INTO radar_chat_history (item_id, from_user, role, content)
            VALUES (?, ?, ?, ?)
            """, (item_id, from_user, role, content))
            conn.commit()

    def get_chat_history(self, item_id: str, limit: int = 6) -> List[Dict[str, str]]:
        """获取指定动态的追问历史."""
        with self._get_connection() as conn:
            cur = conn.cursor()
            cur.execute("""
            SELECT role, content FROM radar_chat_history
            WHERE item_id = ?
            ORDER BY id ASC
            LIMIT ?
            """, (item_id, limit))
            return [{"role": r["role"], "content": r["content"]} for r in cur.fetchall()]
