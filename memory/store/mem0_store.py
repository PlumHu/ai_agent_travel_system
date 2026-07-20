"""
Mem0Store —— 可选混合记忆后端
==============================
把 Mem0（LLM 驱动的记忆抽取 + 向量存储 + 语义检索）作为存储后端接入。

核心裁决——结构化画像 vs Mem0 扁平记忆的阻抗失配：
  Mem0 只有扁平 memory 概念（add/search/get_all），没有 upsert-by-key、
  关系表、状态机。因此 Mem0Store 是【混合后端】：

    ┌──────────────────────────────────────────────┐
    │ Mem0Store                                     │
    │   ├── Mem0 client   → memories 片段 + 向量检索 │
    │   └── 内嵌 SqliteStore → 画像 / 行程 / 冲突    │
    └──────────────────────────────────────────────┘

  即 Mem0 只替换掉原来的 "ChromaDB + memories 表"，
  结构化数据（画像/行程/冲突）仍留 SQLite（精确 upsert / 排序 / 状态机）。

治理（重要性/衰减/冲突判断）仍在 MemoryEngine，Mem0 只作存储+检索后端。

依赖：pip install mem0ai。import 失败时构造抛异常，Facade 会降级 SqliteStore。
说明：切 Mem0 后端不迁移历史 ChromaDB 向量（新旧后端各自独立）。
"""
import logging
import os
from datetime import datetime
from pathlib import Path
from typing import Any, Dict, List, Optional

from memory.store.base import MemoryStore, MemoryId
from memory.store.sqlite_store import SqliteStore

logger = logging.getLogger(__name__)


def _default_mem0_config() -> Dict[str, Any]:
    """默认 Mem0 配置：DeepSeek（LLM）+ 本地 HF embedding + Chroma 向量库。"""
    return {
        "llm": {
            "provider": "openai",
            "config": {
                "model": os.getenv("DEEPSEEK_MODEL", "deepseek-chat"),
                "api_key": os.getenv("DEEPSEEK_API_KEY", ""),
                "openai_base_url": "https://api.deepseek.com",
                "temperature": 0.1,
            },
        },
        "embedder": {
            "provider": "huggingface",
            "config": {"model": os.getenv("EMBEDDING_MODEL", "BAAI/bge-small-zh-v1.5")},
        },
        "vector_store": {
            "provider": "chroma",
            "config": {"collection_name": "ltm_mem0", "path": "./memory/data/mem0_chroma"},
        },
    }


