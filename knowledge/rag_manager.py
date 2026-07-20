"""
RAG 管理器
负责构建和管理向量数据库（ChromaDB）

已适配 chromadb >= 0.4 新版 API（PersistentClient，自动持久化）。
Streamlit 热重载会反复构造 PersistentClient；同一 path 必须进程内单例，
否则会触发 SharedSystemClient KeyError / Event loop is closed。
"""
import json
import logging
import threading
from pathlib import Path
from typing import List, Dict, Any, Optional, TYPE_CHECKING

from config import VECTOR_DB_PATH, RAW_DATA_PATH, EMBEDDING_MODEL, TOP_K_RESULTS

if TYPE_CHECKING:
    from sentence_transformers import SentenceTransformer

logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

_CLIENT_LOCK = threading.Lock()
_CHROMA_CLIENTS: Dict[str, Any] = {}
_EMBEDDING_LOCK = threading.Lock()
_EMBEDDING_MODELS: Dict[str, Any] = {}


def _reset_chroma_shared_system(persist_directory: str) -> None:
    """清理 chromadb 进程内共享 System，便于重建 Client。"""
    try:
        from chromadb.api.shared_system_client import SharedSystemClient

        with SharedSystemClient._refcount_lock:
            SharedSystemClient._identifier_to_system.pop(persist_directory, None)
            SharedSystemClient._identifier_to_refcount.pop(persist_directory, None)
    except Exception as e:
        logger.warning(f"[RAG] 清理 Chroma SharedSystem 失败: {e}")
    _CHROMA_CLIENTS.pop(persist_directory, None)


def get_chroma_client(persist_directory: str):
    """按路径复用 PersistentClient，失败时重置共享状态并重试一次。"""
    import chromadb

    path = str(persist_directory)
    with _CLIENT_LOCK:
        cached = _CHROMA_CLIENTS.get(path)
        if cached is not None:
            return cached

        last_error: Optional[Exception] = None
        for attempt in range(2):
            try:
                client = chromadb.PersistentClient(path=path)
                _CHROMA_CLIENTS[path] = client
                return client
            except (KeyError, RuntimeError, ValueError) as e:
                last_error = e
                logger.warning(
                    f"[RAG] PersistentClient 失败 (attempt={attempt + 1}): {e}; 重置后重试"
                )
                _reset_chroma_shared_system(path)

        raise RuntimeError(
            f"无法创建 Chroma PersistentClient: {path}"
        ) from last_error


def get_embedding_model(model_name: str = EMBEDDING_MODEL):
    """进程内复用 Embedding 模型，避免重复加载。"""
    from sentence_transformers import SentenceTransformer

    with _EMBEDDING_LOCK:
        model = _EMBEDDING_MODELS.get(model_name)
        if model is None:
            logger.info(f"加载 Embedding 模型: {model_name}")
            model = SentenceTransformer(model_name)
            _EMBEDDING_MODELS[model_name] = model
        return model


_WARMUP_STARTED = False


def warmup_rag_in_background(persist_directory: Optional[str] = None) -> None:
    """后台预热 Chroma + Embedding，减少首次检索等待。"""
    global _WARMUP_STARTED
    if _WARMUP_STARTED:
        return
    _WARMUP_STARTED = True
    path = str(persist_directory or VECTOR_DB_PATH)

    def _run():
        try:
            logger.info("[RAG] 后台预热开始…")
            get_chroma_client(path)
            get_embedding_model(EMBEDDING_MODEL)
            # 触达集合，确保后续 retrieve 无冷启动
            client = get_chroma_client(path)
            client.get_or_create_collection(
                name="travel_knowledge",
                metadata={"hnsw:space": "cosine"},
            )
            logger.info("[RAG] 后台预热完成")
        except Exception as e:
            logger.warning(f"[RAG] 后台预热失败（不影响使用）: {e}")

    threading.Thread(target=_run, name="rag-warmup", daemon=True).start()


