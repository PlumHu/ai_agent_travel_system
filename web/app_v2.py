"""
Streamlit Web 界面 V2
支持独立 Agent 调用和智能推荐
"""
import streamlit as st
import sys
from pathlib import Path
import json

# 添加项目根目录到路径
project_root = Path(__file__).parent.parent
sys.path.insert(0, str(project_root))

# bump 后自动重建 session 里的旧 AgentManager，避免热更新后方法签名不匹配
_MANAGER_VERSION = 8
# 轻量常量；AgentManager / RAG 本体延后加载，加快首屏
from agent_catalog import USER_FACING_AGENTS, AGENT_DISPLAY_NAMES
from memory.chat_store import (
    LOCAL_TTL_HOURS,
    clear_chat,
    list_users,
    load_chat,
    normalize_user_id,
    purge_expired,
    save_chat,
)

# 页面配置
st.set_page_config(
    page_title="AI 旅行规划助手 V2",
    page_icon="🧳",
    layout="wide"
)

if "mode" not in st.session_state:
    st.session_state.mode = "互动聊天"

if "user_id" not in st.session_state:
    st.session_state.user_id = "default"

if "chat_history" not in st.session_state:
    st.session_state.chat_history = []   # [(role, content), ...]

if "chat_loaded_for" not in st.session_state:
    st.session_state.chat_loaded_for = None

if "pending_context" not in st.session_state:
    st.session_state.pending_context = None


def _persist_chat() -> None:
    """把当前用户的 UI 历史 + 短期上下文写盘。"""
    manager = st.session_state.get("manager")
    user_id = st.session_state.get("user_id", "default")
    if manager is not None:
        context = manager.save_context()
    else:
        context = st.session_state.get("pending_context") or {
            "history": [],
            "summary": "",
            "compress_count": 0,
        }
    save_chat(user_id, st.session_state.chat_history, context=context)


def _hydrate_chat_ui_only(user_id: str | None = None) -> None:
    """
    首屏只读聊天 JSON，不创建 AgentManager / 不加载 Embedding。
    这是打开变快的关键：页面渲染不再碰 torch/chromadb。
    """
    uid = normalize_user_id(user_id or st.session_state.get("user_id", "default"))
    st.session_state.user_id = uid
    if st.session_state.chat_loaded_for == uid and "chat_history" in st.session_state:
        return
    data = load_chat(uid)
    st.session_state.chat_history = list(data.get("ui_history") or [])
    st.session_state.pending_context = data.get("context") or {
        "history": [],
        "summary": "",
        "compress_count": 0,
    }
    st.session_state.chat_loaded_for = uid


def _switch_user(new_user_id: str) -> None:
    """切换用户：先保存当前用户，再加载目标用户（仅聊天 JSON，轻量）。"""
    new_id = normalize_user_id(new_user_id)
    old_id = normalize_user_id(st.session_state.get("user_id", "default"))
    if new_id == old_id:
        _hydrate_chat_ui_only(new_id)
        return

    # 保存旧用户
    if st.session_state.chat_loaded_for == old_id:
        try:
            _persist_chat()
        except Exception:
            pass

    st.session_state.user_id = new_id
    st.session_state.pop("manager", None)
    st.session_state.pop("manager_version", None)
    st.session_state.chat_history = []
    st.session_state.chat_loaded_for = None
    st.session_state.pending_context = None
    _hydrate_chat_ui_only(new_id)


def _ensure_manager():
    """真正发消息/跑 Agent 时才创建 Manager（避免打开页面就卡住）。"""
    from agent_manager import AgentManager

    user_id = normalize_user_id(st.session_state.get("user_id", "default"))
    st.session_state.user_id = user_id
    _hydrate_chat_ui_only(user_id)

    manager = st.session_state.get("manager")
    version_ok = st.session_state.get("manager_version") == _MANAGER_VERSION
    same_user = getattr(manager, "user_id", None) == user_id if manager else False
    method_ok = False
    if manager is not None:
        try:
            import inspect
            method_ok = "user_facing_only" in inspect.signature(manager.list_agents).parameters
        except Exception:
            method_ok = False

    if manager is None or not version_ok or not method_ok or not same_user:
        with st.spinner(f"正在准备助手（用户：{user_id}）…"):
            st.session_state.manager = AgentManager(user_id=user_id)
            st.session_state.manager_version = _MANAGER_VERSION
            pending = st.session_state.get("pending_context")
            if pending:
                st.session_state.manager.load_context(pending)
            st.session_state.pending_context = None
    return st.session_state.manager


