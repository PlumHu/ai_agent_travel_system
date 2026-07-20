# 多模型 LLM + 免费搜索 - 快速开始指南

## 🎯 新增功能

### 1. 统一 LLM 配置管理器

支持多种 LLM API，用户可自由选择：

- ✅ **百度 OneAPI**（内部集成）：`https://oneapi-comate.baidu-int.com/v1`
- ✅ **英伟达 NIM**：`https://integrate.api.nvidia.com/v1`
- ✅ **DeepSeek**：`https://api.deepseek.com/v1`
- ✅ **OpenAI**：`https://api.openai.com/v1`
- ✅ **自定义 OpenAI 兼容接口**

### 2. 免费搜索工具

- ✅ **DuckDuckGo**：完全免费，无需 API Key，质量高
- ✅ **Browser-Use**：浏览器兜底搜索
- ✅ **智能降级**：自动fallback 保证可用

---

## 🚀 快速配置

### 步骤 1: 配置 LLM（选择一种即可）

#### 方案 A：使用百度 OneAPI（推荐内部用户）

编辑 `.env` 文件：

```env
# 百度 OneAPI（内部集成，推荐）
BAIDU_ONEAPI_KEY=your_api_key_here
BAIDU_ONEAPI_MODEL=ERNIE-4.0-8K

# 设为默认 LLM
DEFAULT_LLM_PROVIDER=baidu_oneapi
```

#### 方案 B：使用英伟达 API

```env
# 英伟达 API
NVIDIA_API_KEY=nvapi-xxxxxxxxx
NVIDIA_MODEL=meta/llama-3.1-70b-instruct

DEFAULT_LLM_PROVIDER=nvidia
```

#### 方案 C：使用 DeepSeek（成本低）

```env
# DeepSeek API
DEEPSEEK_API_KEY=sk-xxxxxxxxx
DEEPSEEK_MODEL=deepseek-chat

DEFAULT_LLM_PROVIDER=deepseek
```

#### 方案 D：使用 OpenAI

```env
# OpenAI API
OPENAI_API_KEY=sk-xxxxxxxxx
OPENAI_MODEL=gpt-4

DEFAULT_LLM_PROVIDER=openai
```

### 步骤 2: 安装依赖

```bash
# 安装所有依赖
pip install -r requirements.txt

# 安装 Playwright 浏览器（首次使用）
playwright install chromium
```

---

## 📖 使用示例

### 1. 使用统一 LLM 配置

```python
from llm_config import LLMConfig, create_llm_from_env

# 方式 1: 自动检测（从环境变量）
llm = create_llm_from_env()

# 方式 2: 指定提供商
llm = LLMConfig(provider="baidu_oneapi")

# 方式 3: 完全自定义
llm = LLMConfig(
    provider="custom",
    api_key="your_key",
    base_url="https://your-endpoint.com/v1",
    model="your-model"
)

# 调用 LLM
response = llm.chat_completion([
    {"role": "user", "content": "你好"}
])
print(response)
```

### 2. BrowserAgent 使用多模型

```python
from agents.browser_agent import BrowserAgent

# 使用百度 OneAPI
agent = BrowserAgent(llm_provider="baidu_oneapi")

# 使用英伟达 API
agent = BrowserAgent(llm_provider="nvidia")

# 使用 DeepSeek
agent = BrowserAgent(llm_provider="deepseek")

# 执行任务
result = await agent.execute("访问百度，搜索Python教程")
```

### 3. 免费搜索（DuckDuckGo）

```python
from tools.utility.free_search import (
    search_duckduckgo,
    search_duckduckgo_news,
    search_with_fallback
)

# 普通搜索
results = search_duckduckgo("Python 教程", max_results=10)
for r in results:
    print(f"{r['title']}: {r['url']}")

# 新闻搜索
news = search_duckduckgo_news("人工智能", max_results=10)

# 智能降级搜索（DuckDuckGo → Browser → Mock）
result = search_with_fallback("北京旅游", max_results=5)
```

---

## 🧪 测试验证

### 测试 1: LLM 配置

```bash
# 测试所有 LLM 提供商
python llm_config.py
```

预期输出：
```
============================================================
LLM 配置管理器
============================================================

支持的 LLM 提供商:
  - baidu_oneapi: 百度 OneAPI（内部集成）
  - nvidia: 英伟达 NIM
  - deepseek: DeepSeek
  - openai: OpenAI
  - custom: 自定义 OpenAI 兼容接口

当前环境可用的提供商:
  ✓ baidu_oneapi
  ✓ nvidia
```

### 测试 2: 免费搜索

```bash
# 测试 DuckDuckGo 搜索
python tools/utility/free_search.py
```

预期输出：
```
============================================================
免费搜索工具测试
============================================================

测试 1: DuckDuckGo 搜索
------------------------------------------------------------
✓ 找到 5 个结果

  [1] Python 教程 - 菜鸟教程
      https://www.runoob.com/python/...
      Python 基础教程，从入门到精通...
```

### 测试 3: BrowserAgent 多模型

```bash
# 测试 BrowserAgent（需配置任一 LLM）
python test_browser_agent.py --test basic
```

---

## 📂 新增文件清单

