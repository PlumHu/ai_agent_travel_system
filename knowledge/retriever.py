"""
混合检索器
支持向量检索和 BM25 检索的混合搜索
"""
import json
import logging
from typing import Dict, Any, List, Optional
from pathlib import Path

logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)


class HybridRetriever:
    """
    混合检索器
    结合向量检索（语义相似）和 BM25 检索（关键词匹配）
    """

    def __init__(
        self,
        vector_weight: float = 0.6,
        bm25_weight: float = 0.4,
        top_k: int = 5
    ):
        """
        初始化混合检索器

        Args:
            vector_weight: 向量检索权重
            bm25_weight: BM25 检索权重
            top_k: 返回结果数量
        """
        self.vector_weight = vector_weight
        self.bm25_weight = bm25_weight
        self.top_k = top_k

        # 向量检索器
        self.vector_retriever = None
        self._init_vector_retriever()

        # BM25 索引
        self.bm25_index = None
        self.documents = []

    def _init_vector_retriever(self):
        """初始化向量检索器"""
        try:
            from knowledge.rag_manager import RAGManager
            self.vector_retriever = RAGManager()
            logger.info("向量检索器初始化成功")
        except Exception as e:
            logger.warning(f"向量检索器初始化失败: {e}")

    def add_documents(self, documents: List[str], metadatas: List[Dict] = None):
        """
        添加文档到索引

        Args:
            documents: 文档列表
            metadatas: 元数据列表
        """
        if metadatas is None:
            metadatas = [{} for _ in documents]

        # 存储文档
        for i, doc in enumerate(documents):
            self.documents.append({
                "content": doc,
                "metadata": metadatas[i] if i < len(metadatas) else {}
            })

        # 添加到向量检索器
        if self.vector_retriever:
            try:
                self.vector_retriever.add_documents(documents, metadatas)
            except Exception as e:
                logger.warning(f"添加向量索引失败: {e}")

        # 构建 BM25 索引
        self._build_bm25_index()

        logger.info(f"添加了 {len(documents)} 个文档")

    def _build_bm25_index(self):
        """构建 BM25 索引"""
        try:
            # 简化的 BM25 实现
            # 实际项目中可以使用 rank_bm25 库
            self.bm25_index = {
                "documents": self.documents,
                "built": True
            }
            logger.info("BM25 索引构建完成")
        except Exception as e:
            logger.warning(f"BM25 索引构建失败: {e}")

    def retrieve(
        self,
        query: str,
        top_k: int = None
    ) -> List[Dict[str, Any]]:
        """
        混合检索

        Args:
            query: 查询文本
            top_k: 返回结果数量

        Returns:
            检索结果列表
        """
        if top_k is None:
            top_k = self.top_k

        logger.info(f"[HybridRetriever] 查询: {query}")

        # 1. 向量检索
        vector_results = []
        if self.vector_retriever:
            try:
                vector_results = self.vector_retriever.retrieve(query, top_k=top_k * 2)
                logger.info(f"向量检索返回 {len(vector_results)} 个结果")
            except Exception as e:
                logger.warning(f"向量检索失败: {e}")

        # 2. BM25 检索
        bm25_results = []
        if self.bm25_index:
            try:
                bm25_results = self._bm25_search(query, top_k * 2)
                logger.info(f"BM25 检索返回 {len(bm25_results)} 个结果")
            except Exception as e:
                logger.warning(f"BM25 检索失败: {e}")

        # 3. 融合结果
        merged_results = self._merge_results(vector_results, bm25_results)

        return merged_results[:top_k]

    def _bm25_search(self, query: str, top_k: int) -> List[Dict]:
        """BM25 检索（简化实现）"""
        if not self.documents:
            return []

        # 简化的关键词匹配
        query_terms = set(query.lower().split())
        results = []

        for doc in self.documents:
            content = doc["content"].lower()
            # 计算简单的匹配分数
            matches = sum(1 for term in query_terms if term in content)
            if matches > 0:
                score = matches / len(query_terms)
                results.append({
                    "content": doc["content"],
                    "metadata": doc["metadata"],
                    "score": score,
                    "source": "bm25"
                })

        # 按分数排序
        results.sort(key=lambda x: x["score"], reverse=True)
        return results[:top_k]

    def _merge_results(
        self,
        vector_results: List[Dict],
        bm25_results: List[Dict]
    ) -> List[Dict]:
        """融合向量和 BM25 结果"""
        # 使用倒排分数融合（RRF）
        merged = {}
        k = 60  # RRF 常数

        # 处理向量结果
        for i, result in enumerate(vector_results):
            content = result.get("content", "")[:100]  # 用前100字符作为键
            if content not in merged:
                merged[content] = {
                    "content": result.get("content", ""),
                    "metadata": result.get("metadata", {}),
                    "vector_rank": i + 1,
                    "bm25_rank": None,
                    "score": 0
                }
            merged[content]["vector_rank"] = i + 1

        # 处理 BM25 结果
        for i, result in enumerate(bm25_results):
            content = result.get("content", "")[:100]
            if content not in merged:
                merged[content] = {
                    "content": result.get("content", ""),
                    "metadata": result.get("metadata", {}),
                    "vector_rank": None,
                    "bm25_rank": i + 1,
                    "score": 0
                }
            merged[content]["bm25_rank"] = i + 1

        # 计算 RRF 分数
        for content, data in merged.items():
            vector_score = 1 / (k + (data["vector_rank"] or len(merged)))
            bm25_score = 1 / (k + (data["bm25_rank"] or len(merged)))

            data["score"] = (
                self.vector_weight * vector_score +
                self.bm25_weight * bm25_score
            )

        # 按分数排序
        results = list(merged.values())
        results.sort(key=lambda x: x["score"], reverse=True)

        return results


# 便捷函数
def hybrid_search(
    query: str,
    documents: List[str] = None,
    top_k: int = 5
) -> List[Dict]:
    """
    执行混合检索

    Args:
        query: 查询文本
        documents: 文档列表（可选，用于临时添加）
        top_k: 返回结果数量

    Returns:
        检索结果
    """
    retriever = HybridRetriever()

    if documents:
        retriever.add_documents(documents)

    return retriever.retrieve(query, top_k)


# 测试代码
if __name__ == "__main__":
    print("=" * 60)
    print("混合检索器测试")
    print("=" * 60)

    retriever = HybridRetriever(vector_weight=0.6, bm25_weight=0.4)

    # 添加测试文档
    test_docs = [
        "大理是云南著名的旅游城市，有美丽的洱海和苍山。",
        "丽江古城是世界文化遗产，以纳西族文化闻名。",
        "三亚位于海南岛南部，是热门的海滨度假胜地。",
        "大理的白族三道茶是当地特色文化体验。",
        "丽江玉龙雪山海拔4680米，是著名景点。"
    ]

    retriever.add_documents(test_docs)

    # 测试检索
    print("\n测试检索: '大理旅游'")
    results = retriever.retrieve("大理旅游", top_k=3)
    for i, r in enumerate(results):
        print(f"\n[{i+1}] 分数: {r['score']:.4f}")
        print(f"    内容: {r['content'][:50]}...")

    print("\n" + "=" * 60)
