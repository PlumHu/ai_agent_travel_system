"""
SqliteStore —— 默认记忆存取后端
================================
SQLite（4 表：user_profile / trip_history / memories / profile_conflicts）
+ ChromaDB（向量语义检索，可选）。

从原 LongTermMemory 的存取部分原样迁移，保留：
  - macOS 挂载目录 PRAGMA workaround
  - last_accessed_at 平滑升级（旧库兼容）
  - ChromaDB 延迟导入 + 失败降级
纯存取，不含任何治理逻辑（治理在 MemoryEngine）。
"""
import json
import logging
import sqlite3
from datetime import datetime
from pathlib import Path
from typing import Any, Dict, List, Optional

from memory.store.base import MemoryStore, MemoryId

logger = logging.getLogger(__name__)

_DEFAULT_DB_DIR = Path(__file__).parent.parent / "data"


class SqliteStore(MemoryStore):
    """SQLite + ChromaDB 存取实现。"""

    def __init__(
        self,
        user_id: str = "default",
        db_dir: Optional[Path] = None,
        embedding_model=None,
    ):
        self.user_id = user_id
        self.db_dir = Path(db_dir) if db_dir else _DEFAULT_DB_DIR
        self.db_dir.mkdir(parents=True, exist_ok=True)

        db_path = self.db_dir / f"memories_{user_id}.db"
        # timeout 避免 Streamlit 多会话抢锁时长时间卡住启动
        self.conn = sqlite3.connect(
            str(db_path), check_same_thread=False, timeout=1.0
        )
        self._init_tables()

        self._chroma_collection = None
        self._embedding_model = embedding_model
        if embedding_model is not None:
            self._init_chroma()

        logger.info(f"[SqliteStore] user={user_id}, db={db_path}")

    # ── 初始化 ────────────────────────────────────────────────
    def _init_tables(self) -> None:
        # macOS 挂载目录友好；不用 EXCLUSIVE，避免多进程/热重载互相堵死
        self.conn.execute("PRAGMA journal_mode=MEMORY")
        self.conn.execute("PRAGMA synchronous=OFF")
        self.conn.execute("PRAGMA busy_timeout=1000")
        tables = [
            """CREATE TABLE IF NOT EXISTS user_profile (
                key TEXT PRIMARY KEY, value TEXT NOT NULL, updated_at TEXT NOT NULL)""",
            """CREATE TABLE IF NOT EXISTS trip_history (
                id INTEGER PRIMARY KEY AUTOINCREMENT, destination TEXT NOT NULL,
                start_date TEXT, end_date TEXT, days INTEGER, budget INTEGER,
                rating INTEGER, notes TEXT, created_at TEXT NOT NULL)""",
            """CREATE TABLE IF NOT EXISTS memories (
                id INTEGER PRIMARY KEY AUTOINCREMENT, memory_type TEXT NOT NULL,
                content TEXT NOT NULL, source TEXT, importance INTEGER DEFAULT 3,
                created_at TEXT NOT NULL, updated_at TEXT NOT NULL)""",
            """CREATE TABLE IF NOT EXISTS profile_conflicts (
                id INTEGER PRIMARY KEY AUTOINCREMENT, key TEXT NOT NULL,
                old_value TEXT, new_value TEXT, resolved INTEGER DEFAULT 0,
                created_at TEXT NOT NULL)""",
        ]
        for stmt in tables:
            self.conn.execute(stmt)
        # 平滑升级：旧库补 last_accessed_at 列
        try:
            self.conn.execute("ALTER TABLE memories ADD COLUMN last_accessed_at TEXT")
            logger.info("[SqliteStore] memories 表已升级：新增 last_accessed_at 列")
        except sqlite3.OperationalError:
            pass
        self.conn.commit()

    def _init_chroma(self) -> None:
        try:
            import chromadb
            chroma_path = self.db_dir / "chroma_memory"
            client = chromadb.PersistentClient(path=str(chroma_path))
            self.chroma_client = client
            self._chroma_collection = client.get_or_create_collection(
                name=f"memory_{self.user_id}",
                metadata={"hnsw:space": "cosine"},
            )
            logger.info("[SqliteStore] ChromaDB 向量存储已启用")
        except Exception as e:
            logger.warning(f"[SqliteStore] ChromaDB 初始化失败，仅用 SQLite: {e}")
            self._chroma_collection = None

    # ── profile ──────────────────────────────────────────────
    def get_profile(self) -> Dict[str, str]:
        rows = self.conn.execute("SELECT key, value FROM user_profile").fetchall()
        return {r[0]: r[1] for r in rows}

    def get_profile_value(self, key: str) -> Optional[str]:
        row = self.conn.execute(
            "SELECT value FROM user_profile WHERE key = ?", (key,)
        ).fetchone()
        return row[0] if row else None

    def set_profile_value(self, key: str, value: str) -> None:
        self.conn.execute(
            """INSERT INTO user_profile (key, value, updated_at) VALUES (?, ?, ?)
               ON CONFLICT(key) DO UPDATE SET value=excluded.value, updated_at=excluded.updated_at""",
            (key, value, datetime.now().isoformat()),
        )
        self.conn.commit()

    # ── memories ─────────────────────────────────────────────
    def add_memory(self, memory_type: str, content: str,
                   source: str = "", importance: int = 3) -> MemoryId:
        now = datetime.now().isoformat()
        cur = self.conn.execute(
            """INSERT INTO memories
               (memory_type, content, source, importance, created_at, updated_at, last_accessed_at)
               VALUES (?, ?, ?, ?, ?, ?, ?)""",
            (memory_type, content, source, importance, now, now, now),
        )
        self.conn.commit()
        return cur.lastrowid

    def all_memories(self) -> List[Dict[str, Any]]:
        rows = self.conn.execute(
            "SELECT id, memory_type, content, importance, created_at, last_accessed_at FROM memories"
        ).fetchall()
        return [
            {"id": r[0], "memory_type": r[1], "content": r[2], "importance": r[3],
             "created_at": r[4], "last_accessed_at": r[5]}
            for r in rows
        ]

    def search_memories_by_keyword(self, keywords: List[str], limit: int = 5) -> List[Dict[str, Any]]:
        if not keywords:
            return []
        like_clause = " OR ".join(["content LIKE ?" for _ in keywords])
        params = [f"%{k}%" for k in keywords] + [limit]
        rows = self.conn.execute(
            f"SELECT id, memory_type, content, importance FROM memories "
            f"WHERE {like_clause} ORDER BY importance DESC, updated_at DESC LIMIT ?",
            params,
        ).fetchall()
        self.touch_memories([r[0] for r in rows])
        return [{"id": r[0], "type": r[1], "content": r[2], "importance": r[3]} for r in rows]

    def touch_memories(self, ids: List[MemoryId]) -> None:
        if not ids:
            return
        now = datetime.now().isoformat()
        try:
            self.conn.executemany(
                "UPDATE memories SET last_accessed_at = ? WHERE id = ?",
                [(now, mid) for mid in ids],
            )
            self.conn.commit()
        except Exception as e:
            logger.warning(f"[SqliteStore] 更新 last_accessed_at 失败: {e}")

    def delete_memories(self, ids: List[MemoryId]) -> None:
        if not ids:
            return
        self.conn.executemany("DELETE FROM memories WHERE id = ?", [(mid,) for mid in ids])
        self.conn.commit()

    def count_memories(self) -> int:
        return self.conn.execute("SELECT COUNT(*) FROM memories").fetchone()[0]

    def memory_exists_like(self, value: str) -> bool:
        row = self.conn.execute(
            "SELECT COUNT(*) FROM memories WHERE content LIKE ?", (f"%{value}%",)
        ).fetchone()
        return bool(row and row[0] > 0)

    # ── trips ────────────────────────────────────────────────
    def add_trip(self, destination: str, days: int = None, budget: int = None,
                 start_date: str = None, end_date: str = None,
                 rating: int = None, notes: str = None) -> int:
        cur = self.conn.execute(
            """INSERT INTO trip_history
               (destination, start_date, end_date, days, budget, rating, notes, created_at)
               VALUES (?, ?, ?, ?, ?, ?, ?, ?)""",
            (destination, start_date, end_date, days, budget, rating, notes,
             datetime.now().isoformat()),
        )
        self.conn.commit()
        logger.info(f"[SqliteStore] 行程已保存: {destination}")
        return cur.lastrowid

    def get_trips(self, limit: int = 10) -> List[Dict[str, Any]]:
        rows = self.conn.execute(
            "SELECT * FROM trip_history ORDER BY created_at DESC LIMIT ?", (limit,)
        ).fetchall()
        cols = ["id", "destination", "start_date", "end_date", "days",
                "budget", "rating", "notes", "created_at"]
        return [dict(zip(cols, r)) for r in rows]

    # ── conflicts ────────────────────────────────────────────
    def add_conflict(self, key: str, old_value: str, new_value: str) -> None:
        self.conn.execute(
            """INSERT INTO profile_conflicts (key, old_value, new_value, resolved, created_at)
               VALUES (?, ?, ?, 0, ?)""",
            (key, old_value, new_value, datetime.now().isoformat()),
        )
        self.conn.commit()

    def get_pending_conflicts(self) -> List[Dict[str, Any]]:
        rows = self.conn.execute(
            "SELECT id, key, old_value, new_value, created_at FROM profile_conflicts "
            "WHERE resolved = 0 ORDER BY created_at DESC"
        ).fetchall()
        return [
            {"id": r[0], "key": r[1], "old_value": r[2], "new_value": r[3], "created_at": r[4]}
            for r in rows
        ]

    def resolve_conflict(self, conflict_id: int) -> None:
        self.conn.execute(
            "UPDATE profile_conflicts SET resolved = 1 WHERE id = ?", (conflict_id,)
        )
        self.conn.commit()

    def supersede_conflicts(self, key: str) -> None:
        self.conn.execute(
            "UPDATE profile_conflicts SET resolved = 1 WHERE key = ? AND resolved = 0", (key,)
        )
        self.conn.commit()

    # ── vector ───────────────────────────────────────────────
    def add_vector(self, text: str, metadata: Dict[str, Any] = None) -> None:
        if self._chroma_collection is None or self._embedding_model is None:
            return
        try:
            embedding = self._embedding_model.encode(text).tolist()
            doc_id = f"{self.user_id}_{datetime.now().timestamp()}"
            self._chroma_collection.add(
                ids=[doc_id], embeddings=[embedding],
                documents=[text], metadatas=[metadata or {}],
            )
        except Exception as e:
            logger.warning(f"[SqliteStore] ChromaDB 写入失败: {e}")

    def search_vector(self, query: str, top_k: int = 5) -> List[str]:
        if self._chroma_collection is None or self._embedding_model is None:
            return []
        try:
            q_emb = self._embedding_model.encode(query).tolist()
            results = self._chroma_collection.query(
                query_embeddings=[q_emb],
                n_results=min(top_k, max(1, self._chroma_collection.count())),
            )
            docs = results.get("documents", [[]])[0]
            return [d[:100] for d in docs if d]
        except Exception as e:
            logger.warning(f"[SqliteStore] ChromaDB 检索失败: {e}")
            return []

    def vector_available(self) -> bool:
        return self._chroma_collection is not None and self._embedding_model is not None

    # ── lifecycle ────────────────────────────────────────────
    def clear(self) -> None:
        for t in ("user_profile", "trip_history", "memories", "profile_conflicts"):
            self.conn.execute(f"DELETE FROM {t}")
        self.conn.commit()
        if self._chroma_collection is not None:
            try:
                ids = self._chroma_collection.get()["ids"]
                if ids:
                    self._chroma_collection.delete(ids=ids)
            except Exception:
                pass
        logger.info(f"[SqliteStore] 用户 {self.user_id} 的记忆已清空")