| 文件 | 说明 |
|------|------|
| `llm_config.py` | 统一 LLM 配置管理器 |
| `tools/utility/free_search.py` | 免费搜索工具（DuckDuckGo） |
| `搜索工具对比指南.md` | 详细的搜索方案对比 |
| `多模型LLM配置指南.md` | 本文件 |
| `.env`（已更新） | 新增多 LLM 配置项 |
| `requirements.txt`（已更新） | 新增 duckduckgo-search |
| `agents/browser_agent.py`（已更新） | 支持多 LLM 提供商 |

---

## 🔧 配置优先级

### LLM 配置优先级

```
函数参数 > 环境变量 > 默认值
```

示例：

```python
# 最高优先级：函数参数
llm = LLMConfig(
    provider="nvidia",
    api_key="nvapi-override",  # 优先使用这个
    model="custom-model"
)

# 次优先级：环境变量
# NVIDIA_API_KEY=nvapi-from-env
# NVIDIA_MODEL=default-model

# 最低优先级：默认值
# default_model = "meta/llama-3.1-70b-instruct"
```

---

## 💡 使用建议

### 1. LLM 选择建议

| 场景 | 推荐 LLM | 理由 |
|------|----------|------|
| **百度内部用户** | 百度 OneAPI | 内网可用，稳定，免费 |
| **成本优先** | DeepSeek | 最便宜，性能好 |
| **性能优先** | 英伟达/OpenAI | 最强性能 |
| **开发测试** | 任意免费模型 | 成本低 |

### 2. 搜索工具选择

| 场景 | 推荐方案 | 成本 |
|------|----------|------|
| **个人项目** | DuckDuckGo | 免费 |
| **中小型项目** | DuckDuckGo + Brave备份 | $0-10/月 |
| **企业应用** | Google/Bing + Duck备份 | $30-100/月 |

### 3. 最经济配置（完全免费）

```env
# LLM: 使用百度 OneAPI（内部免费）
BAIDU_ONEAPI_KEY=your_key
DEFAULT_LLM_PROVIDER=baidu_oneapi

# 搜索: 使用 DuckDuckGo（完全免费）
# 无需配置，直接使用
```

**月成本**: $0

---

## 🎯 系统架构（最新）

```
AI Agent 旅行规划系统（完整版 V4）
│
├── LLM 层（统一配置管理）✅ 新增
│   ├── 百度 OneAPI
│   ├── 英伟达 API
│   ├── DeepSeek API
│   ├── OpenAI API
│   └── 自定义接口
│
├── 搜索层（多工具支持）✅ 新增
│   ├── DuckDuckGo（免费，主力）
│   ├── Brave Search（可选）
│   └── Browser-Use（兜底）
│
├── MCP 层（结构化 API）
│   ├── OpenWeather（天气）✅ 已验证
│   ├── 百度地图（地点/路线）✅ 已验证
│   └── Brave Search（网络搜索）⚠️ 可选
│
├── Agent 层（智能决策）
│   ├── RecommendAgent（推荐）
│   ├── BrowserAgent（浏览器）✅ 支持多模型
│   └── BaseAgent（基类）
│
└── 工具层（数据获取）
    ├── weather_v2.py（天气 + 降级）
    ├── map_route_v2.py（地图 + 降级）
    ├── search_v3.py（搜索 + 浏览器兜底）
    └── free_search.py（免费搜索）✅ 新增
```

---

## 🔗 相关文档

- [搜索工具对比指南](./搜索工具对比指南.md) - 详细对比各种搜索方案
- [Browser-Use 集成指南](./Browser-Use集成指南.md) - 浏览器自动化
- [OpenWeather 集成指南](./OpenWeather集成指南.md) - 天气API
- [百度地图集成指南](./百度地图集成指南.md) - 地图API
- [API 配置状态](./API配置状态.md) - 所有API配置总览

---

## 📝 常见问题

### Q1: 如何切换 LLM？

**A**: 修改 `.env` 文件中的 `DEFAULT_LLM_PROVIDER`，或在代码中指定：

```python
agent = BrowserAgent(llm_provider="deepseek")
```

### Q2: DuckDuckGo 搜索失败怎么办？

**A**: 系统已内置自动降级，会依次尝试：

1. DuckDuckGo
2. Browser-Use 搜索
3. 模拟数据

### Q3: 如何添加自定义 LLM？

**A**: 使用 `custom` 提供商：

```env
CUSTOM_API_KEY=your_key
CUSTOM_BASE_URL=https://your-endpoint.com/v1
CUSTOM_MODEL=your-model
```

```python
llm = LLMConfig(provider="custom")
```

### Q4: 如何查看当前使用的 LLM？

**A**:

```python
llm = create_llm_from_env()
info = llm.get_info()
print(info)
# 输出: {'provider': 'baidu_oneapi', 'model': 'ERNIE-4.0-8K', ...}
```

---

## 🎉 总结

✅ **已完成**：
- 统一 LLM 配置管理器（支持 5+ 种API）
- 免费搜索工具（DuckDuckGo）
- BrowserAgent 多模型支持
- 完整文档和测试

✅ **核心优势**：
- **灵活性**：支持多种 LLM，随时切换
- **经济性**：DuckDuckGo 完全免费
- **易用性**：统一接口，简单配置
- **可靠性**：多层降级，保证可用

**现在可以自由选择任何 LLM API 和搜索工具了！** 🚀
