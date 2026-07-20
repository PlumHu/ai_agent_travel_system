# 🔌 MCP (Model Context Protocol) 集成指南

> **真实的 MCP Server 集成** —— 连接外部 API 和服务

---

## 📋 目录

1. [什么是 MCP](#1-什么是-mcp)
2. [已集成的 MCP Servers](#2-已集成的-mcp-servers)
3. [快速开始](#3-快速开始)
4. [配置说明](#4-配置说明)
5. [使用示例](#5-使用示例)
6. [自定义 MCP Server](#6-自定义-mcp-server)
7. [常见问题](#7-常见问题)

---

## 1. 什么是 MCP

**MCP (Model Context Protocol)** 是 Anthropic 推出的标准协议，用于连接 AI 应用和外部数据源/服务。

### 核心优势

- ✅ **标准化接口**：统一的工具调用协议
- ✅ **可扩展性**：轻松添加新的数据源
- ✅ **社区生态**：丰富的官方和社区 MCP Servers
- ✅ **安全隔离**：进程级隔离，独立运行

---

## 2. 已集成的 MCP Servers

### 2.1 官方 MCP Servers

| Server | 功能 | 状态 | API Key 要求 |
|--------|------|------|--------------|
| **Weather** | 实时天气查询 | ✅ 已启用 | OpenWeather API Key |
| **Brave Search** | 网络搜索 | ✅ 已启用 | Brave Search API Key |
| **Google Maps** | 地图/路线规划 | ⚠️ 可选 | Google Maps API Key |
| **Filesystem** | 本地文件访问 | ✅ 已启用 | 无 |

### 2.2 自定义 MCP Server

| Server | 功能 | 状态 |
|--------|------|------|
| **Custom Travel** | 旅行数据服务 | ⚠️ 示例 |

---

## 3. 快速开始

### 3.1 安装依赖

```bash
# 安装 Node.js（如果没有）
# macOS:
brew install node

# Ubuntu:
sudo apt install nodejs npm

# 安装 Python 依赖
pip install pyyaml
```

### 3.2 配置 API Keys

编辑 `.env` 文件，添加以下 API Keys：

```env
# OpenWeather API（天气服务）
OPENWEATHER_API_KEY=your_openweather_api_key

# Brave Search API（搜索服务）
BRAVE_SEARCH_API_KEY=your_brave_search_api_key

# Google Maps API（可选）
GOOGLE_MAPS_API_KEY=your_google_maps_api_key
```

**如何获取 API Keys：**

- **OpenWeather**: https://openweathermap.org/api
- **Brave Search**: https://brave.com/search/api/
- **Google Maps**: https://developers.google.com/maps

### 3.3 测试 MCP 连接

```bash
# 测试天气 MCP
python -c "from mcp_client import MCPManager; mcp = MCPManager(); mcp.start_server('weather')"

# 测试搜索 MCP
python tools/content/search_guides_v2.py
```

---

## 4. 配置说明

### 4.1 配置文件结构

**文件位置**: `mcp_config.yaml`

```yaml
servers:
  weather:
    name: "Weather MCP Server"
    command: "npx"
    args: ["-y", "@modelcontextprotocol/server-weather"]
    env:
      OPENWEATHER_API_KEY: "${OPENWEATHER_API_KEY}"
    description: "实时天气查询服务"
    enabled: true  # 是否启用

  # 添加更多 servers...

client:
  timeout: 30  # 调用超时（秒）
  max_retries: 3  # 最大重试次数
  log_level: "INFO"  # 日志级别
```

### 4.2 启用/禁用 MCP Server

修改 `enabled` 字段：

```yaml
servers:
  google_maps:
    # ...
    enabled: false  # 禁用
```

---

## 5. 使用示例

### 5.1 在代码中使用 MCP

#### 示例 1：查询天气

```python
from mcp_client import MCPManager

# 方式 1：使用上下文管理器（推荐）
with MCPManager() as mcp:
    result = mcp.call_tool(
        "weather",
        "get_forecast",
        {"city": "Beijing", "days": 7}
    )
    print(result)

# 方式 2：手动管理
mcp = MCPManager()
try:
    mcp.start_server("weather")
    result = mcp.call_tool("weather", "get_current", {"city": "Shanghai"})
    print(result)
finally:
    mcp.stop_all()
```

#### 示例 2：网络搜索

```python
from mcp_client import get_mcp_manager

mcp = get_mcp_manager()

result = mcp.call_tool(
    "brave_search",
    "search",
    {
        "query": "best travel destinations 2026",
        "count": 5
    }
)

for item in result["results"]:
    print(f"- {item['title']}: {item['url']}")
```

### 5.2 在工具中使用 MCP

**V2 版本的工具已集成 MCP**：

```python
# tools/utility/weather_v2.py
from tools.utility.weather_v2 import get_weather

# 自动使用 MCP（失败时降级到模拟数据）
weather = get_weather("大理")
print(weather)

# 强制使用模拟数据
weather = get_weather("大理", use_mcp=False)
```

```python
# tools/content/search_guides_v2.py
from tools.content.search_guides_v2 import search_travel_info

# 本地知识库 + MCP 搜索
result = search_travel_info("冰岛旅行攻略")
print(result)
```

### 5.3 在 Agent 中使用

```python
from agents.recommend_agent import RecommendAgent
from agent_manager import AgentManager

# Agent 会自动调用 MCP 工具
manager = AgentManager()

result = manager.run_agent("recommend", {
    "user_input": "推荐一个春天去的地方",
    "start_date": "2026-04-15",
    "intent": "recommend_destination"
})
```

---

## 6. 自定义 MCP Server

### 6.1 创建自定义 Server

**文件**: `tools/mcp_servers/custom_travel_server.py`

```python
#!/usr/bin/env python3
import json
import sys

class MyMCPServer:
    def handle_request(self, request):
        method = request.get("method")

        if method == "tools/list":
            return {
                "tools": [
                    {
                        "name": "my_tool",
                        "description": "我的工具",
                        "inputSchema": {
                            "type": "object",
                            "properties": {
                                "input": {"type": "string"}
                            }
                        }
                    }
                ]
            }

        elif method == "tools/call":
            tool_name = request["params"]["name"]
            arguments = request["params"]["arguments"]

            # 实现工具逻辑
            return {"result": "..."}

    def run(self):
        for line in sys.stdin:
            request = json.loads(line)
            response = self.handle_request(request)

            result = {
                "jsonrpc": "2.0",
                "id": request.get("id"),
                "result": response
            }

            print(json.dumps(result))
            sys.stdout.flush()

if __name__ == "__main__":
    server = MyMCPServer()
    server.run()
```

### 6.2 注册自定义 Server

在 `mcp_config.yaml` 中添加：

```yaml
servers:
  my_custom_server:
    name: "My Custom MCP Server"
    command: "python"
    args: ["tools/mcp_servers/my_custom_server.py"]
    description: "自定义服务"
    enabled: true
```

### 6.3 测试自定义 Server

```bash
# 赋予执行权限
chmod +x tools/mcp_servers/my_custom_server.py

# 测试运行
echo '{"jsonrpc":"2.0","id":1,"method":"tools/list","params":{}}' | python tools/mcp_servers/my_custom_server.py
```

---

## 7. 常见问题

### Q1: MCP Server 启动失败

**错误信息**:
```
RuntimeError: 启动 MCP Server 失败
```

**解决方案**:
1. 检查 Node.js 是否已安装：`node --version`
2. 检查 API Key 是否正确配置
3. 检查 `mcp_config.yaml` 语法是否正确
4. 查看日志获取详细错误信息

---

### Q2: API Key 无效

**错误信息**:
```
MCP 调用错误: Invalid API key
```

**解决方案**:
1. 检查 `.env` 文件中的 API Key 是否正确
2. 确认 API Key 未过期
3. 检查 API Key 的权限和配额

---

### Q3: MCP 调用超时

**错误信息**:
```
TimeoutError: MCP Server 响应超时
```

**解决方案**:
1. 增加超时时间（修改 `mcp_config.yaml` 中的 `timeout`）
2. 检查网络连接
3. 使用降级策略（模拟数据）

---

### Q4: 如何禁用某个 MCP Server

修改 `mcp_config.yaml`：

```yaml
servers:
  brave_search:
    enabled: false  # 禁用
```

或在代码中：

```python
# 强制使用模拟数据
from tools.utility.weather_v2 import get_weather
weather = get_weather("北京", use_mcp=False)
```

---

### Q5: 如何添加新的官方 MCP Server

1. 查找可用的 MCP Servers：https://github.com/modelcontextprotocol/servers
2. 在 `mcp_config.yaml` 中添加配置
3. 安装所需的依赖（如 npm 包）
4. 测试连接

**示例：添加 GitHub MCP Server**

```yaml
servers:
  github:
    name: "GitHub MCP Server"
    command: "npx"
    args: ["-y", "@modelcontextprotocol/server-github"]
    env:
      GITHUB_TOKEN: "${GITHUB_TOKEN}"
    description: "GitHub API 集成"
    enabled: true
```

---

## 8. 最佳实践

### 8.1 降级策略

**始终提供降级方案**，确保即使 MCP 失败也能正常运行：

```python
def get_data(query: str, use_mcp: bool = True):
    if use_mcp:
        try:
            mcp = get_mcp_manager()
            return mcp.call_tool("my_server", "my_tool", {"query": query})
        except Exception as e:
            logger.warning(f"MCP 失败，降级到本地数据: {e}")

    # 降级方案
    return get_local_data(query)
```

### 8.2 缓存结果

对于频繁调用的 MCP 工具，考虑缓存：

```python
from functools import lru_cache

@lru_cache(maxsize=100)
def get_weather_cached(city: str):
    return get_weather(city)
```

### 8.3 错误处理

```python
try:
    result = mcp.call_tool("weather", "get_forecast", {...})
except TimeoutError:
    logger.error("MCP 调用超时")
    result = get_fallback_data()
except ValueError as e:
    logger.error(f"参数错误: {e}")
    result = {"error": "Invalid parameters"}
except Exception as e:
    logger.error(f"未知错误: {e}")
    result = {"error": str(e)}
```

### 8.4 日志记录

```python
import logging

logger = logging.getLogger(__name__)
logger.setLevel(logging.INFO)

# 记录 MCP 调用
logger.info(f"调用 MCP: {server_name}.{tool_name}")
logger.debug(f"参数: {arguments}")
logger.info(f"结果: {result}")
```

---

## 9. 性能优化

### 9.1 并发调用

```python
import asyncio

async def call_multiple_mcp():
    tasks = [
        mcp.call_tool("weather", "get_forecast", {"city": "Beijing"}),
        mcp.call_tool("brave_search", "search", {"query": "travel tips"})
    ]

    results = await asyncio.gather(*tasks)
    return results
```

### 9.2 连接池

```python
# 复用 MCP 连接
mcp_manager = MCPManager()
mcp_manager.start_all_enabled()

# 在应用生命周期中复用
def get_global_mcp():
    return mcp_manager
```

---

## 10. 参考资源

- **MCP 官方文档**: https://modelcontextprotocol.io/
- **官方 MCP Servers**: https://github.com/modelcontextprotocol/servers
- **Claude Code 文档**: https://docs.anthropic.com/claude/docs

---

## 11. 项目文件清单

| 文件 | 用途 |
|------|------|
| `mcp_config.yaml` | MCP Servers 配置文件 |
| `mcp_client.py` | MCP 客户端管理器 |
| `tools/utility/weather_v2.py` | 天气工具（MCP 版） |
| `tools/content/search_guides_v2.py` | 搜索工具（MCP 版） |
| `tools/mcp_servers/custom_travel_server.py` | 自定义 MCP Server 示例 |

---

## 🎯 总结

通过集成真实的 MCP Servers，项目现在具备：

1. ✅ **真实的外部 API 调用**（天气、搜索）
2. ✅ **标准化的工具接口**（MCP 协议）
3. ✅ **降级策略**（失败时使用模拟数据）
4. ✅ **可扩展性**（轻松添加新 MCP Servers）
5. ✅ **自定义能力**（可创建专属 MCP Server）

**面试加分项**：
- 展示了对 MCP 协议的理解
- 实践了真实的 API 集成
- 体现了系统设计能力（降级、容错）

---

**🎉 MCP 集成完成！项目现在支持真实的外部数据源！**
