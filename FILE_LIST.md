# AI Agent 旅行规划系统 - 文件清单

> 版本：v1.6 | 更新时间：2026-07-13

## 核心文档（8个）
- `README.md` - 完整项目文档（含 Agent 高级能力、长期记忆增强等）
- `系统设计文档.md` - 架构设计、上下文压缩双层方案
- `系统流程图.md` - 10个Mermaid流程图
- `AI岗位面试题与答案.md` - 14个面试题库
- `Agent设计模式详解.md` - 6种设计模式详解
- `RAG与Memory实现方案.md` - RAG+Memory完整方案
- `CHANGELOG.md` - 项目版本更新日志
- `FILE_LIST.md` - 本文件（文件清单）

## 配置文件
- `mcp_config.yaml` - MCP服务器配置（OpenWeather + 百度地图）
- `.env.example` - 完整环境变量模板（5+ LLM + 4工具API）
- `requirements.txt` - Python依赖清单（>=宽松约束，无版本冲突）
- `config.py` - 全局配置
- `llm_config.py` - 多 LLM 提供商配置管理器

## 核心实现
- `state.py` - AgentState（含消息截断 + reflection/react 字段）
- `context_manager.py` - 多轮对话上下文压缩（滑动窗口 + LLM摘要 + 长期记忆集成）⭐
- `agent_manager.py` - Agent管理器（记忆/护栏/流式/HITL/tracing/run_react）⭐
- `memory/long_term_memory.py` - 跨 session 长期记忆（SQLite + ChromaDB + 冲突/衰减/动态重要性/LLM提取）⭐
- `async_executor.py` - 异步并行执行器（信号量 + 超时隔离）⭐
- `streaming.py` - 流式输出回调（观察者模式，9种事件）⭐
- `rag_memory_system.py` - RAG + Memory完整实现
- `mcp_client.py` - MCP客户端

## Agent 高级能力模块（v1.4-v1.5 新增）⭐
- `agents/reflection.py` - 反思自纠错（ReflectionMixin + 3验证器 + LLMJudge）
- `agents/react_agent.py` - ReAct 循环 Agent（Think-Act-Observe + ToolSpec 工具注册）
- `guardrails/input_guard.py` - 输入护栏（注入检测 + PII脱敏 + 内容安全）
- `guardrails/output_guard.py` - 输出护栏（幻觉检测 + PII泄露 + 置信度）
- `guardrails/budget_limiter.py` - 调用限流（token/请求/工具次数）
- `guardrails/config.py` - 护栏配置
- `evaluation/dataset.py` / `evaluator.py` / `metrics.py` / `judges.py` / `run_eval.py` - 评估框架（20用例 + 6指标 + LLM-Judge）
- `evaluation/test_cases/travel_cases.json` - 预置测试用例
- `observability/tracer.py` - 可观测性（Trace/Span 调用链 + 指标 + 导出）
- `planning/planner.py` - 动态规划（Plan-and-Execute 分解 + 重规划）

## Agents（智能代理，13个）
- `agents/base_agent.py` - BaseAgent抽象基类（模板方法 + ReflectionMixin + 错误退避重试）
- `agents/reflection.py` - 反思能力混入 + 验证器 ⭐
- `agents/react_agent.py` - ReAct 循环 Agent ⭐
- `agents/parse_agent_v2.py` - 需求解析Agent（含反思验证，推荐使用）
- `agents/parse_agent.py` - 旧版解析Agent（LangGraph节点）
- `agents/destination_agent.py` - 目的地推荐Agent（独立版）
- `agents/recommend_agent.py` - 双向推荐Agent（目的地/时间）
- `agents/plan_agent.py` - 行程规划Agent（逐日行程+预算）
- `agents/travel_agent.py` - 旅行规划Agent（LangGraph节点）
- `agents/food_agent.py` - 美食营养Agent
- `agents/merge_agent.py` - 内容融合Agent
- `agents/output_agent.py` - 报告生成Agent
- `agents/browser_agent.py` - 浏览器自动化Agent（兜底）

