# 项目更新日志

## V1.7 - 长期记忆分层重构 + Mem0 可插拔后端（2026-07-14）

### 动机

`memory/long_term_memory.py` 原是 471 行单体类，把**治理**（抽取/冲突/重要性/衰减）和**存取**（SQLite + ChromaDB）揉在一起，换存储后端/接 Mem0 都得改内部。对齐参考架构做分层解耦。

### 1. 治理与存取分层 ⭐

```
LongTermMemory (facade, 向后兼容)
    └── MemoryEngine (治理, source of truth)
            └── MemoryStore (存取抽象)
                    ├── SqliteStore (默认: SQLite + ChromaDB)
                    └── Mem0Store  (可选: Mem0 片段+向量 / 内嵌 SQLite 画像+行程+冲突)
```

- **memory/store/base.py**：`MemoryStore` 抽象，按数据类别分方法（profile kv / memories 片段 / trips / conflicts / vector），不硬塞单一 CRUD
- **memory/store/sqlite_store.py**：现有 SQLite + ChromaDB 存取原样迁入（保留 macOS PRAGMA、`last_accessed_at` 平滑升级、Chroma 降级）
- **memory/engine.py**：`MemoryEngine` 收拢全部治理——抽取（正则+LLM）、冲突检测、动态重要性、衰减、context 拼装。衰减策略在 Engine，删除由 Store 执行
- **memory/long_term_memory.py**：改薄成 facade，8 个公共方法委托 Engine/Store，`.conn`/`_score_importance`/`_update_profile` 保留（向后兼容）

### 2. Mem0 作为可插拔后端真接入 ⭐

- **memory/store/mem0_store.py**：混合后端——Mem0 管"记忆片段 + 语义检索"，内嵌 SqliteStore 管"画像/行程/冲突"（解决 Mem0 扁平记忆 vs 结构化画像的阻抗失配）
- 用法：`LongTermMemory(backend="mem0")`；未装 mem0ai 或初始化失败 → **自动降级 SqliteStore**，不崩
- Mem0 后端下关闭 Engine 容量上限，避免与 Mem0 自身记忆管理双重治理
- 默认 config：DeepSeek(LLM) + 本地 HF embedding(bge-small-zh) + Chroma 向量库
- `requirements.txt` 加 `mem0ai>=0.1.0`（可选依赖，注释说明）

### 零破坏

- 8 个公共方法签名不变（只加可选 `backend` 参数，有默认值）
- 外部 6 处调用点（context_manager/agent_manager/parse_agent_v2/recommend_agent/run_eval）零改动
- `tests/test_new_modules.py` 14 项全绿，新增分层架构断言（Facade→Engine→Store）
- 切 Mem0 后端**不迁移**历史 ChromaDB 向量（新旧后端独立）

### 改动文件

| 操作 | 文件 |
|------|------|
| 新增 | `memory/store/__init__.py`, `base.py`, `sqlite_store.py`, `mem0_store.py` |
| 新增 | `memory/engine.py`（MemoryEngine 治理层）|
| 重写 | `memory/long_term_memory.py`（471 行单体 → 薄 facade）|
| 修改 | `requirements.txt`（+mem0ai 可选）|
| 修改 | `tests/test_new_modules.py`（+分层断言）|

---

## V1.6 - 架构收敛：统一工具层 + 实时搜索 + 知识库扩展（2026-07-13）

### 1. 统一工具注册中心 ToolRegistry (`tools/registry.py`) ⭐

消除此前"独立函数 / 硬编码进 Agent / ReActAgent 私有注册表"三套并存的混乱：

- **ToolSpec 上移**：从 `agents/react_agent.py` 移至 `tools/registry.py` 作为全项目统一工具单元，react_agent 改为 re-export（向后兼容）
- **ToolRegistry**：支持按名称（`get`）、按分类（`get_by_category`）检索；分类含 search/weather/health/content/transaction/realtime/knowledge
- **build_default_registry()**：唯一工具装配点，集中懒加载包装全部现有工具（单个失败跳过），不改工具本身
- **AgentManager 集成**：`_build_react_tools()` 改为走 `get_default_registry()`，删除重复手工包装