def _list_user_facing_agents(manager) -> dict:
    """只返回面向用户的 Agent；不依赖 list_agents 的新参数，兼容旧实例。"""
    raw = manager.list_agents()
    agents = {}
    for key in USER_FACING_AGENTS:
        if key not in raw:
            continue
        info = dict(raw[key])
        info.setdefault("display_name", AGENT_DISPLAY_NAMES.get(key, key))
        info.setdefault("description", info.get("description", ""))
        agents[key] = info
    return agents


def _stream_chat_reply(user_input: str) -> str:
    """带多轮上下文的流式回复；失败时降级到 run_pipeline。"""
    from config import AVAILABLE_PROVIDERS
    from langchain_openai import ChatOpenAI
    from langchain_core.messages import AIMessage, HumanMessage, SystemMessage

    manager = _ensure_manager()
    # 先写入用户消息，再取上下文（避免漏记多轮）
    manager.ctx.add_user_message(user_input)
    messages = manager.get_context_messages(query=user_input)

    lc_messages = []
    for m in messages:
        role = m.get("role")
        content = m.get("content", "")
        if role == "system":
            lc_messages.append(SystemMessage(content=content))
        elif role == "assistant":
            lc_messages.append(AIMessage(content=content))
        else:
            lc_messages.append(HumanMessage(content=content))

    p = AVAILABLE_PROVIDERS[0]
    llm_stream = ChatOpenAI(
        model=p["model"],
        temperature=0.7,
        openai_api_key=p["api_key"],
        openai_api_base=p["base_url"],
        streaming=True,
    )

    stream_placeholder = st.empty()
    full_response = ""
    for chunk in llm_stream.stream(lc_messages):
        token = chunk.content or ""
        full_response += token
        stream_placeholder.markdown(full_response + "▌")

    stream_placeholder.markdown(full_response or "_（空回复）_")
    manager.ctx.add_assistant_message(full_response)
    return full_response


# 标题
st.title("🧳 AI Travel Agent V2 - 智能旅行规划助手")
st.markdown("**新功能**：✨ 多用户隔离 + 聊天持久化 + 互动聊天 + 智能推荐")
st.markdown("---")

# 侧边栏
with st.sidebar:
    st.header("👤 当前用户")
    known_users = list_users()
    if "default" not in known_users:
        known_users = ["default"] + known_users
    elif known_users[0] != "default":
        known_users = ["default"] + [u for u in known_users if u != "default"]

    # Streamlit selectbox：session 里残留的旧值不在 options 时会直接报错 → 浏览器白屏
    current_uid = st.session_state.get("user_id", "default")
    if current_uid not in known_users:
        current_uid = "default"
        st.session_state.user_id = current_uid
    if st.session_state.get("user_select") not in known_users:
        st.session_state.user_select = current_uid

    selected = st.selectbox(
        "选择已有用户",
        options=known_users,
        key="user_select",
    )
    new_user = st.text_input(
        "或输入新用户名",
        value="",
        placeholder="例如：alice",
        key="user_new_input",
    )
    col_u1, col_u2 = st.columns(2)
    with col_u1:
        if st.button("切换用户", use_container_width=True):
            target = new_user.strip() or selected
            _switch_user(target)
            st.rerun()
    with col_u2:
        if st.button("进入新用户", use_container_width=True, disabled=not new_user.strip()):
            _switch_user(new_user.strip())
            st.rerun()
    st.caption(
        f"当前：`{st.session_state.user_id}` · 聊天按用户隔离，"
        f"本地保留 {LOCAL_TTL_HOURS} 小时（偏好记忆长期保留）"
    )

    st.markdown("---")
    st.header("📝 使用模式")

    mode = st.radio(
        "选择使用模式：",
        ["互动聊天", "完整流程", "独立 Agent", "智能推荐"],
        key="mode",
    )

    st.markdown("---")

    if mode == "互动聊天":
        st.markdown("""
        ### 💬 互动聊天模式
        多轮对话，记住上下文

        **适用场景：**
        - 边聊边规划
        - 追问美食/预算/行程
        - 连续修改需求
        """)
        if st.button("🗑️ 清空对话", use_container_width=True):
            uid = st.session_state.user_id
            st.session_state.chat_history = []
            st.session_state.pending_context = {
                "history": [], "summary": "", "compress_count": 0
            }
            if "manager" in st.session_state and st.session_state.manager is not None:
                st.session_state.manager.reset_context()
            clear_chat(uid)
            st.session_state.chat_loaded_for = uid
            st.rerun()

    elif mode == "完整流程":
        st.markdown("""
        ### 🚀 完整流程模式
        自动解析需求 → 规划行程 → 生成报告

        **适用场景：**
        - 完整的旅行规划需求
        - 自动路由到合适的 Agent
        """)

    elif mode == "独立 Agent":
        st.markdown("""
        ### 🔧 独立功能模式
        按需选择单项能力

        **可选：**
        - 智能推荐 / 目的地推荐
        - 行程与旅行规划
        - 美食、心理节奏、报告
        """)

    else:  # 智能推荐
        st.markdown("""
        ### 💡 智能推荐模式

        **正向推荐**：
        根据时间/偏好 → 推荐目的地

        **反向推荐**：
        根据目的地 → 推荐出行时间
        """)

    st.markdown("---")
    if st.button("🔄 重建 AgentManager", use_container_width=True):
        try:
            _persist_chat()
        except Exception:
            pass
        st.session_state.pop("manager", None)
        st.session_state.pop("manager_version", None)
        st.session_state.chat_loaded_for = None
        st.rerun()

    st.markdown("---")
    st.markdown("### 🛠️ 技术栈")
    st.markdown("""
    - LangChain + LangGraph
    - ChromaDB (RAG)
    - Streamlit
    - OpenAI GPT-4
    """)