## Tools（工具集，20个）

### 统一入口 ⭐
- `tools/registry.py` - 工具注册中心（ToolSpec + ToolRegistry + build_default_registry，唯一装配点）

### Content（内容与灵感，5个）
- `tools/content/platform_guides.py` - 四平台攻略抓取（DDG site过滤 → browser-use → 本地）⭐
- `tools/content/search_guides.py` - 攻略搜索（本地→DuckDuckGo）
- `tools/content/search_guides_v2.py` - 攻略搜索（MCP版）
- `tools/content/local_customs.py` - 风俗禁忌节日
- `tools/content/local_features.py` - 特色体验/非遗

### Transaction（交易与价格，3个）
- `tools/transaction/flights.py` - 机票搜索（DuckDuckGo→携程链接）
- `tools/transaction/hotels.py` - 酒店搜索（DuckDuckGo→美团链接）
- `tools/transaction/tickets.py` - 门票/活动搜索

### Utility（基础服务，7个）
- `tools/utility/realtime_search.py` - 实时搜索（Brave→Serper→DDG→browser 分级 + 时效标注）⭐
- `tools/utility/weather.py` - 天气查询（OpenWeather→Mock）
- `tools/utility/weather_v2.py` - 天气查询（MCP版）
- `tools/utility/map_route.py` - 路径规划
- `tools/utility/map_route_v2.py` - 路径规划（百度地图MCP版）
- `tools/utility/free_search.py` - 免费搜索（DuckDuckGo）
- `tools/utility/search_v3.py` - 搜索（MCP+浏览器兜底）

### Health（健康与安全，3个）⭐
- `tools/health/allergen_check.py` - 过敏原检测（14类内置知识库）
- `tools/health/drug_interaction_check.py` - 药物-食物相互作用检测（内置规则，无需API）⭐
- `tools/health/food_safety_alert.py` - 食品安全预警

### MCP（协议集成，4个）
- `tools/mcp/mcp_client.py` - MCP客户端管理器（单例）
- `tools/mcp_servers/openweather_server.py` - OpenWeather MCP Server
- `tools/mcp_servers/baidu_maps_server.py` - 百度地图 MCP Server
- `tools/mcp_servers/custom_travel_server.py` - 自定义旅行数据 Server

## Knowledge（知识库）
- `knowledge/rag_manager.py` - RAG管理器（ChromaDB + HuggingFace Embedding）
- `knowledge/retriever.py` - 混合检索器（向量 + BM25 RRF融合）
- `knowledge/build_index.py` - 索引构建脚本
- `knowledge/raw_data/destinations/*.json` - 目的地数据（大理/丽江/三亚）
- `knowledge/raw_data/psychology/*.json` - 心理知识：压力类型/情绪管理/同行心理 ⭐
- `knowledge/raw_data/health/*.json` - 健康知识：高原反应/时差/水土不服 ⭐
- `knowledge/raw_data/customs/*.json` - 风俗礼仪：旅行礼仪/宗教场所 ⭐

## Web界面
- `web/app_v2.py` - Streamlit Web应用（推荐）
- `web/app.py` - 实验版Web应用

## Tests（测试，6个）
- `tests/test_llm_config.py` - LLM配置测试
- `tests/test_rag.py` - RAG系统测试
- `tests/test_parse_agent.py` - 解析Agent测试
- `tests/test_travel_agent.py` - 旅行Agent测试
- `tests/test_output_agent.py` - 输出Agent测试
- `tests/test_new_modules.py` - 新能力集成测试（12项：护栏/反思/评估/记忆/ReAct/可观测/规划/重试）⭐

## 集成指南（5个）
- `OpenWeather集成指南.md`
- `百度地图集成指南.md`
- `Browser-Use集成指南.md`
- `多模型LLM+免费搜索指南.md`
- `搜索工具对比指南.md`