### 2. 独立实时搜索 realtime-search (`tools/utility/realtime_search.py`) ⭐

把"实时性"从降级链兜底提升为一等能力（旅行场景机票/天气/开放状态是刚需）：

- **分级降级**：Brave Search API（freshness 参数，最实时）→ Serper API → DuckDuckGo（免费兜底）→ browser-use（重武器）
- **时效标注**：结果统一带 `fetched_at` 时间戳 + `timeliness`（high/medium/low）
- **BrowserAgent 定位明确**：仍是最后兜底——启动真实 Chromium 慢、依赖 Playwright 重，但能抓 JS 动态页（小红书/马蜂窝）；realtime_search 让轻量实时源先行
- 复用现有 `BRAVE_SEARCH_API_KEY`/`SERPER_API_KEY` 配置，注册进 ToolRegistry（category=search+realtime）

### 3. 知识库扩展 + PsychologyAgent 走 RAG ⭐

补齐此前只有 3 个 destinations、PsychologyAgent 全靠硬编码规则的短板：

- **新增知识库**（`knowledge/raw_data/`）：
  - `psychology/`：旅行压力类型（行程焦虑/社交耗竭/疲劳累积）、情绪管理（4-7-8呼吸法/正念/情绪日记）、同行心理（独行/情侣/家庭/朋友）
  - `health/`：高原反应、时差调整、水土不服（均标注"仅供参考、非医疗建议"）
  - `customs/`：通用旅行礼仪、宗教场所注意事项
- **PsychologyAgent 接入 RAG**：构造 `RAGManager(collection_name="psychology_knowledge")`，在生成个性化建议前检索心理专业知识注入 Prompt；规则评分作为兜底始终保留
- **修复 bug**：PsychologyAgent 的 `super().__init__()` 缺 `name` 参数、缺 `execute()` 实现，一并补齐
- **索引构建**：`python knowledge/build_index.py --data-dir knowledge/raw_data/psychology --collection psychology_knowledge`

### RAGManager 升级到新版 chromadb API ⭐

修复此前"建索引降级为 JSON 存储、RAG 无法真正向量检索"的问题：

- `knowledge/rag_manager.py`：`chromadb.Client(Settings(chroma_db_impl=...))`（已废弃）→ `chromadb.PersistentClient(path=...)`，自动持久化，移除 `client.persist()`
- 新增 `add_documents()` 方法（build_index / HybridRetriever 复用），`get_or_create_collection` 一步建集合
- `retrieve()` 加空集合保护 + `n_results` 不超过实际条数
- `build_index.py`：加 `sys.path` 修复直跑时 `import knowledge` 失败；降级条件从 `ImportError` 放宽到 `Exception`
- **效果**：`psychology_knowledge`（10 条）、`travel_knowledge`（3 条）均已构建为**真实向量索引**，PsychologyAgent 的 RAG 检索实测生效（余弦距离排序正确）

### 修复 rag_memory_system.py 文件损坏 ⭐

`rag_memory_system.py`（README 定位为"RAG + Memory 一体化实现"）此前被**误写入了 220 行 Markdown 设计文档 + 泄漏的工具调用标记**（`<function_calls>` 等），导致整个文件语法错误、无法导入——沦为了"伪实现"。

- **还原为真正的可运行实现**：剥离顶部混入的 Markdown/泄漏标记，保留其中完整的 `RAGMemorySystem` 类（RAG 检索 + 短期记忆 deque + 长期记忆 JSON 持久化 + `build_context` 上下文构建）
- 同步升级 chromadb 新版 API（`PersistentClient`）+ `retrieve()` 空集合保护
- 现已可正常 `from rag_memory_system import RAGMemorySystem` 并实例化运行
- `tests/test_rag.py` 的 6 个用例全部通过（此前 test_import_rag_system 因文件损坏失败）