class RAGManager:
    """RAG 管理器：构建索引、检索文档（Chroma/Embedding 惰性加载，加快启动）"""

    def __init__(
        self,
        collection_name: str = "travel_knowledge",
        persist_directory: Optional[str] = None,
    ):
        """
        初始化 RAG 管理器

        Args:
            collection_name: ChromaDB 集合名称
            persist_directory: 持久化目录，默认用 config.VECTOR_DB_PATH
        """
        self.collection_name = collection_name
        self.persist_directory = str(persist_directory or VECTOR_DB_PATH)
        self._client = None
        self._embedding_model = None
        self._collection = None
        self._ready_logged = False

    @property
    def client(self):
        if self._client is None:
            self._client = get_chroma_client(self.persist_directory)
        return self._client

    @property
    def embedding_model(self):
        if self._embedding_model is None:
            self._embedding_model = get_embedding_model(EMBEDDING_MODEL)
        return self._embedding_model

    @property
    def collection(self):
        if self._collection is None:
            self._collection = self.client.get_or_create_collection(
                name=self.collection_name,
                metadata={"hnsw:space": "cosine"},
            )
            if not self._ready_logged:
                logger.info(
                    f"集合就绪: {self.collection_name}（已有 {self._collection.count()} 条）"
                )
                self._ready_logged = True
        return self._collection

    def add_documents(
        self,
        documents: List[str],
        metadatas: List[Dict[str, Any]] = None,
        ids: List[str] = None,
    ) -> int:
        """
        向集合添加文档（供 build_index / HybridRetriever 调用）。

        Args:
            documents: 文档文本列表
            metadatas: 元数据列表（可选）
            ids: 文档 id 列表（可选，缺省自动生成）

        Returns:
            实际添加的文档数
        """
        if not documents:
            return 0

        if metadatas is None:
            metadatas = [{} for _ in documents]
        if ids is None:
            base = self.collection.count()
            ids = [f"{self.collection_name}_{base + i}" for i in range(len(documents))]

        # 批量生成 embedding
        embeddings = [self.embedding_model.encode(t).tolist() for t in documents]

        self.collection.add(
            ids=ids,
            documents=documents,
            metadatas=metadatas,
            embeddings=embeddings,
        )
        logger.info(f"已添加 {len(documents)} 条文档到集合 {self.collection_name}")
        return len(documents)

    def build_index(self, force_rebuild: bool = False):
        """
        构建向量索引

        Args:
            force_rebuild: 是否强制重建索引
        """
        # 检查是否已有数据
        if self.collection.count() > 0 and not force_rebuild:
            logger.info(f"集合已有 {self.collection.count()} 条数据，跳过构建")
            return

        # 清空旧数据
        if force_rebuild:
            try:
                self.client.delete_collection(self.collection_name)
            except Exception:
                pass  # 集合不存在时忽略
            self.collection = self.client.get_or_create_collection(
                name=self.collection_name,
                metadata={"hnsw:space": "cosine"},
            )
            logger.info("强制重建：已清空旧数据")

        # 加载原始数据
        documents = self._load_raw_data()
        if not documents:
            logger.warning("未找到原始数据，跳过索引构建")
            return

        logger.info(f"开始构建索引，共 {len(documents)} 条文档")

        # 批量添加文档
        ids = []
        texts = []
        metadatas = []
        embeddings = []

        for i, doc in enumerate(documents):
            doc_id = f"doc_{i}"
            text = doc["text"]
            metadata = doc["metadata"]

            ids.append(doc_id)
            texts.append(text)
            metadatas.append(metadata)

            # 生成 Embedding
            embedding = self.embedding_model.encode(text).tolist()
            embeddings.append(embedding)

        # 添加到 ChromaDB（新版 PersistentClient 自动持久化，无需 persist()）
        self.collection.add(
            ids=ids,
            documents=texts,
            metadatas=metadatas,
            embeddings=embeddings
        )

        logger.info(f"索引构建完成，共 {len(documents)} 条文档")

    def _load_raw_data(self) -> List[Dict[str, Any]]:
        """
        加载原始 JSON 数据并转换为文档格式

        Returns:
            文档列表
        """
        documents = []
        destinations_dir = RAW_DATA_PATH / "destinations"

        if not destinations_dir.exists():
            logger.warning(f"目录不存在: {destinations_dir}")
            return documents

        for json_file in destinations_dir.glob("*.json"):
            try:
                with open(json_file, "r", encoding="utf-8") as f:
                    data = json.load(f)

                # 提取关键信息构建文档文本
                destination = data.get("destination", "未知")
                description = data.get("description", "")
                best_season = data.get("best_season", "")

                # 景点信息
                attractions_text = "\n".join([
                    f"- {attr['name']}: {attr['description']}"
                    for attr in data.get("attractions", [])
                ])

                # 美食信息
                food_text = "\n".join([
                    f"- {food['name']}: {food['description']}"
                    for food in data.get("food", [])
                ])

                # 构建完整文本
                full_text = f"""
目的地：{destination}
简介：{description}
最佳季节：{best_season}

主要景点：
{attractions_text}

特色美食：
{food_text}
                """.strip()

                documents.append({
                    "text": full_text,
                    "metadata": {
                        "source": str(json_file.name),
                        "destination": destination,
                        "region": data.get("region", ""),
                        "type": "destination_guide"
                    }
                })

                logger.info(f"加载文档: {json_file.name}")

            except Exception as e:
                logger.error(f"加载文件失败 {json_file}: {e}")

        return documents

    def retrieve(self, query: str, top_k: int = TOP_K_RESULTS) -> List[Dict[str, Any]]:
        """
        检索相关文档

        Args:
            query: 查询文本
            top_k: 返回结果数量

        Returns:
            检索结果列表
        """
        # 空集合直接返回，避免 chromadb 报错
        if self.collection.count() == 0:
            logger.warning(f"集合 {self.collection_name} 为空，无法检索")
            return []

        # 生成查询 Embedding
        query_embedding = self.embedding_model.encode(query).tolist()

        # 检索（n_results 不能超过集合实际条数）
        results = self.collection.query(
            query_embeddings=[query_embedding],
            n_results=min(top_k, self.collection.count())
        )

        # 格式化结果
        formatted_results = []
        if results and results["documents"]:
            for i in range(len(results["documents"][0])):
                formatted_results.append({
                    "id": results["ids"][0][i],
                    "text": results["documents"][0][i],
                    "metadata": results["metadatas"][0][i],
                    "score": results["distances"][0][i] if "distances" in results else None
                })

        logger.info(f"检索到 {len(formatted_results)} 条相关文档")
        return formatted_results


# 测试代码
if __name__ == "__main__":
    # 构建索引
    rag = RAGManager()
    rag.build_index(force_rebuild=True)

    # 测试检索
    results = rag.retrieve("我想去海边度假，有什么推荐？")
    for result in results:
        print(f"\n文档ID: {result['id']}")
        print(f"元数据: {result['metadata']}")
        print(f"内容预览: {result['text'][:100]}...")
