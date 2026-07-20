# Agent 系统设计模式详解

## 📋 本项目使用的设计模式

### 1. 策略模式 (Strategy Pattern) ⭐⭐⭐⭐⭐

**定义**：定义一系列算法，把它们封装起来，并且使它们可以相互替换。

**应用场景**: 多 LLM 提供商支持

**UML 类图**:

```
┌─────────────────┐
│   LLMConfig     │ ◄──── Context
├─────────────────┤
│ + provider      │
│ + create_client()│
│ + chat()        │
└────────┬────────┘
         │
         │implements
   ┌─────┴──────┬──────────┬───────────┐
   │            │          │           │
┌──▼──────┐ ┌──▼─────┐ ┌─▼────────┐ ┌▼──────────┐
│ Baidu   │ │ NVIDIA │ │ DeepSeek │ │ OpenAI    │
│ OneAPI  │ │  API   │ │   API    │ │   API     │
└─────────┘ └────────┘ └──────────┘ └───────────┘
  Strategy   Strategy   Strategy      Strategy
```

**代码实现**:

```python
# llm_config.py

class LLMConfig:
    """策略模式的 Context"""

    PROVIDERS = {
        "baidu_oneapi": {...},
        "nvidia": {...},
        "deepseek": {...},
        "openai": {...}
    }

    def __init__(self, provider: str):
        self.provider = provider  # 选择策略
        self.strategy = self._get_strategy(provider)

    def _get_strategy(self, provider):
        """根据 provider 选择具体策略"""
        config = self.PROVIDERS[provider]
        return OpenAI(
            api_key=config['api_key'],
            base_url=config['base_url']
        )

    def chat_completion(self, messages):
        """统一接口，内部委托给具体策略"""
        return self.strategy.chat.completions.create(
            model=self.model,
            messages=messages
        )
```

**优点**:
- ✅ 易于切换 LLM（改配置即可）
- ✅ 符合开闭原则（新增 LLM 无需改现有代码）
- ✅ 避免大量 if-else

**本项目体现**:
```python
# 切换 LLM 只需改一行
llm = LLMConfig(provider="baidu_oneapi")  # 或 nvidia, deepseek
response = llm.chat_completion(messages)
```

---

### 2. 模板方法模式 (Template Method Pattern) ⭐⭐⭐⭐⭐

**定义**：定义算法骨架，将某些步骤延迟到子类实现。

**应用场景**: BaseAgent 定义 Agent 执行流程

**UML 类图**:

```
┌─────────────────────┐
│    BaseAgent        │ ◄──── Abstract Class
├─────────────────────┤
│ + execute()         │ ◄──── Template Method
│ # _prepare_state()  │ ◄──── Hook Methods
│ # _extract_output() │
└──────────┬──────────┘
           │
           │extends
     ┌─────┴──────┬───────────┐
     │            │           │
┌────▼─────┐ ┌───▼──────┐ ┌──▼──────────┐
│Recommend │ │  Plan    │ │   Browser   │
│  Agent   │ │  Agent   │ │   Agent     │
└──────────┘ └──────────┘ └─────────────┘
 Concrete     Concrete      Concrete
 Class        Class         Class
```

**代码实现**:

```python
# agents/base_agent.py

class BaseAgent(ABC):
    """模板方法模式的抽象类"""

    def execute(self, state: AgentState) -> AgentState:
        """
        Template Method: 定义算法骨架

        执行流程：
        1. 准备状态 → 2. 执行任务 → 3. 提取输出
        """
        # 1. 准备状态（可被子类覆盖）
        prepared_state = self._prepare_state(state)

        # 2. 执行任务（子类必须实现）
        result_state = self._execute_task(prepared_state)

        # 3. 提取输出（可被子类覆盖）
        output = self._extract_output(result_state)

        return output

    def _prepare_state(self, state):
        """Hook Method: 准备状态（子类可覆盖）"""
        return state

    @abstractmethod
    def _execute_task(self, state):
        """Abstract Method: 执行任务（子类必须实现）"""
        pass

    def _extract_output(self, state):
        """Hook Method: 提取输出（子类可覆盖）"""
        return state
```