### 已知问题（既有，非本次引入）

- ~~RAGManager 用旧版 chromadb API~~ → 本版已修复
- ~~rag_memory_system.py 文件损坏无法导入~~ → 本版已修复
- `tests/test_parse_agent.py` / `test_travel_agent.py` / `test_output_agent.py` 依赖 langchain 运行环境，未装依赖时收集报错（与本次改动无关）；离线可跑 `tests/test_new_modules.py`（14 项全绿）和 `tests/test_rag.py`（6 项全绿）

### 改动文件

| 操作 | 文件 |
|------|------|
| 新增 | `tools/registry.py`（ToolRegistry + build_default_registry）|
| 新增 | `tools/utility/realtime_search.py` |
| 新增 | `knowledge/raw_data/{psychology,health,customs}/*.json`（8 个文件）|
| 修改 | `agents/react_agent.py`（ToolSpec re-export）|
| 修改 | `agents/psychology_agent.py`（修 init + 接 RAG）|
| 修改 | `agent_manager.py`（`_build_react_tools` 走 registry）|
| 修改 | `tools/utility/__init__.py`（导出 realtime_search）|
| 修改 | `knowledge/rag_manager.py`（升级 chromadb PersistentClient + add_documents）|
| 修改 | `knowledge/build_index.py`（sys.path 修复 + 降级条件放宽）|
| 修复 | `rag_memory_system.py`（还原为可运行实现，剥离误入的文档/泄漏标记 + 升级 chromadb）|
| 修改 | `tests/test_new_modules.py`（14 项测试全绿）|
| 修改 | `tests/test_rag.py`（6 项全绿）|

---

## V1.5 - 长期记忆增强 + Agent Loop + 能力补全（2026-07-08）

### 长期记忆四项能力补齐 (`memory/long_term_memory.py`)

- **冲突检测**：新旧偏好矛盾（预算偏差≥30%、风格无交集、城市变更）时记录到 `profile_conflicts` 表，`get_memory_context()` 注入「偏好变化提醒」让 Agent 主动确认，不再静默覆盖
- **记忆衰减/遗忘**：`decay_memories()` 时间衰减公式 `importance * exp(-λ·days)` + LRU（`last_accessed_at`）+ 容量上限 500，防止无限增长
- **动态重要性评分**：`_score_importance()` 按语气动态打分（强调 +2、否定偏好置 4、重复 +1），取代固定 importance=3
- **LLM 辅助提取**：`_llm_extract_entities()` 理解隐含偏好（"不想人挤人"→"人少/小众"），与正则结果合并去重；无 LLM 时降级正则

### Agent Loop — ReAct 循环 (`agents/react_agent.py`) ⭐

- **Think→Act→Observe 循环**：LLM 每轮自主决定调用哪个工具或给出最终答案，工具调用次数由推理动态驱动（区别于固定 Pipeline 的硬编码）
- **工具注册表**：`ToolSpec` 包装现有工具（天气/搜索/攻略/机票/酒店/RAG），不改工具本身
- **安全约束**：复用 `BudgetLimiter` 限制工具调用次数；工具异常隔离为 observation，循环继续
- **强制终止**：达到 `max_iterations` 时用已有信息强制生成答案
- **共存策略**：`AgentManager.run_react()` 与固定 Pipeline 并存——简单意图走 Pipeline（快/省），复杂开放式查询走 ReAct

### 补全剩余能力

