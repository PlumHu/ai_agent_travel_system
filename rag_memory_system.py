"""
RAG + Memory 完整实现
结合检索增强生成和记忆系统
"""
import os
from typing import List, Dict, Any, Optional
from datetime import datetime
from collections import deque
import json

# RAG 相关
try:
    import chromadb
    from sentence_transformers import SentenceTransformer
    CHROMADB_AVAILABLE = True
except ImportError:
    CHROMADB_AVAILABLE = False
    print("请安装: pip install chromadb sentence-transformers")


class RAGMemorySystem:
    """
    集成 RAG 和 Memory 的系统

    功能：
    1. RAG: 从向量数据库检索相关文档
    2. 短期记忆: 保存最近N轮对话
    3. 长期记忆: 保存用户偏好和重要事实
    """

    def __init__(
        self,
        collection_name: str = "travel_knowledge",
        persist_directory: str = "./chroma_db",
        short_memory_size: int = 10
    ):
        """
        初始化 RAG + Memory 系统

        Args:
            collection_name: ChromaDB 集合名称
            persist_directory: 数据库持久化目录
            short_memory_size: 短期记忆保存的对话轮数
        """
        # RAG: 向量数据库
        if CHROMADB_AVAILABLE:
            # 新版 chromadb：PersistentClient 自动持久化
            self.chroma_client = chromadb.PersistentClient(path=persist_directory)

            # 创建或获取集合
            self.collection = self.chroma_client.get_or_create_collection(
                name=collection_name
            )

            # Embedding 模型
            self.embedding_model = SentenceTransformer(
                'paraphrase-multilingual-MiniLM-L12-v2'  # 支持中文
            )
        else:
            self.collection = None
            self.embedding_model = None

        # Memory: 短期记忆 (最近N轮对话)
        self.short_memory = deque(maxlen=short_memory_size)

        # Memory: 长期记忆 (用户偏好、历史事实)
        self.long_memory = {
            "user_preferences": {},  # 用户偏好
            "visited_places": [],    # 去过的地方
            "important_facts": {}    # 重要事实
        }

        # 记忆文件路径
        self.memory_file = os.path.join(persist_directory, "long_memory.json")
        self._load_long_memory()

    # ==================== RAG 相关方法 ====================

    def add_documents(
        self,
        documents: List[str],
        metadatas: Optional[List[Dict]] = None,
        ids: Optional[List[str]] = None
    ):
        """
        添加文档到向量数据库

        Args:
            documents: 文档列表
            metadatas: 元数据列表（可选）
            ids: 文档ID列表（可选）
        """
        if not CHROMADB_AVAILABLE:
            print("ChromaDB 未安装，无法添加文档")
            return

        if ids is None:
            ids = [f"doc_{i}" for i in range(len(documents))]

        # 生成 embeddings
        embeddings = self.embedding_model.encode(documents).tolist()

        # 添加到数据库
        self.collection.add(
            documents=documents,
            embeddings=embeddings,
            metadatas=metadatas,
            ids=ids
        )

        print(f"✓ 添加 {len(documents)} 个文档到 RAG 知识库")

    def retrieve(
        self,
        query: str,
        top_k: int = 5
    ) -> List[Dict[str, Any]]:
        """
        检索相关文档

        Args:
            query: 查询文本
            top_k: 返回前K个结果

        Returns:
            List[Dict]: 相关文档列表
        """
        if not CHROMADB_AVAILABLE:
            return []

        # 空集合保护：无数据时直接返回，避免 chromadb 报错
        if self.collection.count() == 0:
            return []

        # 生成查询向量
        query_embedding = self.embedding_model.encode([query]).tolist()[0]

        # 检索（n_results 不超过实际条数）
        results = self.collection.query(
            query_embeddings=[query_embedding],
            n_results=min(top_k, self.collection.count())
        )

        # 格式化结果
        documents = []
        for i in range(len(results['documents'][0])):
            documents.append({
                "content": results['documents'][0][i],
                "metadata": results['metadatas'][0][i] if results['metadatas'] else {},
                "distance": results['distances'][0][i] if 'distances' in results else 0
            })

        return documents

    # ==================== Memory 相关方法 ====================

    def remember_conversation(
        self,
        user_message: str,
        assistant_message: str
    ):
        """
        保存对话到短期记忆

        Args:
            user_message: 用户消息
            assistant_message: 助手回复
        """
        self.short_memory.append({
            "user": user_message,
            "assistant": assistant_message,
            "timestamp": datetime.now().isoformat()
        })

    def get_recent_conversation(self, n: int = 5) -> List[Dict]:
        """
        获取最近N轮对话

        Args:
            n: 对话轮数

        Returns:
            List[Dict]: 最近的对话列表
        """
        return list(self.short_memory)[-n:]

    def remember_preference(self, key: str, value: Any):
        """
        保存用户偏好到长期记忆

        Args:
            key: 偏好键（如 "budget", "travel_style"）
            value: 偏好值
        """
        self.long_memory["user_preferences"][key] = value
        self._save_long_memory()

    def remember_visited_place(self, place: str, date: Optional[str] = None):
        """
        记录用户去过的地方

        Args:
            place: 地点名称
            date: 访问日期（可选）
        """
        self.long_memory["visited_places"].append({
            "place": place,
            "date": date or datetime.now().isoformat()
        })
        self._save_long_memory()

    def remember_fact(self, key: str, value: Any):
        """
        保存重要事实到长期记忆

        Args:
            key: 事实键
            value: 事实值
        """
        self.long_memory["important_facts"][key] = value
        self._save_long_memory()

    def get_user_preferences(self) -> Dict:
        """获取用户偏好"""
        return self.long_memory["user_preferences"]

    def get_visited_places(self) -> List[Dict]:
        """获取去过的地方"""
        return self.long_memory["visited_places"]

    # ==================== 上下文构建 ====================

    def build_context(
        self,
        query: str,
        include_rag: bool = True,
        include_short_memory: bool = True,
        include_long_memory: bool = True
    ) -> str:
        """
        构建完整上下文（RAG + Memory）

        Args:
            query: 用户查询
            include_rag: 是否包含 RAG 检索结果
            include_short_memory: 是否包含短期记忆
            include_long_memory: 是否包含长期记忆

        Returns:
            str: 格式化的上下文字符串
        """
        context_parts = []

        # 1. RAG: 检索相关文档
        if include_rag and CHROMADB_AVAILABLE:
            docs = self.retrieve(query, top_k=3)
            if docs:
                context_parts.append("【相关知识】")
                for i, doc in enumerate(docs, 1):
                    context_parts.append(f"{i}. {doc['content']}")
                context_parts.append("")

        # 2. 长期记忆: 用户偏好
        if include_long_memory:
            prefs = self.get_user_preferences()
            if prefs:
                context_parts.append("【用户偏好】")
                for key, value in prefs.items():
                    context_parts.append(f"- {key}: {value}")
                context_parts.append("")

            visited = self.get_visited_places()
            if visited:
                context_parts.append("【去过的地方】")
                for item in visited[-5:]:  # 最近5个
                    context_parts.append(f"- {item['place']} ({item['date']})")
                context_parts.append("")

        # 3. 短期记忆: 最近对话
        if include_short_memory:
            recent = self.get_recent_conversation(n=3)
            if recent:
                context_parts.append("【最近对话】")
                for conv in recent:
                    context_parts.append(f"用户: {conv['user']}")
                    context_parts.append(f"助手: {conv['assistant']}")
                context_parts.append("")

        # 4. 当前查询
        context_parts.append("【当前问题】")
        context_parts.append(query)

        return "\n".join(context_parts)

    # ==================== 持久化 ====================

    def _save_long_memory(self):
        """保存长期记忆到磁盘"""
        os.makedirs(os.path.dirname(self.memory_file), exist_ok=True)
        with open(self.memory_file, 'w', encoding='utf-8') as f:
            json.dump(self.long_memory, f, ensure_ascii=False, indent=2)

    def _load_long_memory(self):
        """从磁盘加载长期记忆"""
        if os.path.exists(self.memory_file):
            with open(self.memory_file, 'r', encoding='utf-8') as f:
                self.long_memory = json.load(f)

    def clear_short_memory(self):
        """清空短期记忆"""
        self.short_memory.clear()

    def clear_all_memory(self):
        """清空所有记忆（危险操作）"""
        self.short_memory.clear()
        self.long_memory = {
            "user_preferences": {},
            "visited_places": [],
            "important_facts": {}
        }
        self._save_long_memory()


