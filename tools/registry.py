"""
统一工具注册中心（ToolRegistry）
================================
消除项目中"独立函数 / 硬编码进 Agent / ReActAgent 私有注册表"三套并存的混乱，
提供一个集中的工具装配点，任何 Agent（固定 Pipeline 或 ReAct Loop）都从这里取工具。

核心概念：
  - ToolSpec        : 单个工具的规格（名称/函数/描述/参数schema），从 react_agent 上移至此作为通用单元
  - ToolRegistry    : 工具注册表，支持按名称/分类检索
  - build_default_registry() : 一处集中包装项目现有全部工具（懒加载 + 失败跳过）

设计原则：
  - 不改动任何现有工具函数本身，只做包装
  - 单个工具导入失败不影响其他（懒加载 + try/except）
  - 分类（category）便于 Agent 按需取子集（如只要 search 类）

使用方式：
    from tools.registry import build_default_registry

    registry = build_default_registry()
    all_tools = registry.all_specs()               # 全部工具
    search_tools = registry.get_by_category("search")  # 只要搜索类
    weather = registry.get("get_weather")          # 按名取单个
"""
import logging
from dataclasses import dataclass, field
from typing import Any, Callable, Dict, List, Optional

logger = logging.getLogger(__name__)


@dataclass
class ToolSpec:
    """
    工具规格：包装一个可调用函数，供 Agent（ReAct 循环等）调度。

    这是全项目统一的"工具单元"。ReActAgent 从 agents/react_agent.py re-export 本类，
    保持向后兼容。
    """
    name: str
    func: Callable
    description: str
    args_schema: Dict[str, str] = field(default_factory=dict)  # {参数名: 说明}
    categories: List[str] = field(default_factory=list)         # 分类标签

    def render(self) -> str:
        """渲染成 Prompt 中的工具描述（供 LLM 选择工具）"""
        args_desc = ", ".join(
            f"{k}（{v}）" for k, v in self.args_schema.items()
        ) or "无参数"
        return f"- {self.name}: {self.description} | 参数: {args_desc}"


class ToolRegistry:
    """
    工具注册中心。

    集中管理所有 ToolSpec，支持按名称和分类检索。
    """

    def __init__(self):
        self._tools: Dict[str, ToolSpec] = {}

    def register(self, spec: ToolSpec) -> None:
        """注册一个工具（重名覆盖并告警）"""
        if spec.name in self._tools:
            logger.warning(f"[ToolRegistry] 工具 '{spec.name}' 被重复注册，已覆盖")
        self._tools[spec.name] = spec

    def get(self, name: str) -> Optional[ToolSpec]:
        """按名称取单个工具"""
        return self._tools.get(name)

    def get_by_category(self, category: str) -> List[ToolSpec]:
        """按分类取工具子集"""
        return [s for s in self._tools.values() if category in s.categories]

    def all_specs(self) -> List[ToolSpec]:
        """返回全部工具"""
        return list(self._tools.values())

    def as_dict(self) -> Dict[str, ToolSpec]:
        """返回 {name: ToolSpec} 字典（供 ReActAgent 直接使用）"""
        return dict(self._tools)

    def names(self) -> List[str]:
        """返回所有工具名"""
        return list(self._tools.keys())

    def categories(self) -> List[str]:
        """返回所有出现过的分类"""
        cats = set()
        for s in self._tools.values():
            cats.update(s.categories)
        return sorted(cats)

    def __len__(self) -> int:
        return len(self._tools)


