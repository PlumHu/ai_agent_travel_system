"""
Streamlit Web 界面
提供可视化的交互式旅行规划体验
"""
import streamlit as st
import sys
from pathlib import Path

# 添加项目根目录到路径
project_root = Path(__file__).parent.parent
sys.path.insert(0, str(project_root))

from main import run_agent

# 页面配置
st.set_page_config(
    page_title="AI 旅行规划助手",
    page_icon="🧳",
    layout="wide"
)

# 标题
st.title("🧳 AI Travel Agent - 智能旅行规划助手")
st.markdown("---")

# 侧边栏
with st.sidebar:
    st.header("📝 使用说明")
    st.markdown("""
    ### 如何使用：
    1. 在下方输入框描述您的旅行需求
    2. 点击"开始规划"按钮
    3. 等待 AI 生成旅行计划
    4. 查看详细的行程安排

    ### 示例输入：
    - "我想6月去大理玩5天，预算5000元"
    - "推荐一个适合周末放松的海边目的地"
    - "计划三亚3天游，喜欢潜水和海鲜"
    """)

    st.markdown("---")
    st.markdown("### 🛠️ 技术栈")
    st.markdown("""
    - LangChain
    - LangGraph
    - ChromaDB (RAG)
    - Streamlit
    - OpenAI GPT-4
    """)

# 主界面
st.subheader("📋 请描述您的旅行需求")

user_input = st.text_area(
    "输入您的需求：",
    height=100,
    placeholder="例如：我想6月中旬去大理玩5天，预算5000元，喜欢吃美食和看风景"
)

col1, col2, col3 = st.columns([1, 1, 4])

with col1:
    plan_button = st.button("🚀 开始规划", type="primary", use_container_width=True)

with col2:
    clear_button = st.button("🗑️ 清空", use_container_width=True)

if clear_button:
    st.rerun()

# 执行规划
if plan_button and user_input.strip():
    with st.spinner("🤖 AI 正在为您规划旅行，请稍候..."):
        try:
            result = run_agent(user_input)

            if result.get("error"):
                st.error(f"❌ 规划失败: {result['error']}")
            else:
                st.success("✅ 旅行计划生成成功！")

                # 显示解析的需求
                st.markdown("---")
                st.subheader("📊 需求分析")

                col1, col2, col3, col4 = st.columns(4)
                with col1:
                    st.metric("目的地", result.get("destination", "未指定"))
                with col2:
                    st.metric("预算", f"{result.get('budget', 0)} 元" if result.get("budget") else "未指定")
                with col3:
                    st.metric("出发日期", result.get("start_date", "未指定"))
                with col4:
                    st.metric("返回日期", result.get("end_date", "未指定"))

                # 显示旅行计划
                travel_plan = result.get("travel_plan")
                if travel_plan:
                    st.markdown("---")
                    st.subheader("📅 每日行程")

                    for day_plan in travel_plan.get("day_by_day", []):
                        with st.expander(f"**Day {day_plan.get('day')} - {day_plan.get('date')}**", expanded=True):
                            st.markdown("**活动安排:**")
                            for activity in day_plan.get("activities", []):
                                st.markdown(f"- {activity}")

                            if day_plan.get("meals"):
                                st.markdown("**餐饮推荐:**")
                                for meal in day_plan.get("meals", []):
                                    st.markdown(f"- {meal}")

                    # 住宿建议
                    st.markdown("---")
                    st.subheader("🏨 住宿建议")
                    for acc in travel_plan.get("accommodation", []):
                        st.markdown(f"- {acc}")

                    # 美食推荐
                    st.markdown("---")
                    st.subheader("🍜 美食推荐")
                    food_items = travel_plan.get("food", [])
                    cols = st.columns(min(len(food_items), 3))
                    for i, food in enumerate(food_items):
                        with cols[i % 3]:
                            st.info(food)

                    # 预算分解
                    st.markdown("---")
                    st.subheader("💰 预算分解")
                    budget_breakdown = travel_plan.get("budget_breakdown", {})
                    if budget_breakdown:
                        import pandas as pd
                        df = pd.DataFrame(list(budget_breakdown.items()), columns=["项目", "金额 (元)"])
                        st.bar_chart(df.set_index("项目"))
                        st.dataframe(df, use_container_width=True)

                    # 旅行贴士
                    st.markdown("---")
                    st.subheader("💡 旅行贴士")
                    for tip in travel_plan.get("tips", []):
                        st.warning(tip)

                    # 下载报告
                    st.markdown("---")
                    if result.get("client_report"):
                        st.download_button(
                            label="📥 下载完整报告 (Markdown)",
                            data=result["client_report"],
                            file_name=f"{result.get('destination', 'travel')}_plan.md",
                            mime="text/markdown",
                            use_container_width=True
                        )

        except Exception as e:
            st.error(f"❌ 系统错误: {str(e)}")

elif plan_button:
    st.warning("⚠️ 请先输入您的旅行需求")

# 页脚
st.markdown("---")
st.markdown("""
<div style='text-align: center; color: gray;'>
    🤖 Powered by LangGraph + OpenAI GPT-4 |
    <a href='https://github.com' target='_blank'>GitHub</a>
</div>
""", unsafe_allow_html=True)
