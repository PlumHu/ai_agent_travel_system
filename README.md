# AI Agent 旅行规划系统

一个生产级思路的**多 Agent 智能旅行规划系统**：以 LangGraph 编排多个专职 Agent，融合 RAG 检索增强、Memory 记忆、MCP 协议工具、DuckDuckGo 免费搜索与浏览器自动化，并通过三级降级策略保证高可用。

---

## 项目亮点与技术难点

| 维度 | 实现 | 价值 |
|------|------|------|
| **多 Agent 编排** | LangGraph `StateGraph` + 条件路由（`add_conditional_edges`），按意图分发到解析/推荐/规划/美食/心理/输出等 9+ Agent | 支持分支、状态共享，区别于线性 Chain |
| **状态管理** | `AgentState`（`TypedDict` + 自定义 `_keep_latest_messages`）跨节点追加消息，超 20 条自动截断最旧消息 | 类型安全、防止 token 超限 |
| **RAG 检索增强** | ChromaDB + `BAAI/bge-small-zh-v1.5` 中文 Embedding | 缓解幻觉、提供事实依据 |
| **混合检索（难点）** | 向量检索 + BM25，用 RRF（倒排分数融合，k=60）加权融合排序（`knowledge/retriever.py`） | 兼顾语义相似与关键词精确 |
| **三级降级策略** | 每个工具：真实 API → DuckDuckGo 搜索 → Mock/参考链接 | 无 API Key 也能跑，永不崩 |
| **MCP 协议集成** | 统一管理天气、百度地图、brave 搜索、文件系统 server | 标准化工具接入 |
| **多 LLM 适配** | `LLMConfig` 统一 OpenAI 兼容接口，支持 DeepSeek/OpenAI/英伟达等 | 一键切换模型 |
| **三层 Memory** | 短期（deque 对话窗口）+ 长期（JSON 持久化偏好）+ 语义（RAG） | 个性化上下文 |
| **兜底机制** | MCP/搜索全失败时，browser-use 控制真实浏览器抓取 | 极端可用性 |
| **反思自纠错** | `ReflectionMixin` + 验证器 + LangGraph 回环边，输出不合格自动重试 | Agent 区别于 Chain 的核心 |
| **Agent Loop** | `ReActAgent` 的 Think→Act→Observe 循环，LLM 动态决定调哪个工具 | 工具调用由推理驱动，非硬编码 |
| **安全护栏** | 输入注入检测/PII脱敏 + 输出幻觉检测 + 调用限流（`guardrails/`） | 生产级安全 |
| **动态规划** | `Planner` Plan-and-Execute，复杂目标分解为带依赖子任务 + 重规划 | 应对多步骤复杂任务 |
| **可观测性** | `Tracer` 调用链（Trace/Span）+ token/延迟/成功率指标 + JSON 导出 | 事后分析与监控 |
| **错误重试** | LLM 调用瞬时错误（超时/限流/5xx）指数退避重试，永久错误直接降级 | 韧性 |
| **异步并行** | `AsyncExecutor` 信号量并发 + 超时隔离，无依赖工具并行调用 | 降低延迟 |
| **评估框架** | `evaluation/` 20 测试用例 + 6 指标 + LLM-as-Judge + 自动报告 | 可量化质量 |
| **长期记忆增强** | 冲突检测 + 记忆衰减遗忘 + 动态重要性 + LLM 辅助提取 | 拟人化记忆管理 |

**设计模式**：BaseAgent 抽象基类采用模板方法模式（`execute` 抽象 + `run_standalone` 模板 + Hook 点），并混入 `ReflectionMixin`；各 Agent 既可作 LangGraph 节点，也可独立调用。安全护栏为中间件模式，流式输出为观察者模式，均不侵入 Agent 逻辑。

---

## 目录