# 首屏只恢复聊天记录（毫秒级）；AgentManager / Embedding 延后到真正发消息
# 过期清理每会话一次，避免每次 rerun 扫盘
if not st.session_state.get("_purged_once"):
    try:
        purge_expired()
    except Exception:
        pass
    st.session_state._purged_once = True

try:
    _hydrate_chat_ui_only()
except Exception as e:
    st.error(f"加载聊天记录失败: {e}")
    st.session_state.chat_history = []
    st.session_state.chat_loaded_for = st.session_state.get("user_id", "default")

# ============ 互动聊天模式 ============
if st.session_state.mode == "互动聊天":
    st.subheader(f"💬 旅行助手对话 · {st.session_state.user_id}")
    st.caption(
        f"多轮追问会自动保存；本地聊天保留 {LOCAL_TTL_HOURS} 小时，超时自动清理。"
        "首次发消息时才会加载助手模型。"
    )

    if not st.session_state.chat_history:
        with st.chat_message("assistant"):
            st.markdown(
                "你好！我是旅行规划助手。可以说目的地、天数、预算和偏好，"
                "也可以随时追问行程、美食或预算调整。"
            )

    for role, content in st.session_state.chat_history:
        with st.chat_message(role):
            st.markdown(content)

    chat_input = st.chat_input("输入旅行问题，例如：大理 3 天怎么玩？")
    if chat_input and chat_input.strip():
        user_text = chat_input.strip()
        st.session_state.chat_history.append(("user", user_text))
        with st.chat_message("user"):
            st.markdown(user_text)

        with st.chat_message("assistant"):
            try:
                reply = _stream_chat_reply(user_text)
            except Exception as e:
                st.warning(f"流式输出失败，降级为流水线模式: {e}")
                manager = _ensure_manager()
                result = manager.run_pipeline(user_text, auto_route=True)
                if result.get("success"):
                    reply = str(result.get("final_output") or "规划完成")
                    st.markdown(reply)
                else:
                    reply = f"❌ 规划失败: {result.get('error', '未知错误')}"
                    st.error(reply)
            st.session_state.chat_history.append(("assistant", reply))
        _persist_chat()

