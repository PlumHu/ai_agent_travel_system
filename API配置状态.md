# API 配置状态总览

## ✅ 已配置的 API Keys

### 1. OpenWeather API
- **用途**: 天气查询服务
- **API Key**: `your_openweather_api_key`
- **状态**: ✅ 已验证（2026-06-01）
- **测试结果**:
  - ✅ 北京当前天气: 33.94°C, 晴
  - ✅ 上海天气预报: 48小时预报，16个数据点
- **配额**: 60次/分钟，1,000,000次/天（免费计划）
- **文档**: [OpenWeather集成指南.md](./OpenWeather集成指南.md)

### 2. 百度地图 API
- **用途**: 地点搜索、路线规划、地址解析
- **API Key**: `your_baidu_maps_api_key`
- **状态**: ✅ 已验证（2026-06-01）
- **测试结果**:
  - ✅ 地点搜索: 北京烤鸭，10个结果
  - ✅ 地理编码: 地址转坐标，精度100%
  - ✅ 路线规划: 天安门→颐和园，21.3km
- **配额**: 100,000次/天，100 QPS（免费计划）
- **文档**: [百度地图集成指南.md](./百度地图集成指南.md)

---

## ⚠️ 待配置的 API Keys

以下服务已集成但尚未配置 API Key，使用时会自动降级到模拟数据：

### 3. Brave Search API
- **用途**: 网络搜索服务
- **配置位置**: `.env` 文件中的 `BRAVE_SEARCH_API_KEY`
- **获取方式**: https://brave.com/search/api/
- **状态**: ⚠️ 待配置
- **影响**: 搜索功能会使用模拟数据

### 4. Google Maps API
- **用途**: 全球地图服务（可选，国内不推荐）
- **配置位置**: `.env` 文件中的 `GOOGLE_MAPS_API_KEY`
- **获取方式**: https://console.cloud.google.com/
- **状态**: ⚠️ 待配置（默认已禁用）
- **说明**: 国内推荐使用百度地图，Google Maps 需翻墙

---

## 📁 配置文件位置

所有 API Keys 都配置在以下文件中：

```bash
AI_Agent_Travel_System/.env
```

复制模板并填写：

```bash
cp .env.example .env
```

`.env` 最简示例（LLM + 工具 API）：

```env
# LLM（至少填一个）
OPENAI_API_KEY=sk-your-key
OPENAI_API_BASE=https://api.openai.com/v1
OPENAI_MODEL=gpt-4

# 工具 API（可选，不填自动降级到 DuckDuckGo 或 Mock）
OPENWEATHER_API_KEY=your_openweather_api_key
BAIDU_MAPS_API_KEY=your_baidu_maps_api_key
BRAVE_SEARCH_API_KEY=your_brave_search_api_key_here
```

> 详细配置说明见 `.env.example`，包含所有支持的 LLM 提供商和工具 API。

---

## 🔧 MCP 服务器状态

所有 MCP 服务器配置在 `mcp_config.yaml` 文件中：

| 服务器 | 状态 | 验证状态 | 说明 |
|--------|------|----------|------|
| **weather** (OpenWeather) | ✅ 启用 | ✅ 已验证 | 天气查询服务 |
| **baidu_maps** | ✅ 启用 | ✅ 已验证 | 百度地图服务（国内推荐） |
| **brave_search** | ✅ 启用 | ⚠️ 待配置 | 网络搜索服务 |
| **filesystem** | ✅ 启用 | N/A | 本地文件系统访问 |
| **custom** | ✅ 启用 | N/A | 自定义旅行数据服务 |

> DuckDuckGo 免费搜索（`tools/utility/free_search.py`）不需要 API Key，作为搜索第一降级选项，优先级高于 Brave Search。

---

## 🚀 快速测试

### 测试所有已配置的 API

```bash
# 1. 测试 OpenWeather
export OPENWEATHER_API_KEY=your_openweather_api_key
python tools/mcp_servers/openweather_server.py test

# 2. 测试百度地图
export BAIDU_MAPS_API_KEY=your_baidu_maps_api_key
python test_baidu_maps.py
```

### 在代码中使用

```python
from mcp_client import MCPManager

# 初始化 MCP Manager
mcp = MCPManager()

# 获取天气
weather = mcp.call_tool("weather", "current_weather", {
    "city": "Beijing",
    "country": "CN"
})

# 搜索地点
places = mcp.call_tool("baidu_maps", "place_search", {
    "query": "烤鸭",
    "region": "北京"
})
```

---

## 📊 降级策略

当 API 调用失败时，系统会自动降级到模拟数据，确保功能正常运行：

### 自动降级场景

1. **API Key 无效**
   - 天气服务 → 使用历史天气数据
   - 地图服务 → 使用常见地点数据

2. **网络请求失败**
   - 超时 → 重试 3 次后降级
   - 连接失败 → 立即降级

3. **配额超限**
   - 达到日配额 → 降级并记录日志
   - 并发超限 → 等待后重试

### 降级数据质量

| 服务 | 降级数据来源 | 数据质量 |
|------|-------------|---------|
| **天气** | 历史气候数据 | ⭐⭐⭐⭐ |
| **地图** | 常见景点/路线 | ⭐⭐⭐ |
| **搜索** | 预设知识库 | ⭐⭐⭐ |

---

## 💡 使用建议

### 生产环境部署

1. **必须配置**（LLM，至少一个）:
   - `OPENAI_API_KEY` + `OPENAI_API_BASE`（支持 DeepSeek/百度OneAPI/英伟达等兼容接口）

2. **推荐配置**（工具 API）:
   - ✅ OpenWeather API Key（天气功能，免费1M次/天）
   - ✅ 百度地图 API Key（地点/路线功能，免费10万次/天）

3. **可选配置**:
   - Brave Search API Key（搜索，DuckDuckGo 已可免费覆盖）

4. **无需配置即可运行**:
   - DuckDuckGo 搜索（免费，无 Key）
   - 药物-食物相互作用检测（内置规则）
   - 过敏原检测（内置14类知识库）

### 开发环境

开发和测试时，未配置的 API 会自动降级（DuckDuckGo → Mock），不影响开发流程。

---

## 🔗 相关文档

- [.env.example](./.env.example) - 完整环境变量模板
- [OpenWeather 集成指南](./OpenWeather集成指南.md)
- [百度地图集成指南](./百度地图集成指南.md)
- [MCP 集成总览](./MCP_集成指南.md)
- [快速启动指南](./快速启动指南.md)

---

## 📝 更新日志

- **2026-07-05**:
  - ✅ 新增 `.env.example` 完整模板
  - ✅ 路径更新为 `AI_Agent_Travel_System/`
  - ✅ 补充 DuckDuckGo 免费搜索说明
  - ✅ MCP 服务器表格更新（移除 google_maps，custom 改为启用）

- **2026-06-01**:
  - ✅ 配置 OpenWeather API Key 并验证
  - ✅ 配置百度地图 API Key 并验证
  - ✅ 更新 mcp_config.yaml
