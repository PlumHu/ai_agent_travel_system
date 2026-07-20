"""
记忆存取抽象层（MemoryStore）
==============================
把记忆的"存取"与"治理"解耦：

- MemoryEngine 负责治理（抽取 / 冲突检测 / 重要性评分 / 衰减 / context 拼装）——source of truth
- MemoryStore  只负责存取（增删改查 + 向量索引 + 持久化）

本项目有 4 类异构数据 + 向量索引，故按数据类别分方法，而非硬塞单一 CRUD：
  - profile      : 用户画像 kv（upsert by key）
  - memories     : 记忆片段（append + 衰减 + LRU）
  - trips        : 历史行程（append-only）
  - conflicts    : 偏好冲突（resolved 状态机）
  - vector       : 语义检索索引

默认实现 SqliteStore（SQLite + ChromaDB）；Mem0Store 为可选后端
（Mem0 只接管"记忆片段 + 语义检索"，结构化画像/行程/冲突仍留 SQLite）。
"""
from abc import ABC, abstractmethod
from typing import Any, Dict, List, Optional, Union

MemoryId = Union[int, str]  # SqliteStore 用 int，Mem0Store 用 str uuid


class MemoryStore(ABC):
    """记忆存取抽象基类。只管存取，不含任何治理逻辑。"""

    # ── profile（画像 kv，按 key upsert）──────────────────────
    @abstractmethod
    def get_profile(self) -> Dict[str, str]:
        """返回完整用户画像字典。"""

    @abstractmethod
    def get_profile_value(self, key: str) -> Optional[str]:
        """读取单个画像字段（冲突检测读旧值用）。"""

    @abstractmethod
    def set_profile_value(self, key: str, value: str) -> None:
        """纯 upsert 画像字段，不含任何冲突逻辑（冲突判断在 Engine）。"""

    # ── memories（片段，append + 衰减 + LRU）──────────────────
    @abstractmethod
    def add_memory(self, memory_type: str, content: str,
                   source: str = "", importance: int = 3) -> MemoryId:
        """新增一条记忆片段，返回其 id。"""

    @abstractmethod
    def all_memories(self) -> List[Dict[str, Any]]:
        """返回全部记忆片段。每条含 id/importance/created_at/last_accessed_at（供 Engine 算衰减）。"""

    @abstractmethod
    def search_memories_by_keyword(self, keywords: List[str], limit: int = 5) -> List[Dict[str, Any]]:
        """关键词检索记忆片段（含召回后 LRU 刷新）。"""

    @abstractmethod
    def touch_memories(self, ids: List[MemoryId]) -> None:
        """刷新被召回记忆的 last_accessed_at（LRU）。"""

    @abstractmethod
    def delete_memories(self, ids: List[MemoryId]) -> None:
        """按 id 批量删除（衰减执行）。"""

    @abstractmethod
    def count_memories(self) -> int:
        """记忆片段总数。"""

    @abstractmethod
    def memory_exists_like(self, value: str) -> bool:
        """是否已存在含 value 的记忆（_score_importance 的"重复+1"判断）。"""

    # ── trips（历史行程，append-only）─────────────────────────
    @abstractmethod
    def add_trip(self, destination: str, days: int = None, budget: int = None,
                 start_date: str = None, end_date: str = None,
                 rating: int = None, notes: str = None) -> int:
        """记录一次行程，返回记录 id。"""

    @abstractmethod
    def get_trips(self, limit: int = 10) -> List[Dict[str, Any]]:
        """返回历史行程（最新在前）。"""

    # ── conflicts（偏好冲突，resolved 状态机）─────────────────
    @abstractmethod
    def add_conflict(self, key: str, old_value: str, new_value: str) -> None:
        """记录一条待确认冲突。"""

    @abstractmethod
    def get_pending_conflicts(self) -> List[Dict[str, Any]]:
        """返回所有 resolved=0 的冲突。"""

    @abstractmethod
    def resolve_conflict(self, conflict_id: int) -> None:
        """标记某条冲突已解决。"""

    @abstractmethod
    def supersede_conflicts(self, key: str) -> None:
        """把同 key 的旧未决冲突标记为已解决（只保留最新一条待确认）。"""

    # ── vector（语义检索）─────────────────────────────────────
    @abstractmethod
    def add_vector(self, text: str, metadata: Dict[str, Any] = None) -> None:
        """把文本向量化后存入索引（无向量能力时可 no-op）。"""

    @abstractmethod
    def search_vector(self, query: str, top_k: int = 5) -> List[str]:
        """语义检索，返回文本片段列表（无向量能力时返回空）。"""

    @abstractmethod
    def vector_available(self) -> bool:
        """向量检索是否可用（Engine 据此决定走向量还是关键词降级）。"""

    # ── lifecycle ────────────────────────────────────────────
    @abstractmethod
    def clear(self) -> None:
        """清空当前用户的所有数据。"""
