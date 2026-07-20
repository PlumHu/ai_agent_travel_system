"""
长期记忆模块（薄 Facade）
========================
本文件自 v1.7 起改为薄封装层，真正实现已拆分为：
  - memory/engine.py            MemoryEngine  —— 治理（抽取/冲突/重要性/衰减/context）
  - memory/store/base.py        MemoryStore   —— 存取抽象接口
  - memory/store/sqlite_store.py SqliteStore  —— 默认后端（SQLite + ChromaDB）
  - memory/store/mem0_store.py  Mem0Store     —— 可选后端（Mem0 管片段+向量，SQLite 管画像/行程/冲突）

LongTermMemory 保持原有公共 API 不变（向后兼容），内部委托给 Engine。
新增可选 backend 参数选择存储后端，默认 "sqlite"（行为与旧版完全一致）。

分层收益：治理逻辑唯一（不随后端重复），换存储后端不动业务代码。

典型用法（不变）：
    mem = LongTermMemory(user_id="user_001", llm=my_llm)
    mem.extract_and_save(user_msg, assistant_msg)
    context = mem.get_memory_context(query="大理旅游")
    conflicts = mem.get_pending_conflicts()
    mem.decay_memories()

用 Mem0 作后端（需 pip install mem0ai + key；失败自动降级 sqlite）：
    mem = LongTermMemory(user_id="u1", backend="mem0")
"""
import logging
from pathlib import Path
from typing import Any, Dict, List, Optional

from memory.engine import MemoryEngine

logger = logging.getLogger(__name__)


class LongTermMemory:
    """
    长期记忆管理器（Facade）。

    公共 API 与拆分前完全一致；内部委托 MemoryEngine + MemoryStore。
    """

    def __init__(
        self,
        user_id: str = "default",
        db_dir: Optional[Path] = None,
        embedding_model=None,
        max_context_items: int = 5,
        llm=None,
        backend: str = "sqlite",
        mem0_config: Optional[Dict[str, Any]] = None,
    ):
        """
        Args:
            user_id: 用户唯一标识，不同用户记忆隔离
            db_dir: 存储目录，默认 memory/data/
            embedding_model: SentenceTransformer 实例，用于向量检索（sqlite 后端）
            max_context_items: get_memory_context 语义检索返回上限
            llm: 可选 LangChain ChatLLM，用于 LLM 辅助实体提取
            backend: 存储后端，"sqlite"（默认）或 "mem0"
            mem0_config: mem0 后端配置（backend="mem0" 时用）
        """
        self.user_id = user_id
        store = self._build_store(backend, user_id, db_dir, embedding_model, mem0_config)
        # Mem0 后端下关闭容量上限，避免与 Mem0 自身记忆管理双重治理
        enforce_capacity = not isinstance(store, self._mem0_store_type())
        self._engine = MemoryEngine(
            store, user_id=user_id, llm=llm,
            max_context_items=max_context_items,
            enforce_capacity=enforce_capacity,
        )

    @staticmethod
    def _build_store(backend, user_id, db_dir, embedding_model, mem0_config):
        """构建存储后端，mem0 初始化失败时降级 sqlite。"""
        from memory.store.sqlite_store import SqliteStore
        if backend == "mem0":
            try:
                from memory.store.mem0_store import Mem0Store
                store = Mem0Store(user_id=user_id, db_dir=db_dir, mem0_config=mem0_config)
                logger.info("[LongTermMemory] 使用 Mem0 后端")
                return store
            except Exception as e:
                logger.warning(f"[LongTermMemory] Mem0 后端不可用，降级 sqlite: {e}")
        return SqliteStore(user_id=user_id, db_dir=db_dir, embedding_model=embedding_model)

    @staticmethod
    def _mem0_store_type():
        """返回 Mem0Store 类型用于 isinstance 判断（导入失败返回哨兵）。"""
        try:
            from memory.store.mem0_store import Mem0Store
            return Mem0Store
        except Exception:
            return type(None)  # 不会匹配任何真实 store

    # ── 公共 API：转发到 Engine / Store ──────────────────────
    def extract_and_save(self, user_message: str, assistant_message: str) -> Dict[str, Any]:
        return self._engine.extract_and_save(user_message, assistant_message)

    def get_memory_context(self, query: str = "") -> str:
        return self._engine.get_memory_context(query)

    def get_user_profile(self) -> Dict[str, str]:
        return self._engine.store.get_profile()

    def update_profile(self, key: str, value: str) -> None:
        """手动更新画像字段（含冲突检测）。"""
        self._engine.update_profile(key, value)

    def save_trip(self, destination: str, **kwargs) -> int:
        return self._engine.store.add_trip(destination, **kwargs)

    def get_trip_history(self, limit: int = 10) -> List[Dict]:
        return self._engine.store.get_trips(limit=limit)

    def save_important_fact(self, content: str, importance: int = 4) -> None:
        self._engine.store.add_memory("important_fact", content, importance=importance)

    def get_pending_conflicts(self) -> List[Dict[str, Any]]:
        return self._engine.store.get_pending_conflicts()

    def resolve_conflict(self, conflict_id: int) -> None:
        self._engine.store.resolve_conflict(conflict_id)

    def decay_memories(self) -> Dict[str, int]:
        return self._engine.decay_memories()

    def clear(self) -> None:
        self._engine.store.clear()

    # ── 兼容旧内部接口（被 tests/test_new_modules.py 直接调用）──
    def _update_profile(self, key: str, value: str) -> None:
        self._engine.update_profile(key, value)

    def _score_importance(self, entity_type: str, value: str, source_text: str) -> int:
        return self._engine.score_importance(entity_type, value, source_text)

    @property
    def conn(self):
        """暴露底层 SQLite 连接（仅 SqliteStore 后端；供旧测试/调试直连）。"""
        return getattr(self._engine.store, "conn", None)
