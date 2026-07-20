"""
离线索引构建脚本
用于构建向量数据库索引
"""
import json
import logging
import sys
from pathlib import Path
from typing import Dict, Any, List, Optional

# 确保项目根目录在 sys.path，使脚本直跑时能 import knowledge/config
_PROJECT_ROOT = Path(__file__).parent.parent
if str(_PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(_PROJECT_ROOT))

logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)


class IndexBuilder:
    """索引构建器"""

    def __init__(self, persist_directory: str = None):
        """
        初始化索引构建器

        Args:
            persist_directory: 索引持久化目录
        """
        if persist_directory is None:
            persist_directory = Path(__file__).parent / "vector_db"

        self.persist_directory = Path(persist_directory)
        self.persist_directory.mkdir(parents=True, exist_ok=True)

        logger.info(f"索引目录: {self.persist_directory}")

    def build_from_json_files(
        self,
        data_directory: str,
        collection_name: str = "travel_knowledge"
    ) -> Dict[str, Any]:
        """
        从 JSON 文件构建索引

        Args:
            data_directory: JSON 文件目录
            collection_name: 集合名称

        Returns:
            构建结果统计
        """
        logger.info(f"开始构建索引: {data_directory}")

        data_dir = Path(data_directory)
        if not data_dir.exists():
            logger.error(f"数据目录不存在: {data_dir}")
            return {"error": "数据目录不存在"}

        # 收集所有文档
        all_documents = []
        all_metadatas = []
        all_ids = []

        # 遍历 JSON 文件
        for json_file in data_dir.rglob("*.json"):
            try:
                with open(json_file, "r", encoding="utf-8") as f:
                    data = json.load(f)

                # 处理数据
                if isinstance(data, list):
                    for i, item in enumerate(data):
                        doc_text = self._extract_text(item)
                        if doc_text:
                            all_documents.append(doc_text)
                            all_metadatas.append({
                                "source": str(json_file),
                                "index": i,
                                **item.get("metadata", {})
                            })
                            all_ids.append(f"{json_file.stem}_{i}")
                elif isinstance(data, dict):
                    doc_text = self._extract_text(data)
                    if doc_text:
                        all_documents.append(doc_text)
                        all_metadatas.append({
                            "source": str(json_file),
                            **data.get("metadata", {})
                        })
                        all_ids.append(json_file.stem)

            except Exception as e:
                logger.error(f"处理文件失败 {json_file}: {e}")

        logger.info(f"收集了 {len(all_documents)} 个文档")

        # 构建向量索引
        if all_documents:
            try:
                self._build_vector_index(
                    documents=all_documents,
                    metadatas=all_metadatas,
                    ids=all_ids,
                    collection_name=collection_name
                )
            except Exception as e:
                logger.error(f"构建向量索引失败: {e}")

        return {
            "total_documents": len(all_documents),
            "collection_name": collection_name,
            "persist_directory": str(self.persist_directory)
        }

    def _extract_text(self, data: Dict) -> Optional[str]:
        """从数据中提取文本内容"""
        # 尝试多种文本字段
        text_fields = [
            "content", "text", "description", "body",
            "destination", "title", "summary"
        ]

        text_parts = []
        for field in text_fields:
            if field in data and data[field]:
                text_parts.append(str(data[field]))

        # 如果有更多字段，也添加进来
        if "features" in data:
            features = data["features"]
            if isinstance(features, list):
                text_parts.extend([f.get("name", "") for f in features])

        if "customs" in data:
            customs = data["customs"]
            if isinstance(customs, list):
                text_parts.extend([c.get("name", "") for c in customs])

        return " ".join(text_parts) if text_parts else None

    def _build_vector_index(
        self,
        documents: List[str],
        metadatas: List[Dict],
        ids: List[str],
        collection_name: str
    ):
        """构建向量索引"""
        try:
            from knowledge.rag_manager import RAGManager

            rag = RAGManager(
                collection_name=collection_name,
                persist_directory=str(self.persist_directory)
            )

            rag.add_documents(
                documents=documents,
                metadatas=metadatas,
                ids=ids
            )

            logger.info(f"向量索引构建完成: {collection_name}")

        except Exception as e:
            logger.warning(f"向量索引构建失败（{e}），降级保存为 JSON")
            # 保存为 JSON 文件作为后备
            self._save_as_json(documents, metadatas, ids, collection_name)

    def _save_as_json(
        self,
        documents: List[str],
        metadatas: List[Dict],
        ids: List[str],
        collection_name: str
    ):
        """保存为 JSON 文件"""
        data = []
        for i, doc in enumerate(documents):
            data.append({
                "id": ids[i] if i < len(ids) else f"doc_{i}",
                "content": doc,
                "metadata": metadatas[i] if i < len(metadatas) else {}
            })

        output_file = self.persist_directory / f"{collection_name}.json"
        with open(output_file, "w", encoding="utf-8") as f:
            json.dump(data, f, ensure_ascii=False, indent=2)

        logger.info(f"索引保存为 JSON: {output_file}")

    def build_sample_data(self):
        """构建示例数据索引"""
        logger.info("构建示例数据索引...")

        # 示例目的地数据
        sample_data = [
            {
                "destination": "大理",
                "content": "大理位于云南省西部，是著名的旅游城市。拥有美丽的洱海、苍山，以及历史悠久的古城。白族文化浓厚，三月街、火把节等传统节日吸引众多游客。",
                "metadata": {"type": "destination", "region": "云南"}
            },
            {
                "destination": "丽江",
                "content": "丽江是世界文化遗产古城，以纳西族东巴文化闻名。玉龙雪山、束河古镇、泸沽湖等景点备受游客喜爱。纳西古乐是文化瑰宝。",
                "metadata": {"type": "destination", "region": "云南"}
            },
            {
                "destination": "三亚",
                "content": "三亚位于海南岛南部，是中国著名的热带海滨旅游城市。亚龙湾、天涯海角、南山文化旅游区等景点闻名全国。适合冬季度假。",
                "metadata": {"type": "destination", "region": "海南"}
            }
        ]

        # 添加到索引
        documents = [d["content"] for d in sample_data]
        metadatas = [d["metadata"] for d in sample_data]
        ids = [d["destination"] for d in sample_data]

        self._build_vector_index(
            documents=documents,
            metadatas=metadatas,
            ids=ids,
            collection_name="sample_destinations"
        )

        logger.info("示例数据索引构建完成")

    def get_index_stats(self, collection_name: str = None) -> Dict:
        """获取索引统计信息"""
        stats = {
            "persist_directory": str(self.persist_directory),
            "collections": []
        }

        # 统计 JSON 文件
        for json_file in self.persist_directory.glob("*.json"):
            try:
                with open(json_file, "r", encoding="utf-8") as f:
                    data = json.load(f)
                stats["collections"].append({
                    "name": json_file.stem,
                    "file": str(json_file),
                    "document_count": len(data) if isinstance(data, list) else 1
                })
            except Exception as e:
                logger.warning(f"读取统计失败: {e}")

        return stats


# 主函数
def main():
    """主函数"""
    import argparse

    parser = argparse.ArgumentParser(description="构建向量索引")
    parser.add_argument("--data-dir", help="数据目录路径")
    parser.add_argument("--collection", default="travel_knowledge", help="集合名称")
    parser.add_argument("--sample", action="store_true", help="构建示例数据")
    parser.add_argument("--stats", action="store_true", help="显示索引统计")

    args = parser.parse_args()

    builder = IndexBuilder()

    if args.stats:
        stats = builder.get_index_stats()
        print(json.dumps(stats, ensure_ascii=False, indent=2))
        return

    if args.sample:
        builder.build_sample_data()
        return

    if args.data_dir:
        result = builder.build_from_json_files(args.data_dir, args.collection)
        print(json.dumps(result, ensure_ascii=False, indent=2))
    else:
        print("请指定 --data-dir 或使用 --sample 构建示例数据")


if __name__ == "__main__":
    main()
