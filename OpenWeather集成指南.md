# OpenWeather API 集成指南

## 📋 目录

1. [API Key 配置](#api-key-配置)
2. [MCP Server 架构](#mcp-server-架构)
3. [可用功能](#可用功能)
4. [使用示例](#使用示例)
5. [故障排查](#故障排查)
6. [API 限制说明](#api-限制说明)

---

## ✅ API Key 配置

### 当前配置状态

- **API Key**: `your_openweather_api_key`
- **验证状态**: ✅ 已通过测试（2026-06-01）
- **测试结果**:
  - 北京当前天气: ✅ 成功 (33.94°C, 晴)
  - 上海天气预报: ✅ 成功 (48小时预报)

### 获取 API Key

1. 访问 [OpenWeather 官网](https://openweathermap.org/api)
2. 注册/登录账号
3. 进入 [API Keys 页面](https://home.openweathermap.org/api_keys)
4. 复制 API Key

### 配置到项目

API Key 已配置在 `.env` 文件中：

```bash
OPENWEATHER_API_KEY=your_openweather_api_key
```

---

## 🏗️ MCP Server 架构

### 文件位置

```
AI_Agent_Travel_System/
├── tools/mcp_servers/
│   └── openweather_server.py     # OpenWeather MCP Server
├── tools/utility/
│   └── weather_v2.py              # 高层封装（含降级策略）
├── mcp_config.yaml                # MCP 配置
└── .env                           # 环境变量（从 .env.example 复制）
```

### MCP 配置

`mcp_config.yaml` 中的配置：

```yaml
servers:
  weather:
    name: "OpenWeather MCP Server"
    command: "python"
    args: ["tools/mcp_servers/openweather_server.py"]
    env:
      OPENWEATHER_API_KEY: "${OPENWEATHER_API_KEY}"
    description: "OpenWeather 天气查询服务"
    enabled: true
    verified: true  # 已验证
```

---

## 🛠️ 可用功能

### 1. 当前天气查询 (current_weather)

获取指定城市的实时天气信息。

**输入参数**:
- `city` (必需): 城市名称（英文或拼音）
- `country` (可选): 国家代码（如 CN, US）
- `units` (可选): 单位系统
  - `metric`: 摄氏度（默认）
  - `imperial`: 华氏度

**返回数据**:
```python
{
    "city": "Beijing",
    "country": "CN",
    "temperature": 33.94,      # 当前温度
    "feels_like": 32.1,        # 体感温度
    "temp_min": 30.0,          # 最低温度
    "temp_max": 35.0,          # 最高温度
    "humidity": 22,            # 湿度 (%)
    "pressure": 1013,          # 气压 (hPa)
    "weather": "晴",           # 天气描述
    "wind_speed": 6.9,         # 风速 (m/s)
    "clouds": 10,              # 云量 (%)
    "visibility": 10000,       # 能见度 (米)
    "dt": 1717234567,          # 时间戳
    "timezone": 28800          # 时区偏移 (秒)
}
```

### 2. 天气预报 (weather_forecast)

获取5天天气预报（每3小时一次，共40个数据点，默认返回前48小时）。

**输入参数**:
- `city` (必需): 城市名称
- `country` (可选): 国家代码
- `units` (可选): 单位系统

**返回数据**:
```python
{
    "city": "Shanghai",
    "country": "CN",
    "forecasts": [
        {
            "dt": 1717234800,
            "dt_txt": "2026-06-01 12:00:00",
            "temperature": 27.87,
            "feels_like": 28.5,
            "temp_min": 27.0,
            "temp_max": 28.0,
            "humidity": 65,
            "weather": "晴",
            "clouds": 10,
            "wind_speed": 3.5,
            "pop": 0.1            # 降水概率 (0-1)
        },
        # ... 更多预报数据点
    ]
}
```

### 3. 坐标天气查询 (weather_by_coordinates)

根据经纬度获取天气信息。

**输入参数**:
- `lat` (必需): 纬度
- `lon` (必需): 经度
- `units` (可选): 单位系统

**返回数据**:
```python
{
    "city": "Beijing",
    "country": "CN",
    "coordinates": {"lat": 39.9, "lon": 116.4},
    "temperature": 33.94,
    "feels_like": 32.1,
    "humidity": 22,
    "weather": "晴",
    "wind_speed": 6.9
}
```

---

## 📖 使用示例

### 方式 1: 通过 MCP Manager（推荐）

```python
from mcp_client import MCPManager

# 初始化 MCP Manager
mcp = MCPManager()

# 查询北京天气
result = mcp.call_tool("weather", "current_weather", {
    "city": "Beijing",
    "country": "CN",
    "units": "metric"
})

print(result)
```

### 方式 2: 通过高层封装（带降级）

```python
from tools.utility.weather_v2 import get_weather, get_weather_forecast

# 获取当前天气（失败时自动降级到模拟数据）
weather = get_weather("北京", use_mcp=True)
print(weather)

# 获取天气预报
forecast = get_weather_forecast("上海", use_mcp=True)
print(forecast)
```

### 方式 3: 直接测试 MCP Server

```bash
# 命令行测试
export OPENWEATHER_API_KEY=your_openweather_api_key
python tools/mcp_servers/openweather_server.py test
```

### 方式 4: Agent 中使用

```python
from agents.recommend_agent import RecommendAgent

# Agent 会自动调用 MCP 获取天气
agent = RecommendAgent()
result = agent.run_standalone({
    "user_request": "推荐3月去哪里旅游",
    "preferences": {"climate": "温暖"}
})
```

---

## 🔧 故障排查

### 问题 1: API Key 无效

**症状**:
```
❌ 请求失败: 401 Unauthorized
```

**解决方案**:
1. 检查 `.env` 文件中的 API Key 是否正确
2. 确认 API Key 已激活（新注册的 Key 可能需要等待几分钟）
3. 在 [OpenWeather 官网](https://home.openweathermap.org/api_keys) 验证 Key 状态

### 问题 2: 请求超时

**症状**:
```
❌ 请求失败: Timeout
```

**解决方案**:
1. 检查网络连接
2. 确认是否需要代理访问国外 API
3. 增加超时时间（默认 10 秒）

### 问题 3: 城市名称无法识别

**症状**:
```
❌ 请求失败: 404 Not Found
```

**解决方案**:
1. 使用英文城市名或拼音（如 "Beijing" 而非"北京"）
2. 添加国家代码：`city="Shanghai", country="CN"`
3. 使用坐标查询：`weather_by_coordinates(lat=39.9, lon=116.4)`

### 问题 4: MCP Server 无法启动

**症状**:
```
Error: Failed to start MCP server 'weather'
```

**解决方案**:
1. 检查 Python 环境是否安装 `requests` 库：
   ```bash
   pip install requests
   ```

2. 确认文件权限：
   ```bash
   chmod +x tools/mcp_servers/openweather_server.py
   ```

3. 手动测试服务器：
   ```bash
   python tools/mcp_servers/openweather_server.py test
   ```

---

## 📊 API 限制说明

### 免费计划 (Free Tier)

OpenWeather API Key `your_openweather_api_key` 使用的是免费计划：

| 项目 | 限制 |
|------|------|
| **每分钟调用次数** | 60 次 |
| **每天调用次数** | 1,000,000 次 |
| **可用 API** | Current Weather, 5 Day Forecast |
| **数据延迟** | 实时 |
| **支持语言** | 中文 (zh_cn) |

### 使用建议

1. **缓存策略**: 天气数据每 10 分钟更新一次，建议缓存结果
2. **批量查询**: 需要多个城市数据时，考虑使用预报 API（一次获取多个时间点）
3. **降级策略**: 项目已内置降级到模拟数据的逻辑（见 `weather_v2.py`）

### 超出限制时的行为

```python
{
    "success": False,
    "error": "429 Too Many Requests"
}
```

此时会自动降级到模拟数据（如果使用 `weather_v2.py`）。

---

## 🌟 最佳实践

### 1. 优先使用 MCP 模式

```python
# ✅ 推荐：通过 MCP Manager
mcp.call_tool("weather", "current_weather", {...})

# ⚠️ 不推荐：直接 HTTP 请求（绕过 MCP 架构）
requests.get("https://api.openweathermap.org/...")
```

### 2. 始终处理降级情况

```python
from tools.utility.weather_v2 import get_weather

# 自动降级：MCP 失败时使用模拟数据
weather = get_weather("北京", use_mcp=True)
```

### 3. 合理设置单位

```python
# 国内用户：metric（摄氏度）
get_weather("北京", units="metric")

# 美国用户：imperial（华氏度）
get_weather("New York", units="imperial")
```

### 4. 使用国家代码避免歧义

```python
# ✅ 明确指定国家
current_weather(city="Paris", country="FR")  # 法国巴黎
current_weather(city="Paris", country="US")  # 美国德州巴黎

# ⚠️ 可能返回错误的城市
current_weather(city="Paris")  # 默认返回最大的同名城市
```

---

## 📝 测试记录

### 2026-06-01 测试结果

✅ **测试 1: 北京当前天气**
- 温度: 33.94°C
- 体感: 32.1°C
- 湿度: 22%
- 天气: 晴
- 风速: 6.9 m/s

✅ **测试 2: 上海天气预报**
- 城市: Shanghai, CN
- 预报数据点: 16 个（48小时）
- 第一个预报: 2026-06-01 12:00:00, 27.87°C, 晴

---

## 🔗 相关文档

- [OpenWeather API 官方文档](https://openweathermap.org/api)
- [Current Weather API](https://openweathermap.org/current)
- [5 Day Forecast API](https://openweathermap.org/forecast5)
- [MCP 集成指南](./MCP_集成指南.md)
- [百度地图集成指南](./百度地图集成指南.md)

---

## 🎯 总结

✅ **配置完成**: API Key 已配置并验证
✅ **测试通过**: 当前天气、预报功能正常
✅ **MCP 集成**: 已加入 MCP 服务器列表
✅ **降级策略**: 失败时自动切换模拟数据

**开始使用**: 现在可以在项目中调用 OpenWeather API 获取实时天气数据！