- **可观测性 (`observability/tracer.py`)**：Trace/Span 调用链追踪、token/延迟/成功率指标、JSON 导出。`AgentManager` 每个 Agent 执行自动记 span，`get_trace_summary()` / `export_traces()` 查看
- **错误重试 (`agents/base_agent.py`)**：`_invoke_with_fallback` 增加瞬时错误（超时/限流/5xx）指数退避重试，永久错误（认证/4xx）直接降级；`_is_transient_error()` 区分
- **动态规划 (`planning/planner.py`)**：Plan-and-Execute，`create_plan()` 把复杂目标分解为带依赖的子任务，`replan()` 执行中重规划；无 LLM 时规则降级

### 改动文件

| 操作 | 文件 |
|------|------|
| 修改 | `memory/long_term_memory.py`（冲突/衰减/重要性/LLM提取）|
| 新增 | `agents/react_agent.py`（ReAct 循环 Agent）|
| 新增 | `observability/__init__.py`, `tracer.py` |
| 新增 | `planning/__init__.py`, `planner.py` |
| 修改 | `agents/base_agent.py`（错误重试 + 退避）|
| 修改 | `agent_manager.py`（run_react + 工具注册 + tracing + 透传 llm 给记忆）|
| 修改 | `state.py`（react_scratchpad / react_iterations / react_answer）|
| 修改 | `tests/test_new_modules.py`（12 项测试全绿）|

### 能力覆盖总览（截至本版本）

| 能力 | 状态 | 实现位置 |
|------|------|----------|
| 反思/自纠错 | ✅ | `agents/reflection.py` |
| 人机交互确认 | ✅ | `agent_manager.py` confirm_callback |
| 可观测性 | ✅ | `observability/tracer.py` |
| 错误重试 | ✅ | `agents/base_agent.py` 退避重试 |
| 动态规划 | ✅ | `planning/planner.py` |
| 评估框架 | ✅ | `evaluation/` |
| 安全护栏 | ✅ | `guardrails/` |
| 异步并行 | ✅ | `async_executor.py` |
| 流式输出 | ✅ | `streaming.py` |
| Agent Loop | ✅ | `agents/react_agent.py` |
| 记忆-冲突检测 | ✅ | `long_term_memory.py` |
| 记忆-衰减遗忘 | ✅ | `long_term_memory.py` |
| 记忆-重要性排序 | ✅ | `long_term_memory.py` |
| 记忆-LLM辅助提取 | ✅ | `long_term_memory.py` |

---

## V1.4 - Agent 系统核心能力补齐（2026-07-08）

### 新功能

#### 1. Reflection 反思与自纠错 (`agents/reflection.py`) ⭐

Agent 执行后自动验证输出质量，失败时注入 critique 重试：

- **ReflectionMixin**：混入 BaseAgent，任何 Agent 可复用 `execute_with_reflection()`
- **ParseOutputValidator**：规则式验证（intent 合法、字段完整、日期格式、预算正数）
- **TravelPlanValidator**：行程完整度 + 预算合理性（偏差 ≤30%）
- **LLMJudgeValidator**：LLM-as-Judge 综合评分（信息完整/逻辑一致/实用性/个性化）
- **LangGraph 回环边**：`main.py` 中 parse_agent → validate → retry 闭环

#### 2. Guardrails 安全护栏 (`guardrails/`) ⭐

三层防护中间件，不侵入 Agent 逻辑：

- **InputGuard**：Prompt Injection 检测、PII 自动脱敏（身份证/银行卡/手机号/邮箱）、内容安全黑名单、长度限制
- **OutputGuard**：幻觉检测（"已为您预订"等）、PII 泄露检查、置信度评估与标记
- **BudgetLimiter**：会话 token 上限（50k）、每小时请求限制（30次）、工具调用限制（10次/请求）

#### 3. Evaluation 评估框架 (`evaluation/`) ⭐

可重复运行的 Agent 质量评估 Pipeline：