1. [系统概述](#系统概述)
2. [系统架构](#系统架构)
3. [快速开始](#快速开始)
4. [LLM 配置](#llm-配置)
5. [Agent 说明](#agent-说明)
6. [工具集成](#工具集成)
7. [RAG 与 Memory](#rag-与-memory)
8. [MCP 协议集成](#mcp-协议集成)
9. [项目结构](#项目结构)
10. [测试指南](#测试指南)
11. [常见问题](#常见问题)

---

## 系统概述

基于 AI Agent 的智能旅行规划系统，能够根据用户的时间、预算、偏好等需求，智能推荐旅行目的地、生成行程规划，并提供实时天气、地图、搜索等信息支持。

**核心特性**：
- 支持多种主流 LLM（DeepSeek、OpenAI、英伟达 NIM 等）
- 真实 API 优先，失败自动降级（OpenWeather → DuckDuckGo → Mock）
- RAG 检索增强 + Memory 记忆系统（ChromaDB + sentence-transformers）
- MCP 协议集成（天气、百度地图、搜索）
- 浏览器自动化兜底（browser-use）
- Streamlit Web UI（`web/app_v2.py`）

---

## 系统架构

```
用户请求
    │
    ▼
Web UI (web/app_v2.py)
    │
    ▼
AgentManager (agent_manager.py)
    │
    ├─► ParseAgent            # 需求解析 + 意图路由
    │       └─ LLM → 提取 destination/dates/budget/preferences/intent
    │
    ├─► RecommendAgent        # 双向推荐
    │       ├─ 正向: 根据偏好推荐目的地
    │       └─ 反向: 根据目的地推荐最佳出行时间
    │
    ├─► PlanAgent             # 行程规划
    │       └─ LLM → 生成逐日行程 + 住宿/交通/预算建议
    │
    ├─► FoodAgent             # 美食推荐
    │       └─ LLM → 当地特色美食 + 营养建议
    │
    ├─► PsychologyAgent       # 心理健康评估
    │       └─ LLM → 旅行压力评估 + 节奏建议
    │
    └─► BrowserAgent          # 浏览器自动化兜底
            └─ browser-use → 真实网页操作

LangGraph 编排 (main.py)
    ParseAgent → TravelAgent → OutputAgent
```

**两套入口**：

| 入口 | 文件 | 特点 |
|------|------|------|
| AgentManager 模式 | `agent_manager.py` | 轻量、灵活、Web UI 使用 |
| LangGraph 模式 | `main.py` | 图编排、状态流转、命令行使用 |

---

## 快速开始

### 1. 安装依赖

```bash
pip install -r requirements.txt

# 浏览器自动化（可选）
playwright install chromium
```

### 2. 配置环境变量

编辑 `.env` 文件，**只需改两行**即可启动：

```env
# 1. 选择提供商（改这行）
DEFAULT_LLM_PROVIDER=deepseek          # openai | deepseek | nvidia | custom

# 2. 填入对应的 Key（取消注释 + 填入，其他提供商无需改动）
DEEPSEEK_API_KEY=sk-你的key            # DeepSeek：https://platform.deepseek.com/api_keys
# OPENAI_API_KEY=sk-你的key           # OpenAI
# NVIDIA_API_KEY=nvapi-你的key        # NVIDIA NIM：https://build.nvidia.com/

# 工具 API（可选，不填自动降级）
# OPENWEATHER_API_KEY=你的key         # 天气，openweathermap.org 免费注册
# BAIDU_MAPS_API_KEY=你的key          # 路线，lbsyun.baidu.com（百度地图保留）
# BRAVE_SEARCH_API_KEY=BSA你的key     # 搜索增强，api.search.brave.com 免费2000次/月
```

config.py 会按 `DEFAULT_LLM_PROVIDER` 自动路由，无需手动改 `OPENAI_API_BASE`。

### 3. 启动 Web UI

```bash
streamlit run web/app_v2.py
```

### 4. 命令行运行（LangGraph 模式）

```bash
python main.py
```

### 5. 代码调用示例

```python
from agent_manager import AgentManager

manager = AgentManager()

# 完整流水线
result = manager.run_pipeline("我想3月去云南旅游，预算5000元，喜欢自然风光")

# 单独调用 Agent
result = manager.run_agent("recommend", {
    "user_input": "三亚什么时候去最合适？",
    "destination": "三亚",
    "intent": "recommend_time"
})
```

---

## LLM 配置

所有 Agent 统一使用 `LLMConfig`（`llm_config.py`），通过 OpenAI 兼容接口调用。

| 提供商 | provider 参数 | 默认模型 | 环境变量 |
|-------|--------------|---------|---------|
| DeepSeek | `deepseek` | deepseek-chat | `DEEPSEEK_API_KEY` |
| OpenAI | `openai` | gpt-4 | `OPENAI_API_KEY` |
| 英伟达 NIM | `nvidia` | llama-3.1-70b | `NVIDIA_API_KEY` |
| 自定义 | `custom` | 自定义 | `CUSTOM_API_KEY` |

**自动检测**：

```python
from llm_config import create_llm_from_env

llm = create_llm_from_env()  # 自动使用 DEFAULT_LLM_PROVIDER
```

**各 Agent 目前直接使用 `config.py` 中的 `OPENAI_API_KEY/OPENAI_API_BASE/OPENAI_MODEL`**，需要在 `.env` 中配置：

```bash
OPENAI_API_KEY=your_key
OPENAI_API_BASE=https://api.openai.com/v1   # 或其他兼容接口
OPENAI_MODEL=gpt-4
```

---

## Agent 说明

### ParseAgent（`agents/parse_agent_v2.py`）

解析用户自然语言输入，提取结构化信息。支持 `long_term_memory` 注入：构造 messages 时自动将用户画像插入 system 消息，LLM 可结合历史偏好更准确地补全缺省字段（如预算、偏好）。

**输入**：`user_input: str`

**输出**：
```json
{
  "destination": "大理",
  "start_date": "2026-07-01",
  "end_date": "2026-07-05",
  "budget": 5000,
  "preferences": ["自然风光", "美食"],
  "intent": "plan_trip",
  "next_action": "plan"
}
```

**intent 取值**：`plan_trip` / `recommend_destination` / `recommend_time`

### RecommendAgent（`agents/recommend_agent.py`）

双向推荐 Agent。支持 `long_term_memory` 注入：`system_prompt` 里内嵌用户历史行程和偏好，使推荐结果更个性化（避免重复推荐去过的目的地、匹配历史预算区间）。

- **正向推荐**（`intent=recommend_destination`）：根据时间/偏好/预算 + 历史行程推荐目的地
- **反向推荐**（`intent=recommend_time`）：根据目的地分析最佳出行时间、节假日、人流

依赖：RAGManager + LLM + LongTermMemory（可选）

### PlanAgent（`agents/plan_agent.py`）

生成详细行程规划。

**输出**（JSON）：
```json
{
  "destination": "大理",
  "total_days": 5,
  "day_plan": [...],
  "accommodation": {...},
  "transportation": {...},
  "budget_breakdown": {...},
  "tips": [...]
}
```

### FoodAgent（`agents/food_agent.py`）

推荐当地美食，分析营养，提供餐厅建议。

### PsychologyAgent（`agents/psychology_agent.py`）

评估旅行压力，建议行程节奏，提供心理健康旅行方案。规则评分打底 + **RAG 检索心理专业知识库**（`psychology_knowledge`：压力类型/情绪管理/同行心理）注入 LLM 生成个性化建议；知识库不可用时降级为纯规则。

### BrowserAgent（`agents/browser_agent.py`）

当 MCP 和搜索工具全部失败时，使用 browser-use 控制真实浏览器获取信息。

```python
from agents.browser_agent import BrowserAgent

agent = BrowserAgent(llm_provider="nvidia")
result = await agent.execute({"task": "搜索北京旅游景点"})
```

---

## 工具集成

### 统一工具注册中心（`tools/registry.py`）⭐

所有工具通过 `ToolRegistry` 集中注册，`build_default_registry()` 是**唯一装配点**，消除了此前"独立函数/硬编码/私有注册表"三套并存。任何 Agent（ReAct Loop 等）都从这里取工具：

```python
from tools.registry import build_default_registry

registry = build_default_registry()
registry.all_specs()              # 全部工具
registry.get_by_category("search")# 按分类取（search/weather/health/content/transaction/realtime）
registry.get("get_weather")       # 按名取
```

### 实时搜索（`tools/utility/realtime_search.py`）⭐

把"实时性"提升为一等能力，分级降级并标注时效：

```python
from tools.utility.realtime_search import realtime_search

result = realtime_search("北京到大理 机票价格", freshness="day")
# 分级：Brave API（最实时）→ Serper → DuckDuckGo → browser-use（兜底）
# 返回带 fetched_at 时间戳 + timeliness(high/medium/low)
```

> **BrowserAgent 为何是兜底**：启动真实 Chromium 慢（秒级）、依赖 Playwright 重，但能抓 JS 动态页（小红书/马蜂窝）。realtime_search 让轻量实时源（Brave/Serper）先行，browser 只在前面全失败时唤醒。

### 降级策略

所有工具遵循：**真实 API → DuckDuckGo 搜索 → Mock 数据**

### 天气工具（`tools/utility/weather.py`）

优先调用 **OpenWeather API**（需配置 `OPENWEATHER_API_KEY`），失败时降级 Mock。

支持城市自动中英文映射（大理→Dali,CN 等）。

```python
from tools.utility.weather import get_weather

result = get_weather("大理")  # 返回 JSON 字符串
```

### 搜索工具（`tools/utility/free_search.py`）

**完全免费**，使用 DuckDuckGo。

```python
from tools.utility.free_search import search_with_fallback

results = search_with_fallback("北京旅游景点")
```

降级链：`DuckDuckGo → Browser-Use → Mock`

### 机票工具（`tools/transaction/flights.py`）

使用 DuckDuckGo 搜索真实航班信息，失败时返回携程/去哪儿等订票渠道链接。

### 酒店工具（`tools/transaction/hotels.py`）

使用 DuckDuckGo 搜索真实酒店信息，失败时返回携程/美团等平台链接。

### 门票工具（`tools/transaction/tickets.py`）

使用 DuckDuckGo 搜索景点门票和活动，失败时返回参考建议。

### 平台攻略抓取（`tools/content/platform_guides.py`）⭐

从小红书、马蜂窝、携程、飞猪四大平台抓取旅游攻略与路线，三层降级策略：

1. **DuckDuckGo site 过滤搜索**（免费，返回搜索摘要）
2. **browser-use 浏览器抓取**（慢，需 playwright，返回完整正文）
3. **本地知识库兜底**（无网络时读取 `knowledge/raw_data/destinations/`）

```python
from tools.content.platform_guides import search_platform_guides, search_travel_routes

# 搜索全平台攻略
result = search_platform_guides("大理")

# 专项：路线行程单（马蜂窝 + 飞猪 + 小红书）
routes = search_travel_routes("大理")

# 专项：游记/种草笔记（小红书 + 马蜂窝）
from tools.content.platform_guides import search_destination_notes
notes = search_destination_notes("丽江")
```

### 攻略工具（`tools/content/search_guides.py`）

优先从 `knowledge/raw_data/destinations/` 本地知识库读取，未找到时用 DuckDuckGo 搜索。

### 风俗禁忌（`tools/content/local_customs.py`）

优先从 `knowledge/raw_data/customs/` 读取，未找到时用 DuckDuckGo 搜索。

### 特色体验（`tools/content/local_features.py`）

优先从 `knowledge/raw_data/features/` 读取，未找到时用 DuckDuckGo 搜索。

### 过敏原检测（`tools/health/allergen_check.py`）

基于内置14类标准过敏原关键词库（本地逻辑，无需 API）；目的地风险信息通过 DuckDuckGo 补充。

```python
from tools.health.allergen_check import check_food_allergens

result = check_food_allergens("洱海虾仁", user_allergies=["海鲜"])
```

### 药物相互作用检测（`tools/health/drug_interaction_check.py`）

检查用户正在服用的药物与食物/酒精是否存在危险相互作用（如头孢+酒精的双硫仑样反应），内置严重程度分级（fatal/high/medium）和服药禁忌时间窗口。**无需 API，完全本地运行。**

```python
from tools.health.drug_interaction_check import check_drug_interactions

result = check_drug_interactions(
    medications=["头孢克洛"],
    planned_foods=["啤酒鸭", "醉蟹"]
)
```

### 食品安全（`tools/health/food_safety_alert.py`）

使用 DuckDuckGo 搜索目的地食品安全信息；急救号码（120/110）固定内置。

---

## 上下文压缩

多轮对话下，消息历史会持续增长，导致超出 LLM token 限制。系统通过两层机制解决此问题：

**层 1 — AgentState 滑动截断（`state.py`）**

`messages` 字段使用自定义合并函数 `_keep_latest_messages`，每次追加新消息后，自动保留最新的 20 条（约 10 轮），丢弃最旧的。无需任何 API，零成本。

**层 2 — ContextManager 摘要压缩（`context_manager.py`）**

`AgentManager` 持有一个 `ContextManager` 实例，跨轮次管理完整对话历史：

- 滑动窗口：保留最近 5 轮完整对话
- LLM 摘要：超出 6000 token 时，将旧消息压缩为一段摘要，摘要始终跟随上下文传给 LLM
- 规则降级：LLM 不可用时，自动提取目的地/时间/预算等关键词作为摘要

```python
from agent_manager import AgentManager

# 支持多轮对话
manager = AgentManager()

r1 = manager.run_pipeline("我想去大理，预算5000")
r2 = manager.run_pipeline("改成丽江可以吗？")   # 上下文中有第1轮摘要
r3 = manager.run_pipeline("时间定在3月")        # 上下文中有前2轮摘要

# 查看压缩统计
print(manager.ctx.get_stats())
# {'history_turns': 3, 'estimated_tokens': 420, 'compress_count': 0}

# 持久化上下文（跨进程恢复）
state = manager.save_context()
manager.load_context(state)

# 开始全新会话
manager.reset_context()
```

**层 3 — LongTermMemory 长期记忆（`memory/long_term_memory.py`）**⭐

跨 session 持久化，进程结束后记忆保留，下次对话自动注入：

- **SQLite 存储**：用户画像（出发城市/预算/风格/同行人员）、历史行程、重要事实
- **向量语义检索**（可选，需传入 embedding_model）：ChromaDB 存储对话片段，相关历史召回
- **自动提取**：每轮 `add_turn()` 后，自动从对话中正则提取目的地、预算、风格等实体

```python
from agent_manager import AgentManager

# 启用长期记忆（默认开启）
manager = AgentManager(user_id="user_001", enable_long_term_memory=True)

# 第一次会话
r1 = manager.run_pipeline("我想从上海去大理，预算5000，喜欢美食")
manager.save_trip("大理", days=5, rating=5)

# 第二次会话（新进程，user_id 相同时自动恢复记忆）
manager2 = AgentManager(user_id="user_001")
# 每个 Agent 收到的 messages 里自动包含：
# [system] 你是旅行规划助手
# [system] [长期记忆] 出发城市=上海、预算=5000、历史行程=大理(5天 ⭐5)
# [human] 用户当前输入

# 查看用户画像
print(manager2.get_user_profile())
# {'departure_city': '上海', 'budget_range': '5000元', 'travel_style': '["美食"]', ...}

# 查看历史行程
print(manager2.get_trip_history())
```

---

### RAG 系统

**核心组件**：`knowledge/rag_manager.py`

- 向量数据库：ChromaDB `PersistentClient`（新版 API，自动持久化）
- Embedding 模型：`BAAI/bge-small-zh-v1.5`（支持中文）
- 混合检索：`knowledge/retriever.py`（向量 + BM25 RRF 融合）
- 多知识库：destinations / psychology / health / customs，各自独立 collection

```python
from knowledge.rag_manager import RAGManager

# 目的地知识库
rag = RAGManager(collection_name="travel_knowledge")
rag.add_documents(["大理是云南著名旅游城市..."])
docs = rag.retrieve("大理旅游", top_k=5)

# 心理知识库（PsychologyAgent 使用）
psych_rag = RAGManager(collection_name="psychology_knowledge")
docs = psych_rag.retrieve("旅行压力大 疲劳 怎么调节", top_k=3)
```

构建各知识库索引：
```bash
python knowledge/build_index.py --data-dir knowledge/raw_data/destinations --collection travel_knowledge
python knowledge/build_index.py --data-dir knowledge/raw_data/psychology  --collection psychology_knowledge
```

### Memory 系统

**三层记忆架构**：

短期记忆（`context_manager.py`）：滑动窗口 deque，保留最近 5 轮完整对话，超出后 LLM 摘要压缩。

长期记忆（`memory/`）：**分层架构**——`LongTermMemory`(facade) → `MemoryEngine`(治理) → `MemoryStore`(存取抽象)。治理逻辑（抽取/冲突/重要性/衰减）唯一归属 Engine；存取后端可插拔：`SqliteStore`（默认，SQLite + ChromaDB）或 `Mem0Store`（可选，Mem0 管片段+向量、内嵌 SQLite 管画像/行程/冲突）。ContextManager 在 `get_messages()` 时自动注入长期记忆。

语义记忆（`knowledge/rag_manager.py`）：ChromaDB 目的地知识库，检索景点/美食/住宿信息。

```python
from memory.long_term_memory import LongTermMemory

mem = LongTermMemory(user_id="user_001")          # 默认 SqliteStore 后端
# mem = LongTermMemory(user_id="user_001", backend="mem0")  # 可选 Mem0 后端（未装 mem0ai 自动降级）

# 自动从对话中提取实体
mem.extract_and_save("我想去大理，预算5000，喜欢美食", "好的，大理不错")

# 手动记录已完成的行程
mem.save_trip("大理", days=5, budget=4800, rating=5)

# 获取注入 Prompt 的格式化记忆
context = mem.get_memory_context("云南旅游")
# [长期记忆]
# 【用户偏好】
#   - 预算偏好：5000元
#   - 旅行风格：美食
# 【历史行程】
#   - 大理（5天） 评分5/5
```

**分层收益**：治理与存取解耦，换存储后端（SQLite/Mem0/未来 PG）不动业务代码；Mem0 只作"存储+语义检索"后端，冲突/衰减/重要性等治理永远在 Engine（source of truth）。

**长期记忆四项增强能力**：

- **记忆抽取**：正则提取（快、兜底）+ 可选 LLM 辅助（`llm=` 参数，理解隐含偏好，如"不想人挤人"→"人少/小众"），两者合并去重
- **冲突检测**：新旧偏好矛盾（预算偏差≥30%、风格无交集、城市变更）时记录到 `profile_conflicts` 表，`get_memory_context()` 注入「偏好变化提醒」让 Agent 主动确认，不静默覆盖

```python
mem._update_profile("budget_range", "5000元")
mem._update_profile("budget_range", "3000元")   # 触发冲突
conflicts = mem.get_pending_conflicts()          # [{key, old_value, new_value, ...}]
mem.resolve_conflict(conflicts[0]["id"])          # 用户确认后标记解决
```

- **记忆衰减/遗忘**：`decay_memories()` 时间衰减 `importance * exp(-λ·days)` + LRU（`last_accessed_at` 召回时刷新）+ 容量上限 500，防止无限增长
- **动态重要性评分**：按语气动态打分——强调（"一定要"）+2、否定偏好（"不喜欢"）置 4、重复出现 +1，取代固定 importance=3

```python
mem.decay_memories()   # {"decayed_removed": n, "capacity_removed": m, "remaining": k}
```


### 知识库索引构建

```bash
# 从 knowledge/raw_data/destinations/ 构建索引
python knowledge/build_index.py --data-dir knowledge/raw_data --collection travel_knowledge

# 构建示例数据
python knowledge/build_index.py --sample
```

---

## Agent 高级能力

以下能力使系统达到生产级 Agent 完整度。全部为**可选启用 + 优雅降级**，关闭后行为与基础版一致。

### Reflection 反思与自纠错（`agents/reflection.py`）

Agent 执行后自动验证输出质量，不合格时注入 critique 重试。

- `ReflectionMixin.execute_with_reflection()`：执行 → 验证 → 失败重试的闭环
- 验证器：`ParseOutputValidator`（字段/格式/日期逻辑）、`TravelPlanValidator`（完整度/预算合理性）、`LLMJudgeValidator`（LLM 综合评分）
- LangGraph 回环边：`main.py` 中 `parse_agent → 验证 → retry`，`MAX_REFLECTION_RETRIES=2` 防死循环

### Agent Loop — ReAct 循环（`agents/react_agent.py`）⭐

`Think → Act → Observe` 迭代循环，LLM 每轮自主决定调用哪个工具或给出答案，工具调用由推理动态驱动（区别于固定 Pipeline 的硬编码）。

```python
from agent_manager import AgentManager

manager = AgentManager()
# 复杂开放式查询走 ReAct（多次动态取数）
result = manager.run_react("对比大理和丽江，哪个更适合带老人，顺便看看天气")
print(result["data"]["answer"])
print(result["data"]["scratchpad"])  # 每轮 Think/Action/Observation
```

- 简单意图走 `run_pipeline()`（快/省 token），复杂查询走 `run_react()`——两者共存
- 复用 `BudgetLimiter` 限制工具调用次数；工具异常隔离；`max_iterations` 强制终止

### Guardrails 安全护栏（`guardrails/`）

三层中间件防护，不侵入 Agent 逻辑：

- **InputGuard**：Prompt Injection 检测、PII 自动脱敏（身份证/银行卡/手机号/邮箱）、内容安全黑名单、长度限制
- **OutputGuard**：幻觉检测（"已为您预订"等）、PII 泄露检查、置信度评估与标记
- **BudgetLimiter**：会话 token 上限（默认 50k）、每小时请求数（30）、单请求工具调用数（10）

```python
manager = AgentManager(enable_guardrails=True)  # 默认开启
# 注入攻击、超长输入、敏感信息自动拦截或脱敏
```

### 动态规划 Plan-and-Execute（`planning/planner.py`）

复杂目标先分解为带依赖的子任务，执行中可重规划。

```python
from planning import Planner

planner = Planner(llm=my_llm)   # 无 llm 时规则降级
plan = planner.create_plan("规划从上海到大理5天游，含机票酒店")
step = plan.next_step()          # 依赖调度：先执行无依赖步骤
plan = planner.replan(plan, observation="机票已查到均价800")  # 动态重规划
```

### 可观测性（`observability/tracer.py`）

结构化调用链追踪，弥补纯 logging 的不足。

```python
manager = AgentManager(enable_tracing=True)  # 默认开启
result = manager.run_pipeline("我想去大理")
print(manager.get_trace_summary())   # token/延迟/成功率/各 Agent 统计
manager.export_traces("logs/traces/")  # 导出 JSON，可对接 LangSmith
```

### 异步并行执行（`async_executor.py`）

无依赖的工具调用并行化，降低延迟。

```python
from async_executor import parallel_execute

results = parallel_execute([
    lambda: get_weather("大理"),
    lambda: search_travel_guides("大理"),
    lambda: rag.retrieve("大理旅游"),
], task_names=["weather", "guides", "rag"])
```

### 流式输出（`streaming.py`）

全链路实时事件回调（观察者模式），9 种事件类型。

```python
from streaming import StreamingCallback, ConsoleStreamListener

cb = StreamingCallback()
cb.add_listener(ConsoleStreamListener())
manager = AgentManager(streaming_callback=cb)  # token 级流式 + Agent/工具进度
```

### 评估框架（`evaluation/`）

```bash
# 运行评估（20 个测试用例 + 6 项指标）
python evaluation/run_eval.py

# 启用 LLM-as-Judge 综合评分（有 API 成本）
python evaluation/run_eval.py --llm-judge

# 只评估某分类
python evaluation/run_eval.py --category basic_planning --max 5
```

指标：意图准确率、实体提取 F1、行程完整度、预算合理性、响应时间、LLM 综合评分。

### Human-in-the-Loop（`agent_manager.py`）

关键决策点注入用户确认钩子：

```python
def my_confirm(question, options):
    print(question)
    return input(f"选择 {options}: ")

manager = AgentManager(confirm_callback=my_confirm)
# Parse 后会确认目的地/预算，用户可确认/修改/取消
```

---

## MCP 协议集成

通过 `mcp_config.yaml` 配置，由 `mcp_client.py` 统一管理。

| MCP 服务器 | 实现 | 功能 | 状态 |
|-----------|------|------|------|
| weather | `tools/mcp_servers/openweather_server.py` | 天气查询 | ✅ enabled |
| baidu_maps | `tools/mcp_servers/baidu_maps_server.py` | 地点搜索/路线 | ✅ enabled |
| brave_search | npx @modelcontextprotocol/server-brave-search | 网络搜索 | ✅ enabled |
| filesystem | npx @modelcontextprotocol/server-filesystem | 本地文件 | ✅ enabled |

```python
from mcp_client import MCPManager

with MCPManager() as mcp:
    result = mcp.call_tool("weather", "current_weather", {"city": "Beijing", "country": "CN"})
```

---

## 项目结构

```
AI_Agent_Travel_System/
├── main.py                      # LangGraph 图编排入口（含 Reflection 回环边）
├── agent_manager.py             # AgentManager（护栏/流式/HITL/tracing/run_react）
├── config.py                    # 全局配置（读取 .env）
├── state.py                     # AgentState 类型定义（含 reflection/react 字段）
├── llm_config.py                # 多 LLM 统一配置管理
├── rag_memory_system.py         # RAG + Memory 一体化系统（设计文档）
├── mcp_client.py                # MCP 客户端管理器
├── mcp_config.yaml              # MCP 服务器配置
├── async_executor.py            # 异步并行执行器 ⭐
├── streaming.py                 # 流式输出回调（观察者模式）⭐
├── requirements.txt             # Python 依赖
│
├── memory/                      # 长期记忆模块（分层架构）⭐
│   ├── __init__.py
│   ├── long_term_memory.py      # Facade（向后兼容，委托 Engine）
│   ├── engine.py                # MemoryEngine 治理层（抽取/冲突/重要性/衰减）
│   ├── store/
│   │   ├── base.py              # MemoryStore 存取抽象
│   │   ├── sqlite_store.py      # 默认后端（SQLite + ChromaDB）
│   │   └── mem0_store.py        # 可选后端（Mem0 片段+向量 / SQLite 画像+行程+冲突）
│   └── data/                    # 用户记忆数据库（.db 文件）
│
├── guardrails/                  # 安全护栏 ⭐
│   ├── input_guard.py           # 注入检测 + PII 脱敏 + 内容安全
│   ├── output_guard.py          # 幻觉检测 + PII 泄露 + 置信度
│   ├── budget_limiter.py        # token/请求/工具调用限流
│   └── config.py                # 护栏配置
│
├── evaluation/                  # 评估框架 ⭐
│   ├── dataset.py               # 评估数据集管理
│   ├── evaluator.py             # 评估器核心
│   ├── metrics.py               # 6 项评估指标
│   ├── judges.py                # LLM-as-Judge 评分
│   ├── run_eval.py              # 评估入口脚本
│   └── test_cases/              # 20 个预置测试用例
│
├── observability/               # 可观测性 ⭐
│   ├── __init__.py
│   └── tracer.py                # Trace/Span 调用链 + 指标 + 导出
│
├── planning/                    # 动态规划 ⭐
│   ├── __init__.py
│   └── planner.py               # Plan-and-Execute 任务分解 + 重规划
│
├── agents/                      # Agent 节点
│   ├── base_agent.py            # 抽象基类（模板方法 + ReflectionMixin + 错误重试）
│   ├── reflection.py            # 反思自纠错（Mixin + 验证器 + LLMJudge）⭐
│   ├── react_agent.py           # ReAct 循环 Agent（Think-Act-Observe）⭐
│   ├── parse_agent_v2.py        # 需求解析 + 意图路由 + 反思验证（推荐使用）
│   ├── parse_agent.py           # 旧版 ParseAgent（LangGraph 用）
│   ├── recommend_agent.py       # 双向推荐 Agent
│   ├── plan_agent.py            # 行程规划 Agent
│   ├── travel_agent.py          # 旅行规划（LangGraph 节点）
│   ├── destination_agent.py     # 目的地推荐（独立版）
│   ├── food_agent.py            # 美食营养 Agent
│   ├── merge_agent.py           # 内容融合 Agent
│   ├── output_agent.py          # 报告生成 Agent
│   ├── psychology_agent.py      # 心理健康 Agent
│   └── browser_agent.py         # 浏览器自动化（兜底）
│
├── tools/                       # 工具层
│   ├── registry.py              # 统一工具注册中心（ToolRegistry + build_default_registry）⭐
│   ├── utility/
│   │   ├── realtime_search.py   # 实时搜索（Brave→Serper→DDG→browser 分级 + 时效标注）⭐
│   │   ├── free_search.py       # DuckDuckGo 免费搜索（降级链）
│   │   ├── weather.py           # OpenWeather API → Mock
│   │   ├── weather_v2.py        # MCP 天气
│   │   ├── map_route.py         # 路线规划
│   │   ├── map_route_v2.py      # 百度地图 MCP
│   │   └── search_v3.py         # MCP + 浏览器兜底搜索
│   ├── content/
│   │   ├── platform_guides.py   # 四平台攻略抓取（DDG site过滤 → browser-use → 本地）⭐
│   │   ├── search_guides.py     # 攻略搜索（本地 → DuckDuckGo）
│   │   ├── search_guides_v2.py  # 攻略搜索（MCP 版）
│   │   ├── local_customs.py     # 风俗禁忌（本地 → DuckDuckGo）
│   │   └── local_features.py    # 特色体验（本地 → DuckDuckGo）
│   ├── transaction/
│   │   ├── flights.py           # 机票搜索（DuckDuckGo → 参考链接）
│   │   ├── hotels.py            # 酒店搜索（DuckDuckGo → 参考链接）
│   │   └── tickets.py           # 门票搜索（DuckDuckGo → 参考链接）
│   ├── health/
│   │   ├── allergen_check.py         # 过敏原检测（内置14类知识库 + DuckDuckGo）
│   │   ├── drug_interaction_check.py # 药物-食物相互作用（内置，无需API）
│   │   └── food_safety_alert.py      # 食品安全预警（DuckDuckGo → 通用建议）
│   └── mcp/
│       └── mcp_client.py        # MCP 客户端封装（单例）
│
├── tools/mcp_servers/           # MCP 服务器实现
│   ├── openweather_server.py    # OpenWeather MCP Server
│   ├── baidu_maps_server.py     # 百度地图 MCP Server
│   └── custom_travel_server.py  # 自定义旅行数据 Server
│
├── knowledge/                   # 知识库
│   ├── rag_manager.py           # RAG 管理器（ChromaDB）
│   ├── retriever.py             # 混合检索器（向量 + BM25）
│   ├── build_index.py           # 离线索引构建脚本
│   ├── raw_data/
│   │   ├── destinations/        # 目的地：dali/lijiang/sanya.json
│   │   ├── psychology/          # 心理知识：压力类型/情绪管理/同行心理 ⭐
│   │   ├── health/              # 健康知识：高原反应/时差/水土不服 ⭐
│   │   └── customs/             # 风俗礼仪：旅行礼仪/宗教场所 ⭐
│   └── vector_db/               # ChromaDB 持久化目录
│
├── web/
│   ├── app_v2.py                # Streamlit Web UI（推荐）
│   └── app.py                   # 实验版 Web UI
│
├── output/
│   ├── reports/                 # 客户报告（Markdown）
│   └── social/                  # 自媒体素材（JSON）
│
├── tests/
│   ├── test_parse_agent.py
│   ├── test_travel_agent.py
│   ├── test_llm_config.py
│   ├── test_rag.py
│   ├── test_output_agent.py
│   └── test_new_modules.py      # 新能力集成测试（12 项：护栏/反思/评估/记忆/ReAct/可观测/规划等）⭐
│
└── logs/
    ├── agent.log
    ├── browser_agent.log
    └── traces/                  # 可观测性调用链导出目录
```

---

## 测试指南

### 运行所有测试

```bash
pytest tests/ -v
```

### 运行新能力集成测试（无需 API Key，离线可跑）

```bash
python tests/test_new_modules.py
# 覆盖 12 项：输入/输出护栏、限流、流式、异步并行、评估数据集/指标、
#            长期记忆增强、ReAct Loop、可观测性、动态规划、错误重试
```

### 测试天气工具（真实 API）

```bash
python tools/utility/weather.py
```

### 测试搜索工具

```bash
python tools/utility/free_search.py
```

### 测试 MCP 服务器

```bash
# OpenWeather MCP
OPENWEATHER_API_KEY=your_key python tools/mcp_servers/openweather_server.py test

# 百度地图 MCP
BAIDU_MAPS_API_KEY=your_key python tools/mcp_servers/baidu_maps_server.py test
```

### 测试 AgentManager Pipeline

```bash
python agent_manager.py
```

---

## 常见问题

### Q1: 天气查询返回模拟数据？

检查 `.env` 中是否配置 `OPENWEATHER_API_KEY`，或 API Key 是否有效。

### Q2: 机票/酒店搜索没有返回价格？

当前通过 DuckDuckGo 搜索，返回的是搜索结果链接而非结构化价格数据。如需精确价格，需对接携程/去哪儿等开放 API。

### Q3: DuckDuckGo 搜索失败？

网络问题，系统会自动降级到 Mock 数据或参考链接。可安装 VPN 或改用 Brave Search（需配置 `BRAVE_SEARCH_API_KEY`）。

### Q4: RAG 检索没有结果？

需要先构建索引：

```bash
python knowledge/build_index.py --sample
```

### Q5: 如何添加新目的地到知识库？

在 `knowledge/raw_data/destinations/` 创建 JSON 文件，然后重建索引：

```bash
python knowledge/build_index.py --data-dir knowledge/raw_data
```

### Q6: 如何切换 LLM？

修改 `.env`：

```bash
DEFAULT_LLM_PROVIDER=deepseek
DEEPSEEK_API_KEY=your_key
```

各 Agent 目前读取 `OPENAI_API_KEY/OPENAI_API_BASE/OPENAI_MODEL`，设置这三个变量可以指向任意 OpenAI 兼容接口。

### Q7: browser-use 相关依赖报错？

```bash
pip install browser-use playwright
playwright install chromium
```

---

### Q8: requirements.txt 里的版本号与实际安装冲突？

`requirements.txt` 已更新为 `>=` 宽松约束。旧版固定版本（如 `langchain==0.1.20`）与 `langchain-openai` 存在依赖冲突，直接使用最新兼容版本即可：

```bash
pip install -r requirements.txt
```

chromadb 和 sentence-transformers 体积较大，安装时间较长（3-5 分钟），请耐心等待。

---

**最后更新**: 2026-07-13

**版本**: v1.6.0