def build_default_registry() -> ToolRegistry:
    """
    构建项目默认工具注册表。

    这是全项目**唯一的工具装配点**：集中包装现有工具函数。
    每个工具懒加载（import 放在 try 内），单个失败只跳过该工具、不影响其他。

    Returns:
        装配好的 ToolRegistry
    """
    registry = ToolRegistry()

    # ── 天气 ──
    try:
        from tools.utility.weather import get_weather
        registry.register(ToolSpec(
            name="get_weather",
            func=get_weather,
            description="查询指定城市的天气信息",
            args_schema={"city": "城市名称"},
            categories=["weather", "realtime"],
        ))
    except Exception as e:
        logger.warning(f"[ToolRegistry] 加载 get_weather 失败: {e}")

    # ── 实时搜索（一等公民，优先于普通 web_search）──
    try:
        from tools.utility.realtime_search import realtime_search
        registry.register(ToolSpec(
            name="realtime_search",
            func=realtime_search,
            description="实时联网搜索最新信息（机票价格/景点开放/临时管制等时效性内容），结果带时间戳",
            args_schema={"query": "搜索关键词", "freshness": "时效要求 recent/day/any（可选）"},
            categories=["search", "realtime"],
        ))
    except Exception as e:
        logger.warning(f"[ToolRegistry] 加载 realtime_search 失败: {e}")

    # ── 普通搜索（免费兜底）──
    try:
        from tools.utility.free_search import search_with_fallback
        registry.register(ToolSpec(
            name="web_search",
            func=search_with_fallback,
            description="联网搜索一般信息（攻略/资讯），免费但时效性弱于 realtime_search",
            args_schema={"query": "搜索关键词"},
            categories=["search"],
        ))
    except Exception as e:
        logger.warning(f"[ToolRegistry] 加载 web_search 失败: {e}")

    # ── 攻略 ──
    try:
        from tools.content.search_guides import search_travel_guides
        registry.register(ToolSpec(
            name="search_guides",
            func=search_travel_guides,
            description="查询目的地旅游攻略（本地知识库优先，未命中则联网）",
            args_schema={"destination": "目的地名称"},
            categories=["content"],
        ))
    except Exception as e:
        logger.warning(f"[ToolRegistry] 加载 search_guides 失败: {e}")

    # ── 机票 ──
    try:
        from tools.transaction.flights import search_flights
        registry.register(ToolSpec(
            name="search_flights",
            func=search_flights,
            description="搜索航班信息",
            args_schema={"departure": "出发城市", "arrival": "到达城市", "date": "出发日期(可选)"},
            categories=["transaction", "realtime"],
        ))
    except Exception as e:
        logger.warning(f"[ToolRegistry] 加载 search_flights 失败: {e}")

    # ── 酒店 ──
    try:
        from tools.transaction.hotels import search_hotels
        registry.register(ToolSpec(
            name="search_hotels",
            func=search_hotels,
            description="搜索酒店信息",
            args_schema={"destination": "目的地", "check_in": "入住日期(可选)", "check_out": "离店日期(可选)"},
            categories=["transaction", "realtime"],
        ))
    except Exception as e:
        logger.warning(f"[ToolRegistry] 加载 search_hotels 失败: {e}")

    # ── 门票/活动 ──
    try:
        from tools.transaction.tickets import search_tickets
        registry.register(ToolSpec(
            name="search_tickets",
            func=search_tickets,
            description="搜索景点门票和活动",
            args_schema={"destination": "目的地", "attraction": "景点名称(可选)"},
            categories=["transaction"],
        ))
    except Exception as e:
        logger.warning(f"[ToolRegistry] 加载 search_tickets 失败: {e}")

    # ── 过敏原检测（健康，本地无需 API）──
    try:
        from tools.health.allergen_check import check_food_allergens
        registry.register(ToolSpec(
            name="check_food_allergens",
            func=check_food_allergens,
            description="检测食物中的过敏原",
            args_schema={"food_name": "食物名称", "user_allergies": "用户过敏列表(可选)"},
            categories=["health"],
        ))
    except Exception as e:
        logger.warning(f"[ToolRegistry] 加载 check_food_allergens 失败: {e}")

    # ── 药物-食物相互作用（健康，本地无需 API）──
    try:
        from tools.health.drug_interaction_check import check_drug_interactions
        # 该函数用 @tool 装饰，取其底层函数以便直接调用
        _drug_func = getattr(check_drug_interactions, "func", check_drug_interactions)
        registry.register(ToolSpec(
            name="check_drug_interactions",
            func=_drug_func,
            description="检查药物与食物/酒精的危险相互作用（如头孢+酒精）",
            args_schema={"medications": "药物列表", "planned_foods": "计划食用的食物列表"},
            categories=["health"],
        ))
    except Exception as e:
        logger.warning(f"[ToolRegistry] 加载 check_drug_interactions 失败: {e}")

    # ── RAG 知识库检索 ──
    try:
        from knowledge.rag_manager import RAGManager
        _rag = RAGManager()
        registry.register(ToolSpec(
            name="rag_retrieve",
            func=lambda query: str(_rag.retrieve(query, top_k=3)),
            description="从本地知识库检索目的地攻略/景点/美食",
            args_schema={"query": "检索关键词"},
            categories=["content", "knowledge"],
        ))
    except Exception as e:
        logger.warning(f"[ToolRegistry] 加载 rag_retrieve 失败: {e}")

    logger.info(
        f"[ToolRegistry] 默认注册表构建完成，共 {len(registry)} 个工具: {registry.names()}"
    )
    return registry


# 全局单例（懒加载）
_default_registry: Optional[ToolRegistry] = None


def get_default_registry() -> ToolRegistry:
    """获取全局默认注册表单例"""
    global _default_registry
    if _default_registry is None:
        _default_registry = build_default_registry()
    return _default_registry