---

## 核心特性

1. **多LLM支持**：百度OneAPI、英伟达、DeepSeek、OpenAI、自定义
2. **上下文压缩**：双层机制（AgentState截断 + ContextManager摘要），支持无限轮对话 ⭐
3. **免费搜索**：DuckDuckGo（完全免费，无需API Key）
4. **RAG系统**：HuggingFace Embedding（文字→向量）+ ChromaDB（存储+检索）+ BM25混合检索
5. **Memory系统**：短期（deque）+ 长期（SQLite+ChromaDB，含冲突检测/衰减/动态重要性/LLM提取）+ 语义（RAG）⭐
6. **药物安全检测**：内置高危药物-食物组合规则，旅行场景专用
7. **三级工具降级**：真实API → DuckDuckGo → Mock/参考链接
8. **浏览器自动化**：browser-use + Playwright 兜底
9. **MCP协议**：OpenWeather + 百度地图 + Brave Search
10. **Agent 高级能力**：反思自纠错 + ReAct Loop + 安全护栏 + 动态规划 + 可观测性 + 错误重试 + 异步并行 + 流式输出 + 评估框架 ⭐
11. **设计模式**：模板方法、Mixin、中间件、观察者、策略、责任链、工厂、单例

## 统计信息

| 项目 | 数量 |
|------|------|
| Python文件 | 55+个 |
| Markdown文档 | 20个 |
| 代码总行数 | 10000+行 |
| Agent数量 | 13个 |
| Tool数量 | 17个 |
| Agent高级能力模块 | 9类 |
| 支持LLM | 5+种 |
| 测试文件 | 6个（新能力测试12项全绿）|

## 快速开始

```bash
cd AI_Agent_Travel_System
pip install -r requirements.txt
cp .env.example .env          # 填入 LLM API Key
python3 knowledge/build_index.py --sample   # 首次构建RAG索引
streamlit run web/app_v2.py   # 启动Web UI
```


## 📋 完整文件列表

### 核心文档
- `README.md` - 完整项目文档（31KB+）
- `系统流程图.md` - 10个Mermaid流程图
- `AI岗位面试题与答案.md` - 14个面试题库
- `Agent设计模式详解.md` - 6种设计模式详解
- `RAG与Memory实现方案.md` - RAG+Memory完整方案
- `FILE_LIST.md` - 本文件（文件清单）

### 配置文件
- `mcp_config.yaml` - MCP服务器配置（OpenWeather + 百度地图）
- `.env.example` - 环境变量模板
- `requirements.txt` - Python依赖清单
- `config.py` - 全局配置
- `state.py` - AgentState类型定义

### 核心实现
- `llm_config.py` - LLM统一配置管理器（支持5+种LLM）
- `rag_memory_system.py` - RAG + Memory完整实现
- `agent_manager.py` - Agent管理器
- `mcp_client.py` - MCP客户端

### Agents（智能代理）
- `agents/base_agent.py` - BaseAgent抽象基类（模板方法模式）
- `agents/parse_agent.py` - 需求解析Agent
- `agents/destination_agent.py` - 目的地推荐Agent
- `agents/recommend_agent.py` - 推荐Agent
- `agents/travel_agent.py` - 旅行规划Agent
- `agents/plan_agent.py` - 行程规划Agent（别名）
- `agents/food_agent.py` - 美食营养与心理健康Agent ⭐
- `agents/merge_agent.py` - 内容融合Agent
- `agents/output_agent.py` - 输出Agent
- `agents/browser_agent.py` - 浏览器自动化Agent

### Tools（工具集）
#### Content（内容与灵感）
- `tools/content/platform_guides.py` - 四平台攻略抓取（小红书/马蜂窝/携程/飞猪，三层降级）⭐
- `tools/content/search_guides.py` - 多平台攻略搜索
- `tools/content/local_customs.py` - 风俗禁忌节日
- `tools/content/local_features.py` - 特色体验/非遗

