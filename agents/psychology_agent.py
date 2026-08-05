"""
心理健康 Agent

功能：
1. 旅行心理健康评估（规则打分）
2. 压力与疲劳度分析
3. 心理调适建议
4. 情绪管理指导
5. RAG 检索心理专业知识（psychology_knowledge 知识库），注入 LLM 生成个性化建议

RAG 说明：规则评分作为兜底始终执行；知识库检索到内容时注入 Prompt 增强专业性，
检索为空或失败时不影响运行。
"""

from typing import Dict, Any, List
from agents.base_agent import BaseAgent
from llm_config import create_llm_from_env


class PsychologyAgent(BaseAgent):
    """心理健康 Agent（规则评分 + RAG 增强）"""

    def __init__(self, llm_provider: str = None, rag=None):
        """
        初始化 PsychologyAgent

        Args:
            llm_provider: LLM 提供商（deepseek/openai/nvidia/custom）
            rag: 可选的共享 RAGManager（psychology_knowledge 集合）
        """
        super().__init__("PsychologyAgent")
        self._llm = None
        self._llm_provider = llm_provider
        self._rag = rag
        self._rag_init_attempted = rag is not None

    @property
    def llm(self):
        if self._llm is None and not self._llm_provider:
            self._llm = create_llm_from_env()
        return self._llm

    @property
    def rag(self):
        if self._rag is None and not self._rag_init_attempted:
            self._rag_init_attempted = True
            try:
                from knowledge.rag_manager import RAGManager
                self._rag = RAGManager(collection_name="psychology_knowledge")
            except Exception as e:
                self.logger.warning(f"[PsychologyAgent] 心理知识库不可用，仅用规则: {e}")
                self._rag = None
        return self._rag

    def execute(self, state: Dict[str, Any]) -> Dict[str, Any]:
        """执行入口（实现 BaseAgent 抽象方法）：准备状态 → 分析"""
        state = self._enrich_state(state)
        return self._execute_task(state)

    def _enrich_state(self, state: Dict[str, Any]) -> Dict[str, Any]:
        """准备状态（勿覆盖 BaseAgent._prepare_state）"""
        if not state.get("destination"):
            inferred = self.infer_destination(state.get("user_input", ""))
            if inferred:
                state["destination"] = inferred
            else:
                state["error"] = "缺少目的地信息"

        if not state.get("travel_days"):
            state["travel_days"] = 5  # 默认5天

        if not state.get("travel_style"):
            state["travel_style"] = "休闲"  # 休闲/紧凑/探险

        if not state.get("group_type"):
            state["group_type"] = "独自"  # 独自/情侣/家庭/朋友

        return state

    def _execute_task(self, state: Dict[str, Any]) -> Dict[str, Any]:
        """执行心理健康分析"""
        if state.get("error"):
            return state

        destination = state["destination"]
        travel_days = state["travel_days"]
        travel_style = state.get("travel_style", "休闲")
        group_type = state.get("group_type", "独自")

        # 1. 心理健康评估
        mental_assessment = self._assess_mental_health(
            destination, travel_days, travel_style, group_type
        )

        # 2. 压力与疲劳度分析
        stress_analysis = self._analyze_stress_fatigue(
            travel_days, travel_style, state.get("daily_plan", [])
        )

        # 3. 生成心理调适建议
        mental_tips = self._generate_mental_tips(
            mental_assessment, stress_analysis, group_type
        )

        # 4. 情绪管理指导
        emotion_guidance = self._generate_emotion_guidance(
            destination, travel_style, mental_assessment
        )

        # 5. LLM 生成个性化建议
        personalized_advice = self._generate_personalized_advice(
            destination, travel_days, mental_assessment, stress_analysis
        )

        state["mental_assessment"] = mental_assessment
        state["stress_analysis"] = stress_analysis
        state["mental_tips"] = mental_tips
        state["emotion_guidance"] = emotion_guidance
        state["personalized_advice"] = personalized_advice

        return state

    def _extract_output(self, state: Dict[str, Any]) -> Dict[str, Any]:
        """提取输出"""
        return {
            "mental_assessment": state.get("mental_assessment", {}),
            "stress_analysis": state.get("stress_analysis", {}),
            "mental_tips": state.get("mental_tips", []),
            "emotion_guidance": state.get("emotion_guidance", []),
            "personalized_advice": state.get("personalized_advice", ""),
            "error": state.get("error")
        }

    def _assess_mental_health(
        self,
        destination: str,
        travel_days: int,
        travel_style: str,
        group_type: str
    ) -> Dict[str, Any]:
        """心理健康评估"""
        assessment = {
            "overall_score": 0,  # 总体健康分数（0-100）
            "stress_level": "低",  # 压力水平：低/中/高
            "relaxation_potential": 0,  # 放松潜力（0-10）
            "social_support": 0,  # 社交支持（0-10）
            "risk_factors": [],  # 风险因素
            "protective_factors": []  # 保护因素
        }

        # 基于旅行天数评估
        if travel_days <= 3:
            assessment["stress_level"] = "中"
            assessment["relaxation_potential"] = 6
            assessment["risk_factors"].append("旅行时间较短，可能行程紧张")
        elif travel_days <= 7:
            assessment["stress_level"] = "低"
            assessment["relaxation_potential"] = 8
            assessment["protective_factors"].append("适中的旅行时长，有充足放松时间")
        else:
            assessment["stress_level"] = "低"
            assessment["relaxation_potential"] = 9
            assessment["protective_factors"].append("长途旅行，有足够时间深度放松")
            assessment["risk_factors"].append("长途旅行需注意疲劳累积")

        # 基于旅行风格评估
        style_scores = {
            "休闲": 9,
            "紧凑": 4,
            "探险": 6,
            "文化": 7,
            "购物": 5
        }
        assessment["relaxation_potential"] = style_scores.get(travel_style, 7)

        if travel_style == "紧凑":
            assessment["stress_level"] = "高"
            assessment["risk_factors"].append("行程安排紧凑，可能导致疲劳")
        elif travel_style == "探险":
            assessment["stress_level"] = "中"
            assessment["risk_factors"].append("探险活动有一定压力")
            assessment["protective_factors"].append("新鲜刺激有助于心理健康")

        # 基于同行人群评估
        group_scores = {
            "独自": 5,
            "情侣": 8,
            "家庭": 7,
            "朋友": 9
        }
        assessment["social_support"] = group_scores.get(group_type, 6)

        if group_type == "独自":
            assessment["risk_factors"].append("独自旅行可能感到孤独")
            assessment["protective_factors"].append("独处时间有助于自我反思")
        elif group_type == "朋友":
            assessment["protective_factors"].append("朋友陪伴提供良好社交支持")

        # 计算总体分数
        score = (
            assessment["relaxation_potential"] * 4 +
            assessment["social_support"] * 3 +
            (10 - len(assessment["risk_factors"]) * 2) * 3
        )
        assessment["overall_score"] = min(100, max(0, score))

        return assessment

    def _analyze_stress_fatigue(
        self,
        travel_days: int,
        travel_style: str,
        daily_plan: List[Dict]
    ) -> Dict[str, Any]:
        """压力与疲劳度分析"""
        analysis = {
            "fatigue_curve": [],  # 疲劳度曲线（每天）
            "peak_stress_days": [],  # 压力高峰日
            "rest_days": [],  # 休息日
            "cumulative_fatigue": 0,  # 累积疲劳度
            "recovery_time": 0  # 恢复时间（天）
        }

        # 模拟每日疲劳度
        base_fatigue = {"休闲": 2, "紧凑": 7, "探险": 5, "文化": 4}
        daily_fatigue = base_fatigue.get(travel_style, 3)

        cumulative = 0
        for day in range(1, travel_days + 1):
            # 累积疲劳
            cumulative += daily_fatigue

            # 周末恢复
            if day % 7 in [6, 0]:
                cumulative *= 0.7
                analysis["rest_days"].append(day)

            # 记录疲劳曲线
            analysis["fatigue_curve"].append({
                "day": day,
                "fatigue_level": min(10, cumulative / day)
            })

            # 识别压力高峰
            if cumulative / day > 7:
                analysis["peak_stress_days"].append(day)

        analysis["cumulative_fatigue"] = cumulative
        analysis["recovery_time"] = max(1, int(cumulative / 10))

        return analysis

    def _generate_mental_tips(
        self,
        assessment: Dict[str, Any],
        stress_analysis: Dict[str, Any],
        group_type: str
    ) -> List[str]:
        """生成心理调适建议"""
        tips = []

        # 基于压力水平
        stress_level = assessment.get("stress_level", "中")
        if stress_level == "高":
            tips.extend([
                "🧘 建议每天预留1-2小时放松时间，可以冥想或轻度运动",
                "💤 保证充足睡眠（每晚8小时以上），避免过度疲劳",
                "🚶 适当降低行程密度，给自己喘息的空间"
            ])
        elif stress_level == "中":
            tips.extend([
                "⏰ 合理安排作息时间，避免早出晚归",
                "🌅 每天留出一些自由活动时间，享受旅行的乐趣"
            ])

        # 基于疲劳分析
        if stress_analysis["cumulative_fatigue"] > 30:
            tips.append("🛀 建议中途安排一天休息日，不安排外出活动")

        if stress_analysis["peak_stress_days"]:
            peak_days = ", ".join([f"第{d}天" for d in stress_analysis["peak_stress_days"][:3]])
            tips.append(f"📅 预计{peak_days}可能较为疲劳，注意调整心态")

        # 基于同行人群
        if group_type == "独自":
            tips.extend([
                "👥 主动与当地人或其他旅行者交流，避免过度孤独",
                "📞 定期与家人朋友视频通话，保持情感连接"
            ])
        elif group_type == "家庭":
            tips.extend([
                "👨‍👩‍👧‍👦 照顾家人的同时也要关注自己的需求",
                "🎮 安排一些家庭互动活动，增进感情"
            ])

        # 通用建议
        tips.extend([
            "😊 保持积极心态，接纳旅行中的小插曲",
            "📸 记录美好时刻，但不要过度依赖手机",
            "🌳 多接触大自然，有助于减压和放松",
            "🍽️ 规律饮食，避免暴饮暴食或不吃饭"
        ])

        return tips[:8]  # 返回前8条

    def _generate_emotion_guidance(
        self,
        destination: str,
        travel_style: str,
        assessment: Dict[str, Any]
    ) -> List[Dict[str, str]]:
        """生成情绪管理指导"""
        guidance = []

        # 情绪识别
        guidance.append({
            "title": "🎭 情绪识别",
            "content": "旅行中可能出现的情绪：兴奋、疲惫、焦虑、失落、愉悦。识别自己的情绪是管理情绪的第一步。",
            "tip": "每天晚上花5分钟回顾今天的情绪状态，记录在日记中。"
        })

        # 压力应对
        if assessment.get("stress_level") in ["中", "高"]:
            guidance.append({
                "title": "💪 压力应对",
                "content": "感到压力时，尝试深呼吸、短暂散步或听舒缓音乐。不要强迫自己完成所有计划。",
                "tip": "使用「4-7-8呼吸法」：吸气4秒，憋气7秒，呼气8秒，重复4次。"
            })

        # 社交支持
        if assessment.get("social_support", 0) < 7:
            guidance.append({
                "title": "🤝 寻求支持",
                "content": "遇到困难时，不要独自承受。与同行伙伴、家人或朋友倾诉，寻求情感支持。",
                "tip": "建立「旅行伙伴制度」，互相关心彼此的状态。"
            })

        # 正念练习
        guidance.append({
            "title": "🧠 正念旅行",
            "content": "专注于当下的体验，用五感感受目的地：看风景、听声音、闻气味、尝美食、触摸物品。",
            "tip": "每天选择一个时刻（如日出、用餐）进行5分钟正念练习。"
        })

        # 自我关怀
        guidance.append({
            "title": "💝 自我关怀",
            "content": "旅行是为了让自己开心，不是为了打卡或取悦他人。累了就休息，不喜欢的活动可以跳过。",
            "tip": "每天给自己一个「自我关怀时刻」，做自己喜欢的事。"
        })

        return guidance

    def _generate_personalized_advice(
        self,
        destination: str,
        travel_days: int,
        assessment: Dict[str, Any],
        stress_analysis: Dict[str, Any]
    ) -> str:
        """使用 RAG 检索心理知识 + LLM 生成个性化建议"""

        # ── RAG：检索心理专业知识注入 Prompt ──
        knowledge_context = ""
        if self.rag is not None:
            try:
                stress_level = assessment.get("stress_level", "中")
                # 用压力水平 + 疲劳情况构造检索 query
                query = f"旅行压力 {stress_level} 疲劳 情绪管理 心理调适"
                docs = self.rag.retrieve(query, top_k=3)
                if docs:
                    knowledge_context = "\n\n专业心理知识参考：\n" + "\n".join(
                        f"- {d.get('text', '')[:200]}" for d in docs
                    )
                    self.logger.info(f"[PsychologyAgent] RAG 检索到 {len(docs)} 条心理知识")
            except Exception as e:
                self.logger.warning(f"[PsychologyAgent] RAG 检索失败，跳过: {e}")

        prompt = f"""你是一位专业的旅行心理咨询师。请为去{destination}旅行{travel_days}天的游客提供个性化的心理健康建议。

心理健康评估：
- 总体分数：{assessment['overall_score']}/100
- 压力水平：{assessment['stress_level']}
- 放松潜力：{assessment['relaxation_potential']}/10
- 社交支持：{assessment['social_support']}/10
- 风险因素：{', '.join(assessment['risk_factors'])}
- 保护因素：{', '.join(assessment['protective_factors'])}

压力分析：
- 累积疲劳度：{stress_analysis['cumulative_fatigue']}
- 压力高峰日：{', '.join([f'第{d}天' for d in stress_analysis['peak_stress_days']])}
- 建议恢复时间：{stress_analysis['recovery_time']}天
{knowledge_context}

请提供：
1. 个性化的心理健康建议（200字以内）
2. 重点关注的心理调适方向
3. 具体的实践建议（可结合上述专业知识参考）

请用温暖、专业的语气，直接给出建议，不要包含"作为心理咨询师"等开场白。
"""

        try:
            if self.llm:
                response = self.llm.chat_completion(
                    messages=[{"role": "user", "content": prompt}],
                    temperature=0.7
                )
                return response.choices[0].message.content.strip()
        except Exception as e:
            print(f"LLM 生成建议失败: {e}")

        # 降级方案
        return f"""根据您的{travel_days}天{destination}之旅，我有以下建议：

您的心理健康评分为{assessment['overall_score']}/100，总体状态良好。旅行期间建议：

1. **节奏调整**：前几天可能会较为兴奋，但注意不要透支体力，预留充足的休息时间。

2. **情绪管理**：旅行中难免遇到小挫折（如天气、交通等），保持弹性心态，接纳不完美。

3. **社交平衡**：既要享受独处时光，也要适度社交，找到适合自己的平衡点。

4. **自我关怀**：每天给自己一些"me time"，做喜欢的事情，不要让行程成为负担。

祝您旅途愉快，收获满满的美好回忆！"""