- **20 个预置测试用例**：覆盖 7 个分类（基础规划/时间推荐/目的地推荐/模糊输入/健康感知/对比/特殊需求）
- **6 项评估指标**：意图准确率、实体提取 F1、行程完整度、预算合理性、响应时间、工具成功率
- **LLM-as-Judge**：综合质量评分（0-10），四维度加权（完整性×0.3 + 一致性×0.25 + 实用性×0.25 + 个性化×0.2）
- **自动报告生成**：JSON + Markdown 格式，含分类统计和失败用例分析

#### 4. 异步并行执行 (`async_executor.py`)

无依赖工具调用并行化，显著降低延迟：

- **AsyncExecutor**：信号量控制并发（默认 5）、单任务超时保护、错误隔离
- **parallel_execute()**：便捷同步接口，自动处理事件循环
- **ThreadPoolExecutor 降级**：在已有 async 上下文中自动降级为线程池

#### 5. 流式输出贯通 (`streaming.py`)

全链路实时事件回调：

- **StreamingCallback**：观察者模式，9 种事件类型（pipeline/agent/tool/reflection/error）
- **ConsoleStreamListener**：终端调试用格式化输出
- **CollectorListener**：测试用事件收集器
- **BaseAgent 集成**：`_invoke_with_fallback` 支持逐 token 回调

#### 6. Human-in-the-Loop (`agent_manager.py`)

关键决策点注入用户确认钩子：

- **confirm_callback**：签名 `(question, options) -> str`
- **决策点**：Parse 后确认目的地和预算
- **Web UI / CLI 通用**：Streamlit 用 `st.radio`，CLI 用 `input()`

### 改动文件

| 操作 | 文件 |
|------|------|
| 新增 | `agents/reflection.py` |
| 新增 | `guardrails/__init__.py`, `config.py`, `input_guard.py`, `output_guard.py`, `budget_limiter.py` |
| 新增 | `evaluation/__init__.py`, `dataset.py`, `evaluator.py`, `metrics.py`, `judges.py`, `run_eval.py` |
| 新增 | `evaluation/test_cases/travel_cases.json` |
| 新增 | `async_executor.py` |
| 新增 | `streaming.py` |
| 新增 | `tests/test_new_modules.py` |
| 修改 | `agents/base_agent.py` — 混入 ReflectionMixin + streaming_callback |
| 修改 | `agents/parse_agent_v2.py` — 集成反思验证 |
| 修改 | `agent_manager.py` — 集成 Guardrails + Streaming + HITL |
| 修改 | `main.py` — LangGraph 增加 Reflection 回环边 |
| 修改 | `state.py` — 新增 reflection/guardrail 字段 |

---

## V1.3 - 长期记忆（2026-07-07）

### 新功能

#### 1. 长期记忆（`memory/long_term_memory.py`）⭐

跨 session 持久化用户偏好和历史行程：

- **SQLite 存储**：用户画像（出发城市/预算/旅行风格/同行人员）、历史行程评分、重要事实
- **向量语义检索**（可选）：ChromaDB 存储对话片段，相关历史召回
- **自动实体提取**：正则从对话中提取目的地/预算/风格/同行人，写入 `extract_and_save()`
- **三层降级**：向量检索 → SQLite 关键词检索 → 空结果

#### 2. ContextManager 集成长期记忆

- `add_turn()` / `add_assistant_message()` 自动写长期记忆
- `get_messages(query)` 自动将用户画像 + 相关历史注入 system 消息
- 短期记忆（压缩摘要）和长期记忆独立管理，互不干扰

#### 3. AgentManager 新增长期记忆接口

- 构造参数新增：`user_id`、`enable_long_term_memory`、`embedding_model`
- 新增方法：`save_trip()`、`get_user_profile()`、`get_trip_history()`
- `reset_context()` 只清短期记忆，长期记忆永久保留

#### 4. ParseAgent 和 RecommendAgent 注入长期记忆

每个 Agent 现在直接感知用户历史偏好：