# ============ 完整流程模式 ============
elif st.session_state.mode == "完整流程":
    st.subheader("📋 请描述您的旅行需求")

    user_input = st.text_area(
        "输入您的需求：",
        height=100,
        placeholder="例如：我想6月中旬去大理玩5天，预算5000元，喜欢吃美食和看风景"
    )

    col1, col2 = st.columns([1, 4])

    with col1:
        run_button = st.button("🚀 开始规划", type="primary", use_container_width=True)

    if run_button and user_input.strip():
        manager = _ensure_manager()
        # 显示用户消息
        st.session_state.chat_history.append(("user", user_input))

        # 流式输出区域
        with st.chat_message("assistant"):
            stream_placeholder = st.empty()
            full_response = ""

            try:
                from config import AVAILABLE_PROVIDERS
                from langchain_openai import ChatOpenAI
                from langchain_core.messages import HumanMessage, SystemMessage

                # 构造带记忆的消息
                messages = manager.get_context_messages(query=user_input)
                messages.append({"role": "user", "content": user_input})

                # 转成 LangChain message 对象
                lc_messages = []
                for m in messages:
                    if m["role"] == "system":
                        lc_messages.append(SystemMessage(content=m["content"]))
                    else:
                        lc_messages.append(HumanMessage(content=m["content"]))

                # 流式调用（自动兜底）
                p = AVAILABLE_PROVIDERS[0]
                llm_stream = ChatOpenAI(
                    model=p["model"],
                    temperature=0.7,
                    openai_api_key=p["api_key"],
                    openai_api_base=p["base_url"],
                    streaming=True,
                )

                for chunk in llm_stream.stream(lc_messages):
                    token = chunk.content
                    full_response += token
                    stream_placeholder.markdown(full_response + "▌")

                stream_placeholder.markdown(full_response)
                st.session_state.chat_history.append(("assistant", full_response))

                # 写入短期 + 长期记忆
                manager.ctx.add_assistant_message(full_response)
                _persist_chat()

            except Exception as e:
                # 流式失败时降级为普通调用
                st.warning(f"流式输出失败，降级为普通模式: {e}")
                result = manager.run_pipeline(user_input, auto_route=True)
                if not result.get("success"):
                    st.error(f"❌ 规划失败: {result.get('error', '未知错误')}")
                else:
                    st.success("✅ 规划完成！")

                    # 显示执行步骤
                    with st.expander("📊 执行步骤", expanded=False):
                        for i, step in enumerate(result.get("steps", []), 1):
                            st.markdown(f"**Step {i}: {step['agent']}**")
                            if step["result"].get("success"):
                                st.json(step["result"].get("data"))
                            else:
                                st.error(step["result"].get("error"))

                    final_output = result.get("final_output")
                    if not isinstance(final_output, dict):
                        output = str(final_output or "规划完成")
                        stream_placeholder.markdown(output)
                        st.session_state.chat_history.append(("assistant", output))
                    else:
                        output_type = final_output.get("type")
                        # 结构化结果也记一条摘要，便于按用户回看
                        st.session_state.chat_history.append(
                            ("assistant", f"[规划结果] {output_type or 'done'}: {str(final_output)[:800]}")
                        )

                        if output_type == "time_recommendation":
                            st.markdown("---")
                            st.subheader("🕒 最佳出行时间推荐")
                            recommendation = final_output.get("recommendation", {})

                            if "best_periods" in recommendation:
                                st.markdown("### ⭐ 推荐时间段")
                                for period in recommendation["best_periods"]:
                                    with st.expander(
                                        f"**{period['period']}** (评分: {period.get('score', 0)}/100)",
                                        expanded=True,
                                    ):
                                        st.markdown("**推荐理由：**")
                                        for reason in period.get("reasons", []):
                                            st.markdown(f"- {reason}")

                                        col1, col2 = st.columns(2)
                                        with col1:
                                            st.metric("人流等级", period.get("crowd_level", "未知"))
                                            st.metric("价格水平", period.get("price_level", "未知"))
                                        with col2:
                                            weather = period.get("weather", {})
                                            st.metric("平均气温", weather.get("avg_temp", "未知"))
                                            st.metric("天气状况", weather.get("condition", "未知"))

                                        if period.get("highlights"):
                                            st.markdown("**特色亮点：**")
                                            for highlight in period["highlights"]:
                                                st.info(highlight)

                            if "avoid_periods" in recommendation:
                                st.markdown("### ❌ 不推荐时间段")
                                for period in recommendation["avoid_periods"]:
                                    st.warning(
                                        f"**{period['period']}**: {', '.join(period.get('reasons', []))}"
                                    )

                            if "festival_calendar" in recommendation:
                                st.markdown("### 🎉 当地节庆日历")
                                for festival in recommendation["festival_calendar"]:
                                    st.markdown(
                                        f"- **{festival['name']}** ({festival['date']}): "
                                        f"{festival['description']}"
                                    )

                            if "flexible_tips" in recommendation:
                                st.info(f"💡 {recommendation['flexible_tips']}")

                        elif output_type == "destination_recommendation":
                            st.markdown("---")
                            st.subheader("📍 目的地推荐")
                            recommendation = final_output.get("recommendation", {})

                            if "recommendations" in recommendation:
                                for i, dest in enumerate(recommendation["recommendations"], 1):
                                    with st.expander(
                                        f"**推荐 {i}: {dest['destination']}** "
                                        f"(评分: {dest.get('score', 0)}/100)",
                                        expanded=True,
                                    ):
                                        st.markdown("**推荐理由：**")
                                        for reason in dest.get("reasons", []):
                                            st.markdown(f"- ✅ {reason}")

                                        if dest.get("best_activities"):
                                            st.markdown("**推荐活动：**")
                                            cols = st.columns(min(len(dest["best_activities"]), 3))
                                            for j, activity in enumerate(dest["best_activities"]):
                                                with cols[j % 3]:
                                                    st.info(activity)

                            if "time_advice" in recommendation:
                                st.markdown("### 🕒 出行时间建议")
                                st.success(recommendation["time_advice"])

                            if "budget_tips" in recommendation:
                                st.markdown("### 💰 预算建议")
                                st.info(recommendation["budget_tips"])

                        else:
                            output = str(final_output)
                            stream_placeholder.markdown(output)
                    _persist_chat()

    elif run_button:
        st.warning("⚠️ 请先输入您的旅行需求")

