"""
智能推荐 Agent
支持双向推荐：
1. 正向：根据时间/节奏/偏好 → 推荐目的地
2. 反向：根据目的地/节假日/人流 → 推荐出行时间
"""
import json
import logging
from typing import Dict, Any, List
from datetime import datetime, timedelta

from langchain_core.messages import HumanMessage, SystemMessage
from langchain_core.messages import HumanMessage, SystemMessage

from agents.base_agent import BaseAgent
from state import AgentState
from config import OPENAI_API_KEY, OPENAI_API_BASE, OPENAI_MODEL, TEMPERATURE  # kept for compat
from knowledge.rag_manager import RAGManager

logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)


class RecommendAgent(BaseAgent):
    """智能推荐 Agent"""

    def __init__(self, long_term_memory=None, rag=None):
        super().__init__("RecommendAgent")
        self._rag = rag  # 惰性：首次检索时再创建
        self.long_term_memory = long_term_memory

    @property
    def rag(self):
        if self._rag is None:
            self._rag = RAGManager()
        return self._rag

    def execute(self, state: AgentState) -> AgentState:
        """执行推荐逻辑"""
        logger.info("=" * 50)
        logger.info("[Recommend Agent] 开始智能推荐")

        intent = state.get("intent", "recommend_destination")

        if intent == "recommend_time":
            # 反向推荐：推荐出行时间
            return self._recommend_time(state)
        else:
            # 正向推荐：推荐目的地
            return self._recommend_destination(state)

    def _recommend_destination(self, state: AgentState) -> AgentState:
        """
        正向推荐：根据时间/节奏/偏好推荐目的地
        """
        logger.info("[正向推荐] 根据用户需求推荐目的地")

        start_date = state.get("start_date")
        budget = state.get("budget")
        preferences = state.get("preferences", [])

        # 分析时间特征
        time_features = self._analyze_time_features(start_date)

        # 构造查询
        query_parts = []

        # 偏好
        if preferences:
            query_parts.append(" ".join(preferences))

        # 时间特征
        if time_features["season"]:
            query_parts.append(f"{time_features['season']}适合旅游")

        # 预算
        if budget:
            if budget < 3000:
                query_parts.append("经济实惠")
            elif budget > 8000:
                query_parts.append("高端度假")

        query = " ".join(query_parts) if query_parts else "旅游目的地推荐"

        # RAG 检索
        try:
            retrieved_docs = self.rag.retrieve(query, top_k=5)
            state["retrieved_docs"] = retrieved_docs
        except Exception as e:
            logger.warning(f"RAG 检索失败: {e}")
            retrieved_docs = []

        # 构造上下文
        context = "\n\n".join([
            f"选项 {i+1}: {doc['metadata']['destination']}\n{doc['text'][:500]}"
            for i, doc in enumerate(retrieved_docs[:3])
        ]) if retrieved_docs else "（暂无知识库参考）"

        # 从长期记忆获取用户画像
        mem_context = ""
        if self.long_term_memory is not None:
            try:
                mem_context = self.long_term_memory.get_memory_context(
                    query=f"{' '.join(preferences or [])} 旅游推荐"
                )
            except Exception as e:
                logger.warning(f"[RecommendAgent] 长期记忆读取失败: {e}")

        system_prompt = f"""你是一个专业的旅行规划师。
请根据用户的需求和时间特征，从知识库中推荐最合适的目的地。

**用户需求：**
- 出发时间：{start_date or "灵活"}
- 预算：{budget or "未指定"} 元
- 偏好：{", ".join(preferences) if preferences else "无特殊偏好"}
{"" if not mem_context else chr(10) + mem_context + chr(10)}
**时间特征分析：**
- 季节：{time_features["season"]}
- 月份：{time_features["month"]}
- 是否节假日：{time_features["is_holiday"]}
- 预计人流：{time_features["crowd_level"]}

**知识库参考：**
{context}

**输出要求：**
以 JSON 格式输出推荐结果，包含：
- recommendations: 推荐的目的地列表（3个）
- reasoning: 推荐理由

示例格式：
```json
{{
  "recommendations": [
    {{
      "destination": "大理",
      "score": 95,
      "reasons": ["春季气候宜人", "文化底蕴深厚", "预算适中"],
      "best_activities": ["洱海骑行", "古城漫步", "品尝白族美食"]
    }}
  ],
  "time_advice": "建议避开五一假期，选择4月下旬或5月中旬，人流较少",
  "budget_tips": "住宿选择民宿性价比高，餐饮人均50-80元"
}}
```
"""

        messages = [
            SystemMessage(content=system_prompt),
            HumanMessage(content="请为我推荐最合适的旅行目的地")
        ]

        try:
            response_text = self._invoke_with_fallback(messages, streaming=False)

            # 提取 JSON
            import re
            json_match = re.search(r'```(?:json)?\s*(\{.*?\})\s*```', response_text, re.DOTALL)
            if json_match:
                json_str = json_match.group(1)
            else:
                json_str = response_text.strip()

            recommendation = json.loads(json_str)
            state["destination_recommendation"] = recommendation

            logger.info(f"推荐了 {len(recommendation.get('recommendations', []))} 个目的地")

            state["current_step"] = "recommendation_completed"
            state["next_action"] = "output"
            state["error"] = None

        except Exception as e:
            logger.error(f"推荐失败: {e}")
            state["error"] = f"推荐失败: {str(e)}"
            state["next_action"] = "end"

        return state

    def _recommend_time(self, state: AgentState) -> AgentState:
        """
        反向推荐：根据目的地推荐最佳出行时间
        """
        logger.info("[反向推荐] 根据目的地推荐最佳出行时间")

        destination = state.get("destination")
        preferences = state.get("preferences", [])

        if not destination:
            state["error"] = "缺少目的地信息"
            return state

        # RAG 检索目的地信息
        try:
            retrieved_docs = self.rag.retrieve(f"{destination} 最佳旅行时间 节假日 人流", top_k=3)
            state["retrieved_docs"] = retrieved_docs
        except Exception as e:
            logger.warning(f"RAG 检索失败: {e}")
            retrieved_docs = []

        # 构造上下文
        context = "\n\n".join([
            doc['text'][:800]
            for doc in retrieved_docs
        ]) if retrieved_docs else "（暂无知识库参考）"

        # 从长期记忆获取用户偏好（历史行程 + 风格偏好）
        mem_context_time = ""
        if self.long_term_memory is not None:
            try:
                mem_context_time = self.long_term_memory.get_memory_context(
                    query=f"{destination} 最佳出行时间"
                )
            except Exception as e:
                logger.warning(f"[RecommendAgent] 长期记忆读取失败: {e}")

        system_prompt = f"""你是一个专业的旅行规划师。
请根据目的地特征和用户偏好，推荐最佳的出行时间。

**目的地：** {destination}

**用户偏好：**
{", ".join(preferences) if preferences else "无特殊偏好"}
{"" if not mem_context_time else chr(10) + mem_context_time + chr(10)}
**知识库参考：**
{context}

**分析维度：**
1. **气候/天气**：什么时间段天气最适宜？
2. **节假日与人流**：避开高峰期还是享受热闹？
3. **特殊活动/节日**：当地有哪些特色节庆？
4. **价格因素**：淡旺季价格差异

**输出要求：**
以 JSON 格式输出，包含：
- best_periods: 推荐的时间段（3个）
- avoid_periods: 不推荐的时间段
- festival_calendar: 当地节庆日历

示例格式：
```json
{{
  "best_periods": [
    {{
      "period": "3月-5月",
      "score": 95,
      "reasons": ["春季气候宜人", "花期正盛", "人流适中"],
      "weather": {{"avg_temp": "15-20°C", "condition": "晴朗少雨"}},
      "crowd_level": "中等",
      "price_level": "适中",
      "highlights": ["洱海樱花", "苍山杜鹃"]
    }}
  ],
  "avoid_periods": [
    {{
      "period": "7月-8月",
      "reasons": ["暑期高峰", "雨季", "价格高涨"]
    }}
  ],
  "festival_calendar": [
    {{
      "name": "三月街民族节",
      "date": "农历三月十五",
      "description": "白族最盛大的传统节日"
    }}
  ],
  "flexible_tips": "如果时间灵活，建议选择4月下旬或10月上旬，既避开高峰又能享受好天气"
}}
```
"""

        messages = [
            SystemMessage(content=system_prompt),
            HumanMessage(content=f"请推荐{destination}的最佳出行时间")
        ]

        try:
            response_text = self._invoke_with_fallback(messages, streaming=False)

            # 提取 JSON
            import re
            json_match = re.search(r'```(?:json)?\s*(\{.*?\})\s*```', response_text, re.DOTALL)
            if json_match:
                json_str = json_match.group(1)
            else:
                json_str = response_text.strip()

            time_recommendation = json.loads(json_str)
            state["time_recommendation"] = time_recommendation

            logger.info(f"推荐了 {len(time_recommendation.get('best_periods', []))} 个时间段")

            state["current_step"] = "time_recommendation_completed"
            state["next_action"] = "output"
            state["error"] = None

        except Exception as e:
            logger.error(f"时间推荐失败: {e}")
            state["error"] = f"时间推荐失败: {str(e)}"
            state["next_action"] = "end"

        return state

    def _analyze_time_features(self, start_date: str = None) -> Dict[str, Any]:
        """
        分析时间特征

        Args:
            start_date: 出发日期（YYYY-MM-DD）

        Returns:
            时间特征字典
        """
        if not start_date:
            return {
                "season": None,
                "month": None,
                "is_holiday": False,
                "crowd_level": "未知"
            }

        try:
            date = datetime.strptime(start_date, "%Y-%m-%d")
        except:
            return {
                "season": None,
                "month": None,
                "is_holiday": False,
                "crowd_level": "未知"
            }

        month = date.month

        # 季节判断
        if month in [3, 4, 5]:
            season = "春季"
        elif month in [6, 7, 8]:
            season = "夏季"
        elif month in [9, 10, 11]:
            season = "秋季"
        else:
            season = "冬季"

        # 节假日判断（简化版，实际应调用日历API）
        is_holiday = False
        crowd_level = "适中"

        if month in [1, 2]:  # 春节
            is_holiday = True
            crowd_level = "极高"
        elif month in [7, 8]:  # 暑假
            is_holiday = True
            crowd_level = "很高"
        elif month == 10 and 1 <= date.day <= 7:  # 国庆
            is_holiday = True
            crowd_level = "极高"
        elif month == 5 and 1 <= date.day <= 3:  # 五一
            is_holiday = True
            crowd_level = "很高"

        return {
            "season": season,
            "month": f"{month}月",
            "is_holiday": is_holiday,
            "crowd_level": crowd_level
        }

    def _extract_output(self, state: AgentState) -> Dict[str, Any]:
        """提取输出"""
        intent = state.get("intent")

        if intent == "recommend_time":
            return {
                "type": "time_recommendation",
                "destination": state.get("destination"),
                "recommendation": state.get("time_recommendation"),
                "error": state.get("error")
            }
        else:
            return {
                "type": "destination_recommendation",
                "recommendation": state.get("destination_recommendation"),
                "retrieved_docs": state.get("retrieved_docs"),
                "error": state.get("error")
            }