**子类实现**:

```python
# agents/recommend_agent.py

class RecommendAgent(BaseAgent):
    """具体子类：推荐 Agent"""

    def _prepare_state(self, state):
        """覆盖：添加用户偏好"""
        state['preferences'] = self._load_user_preferences()
        return state

    def _execute_task(self, state):
        """实现：推荐逻辑"""
        # 1. 搜索目的地
        destinations = self._search_destinations(state)

        # 2. 查询天气
        weather_data = self._query_weather(destinations)

        # 3. 综合推荐
        recommendations = self._generate_recommendations(
            destinations, weather_data, state['preferences']
        )

        state['recommendations'] = recommendations
        return state

    def _extract_output(self, state):
        """覆盖：格式化输出"""
        return {
            "recommendations": state['recommendations'],
            "reasoning": state.get('reasoning', '')
        }
```

**优点**:
- ✅ 统一执行流程
- ✅ 复用公共代码
- ✅ 灵活扩展（子类只需实现特定步骤）

**本项目体现**:
所有 Agent（RecommendAgent、PlanAgent、BrowserAgent）都继承 BaseAgent，复用执行流程。

---

### 3. 责任链模式 (Chain of Responsibility Pattern) ⭐⭐⭐⭐⭐

**定义**：将请求沿着处理者链传递，直到某个处理者处理它。

**应用场景**: 搜索工具的多层降级

**UML 类图**:

```
  Request
     ↓
┌────────────┐   fail   ┌────────────┐   fail   ┌────────────┐
│ DuckDuckGo │─────────→│BraveSearch │─────────→│Browser-Use │
│  (免费)     │          │  (付费)     │          │  (兜底)     │
└────────────┘          └────────────┘          └────────────┘
     │ success              │ success              │ success
     ↓                      ↓                      ↓
  ┌────────────────────────────────────────────────┐
  │              Return Result                     │
  └────────────────────────────────────────────────┘
```

**代码实现**:

```python
# tools/utility/free_search.py

def search_with_fallback(query: str) -> str:
    """责任链模式：搜索降级策略"""

    # Handler 1: DuckDuckGo（免费，快速）
    try:
        logger.info("尝试 DuckDuckGo 搜索")
        results = search_duckduckgo(query)
        return format_results(results, source="DuckDuckGo")
    except Exception as e:
        logger.warning(f"DuckDuckGo 失败: {e}")

    # Handler 2: Brave Search（付费，质量高）
    if BRAVE_API_KEY:
        try:
            logger.info("降级到 Brave Search")
            results = search_brave(query)
            return format_results(results, source="Brave")
        except Exception as e:
            logger.warning(f"Brave Search 失败: {e}")

    # Handler 3: Browser-Use（兜底，慢）
    if use_browser:
        try:
            logger.info("降级到 Browser-Use")
            results = asyncio.run(search_with_browser(query))
            return results
        except Exception as e:
            logger.error(f"Browser-Use 失败: {e}")

    # Handler 4: Mock Data（最后兜底）
    logger.warning("所有搜索失败，返回模拟数据")
    return get_mock_search_results(query)
```

**优点**:
- ✅ 高可用性（多层兜底）
- ✅ 易于扩展（添加新 Handler）
- ✅ 解耦（每个 Handler 独立）

**本项目体现**:
- 搜索: DuckDuckGo → Brave → Browser → Mock
- 天气: OpenWeather MCP → Mock Data
- 地图: 百度地图 MCP → Mock Data

---

### 4. 工厂模式 (Factory Pattern) ⭐⭐⭐⭐

**定义**：定义创建对象的接口，由子类决定实例化哪个类。

**应用场景**: 创建不同类型的 Agent

**UML 类图**:

```
                 ┌──────────────┐
                 │ AgentFactory │
                 ├──────────────┤
                 │create_agent()│
                 └──────┬───────┘
                        │
          ┌─────────────┼─────────────┐
          │             │             │
     ┌────▼─────┐  ┌───▼──────┐ ┌───▼──────────┐
     │Recommend │  │   Plan   │ │    Browser   │
     │  Agent   │  │   Agent  │ │    Agent     │
     └──────────┘  └──────────┘ └──────────────┘
```