# ============ 独立 Agent 模式 ============
elif st.session_state.mode == "独立 Agent":
    st.subheader("🔧 选择功能")

    # 只展示面向用户的能力；parse/merge/react/browser 等内部 Agent 不露出
    manager = _ensure_manager()
    agents = _list_user_facing_agents(manager)
    agent_keys = list(agents.keys())

    placeholders = {
        "recommend": "例如：推荐适合情侣、预算8000的目的地",
        "destination": "例如：喜欢自然风光和慢生活，预算6000",
        "plan": "例如：去大理玩5天，预算5000，喜欢风景",
        "travel": "例如：规划丽江4日游，喜欢古城和雪山",
        "food": "例如：大理有什么特色美食？我海鲜过敏",
        "psychology": "例如：三亚5天休闲游，两个人去，别太赶",
        "output": "例如：生成大理3天旅行计划报告",
    }

    col1, col2 = st.columns([1, 2])

    with col1:
        agent_name = st.selectbox(
            "选择功能：",
            agent_keys,
            format_func=lambda k: agents[k].get("display_name")
            or agents[k].get("description")
            or k,
        )
        agent_info = agents[agent_name]
        st.info(agent_info.get("description") or "")

    with col2:
        user_input = st.text_area(
            "说说你的需求：",
            height=150,
            placeholder=placeholders.get(agent_name, "例如：我想去大理，预算5000元"),
        )

    display_name = agents[agent_name].get("display_name", agent_name)
    run_button = st.button(f"▶️ 开始{display_name}", type="primary")

    if run_button and user_input.strip():
        with st.spinner(f"🔄 正在{display_name}..."):
            result = st.session_state.manager.run_agent(agent_name, {
                "user_input": user_input.strip()
            })

            if result.get("success"):
                st.success(f"✅ {display_name}完成")
                data = result.get("data")
                if isinstance(data, dict) and data.get("client_report"):
                    st.markdown(data["client_report"])
                elif isinstance(data, dict):
                    # 面向用户优先展示可读字段，避免整坨内部结构
                    shown = False
                    for key in (
                        "personalized_advice",
                        "recommendation",
                        "recommendations",
                        "plan",
                        "travel_plan",
                        "food_recommendations",
                        "mental_tips",
                    ):
                        if data.get(key):
                            st.write(data[key])
                            shown = True
                    if not shown:
                        st.write(data)
                else:
                    st.write(data if data is not None else result)
            else:
                st.error(f"❌ 失败: {result.get('error')}")

