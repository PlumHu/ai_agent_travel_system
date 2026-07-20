# Browser-Use 集成指南

## 📋 目录

1. [概述](#概述)
2. [安装配置](#安装配置)
3. [英伟达 API 配置](#英伟达-api-配置)
4. [BrowserAgent 使用](#browseragent-使用)
5. [集成到旅行系统](#集成到旅行系统)
6. [测试验证](#测试验证)
7. [故障排查](#故障排查)
8. [最佳实践](#最佳实践)

---

## 🎯 概述

**browser-use** 是一个开源的 AI 浏览器自动化框架，允许 Agent 像人类一样操作浏览器。

### 在旅行系统中的角色

```
调用优先级：
1. MCP 工具（OpenWeather、百度地图）→ 快速、稳定、结构化数据
2. 模拟数据降级 → 保证基本可用
3. BrowserAgent → 最后兜底，处理复杂网页交互
```

### 适用场景

✅ **适合使用 BrowserAgent**：
- 需要真实网页交互（登录、点击、表单填写）
- 目标网站没有 API 或 API 失效
- 需要动态渲染的内容（JavaScript 生成）
- 验证码处理、复杂流程

❌ **不适合使用**：
- 已有 MCP 工具可用（OpenWeather、百度地图等）
- 简单的 HTTP 请求可以完成
- 对性能要求高（浏览器比 API 慢 10-100 倍）
- 需要高频调用（成本高）

---

## 📦 安装配置

### 1. 安装依赖

项目已在 `requirements.txt` 中添加所需依赖：

```bash
# 安装 Python 依赖
pip install -r requirements.txt

# 安装 Playwright 浏览器（首次使用必需）
playwright install chromium
```

**依赖说明**：
- `browser-use>=0.1.10` - 开源浏览器自动化框架
- `playwright>=1.44.0` - 浏览器驱动（底层）
- `openai>=1.30.0` - LLM SDK（OpenAI 兼容接口，支持 DeepSeek/英伟达等）

### 2. 验证安装

```bash
# 检查 browser-use 是否安装成功
python -c "import browser_use; print('✓ browser-use 已安装')"

# 检查 Playwright 浏览器
playwright list
```

预期输出：
```
✓ browser-use 已安装
Chromium 125.0.6422.14 (playwright build v1105) - downloaded
```

---

## 🔑 英伟达 API 配置

### 获取 API Key

1. 访问 [NVIDIA NIM](https://build.nvidia.com/explore/discover)
2. 注册/登录账号
3. 选择模型（推荐：`meta/llama-3.1-70b-instruct`）
4. 生成 API Key

### 配置到项目

在 `.env` 文件中添加：

```env
# 英伟达 API（用于 Browser-Use Agent）
NVIDIA_API_KEY=nvapi-xxxxxxxxxxxxxxxxxxxxxxxxxx
NVIDIA_BASE_URL=https://integrate.api.nvidia.com/v1
NVIDIA_MODEL=meta/llama-3.1-70b-instruct
```

**模型选择**：

| 模型 | 特点 | 推荐场景 |
|------|------|----------|
| `meta/llama-3.1-70b-instruct` | 平衡性能和成本 | 通用场景（推荐）|
| `meta/llama-3.1-405b-instruct` | 最强性能 | 复杂推理任务 |
| `mistralai/mixtral-8x7b-instruct-v0.1` | 成本最低 | 简单任务 |

### 验证配置

```bash
# 运行配置检查
python test_browser_agent.py --test basic
```

---

## 🤖 BrowserAgent 使用

### 基本使用

```python
from agents.browser_agent import BrowserAgent
import asyncio

async def main():
    # 创建 Agent
    agent = BrowserAgent(
        headless=True,      # 无头模式（生产环境）
        max_steps=30        # 最大操作步数
    )

    # 执行任务
    result = await agent.execute(
        task="访问百度，搜索'北京旅游景点'，提取前3个结果",
        start_url="https://www.baidu.com"
    )

    print(result)

asyncio.run(main())
```

**返回结果**：
```python
{
    "success": True,
    "result": "搜索结果: [{'title': '...', 'url': '...'}]",
    "screenshots": [],
    "error": None
}
```

### 便捷函数

#### 1. 网络搜索

```python
from agents.browser_agent import search_with_browser
import asyncio

async def search_example():
    results = await search_with_browser("上海美食推荐", max_results=5)
    print(results)

asyncio.run(search_example())
```

#### 2. 地点信息提取

```python
from agents.browser_agent import extract_place_info
import asyncio

async def place_example():
    info = await extract_place_info("天安门", "北京")
    print(info)

asyncio.run(place_example())
```

### 高级选项

```python
agent = BrowserAgent(
    api_key="nvapi-xxx",              # 自定义 API Key
    base_url="https://...",            # 自定义端点
    model="meta/llama-3.1-405b",       # 自定义模型
    headless=False,                    # 可见模式（调试用）
    max_steps=50                       # 增加操作步数
)

result = await agent.execute(
    task="复杂任务描述",
    start_url="https://...",
    save_screenshots=True              # 保存截图
)
```

---

## 🔗 集成到旅行系统

### 1. 作为搜索工具的兜底

在 `tools/utility/search_v3.py` 中：

```python
from agents.browser_agent import search_with_browser
import asyncio

def search_web(query: str, use_mcp: bool = True, use_browser_fallback: bool = False):
    """
    网络搜索

    优先级：MCP → 模拟数据 → Browser Agent
    """
    # 1. 尝试 MCP (Brave Search)
    if use_mcp:
        try:
            mcp = MCPManager()
            return mcp.call_tool("brave_search", "search", {"query": query})
        except:
            pass

    # 2. 模拟数据降级
    if not use_browser_fallback:
        return get_mock_results(query)

    # 3. 浏览器兜底（用户确认后）
    return asyncio.run(search_with_browser(query))
```

### 2. 在 RecommendAgent 中使用

```python
from agents.base_agent import BaseAgent
from agents.browser_agent import BrowserAgent

class RecommendAgent(BaseAgent):
    def __init__(self):
        super().__init__("recommend")
        self.browser_agent = None  # 延迟初始化

    def _search_destinations(self, state):
        """搜索目的地（带浏览器兜底）"""
        try:
            # 优先使用 MCP
            mcp = MCPManager()
            results = mcp.call_tool("brave_search", "search", {...})
        except:
            # MCP 失败，询问用户是否使用浏览器
            if user_confirmed:
                if not self.browser_agent:
                    self.browser_agent = BrowserAgent()
                results = asyncio.run(self.browser_agent.execute(...))

        return results
```

### 3. 使用场景示例

#### 场景 1：实时景点评分查询

```python
async def get_place_rating(place_name: str, city: str):
    """从大众点评获取景点评分（无 API 时的兜底）"""
    agent = BrowserAgent()

    task = f"""
    访问大众点评，搜索 "{city} {place_name}"
    提取评分、评论数、价格区间
    返回 JSON 格式数据
    """

    result = await agent.execute(task, start_url="https://www.dianping.com")
    return result
```

#### 场景 2：酒店预订可用性检查

```python
async def check_hotel_availability(hotel_name: str, checkin: str, checkout: str):
    """检查酒店可订日期（携程等网站）"""
    agent = BrowserAgent()

    task = f"""
    访问携程，搜索 "{hotel_name}"
    选择入住日期 {checkin}，离店日期 {checkout}
    检查是否有房，返回房型和价格
    """

    result = await agent.execute(task, start_url="https://www.ctrip.com")
    return result
```

---

## ✅ 测试验证

### 运行测试套件

```bash
# 完整测试
python test_browser_agent.py --test all

# 单项测试
python test_browser_agent.py --test basic    # 基本导航
python test_browser_agent.py --test search   # 搜索功能
python test_browser_agent.py --test place    # 地点提取
python test_browser_agent.py --test form     # 表单交互
```

### 预期输出

```
============================================================
BrowserAgent 测试套件
============================================================

配置检查
------------------------------------------------------------
✓ NVIDIA_API_KEY: nvapi-xxx...
✓ NVIDIA_BASE_URL: https://integrate.api.nvidia.com/v1
✓ NVIDIA_MODEL: meta/llama-3.1-70b-instruct

✓ 配置完整

============================================================
测试 1: 基本页面导航
============================================================
✓ 导航成功
  结果: 页面标题: 百度一下，你就知道

============================================================
测试结果汇总
============================================================
  ✓ 通过  基本导航
  ✓ 通过  搜索功能
  ✓ 通过  地点提取
  ✓ 通过  表单交互

通过率: 4/4 (100%)

🎉 所有测试通过！BrowserAgent 工作正常
```

---

## 🔧 故障排查

### 问题 1: Playwright 浏览器未安装

**症状**：
```
Error: Executable doesn't exist at ...
```

**解决方案**：
```bash
playwright install chromium
```

### 问题 2: 英伟达 API Key 无效

**症状**：
```
Error: 401 Unauthorized
```

**解决方案**：
1. 检查 `.env` 文件中的 `NVIDIA_API_KEY` 是否正确
2. 确认 API Key 未过期
3. 访问 [NVIDIA NIM Console](https://build.nvidia.com/explore/discover) 验证

### 问题 3: 网络连接超时

**症状**：
```
Error: Navigation timeout exceeded
```

**解决方案**：
1. 检查网络连接
2. 增加超时时间：`agent = BrowserAgent(max_steps=50)`
3. 使用代理（如需访问国外网站）

### 问题 4: 内存不足

**症状**：
```
Error: Out of memory
```

**解决方案**：
1. 确保系统有至少 4GB 可用内存
2. 使用无头模式：`headless=True`
3. 减少并发 Agent 数量

### 问题 5: Element not found

**症状**：
```
Error: Element not found: ...
```

**解决方案**：
1. 网页结构可能变化，调整任务描述
2. 增加等待时间
3. 使用可见模式调试：`headless=False`

---

## 🌟 最佳实践

### 1. 优先使用专项工具

```python
# ❌ 不推荐：直接使用浏览器
result = browser_agent.execute("获取北京天气")

# ✅ 推荐：优先使用 MCP
weather = mcp.call_tool("weather", "current_weather", {"city": "Beijing"})
```

### 2. 明确任务描述

```python
# ❌ 模糊描述
task = "搜索旅游信息"

# ✅ 清晰描述
task = """
访问百度搜索，完成以下操作：
1. 在搜索框输入"北京旅游景点"
2. 点击搜索按钮
3. 提取前5个结果的标题、链接和摘要
4. 返回 JSON 格式数据
"""
```

### 3. 合理设置步数限制

```python
# 简单任务
agent = BrowserAgent(max_steps=10)

# 复杂任务（多页面跳转）
agent = BrowserAgent(max_steps=50)
```

### 4. 使用异步调用

```python
# ✅ 推荐：异步调用，不阻塞
import asyncio

async def batch_search(queries):
    tasks = [search_with_browser(q) for q in queries]
    results = await asyncio.gather(*tasks)
    return results

# ❌ 不推荐：同步调用，串行执行
def batch_search_slow(queries):
    return [agent.execute_sync(q) for q in queries]
```

### 5. 错误处理和降级

```python
async def robust_search(query):
    """稳健的搜索（多层降级）"""
    try:
        # 1. MCP
        return mcp.call_tool("brave_search", "search", {"query": query})
    except:
        try:
            # 2. Browser Agent
            return await search_with_browser(query)
        except:
            # 3. 模拟数据
            return get_mock_results(query)
```

### 6. 成本控制

```python
# 使用更便宜的模型处理简单任务
cheap_agent = BrowserAgent(model="mistralai/mixtral-8x7b-instruct-v0.1")

# 只在必要时使用高性能模型
premium_agent = BrowserAgent(model="meta/llama-3.1-405b-instruct")
```

---

## 📊 性能对比

| 方法 | 速度 | 成本 | 稳定性 | 适用场景 |
|------|------|------|--------|----------|
| **MCP 工具** | ⚡⚡⚡ 快 | 💰 低 | ⭐⭐⭐ 高 | 结构化 API 数据 |
| **Browser Agent** | 🐌 慢 (10-30秒) | 💰💰💰 高 | ⭐⭐ 中 | 复杂网页交互 |
| **模拟数据** | ⚡⚡⚡ 极快 | 免费 | ⭐⭐ 中 | 开发测试 |

---

## 🔗 相关文档

- [browser-use 开源项目](https://github.com/browser-use/browser-use)
- [NVIDIA NIM 官方文档](https://docs.nvidia.com/nim/)
- [Playwright 文档](https://playwright.dev/python/)
- [OpenWeather 集成指南](./OpenWeather集成指南.md)
- [百度地图集成指南](./百度地图集成指南.md)
- [MCP 集成总览](./MCP_集成指南.md)

---

## 🎯 总结

✅ **已完成**：
- browser-use 开源库集成
- 英伟达 API 配置
- BrowserAgent 封装
- 搜索/地点提取便捷函数
- 完整测试套件
- 集成文档

✅ **使用场景**：
- MCP 工具失败时的兜底策略
- 需要真实网页交互的复杂任务
- 目标网站无 API 时的替代方案

⚠️ **注意事项**：
- 优先使用 MCP 工具（更快、更稳定）
- Browser Agent 成本高、速度慢，仅作最后兜底
- 需要英伟达 API Key 才能使用
- 首次运行需安装 Playwright 浏览器

**现在可以在旅行系统中使用浏览器自动化功能了！** 🚀