**ParseAgent（`agents/parse_agent_v2.py`）**
- `__init__` 新增 `long_term_memory` 参数
- `execute()` 构造 messages 时插入长期记忆 system 消息
- 效果：LLM 解析意图时可参考历史预算/偏好，减少用户重复输入

**RecommendAgent（`agents/recommend_agent.py`）**
- `__init__` 新增 `long_term_memory` 参数
- `_recommend_destination()` 和 `_recommend_time()` 的 `system_prompt` 内嵌 `mem_context`
- 效果：推荐目的地时自动避开评分低的历史行程，优先匹配历史风格偏好

**AgentManager**
- `_register_agents()` 传入 `long_term_memory=self.long_term_memory`，两个 Agent 共用同一实例

---

### 新功能

#### 1. 多轮对话上下文压缩（`context_manager.py`）

长对话下 token 无限增长的问题彻底解决，双层方案：

- **层 1 — AgentState 截断**：`state.py` 中用 `_keep_latest_messages` 替换 `operator.add`，消息超过 20 条自动截断最旧消息
- **层 2 — ContextManager 摘要**：`context_manager.py` 新增独立模块，滑动窗口保留最近 5 轮 + LLM 摘要压缩历史，规则降级（无 LLM 时提取目的地/时间/预算关键词）
- 支持持久化：`save_context()` / `load_context()`，跨进程恢复对话

```python
manager = AgentManager()
r1 = manager.run_pipeline("我想去大理，预算5000")
r2 = manager.run_pipeline("改成丽江可以吗")   # 自动带历史摘要
print(manager.ctx.get_stats())
manager.reset_context()   # 新会话
```

#### 2. 药物-食物相互作用检测（`tools/health/drug_interaction_check.py`）

从 travel_system 补充，内置高危组合规则，无需外部 API：

- 头孢类 + 酒精 → 双硫仑样反应（severity: fatal）
- 华法林 + 维生素K食物 → 抗凝失效
- MAO 抑制剂 + 酪胺食物 → 高血压危象
- 已注册到 `tools/health/__init__.py`

#### 3. 四平台攻略抓取（`tools/content/platform_guides.py`）⭐

新增从小红书、马蜂窝、携程、飞猪四大平台抓取旅游攻略与路线，三层降级：

1. **DuckDuckGo site 过滤搜索**（免费，返回搜索摘要）
2. **browser-use 浏览器抓取**（需 playwright，返回完整正文）
3. **本地知识库兜底**（无网络时读取 `knowledge/raw_data/destinations/`）

提供三个便捷函数：
- `search_platform_guides(destination)` — 全平台搜索
- `search_travel_routes(destination)` — 专项路线（马蜂窝+飞猪+小红书）
- `search_destination_notes(destination)` — 游记/种草（小红书+马蜂窝）

#### 4. 完整 `.env.example`

覆盖所有配置项：5+ LLM 提供商、4 个工具 API、RAG、系统参数，含申请链接和说明。

#### 5. `requirements.txt` 修正

固定版本（如 `langchain==0.1.20`）与 `langchain-openai` 存在依赖冲突，全部改为 `>=` 宽松约束；新增 `duckduckgo-search` 依赖。

### Bug 修复

- `tools/transaction/flights.py` / `hotels.py` / `tickets.py` — 中文弯引号 `"…"` 在 f-string 中触发语法错误，已修正
- `tools/content/local_features.py` — 同上
- `tools/transaction/__init__.py` — 导入了不存在的 `get_flight_price_trend`、`get_hotel_recommendations`，已移除

---

## V3 - MCP 集成版（2026-06-01）

### 新功能

#### 1. 真实的 MCP (Model Context Protocol) 集成

**新增文件：**
- `mcp_config.yaml` - MCP Servers 配置文件
- `mcp_client.py` - MCP 客户端管理器
- `tools/utility/weather_v2.py` - 天气工具（MCP 版）
- `tools/content/search_guides_v2.py` - 搜索工具（MCP 版）
- `tools/mcp_servers/custom_travel_server.py` - 自定义 MCP Server
- `MCP_集成指南.md` - 详细的 MCP 使用文档