# 示例用法
if __name__ == "__main__":
    agent = PsychologyAgent()

    state = {
        "destination": "大理",
        "travel_days": 7,
        "travel_style": "休闲",
        "group_type": "朋友",
        "daily_plan": [
            {"day": 1, "activities": ["洱海"]},
            {"day": 2, "activities": ["苍山"]},
            {"day": 3, "activities": ["古城"]},
            {"day": 4, "activities": ["双廊"]},
            {"day": 5, "activities": ["休息"]},
            {"day": 6, "activities": ["周边游"]},
            {"day": 7, "activities": ["返程"]}
        ]
    }

    result = agent.execute(state)

    print("=" * 50)
    print("心理健康评估：")
    assessment = result["mental_assessment"]
    print(f"  总体分数：{assessment['overall_score']}/100")
    print(f"  压力水平：{assessment['stress_level']}")
    print(f"  放松潜力：{assessment['relaxation_potential']}/10")
    print(f"  社交支持：{assessment['social_support']}/10")

    print("\n" + "=" * 50)
    print("压力分析：")
    stress = result["stress_analysis"]
    print(f"  累积疲劳度：{stress['cumulative_fatigue']}")
    print(f"  压力高峰日：{', '.join([f'第{d}天' for d in stress['peak_stress_days']])}")
    print(f"  建议恢复时间：{stress['recovery_time']}天")

    print("\n" + "=" * 50)
    print("心理调适建议：")
    for tip in result["mental_tips"]:
        print(f"  {tip}")

    print("\n" + "=" * 50)
    print("情绪管理指导：")
    for guide in result["emotion_guidance"]:
        print(f"\n  {guide['title']}")
        print(f"  {guide['content']}")
        print(f"  💡 {guide['tip']}")

    print("\n" + "=" * 50)
    print("个性化建议：")
    print(result["personalized_advice"])