**代码实现**:

```python
# agent_manager.py

class AgentFactory:
    """工厂模式：创建 Agent"""

    @staticmethod
    def create_agent(agent_type: str, **kwargs):
        """
        根据类型创建 Agent

        Args:
            agent_type: Agent 类型（recommend, plan, browser）
            **kwargs: Agent 参数

        Returns:
            BaseAgent: 对应的 Agent 实例
        """
        if agent_type == "recommend":
            return RecommendAgent(**kwargs)

        elif agent_type == "plan":
            return PlanAgent(**kwargs)

        elif agent_type == "browser":
            return BrowserAgent(**kwargs)

        else:
            raise ValueError(f"未知 Agent 类型: {agent_type}")

# 使用示例
agent = AgentFactory.create_agent("recommend")
result = agent.execute(user_query)
```

**优点**:
- ✅ 隐藏创建细节
- ✅ 易于管理（集中创建逻辑）
- ✅ 符合依赖倒置原则

---

### 5. 单例模式 (Singleton Pattern) ⭐⭐⭐

**定义**：确保一个类只有一个实例，并提供全局访问点。

**应用场景**: MCP Manager（避免重复启动 MCP 服务器）

**代码实现**:

```python
# mcp_client.py

class MCPManager:
    """单例模式：MCP 管理器"""

    _instance = None

    def __new__(cls):
        if cls._instance is None:
            cls._instance = super().__new__(cls)
            cls._instance._initialized = False
        return cls._instance

    def __init__(self):
        if self._initialized:
            return

        # 初始化逻辑（只执行一次）
        self.clients = {}
        self.config = self._load_config()
        self._initialized = True

    def start_server(self, server_name):
        """启动 MCP 服务器（确保不重复启动）"""
        if server_name in self.clients:
            logger.info(f"MCP服务器 {server_name} 已启动")
            return

        # 启动服务器
        self.clients[server_name] = self._create_client(server_name)

# 使用示例
mcp1 = MCPManager()  # 第一次创建
mcp2 = MCPManager()  # 返回同一个实例
assert mcp1 is mcp2  # True
```

**优点**:
- ✅ 节省资源（避免重复启动）
- ✅ 全局唯一（状态一致）

---

### 6. 观察者模式 (Observer Pattern) ⭐⭐⭐

**定义**：定义对象间一对多的依赖关系，当一个对象改变状态时，所有依赖者都会收到通知。

**应用场景**: Agent 状态监控

**代码实现**:

```python
# agent_observer.py

class AgentObserver(ABC):
    """观察者接口"""

    @abstractmethod
    def on_agent_start(self, agent, state):
        pass

    @abstractmethod
    def on_agent_complete(self, agent, result):
        pass

    @abstractmethod
    def on_agent_error(self, agent, error):
        pass


class LoggingObserver(AgentObserver):
    """日志观察者"""

    def on_agent_start(self, agent, state):
        logger.info(f"Agent {agent.name} 开始执行")

    def on_agent_complete(self, agent, result):
        logger.info(f"Agent {agent.name} 执行完成")

    def on_agent_error(self, agent, error):
        logger.error(f"Agent {agent.name} 执行失败: {error}")


class BaseAgent:
    """支持观察者的 Agent"""

    def __init__(self):
        self.observers = []

    def attach(self, observer: AgentObserver):
        """注册观察者"""
        self.observers.append(observer)

    def _notify_start(self, state):
        for observer in self.observers:
            observer.on_agent_start(self, state)

    def _notify_complete(self, result):
        for observer in self.observers:
            observer.on_agent_complete(self, result)

    def execute(self, state):
        self._notify_start(state)

        try:
            result = self._execute_task(state)
            self._notify_complete(result)
            return result
        except Exception as e:
            self._notify_error(e)
            raise
```

**优点**:
- ✅ 解耦（Subject 不依赖具体 Observer）
- ✅ 易于扩展（添加新 Observer 无需改 Subject）