# 示例使用
if __name__ == "__main__":
    print("=" * 60)
    print("RAG + Memory 系统测试")
    print("=" * 60)

    # 1. 初始化系统
    rag_memory = RAGMemorySystem()

    # 2. 添加旅游知识到 RAG
    documents = [
        "3月份适合去云南，气候宜人，春暖花开。",
        "3月份适合去江南水乡，油菜花盛开，风景如画。",
        "海南三亚全年都适合旅游，3月份人少价格低。",
        "西藏3月份开始进入旅游季，布达拉宫值得一去。"
    ]

    rag_memory.add_documents(
        documents=documents,
        metadatas=[{"source": "travel_guide"} for _ in documents]
    )

    # 3. 保存用户偏好到长期记忆
    rag_memory.remember_preference("budget", "5000元")
    rag_memory.remember_preference("travel_style", "自然风光")
    rag_memory.remember_visited_place("厦门", "2025-10-01")

    # 4. 模拟对话（短期记忆）
    rag_memory.remember_conversation(
        "我想去海边",
        "根据您的偏好，推荐海南三亚或福建厦门"
    )

    # 5. 构建完整上下文
    query = "3月份适合去哪里旅游？"
    context = rag_memory.build_context(query)

    print("\n构建的上下文:")
    print("-" * 60)
    print(context)

    print("\n" + "=" * 60)
    print("✓ RAG + Memory 系统测试完成")
    print("=" * 60)