**集成的 MCP Servers：**
- ✅ **OpenWeather** - 实时天气查询
- ✅ **Brave Search** - 网络搜索
- ✅ **百度地图** - 地图/路线规划
- ✅ **Filesystem** - 本地文件访问

---

## V2 - Agent 模块化 + 智能推荐（2026-06-01）

### 新功能

#### 1. Agent 模块化架构

**新增文件：**
- `agents/base_agent.py` - Agent 基类
- `agents/parse_agent_v2.py` - 支持独立调用的解析 Agent
- `agents/recommend_agent.py` - 智能推荐 Agent
- `agent_manager.py` - Agent 统一管理器
- `web/app_v2.py` - V2 版 Web 界面

#### 2. 智能推荐系统

- **正向推荐**：根据时间/偏好 → 推荐目的地
- **反向推荐**：根据目的地 → 推荐出行时间

---

## V1 - 基础版（初始版本）

- LangGraph 多 Agent 编排
- RAG 知识检索（ChromaDB）
- Streamlit Web 界面
- 完整的旅行规划流程

---

## 版本对比

| 功能 | V1 | V2 | V3 | V1.2 |
|------|----|----|-----|------|
| **LangGraph 编排** | ✅ | ✅ | ✅ | ✅ |
| **Agent 独立调用** | ❌ | ✅ | ✅ | ✅ |
| **智能推荐** | ❌ | ✅ | ✅ | ✅ |
| **MCP 集成** | ❌ | ❌ | ✅ | ✅ |
| **上下文压缩** | ❌ | ❌ | ❌ | ✅ |
| **药物检测** | ❌ | ❌ | ❌ | ✅ |
| **requirements 无冲突** | ❌ | ❌ | ❌ | ✅ |

---

## 文档索引

| 文档 | 用途 |
|------|------|
| **README.md** | 项目总览 |
| **系统设计文档.md** | 架构设计、上下文压缩方案 |
| **V2_优化说明.md** | V1→V2→V1.2 演进记录 |
| **MCP_集成指南.md** | MCP 集成完整教程 |
| **快速启动指南.md** | 10 分钟部署教程 |
| **面试准备手册.md** | 面试话术和技术深挖 |


## V3 - MCP 集成版（2026-06-01）

### 🆕 新功能

#### 1. 真实的 MCP (Model Context Protocol) 集成

**新增文件：**
- `mcp_config.yaml` - MCP Servers 配置文件
- `mcp_client.py` - MCP 客户端管理器
- `tools/utility/weather_v2.py` - 天气工具（MCP 版）
- `tools/content/search_guides_v2.py` - 搜索工具（MCP 版）
- `tools/mcp_servers/custom_travel_server.py` - 自定义 MCP Server
- `MCP_集成指南.md` - 详细的 MCP 使用文档

**集成的 MCP Servers：**
- ✅ **OpenWeather** - 实时天气查询
- ✅ **Brave Search** - 网络搜索
- ⚠️ **Google Maps** - 地图/路线规划（可选）
- ✅ **Filesystem** - 本地文件访问
- ⚠️ **Custom Travel** - 自定义旅行数据服务（示例）

**核心特性：**
1. **标准化接口**：统一的 MCP 协议调用
2. **降级策略**：MCP 失败时自动使用模拟数据
3. **可扩展性**：轻松添加新的 MCP Servers
4. **自定义能力**：支持创建专属 MCP Server

**使用示例：**
```python
from mcp_client import MCPManager

# 查询天气
with MCPManager() as mcp:
    result = mcp.call_tool("weather", "get_forecast", {"city": "北京", "days": 7})
    print(result)
```

---

## V2 - Agent 模块化 + 智能推荐（2026-06-01）