#### Transaction（交易与价格）
- `tools/transaction/flights.py` - 机票搜索
- `tools/transaction/hotels.py` - 酒店搜索
- `tools/transaction/tickets.py` - 门票/活动搜索

#### Utility（基础服务）
- `tools/utility/weather.py` - 天气查询
- `tools/utility/map_route.py` - 路径规划
- `tools/utility/free_search.py` - 免费搜索工具（DuckDuckGo）

#### Health（健康与安全）
- `tools/health/allergen_check.py` - 过敏原检测
- `tools/health/food_safety_alert.py` - 食品安全预警

#### MCP（协议集成）
- `tools/mcp/mcp_client.py` - MCP客户端管理器

### Knowledge（知识库）
- `knowledge/rag_manager.py` - RAG管理器
- `knowledge/retriever.py` - 混合检索器
- `knowledge/build_index.py` - 索引构建脚本
- `knowledge/raw_data/destinations/*.json` - 目的地数据

### Web界面
- `web/app.py` - Streamlit Web应用

### Tests（测试）
- `tests/test_llm_config.py` - LLM配置测试
- `tests/test_rag.py` - RAG系统测试
- `tests/test_parse_agent.py` - 解析Agent测试
- `tests/test_travel_agent.py` - 旅行Agent测试
- `tests/test_output_agent.py` - 输出Agent测试

### 集成指南
- `OpenWeather集成指南.md`
- `百度地图集成指南.md`
- `Browser-Use集成指南.md`
- `多模型LLM+免费搜索指南.md`
- `搜索工具对比指南.md`

## 🎯 核心特性

1. **多LLM支持**：百度OneAPI、英伟达、DeepSeek、OpenAI、自定义
2. **免费搜索**：DuckDuckGo（完全免费）
3. **RAG系统**：ChromaDB + sentence-transformers
4. **Memory系统**：短期记忆（deque）+ 长期记忆（JSON）
5. **浏览器自动化**：browser-use集成
6. **MCP协议**：OpenWeather + 百度地图
7. **心理健康Agent**：美食营养 + 心理关怀 ⭐
8. **多层降级策略**：99%可用性保障
9. **6种设计模式**：策略、模板方法、责任链、工厂、单例、观察者

## 📊 统计信息

- Python文件：50+ 个
- Markdown文档：15+ 个
- 代码总行数：8000+ 行
- 文档总字数：50000+ 字
- 支持LLM：5+ 种
- Agent数量：9 个
- Tool数量：15+ 个
- 测试文件：5+ 个

## 🚀 快速开始

1. 解压代码包
2. 安装依赖：`pip install -r requirements.txt`
3. 配置环境：`cp .env.example .env`（填写API Key）
4. 运行示例：`python main.py`

## 📝 使用说明

详见 `README.md` 文件，包含：
- 完整安装指南
- API配置说明
- 使用示例
- 常见问题解答
- 设计模式详解
- 面试准备材料

## ⭐ 新增：心理健康Agent

本版本新增 `food_agent.py`（美食营养与心理健康Agent），提供：
- 目的地美食推荐
- 营养成分分析
- 过敏原检测
- 心理健康建议（基于旅行疲劳度、饮食习惯等）

## 📞 技术支持

如有问题，请查阅：
1. `README.md` - 完整文档
2. `AI岗位面试题与答案.md` - 常见问题
3. `Agent设计模式详解.md` - 技术细节

---

**生成时间**：2026-07-13
**版本**：v1.6.0（架构收敛：统一工具层 + 实时搜索 + 知识库扩展）
**包含**：ToolRegistry/realtime-search/psychology-health-customs 知识库 ⭐

> 注：上方「📋 完整文件列表」小节为早期版本快照，最新准确清单以本文件顶部各节为准。