# ============ 智能推荐模式 ============
else:  # 智能推荐
    st.subheader("💡 智能推荐")

    recommend_type = st.radio(
        "选择推荐类型：",
        ["正向推荐（推荐目的地）", "反向推荐（推荐时间）"]
    )

    if recommend_type == "正向推荐（推荐目的地）":
        st.markdown("### 📍 根据您的需求推荐目的地")

        col1, col2 = st.columns(2)

        with col1:
            start_date = st.date_input("出发日期（可选）")
            budget = st.number_input("预算（元）", min_value=0, value=5000)

        with col2:
            preferences = st.multiselect(
                "旅行偏好：",
                ["自然风光", "美食", "文化", "历史", "海滩", "山景", "古镇", "现代都市"],
                default=["自然风光"]
            )

        user_input = st.text_area(
            "补充说明（可选）：",
            placeholder="例如：希望人少一点，适合拍照"
        )

        if st.button("🔍 开始推荐", type="primary"):
            with st.spinner("🤖 正在分析并推荐..."):
                result = _ensure_manager().run_agent("recommend", {
                    "user_input": user_input or "推荐旅行目的地",
                    "start_date": start_date.strftime("%Y-%m-%d") if start_date else None,
                    "budget": budget,
                    "preferences": preferences,
                    "intent": "recommend_destination"
                })

                if result["success"]:
                    st.success("✅ 推荐完成！")

                    recommendation = result["data"].get("recommendation", {})

                    if "recommendations" in recommendation:
                        for i, dest in enumerate(recommendation["recommendations"], 1):
                            with st.expander(f"**推荐 {i}: {dest['destination']}** (评分: {dest.get('score', 0)}/100)", expanded=True):
                                st.markdown(f"**推荐理由：**")
                                for reason in dest.get("reasons", []):
                                    st.markdown(f"- ✅ {reason}")

                                if dest.get("best_activities"):
                                    st.markdown("**推荐活动：**")
                                    for activity in dest["best_activities"]:
                                        st.info(activity)
                else:
                    st.error(f"❌ 推荐失败: {result['error']}")

    else:  # 反向推荐
        st.markdown("### 🕒 根据目的地推荐最佳出行时间")

        destination = st.text_input("目的地：", placeholder="例如：三亚")

        preferences = st.multiselect(
            "您的偏好：",
            ["人少", "天气好", "价格实惠", "有特色活动", "避开雨季"],
            default=["人少", "天气好"]
        )

        user_input = st.text_area(
            "补充说明（可选）：",
            placeholder="例如：想避开节假日高峰"
        )

        if st.button("🔍 开始推荐", type="primary"):
            if not destination:
                st.warning("⚠️ 请先输入目的地")
            else:
                with st.spinner("🤖 正在分析并推荐..."):
                    result = _ensure_manager().run_agent("recommend", {
                        "user_input": user_input or f"{destination}什么时候去最合适",
                        "destination": destination,
                        "preferences": preferences,
                        "intent": "recommend_time"
                    })

                    if result["success"]:
                        st.success("✅ 推荐完成！")

                        recommendation = result["data"].get("recommendation", {})

                        # 最佳时间段
                        if "best_periods" in recommendation:
                            st.markdown("### ⭐ 推荐时间段")
                            for period in recommendation["best_periods"]:
                                with st.expander(f"**{period['period']}** (评分: {period.get('score', 0)}/100)", expanded=True):
                                    st.markdown(f"**推荐理由：**")
                                    for reason in period.get("reasons", []):
                                        st.markdown(f"- {reason}")

                                    col1, col2 = st.columns(2)
                                    with col1:
                                        st.metric("人流等级", period.get("crowd_level", "未知"))
                                        st.metric("价格水平", period.get("price_level", "未知"))
                                    with col2:
                                        weather = period.get("weather", {})
                                        st.metric("平均气温", weather.get("avg_temp", "未知"))
                                        st.metric("天气状况", weather.get("condition", "未知"))

                        # 避开时间段
                        if "avoid_periods" in recommendation:
                            st.markdown("### ❌ 不推荐时间段")
                            for period in recommendation["avoid_periods"]:
                                st.warning(f"**{period['period']}**: {', '.join(period.get('reasons', []))}")

                        # 节庆日历
                        if "festival_calendar" in recommendation:
                            st.markdown("### 🎉 当地节庆日历")
                            for festival in recommendation["festival_calendar"]:
                                st.markdown(f"- **{festival['name']}** ({festival['date']}): {festival['description']}")

                    else:
                        st.error(f"❌ 推荐失败: {result['error']}")

# 页脚
st.markdown("---")
st.markdown("""
<div style='text-align: center; color: gray;'>
    🤖 Powered by LangGraph + OpenAI GPT-4 + RAG |
    ✨ V2: 支持独立 Agent + 智能推荐
</div>
""", unsafe_allow_html=True)