### 🆕 新功能

#### 1. Agent 模块化架构

**新增文件：**
- `agents/base_agent.py` - Agent 基类
- `agents/parse_agent_v2.py` - 支持独立调用的解析 Agent
- `agents/recommend_agent.py` - 智能推荐 Agent
- `agent_manager.py` - Agent 统一管理器
- `web/app_v2.py` - V2 版 Web 界面

**核心特性：**
- ✅ 每个 Agent 可以独立运行（不依赖 LangGraph）
- ✅ 统一的 `BaseAgent` 接口
- ✅ `AgentManager` 统一管理和调度
- ✅ 支持完整流程和独立调用两种模式

**使用示例：**
```python
from agent_manager import AgentManager

manager = AgentManager()

# 独立运行 Parse Agent
result = manager.run_agent("parse", {"user_input": "我想去大理"})
```

#### 2. 智能推荐系统

**两种推荐模式：**

##### 正向推荐：根据时间/偏好 → 推荐目的地
```python
result = manager.run_agent("recommend", {
    "start_date": "2026-04-15",
    "budget": 5000,
    "preferences": ["自然风光", "美食"],
    "intent": "recommend_destination"
})
```

##### 反向推荐：根据目的地 → 推荐出行时间
```python
result = manager.run_agent("recommend", {
    "destination": "三亚",
    "preferences": ["人少", "天气好"],
    "intent": "recommend_time"
})
```

**核心特性：**
- ✅ 时间特征分析（季节/节假日/人流）
- ✅ RAG 知识检索增强
- ✅ 多维度推荐（天气/价格/活动）

#### 3. Web 界面 V2

**三种使用模式：**
1. **完整流程** - 自动路由
2. **独立 Agent** - 手动选择 Agent
3. **智能推荐** - 专属推荐界面（正向/反向）

---

## V1 - 基础版（初始版本）

### 核心功能

- ✅ LangGraph 多 Agent 编排
- ✅ RAG 知识检索（ChromaDB）
- ✅ Prompt Engineering
- ✅ Streamlit Web 界面
- ✅ 完整的旅行规划流程

---

## 版本对比

| 功能 | V1 | V2 | V3 |
|------|----|----|-----|
| **LangGraph 编排** | ✅ | ✅ | ✅ |
| **Agent 独立调用** | ❌ | ✅ | ✅ |
| **智能推荐** | ❌ | ✅ | ✅ |
| **MCP 集成** | ❌ | ❌ | ✅ |
| **真实 API 调用** | ❌ | ❌ | ✅ |
| **使用模式** | 1 种 | 3 种 | 3 种 |
| **降级策略** | ❌ | ❌ | ✅ |

---

## 升级指南

### 从 V1 升级到 V2

1. 新增文件不影响原有代码
2. 原有的 `main.py` 和 `web/app.py` 继续可用
3. 可选择性使用新功能

### 从 V2 升级到 V3

1. 安装 Node.js（用于 MCP Servers）
2. 配置 API Keys（`.env` 文件）
3. 测试 MCP 连接
4. 使用 V2 版本的工具（`weather_v2.py`、`search_guides_v2.py`）

---

## 文档索引

| 文档 | 用途 |
|------|------|
| **README.md** | 项目总览 |
| **V2_优化说明.md** | V2 版本详细说明 |
| **MCP_集成指南.md** | V3 MCP 集成完整教程 |
| **面试准备手册.md** | 面试话术和技术深挖 |
| **快速启动指南.md** | 10 分钟部署教程 |
| **项目交付总结.md** | 项目价值和亮点总结 |

---

## 下载地址

- **V1 基础版**: https://dwz.cn/LgUysE3Z
- **V2 优化版**: https://dwz.cn/8DsYxj8z
- **V3 MCP 版**: （打包中...）

---

**🎉 项目持续迭代中，感谢支持！**