# 独立调用函数（兼容原有代码）
def recommend_agent(state: AgentState) -> AgentState:
    """LangGraph 节点函数"""
    agent = RecommendAgent()
    return agent.execute(state)


# ============ 测试示例 ============

if __name__ == "__main__":
    # 示例 1：正向推荐（推荐目的地）
    print("\n" + "=" * 60)
    print("示例 1：正向推荐 - 推荐目的地")
    print("=" * 60)

    agent = RecommendAgent()

    input_data1 = {
        "user_input": "我想春天去旅游，喜欢自然风光和美食",
        "start_date": "2026-04-15",
        "budget": 5000,
        "preferences": ["自然风光", "美食"],
        "intent": "recommend_destination"
    }

    result1 = agent.run_standalone(input_data1)

    if result1["success"]:
        print("\n✅ 推荐成功!")
        print(json.dumps(result1["data"], ensure_ascii=False, indent=2))

    # 示例 2：反向推荐（推荐时间）
    print("\n" + "=" * 60)
    print("示例 2：反向推荐 - 推荐出行时间")
    print("=" * 60)

    input_data2 = {
        "user_input": "三亚什么时候去最合适？人少、天气好",
        "destination": "三亚",
        "preferences": ["人少", "天气好"],
        "intent": "recommend_time"
    }

    result2 = agent.run_standalone(input_data2)

    if result2["success"]:
        print("\n✅ 推荐成功!")
        print(json.dumps(result2["data"], ensure_ascii=False, indent=2))