class Mem0Store(MemoryStore):
    """
    混合后端：Mem0 管记忆片段 + 向量检索，内嵌 SqliteStore 管画像/行程/冲突。
    """

    def __init__(
        self,
        user_id: str = "default",
        db_dir: Optional[Path] = None,
        mem0_config: Optional[Dict[str, Any]] = None,
    ):
        # Mem0 client（import 失败直接抛，让 Facade 降级）
        from mem0 import Memory as Mem0Memory  # noqa: F401
        self.user_id = user_id
        self._mem0 = Mem0Memory.from_config(mem0_config or _default_mem0_config())

        # 内嵌 SQLite：仅用其结构化部分（画像/行程/冲突）
        self._sql = SqliteStore(user_id=user_id, db_dir=db_dir, embedding_model=None)
        logger.info(f"[Mem0Store] 已初始化混合后端（Mem0 片段+向量 / SQLite 画像+行程+冲突）user={user_id}")

    # ── memories 片段 → Mem0 ─────────────────────────────────
    def add_memory(self, memory_type: str, content: str,
                   source: str = "", importance: int = 3) -> MemoryId:
        try:
            res = self._mem0.add(
                [{"role": "user", "content": content}],
                user_id=self.user_id,
                metadata={"memory_type": memory_type, "source": source,
                          "importance": importance,
                          "created_at": datetime.now().isoformat(),
                          "last_accessed_at": datetime.now().isoformat()},
            )
            # Mem0 返回结构含新建记忆 id（不同版本结构略异，尽力取 id）
            if isinstance(res, dict) and res.get("results"):
                return res["results"][0].get("id", "")
            return ""
        except Exception as e:
            logger.warning(f"[Mem0Store] add_memory 失败: {e}")
            return ""

    def all_memories(self) -> List[Dict[str, Any]]:
        try:
            res = self._mem0.get_all(user_id=self.user_id)
            items = res.get("results", res) if isinstance(res, dict) else res
            out = []
            for it in items or []:
                meta = it.get("metadata") or {}
                out.append({
                    "id": it.get("id"),
                    "memory_type": meta.get("memory_type", "preference"),
                    "content": it.get("memory") or it.get("content", ""),
                    "importance": meta.get("importance", 3),
                    "created_at": meta.get("created_at"),
                    "last_accessed_at": meta.get("last_accessed_at") or meta.get("created_at"),
                })
            return out
        except Exception as e:
            logger.warning(f"[Mem0Store] all_memories 失败: {e}")
            return []

    def search_memories_by_keyword(self, keywords: List[str], limit: int = 5) -> List[Dict[str, Any]]:
        # Mem0 用语义检索替代关键词（行为差异：语义相似而非子串匹配）
        query = " ".join(keywords)
        try:
            res = self._mem0.search(query, user_id=self.user_id, limit=limit)
            items = res.get("results", res) if isinstance(res, dict) else res
            return [{"id": it.get("id"),
                     "type": (it.get("metadata") or {}).get("memory_type", "preference"),
                     "content": it.get("memory") or it.get("content", ""),
                     "importance": (it.get("metadata") or {}).get("importance", 3)}
                    for it in (items or [])]
        except Exception as e:
            logger.warning(f"[Mem0Store] search 失败: {e}")
            return []

    def touch_memories(self, ids: List[MemoryId]) -> None:
        # Mem0 无 LRU 原语；此后端下 LRU 弱化为 no-op
        return

    def delete_memories(self, ids: List[MemoryId]) -> None:
        for mid in ids:
            try:
                self._mem0.delete(memory_id=mid)
            except Exception as e:
                logger.warning(f"[Mem0Store] delete {mid} 失败: {e}")

    def count_memories(self) -> int:
        return len(self.all_memories())

    def memory_exists_like(self, value: str) -> bool:
        # 语义相似判断（非子串），行为与 SQLite 略异但更合理
        try:
            res = self._mem0.search(value, user_id=self.user_id, limit=1)
            items = res.get("results", res) if isinstance(res, dict) else res
            return bool(items)
        except Exception:
            return False

    # ── 向量检索 → Mem0 ──────────────────────────────────────
    def add_vector(self, text: str, metadata: Dict[str, Any] = None) -> None:
        # Mem0 的 add 已内建向量化，无需单独存向量（对话片段已在 add_memory 入库）
        return

    def search_vector(self, query: str, top_k: int = 5) -> List[str]:
        try:
            res = self._mem0.search(query, user_id=self.user_id, limit=top_k)
            items = res.get("results", res) if isinstance(res, dict) else res
            return [(it.get("memory") or it.get("content", ""))[:100] for it in (items or [])]
        except Exception as e:
            logger.warning(f"[Mem0Store] search_vector 失败: {e}")
            return []

    def vector_available(self) -> bool:
        return True  # Mem0 内建向量检索

    # ── 结构化数据 → 内嵌 SQLite（直接委托）──────────────────
    def get_profile(self) -> Dict[str, str]:
        return self._sql.get_profile()

    def get_profile_value(self, key: str) -> Optional[str]:
        return self._sql.get_profile_value(key)

    def set_profile_value(self, key: str, value: str) -> None:
        self._sql.set_profile_value(key, value)

    def add_trip(self, destination: str, **kwargs) -> int:
        return self._sql.add_trip(destination, **kwargs)

    def get_trips(self, limit: int = 10) -> List[Dict[str, Any]]:
        return self._sql.get_trips(limit)

    def add_conflict(self, key: str, old_value: str, new_value: str) -> None:
        self._sql.add_conflict(key, old_value, new_value)

    def get_pending_conflicts(self) -> List[Dict[str, Any]]:
        return self._sql.get_pending_conflicts()

    def resolve_conflict(self, conflict_id: int) -> None:
        self._sql.resolve_conflict(conflict_id)

    def supersede_conflicts(self, key: str) -> None:
        self._sql.supersede_conflicts(key)

    # ── lifecycle ────────────────────────────────────────────
    def clear(self) -> None:
        self._sql.clear()
        try:
            self._mem0.delete_all(user_id=self.user_id)
        except Exception as e:
            logger.warning(f"[Mem0Store] Mem0 clear 失败: {e}")