---

## 🎯 设计模式总结

| 设计模式 | 应用场景 | 核心价值 | 重要性 |
|---------|---------|---------|--------|
| **策略模式** | 多 LLM 提供商 | 算法可替换 | ⭐⭐⭐⭐⭐ |
| **模板方法** | BaseAgent 执行流程 | 复用算法骨架 | ⭐⭐⭐⭐⭐ |
| **责任链** | 搜索降级策略 | 多层兜底 | ⭐⭐⭐⭐⭐ |
| **工厂模式** | 创建 Agent | 隐藏创建细节 | ⭐⭐⭐⭐ |
| **单例模式** | MCP Manager | 全局唯一实例 | ⭐⭐⭐ |
| **观察者** | 流式输出 StreamingCallback | 事件通知/实时展示 | ⭐⭐⭐⭐ |
| **Mixin 混入** | ReflectionMixin 反思能力 | 横切能力复用，不改继承链 | ⭐⭐⭐⭐ |
| **中间件** | Guardrails 输入/输出护栏 | 非侵入式拦截，前置/后置过滤 | ⭐⭐⭐⭐ |

### 新增能力对应的模式（v1.4-v1.5）

- **Mixin 混入模式** — `agents/reflection.py` 的 `ReflectionMixin`：`BaseAgent(ABC, ReflectionMixin)` 让任意 Agent 获得 `execute_with_reflection()` 反思能力，无需修改各 Agent 的继承结构。横切关注点（反思）与业务逻辑解耦。
- **中间件模式** — `guardrails/`：InputGuard/OutputGuard 在 Pipeline 入口/出口拦截，`agent_manager.run_pipeline()` 中前置检查输入、后置检查输出，不侵入任何 Agent 内部逻辑。
- **观察者模式（强化）** — `streaming.py` 的 `StreamingCallback`：注册多个监听器（ConsoleStreamListener/CollectorListener），Agent 执行时发射 9 种事件，实现实时进度展示与事后收集分离。
- **ReAct 循环** — `agents/react_agent.py`：Think→Act→Observe 迭代，属于 Agent 架构模式而非 GoF 模式，是 Agent 区别于 Chain 的核心（工具调用由推理动态驱动）。
- **Plan-and-Execute** — `planning/planner.py`：先规划后执行的任务分解模式，配合动态重规划应对复杂多步骤目标。

---

## 📝 面试回答模板

**Q: 你们项目用了什么设计模式？**

**标准回答**：

我们项目主要使用了 **5 种设计模式**：

**1. 策略模式**（最重要）
- **场景**: 支持多种 LLM（百度/英伟达/DeepSeek）
- **实现**: `LLMConfig` 统一接口，内部切换不同策略
- **好处**: 切换 LLM 只需改配置，无需改代码

**2. 模板方法模式**
- **场景**: `BaseAgent` 定义执行流程
- **实现**: 定义 `execute()` 骨架，子类实现具体步骤
- **好处**: 统一流程，复用代码

**3. 责任链模式**
- **场景**: 搜索工具的降级策略
- **实现**: DuckDuckGo → Brave → Browser → Mock
- **好处**: 高可用性，多层兜底

**4. 工厂模式**
- **场景**: 创建不同类型 Agent
- **实现**: `AgentFactory.create_agent(type)`
- **好处**: 集中管理创建逻辑

**5. 单例模式**
- **场景**: MCP Manager 全局唯一
- **实现**: `__new__` 方法控制实例创建
- **好处**: 避免重复启动服务器

这些设计模式让系统**易扩展、易维护、高可用**。

---

## 🔗 延伸阅读

- 《设计模式：可复用面向对象软件的基础》（GoF）
- LangChain 源码（大量使用策略模式和责任链）
- LlamaIndex 源码（工厂模式和模板方法）

---

## 🎊 总结

✅ **设计模式不是死记硬背，而是解决实际问题的工具**

✅ **本项目体现了软件工程最佳实践**：
- 高内聚低耦合
- 符合 SOLID 原则
- 易扩展易维护

✅ **面试时结合项目讲，更有说服力**！
