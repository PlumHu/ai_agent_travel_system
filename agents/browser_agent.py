"""
Browser Agent - 基于开源 browser-use 的浏览器自动化 Agent
用作 MCP 工具的兜底策略，处理复杂的网页交互任务
支持多种 LLM API：百度 OneAPI、英伟达、DeepSeek 等
"""
import os
import sys
import asyncio
import logging
from typing import Dict, Any, Optional

# 添加项目路径
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

try:
    from browser_use import Agent, Controller
    from browser_use.browser.browser import Browser, BrowserConfig
    BROWSER_USE_AVAILABLE = True
except ImportError:
    BROWSER_USE_AVAILABLE = False
    logging.warning("browser-use 未安装，BrowserAgent 将无法使用")

try:
    from llm_config import LLMConfig, create_llm_from_env
    LLM_CONFIG_AVAILABLE = True
except ImportError:
    LLM_CONFIG_AVAILABLE = False
    logging.warning("llm_config 未找到，将使用传统配置方式")


logger = logging.getLogger(__name__)


class BrowserAgent:
    """
    浏览器自动化 Agent

    基于开源 browser-use 框架，支持多种 LLM API。
    作为 MCP 工具的最后兜底策略，处理需要网页交互的复杂任务。
    """

    def __init__(
        self,
        llm_provider: Optional[str] = None,
        api_key: Optional[str] = None,
        base_url: Optional[str] = None,
        model: Optional[str] = None,
        headless: bool = True,
        max_steps: int = 30
    ):
        """
        初始化 BrowserAgent

        Args:
            llm_provider: LLM 提供商（baidu_oneapi, nvidia, deepseek, openai, custom）
                         默认从环境变量 DEFAULT_LLM_PROVIDER 读取，或自动检测
            api_key: API Key（优先级高于环境变量）
            base_url: API 端点（优先级高于环境变量）
            model: 模型名称（优先级高于环境变量）
            headless: 是否无头模式运行浏览器
            max_steps: 最大操作步数
        """
        if not BROWSER_USE_AVAILABLE:
            raise RuntimeError("browser-use 未安装，请运行: pip install browser-use playwright")

        # 配置 LLM
        if LLM_CONFIG_AVAILABLE and llm_provider:
            # 使用新的统一配置管理器
            self.llm_config = LLMConfig(
                provider=llm_provider,
                api_key=api_key,
                base_url=base_url,
                model=model
            )
            self.client = self.llm_config.create_client()
            self.model = self.llm_config.model
            logger.info(f"BrowserAgent 使用统一配置: {self.llm_config.provider_config['name']}")
        else:
            # 兼容旧的配置方式（仅英伟达）
            self.api_key = api_key or os.getenv("NVIDIA_API_KEY", "")
            self.base_url = base_url or os.getenv("NVIDIA_BASE_URL", "https://integrate.api.nvidia.com/v1")
            self.model = model or os.getenv("NVIDIA_MODEL", "meta/llama-3.1-70b-instruct")

            if not self.api_key:
                raise ValueError("未设置 API Key，请配置 NVIDIA_API_KEY 或使用 llm_provider 参数")

            from openai import OpenAI
            self.client = OpenAI(
                api_key=self.api_key,
                base_url=self.base_url
            )
            logger.info(f"BrowserAgent 使用传统配置: 英伟达 API")

        # 配置浏览器
        self.headless = headless
        self.max_steps = max_steps

        logger.info(f"BrowserAgent 初始化完成，使用模型: {self.model}")

    def _create_llm_function(self):
        """创建 LLM 函数，供 browser-use 调用"""
        def llm(messages):
            """
            LLM 函数包装器

            Args:
                messages: 消息列表 [{"role": "user", "content": "..."}]

            Returns:
                str: LLM 响应内容
            """
            try:
                response = self.client.chat.completions.create(
                    model=self.model,
                    messages=messages,
                    temperature=0.7,
                    max_tokens=2000
                )
                return response.choices[0].message.content
            except Exception as e:
                logger.error(f"LLM 调用失败: {e}")
                raise

        return llm

    async def execute(
        self,
        task: str,
        start_url: Optional[str] = None,
        save_screenshots: bool = False
    ) -> Dict[str, Any]:
        """
        执行浏览器任务

        Args:
            task: 任务描述（清晰描述要完成的操作）
            start_url: 起始 URL（可选）
            save_screenshots: 是否保存截图

        Returns:
            Dict: 执行结果
                - success: 是否成功
                - result: 任务结果（文本、数据等）
                - screenshots: 截图列表（如果启用）
                - error: 错误信息（如果失败）
        """
        logger.info(f"开始执行浏览器任务: {task}")

        try:
            # 配置浏览器
            browser_config = BrowserConfig(
                headless=self.headless,
                disable_security=True  # 禁用安全限制（测试用）
            )

            # 创建浏览器实例
            browser = Browser(config=browser_config)

            # 创建 Agent
            agent = Agent(
                task=task,
                llm=self._create_llm_function(),
                browser=browser,
                max_actions=self.max_steps
            )

            # 如果指定了起始 URL，先导航
            if start_url:
                await browser.new_context()
                page = await browser.get_current_page()
                await page.goto(start_url)
                logger.info(f"已导航到: {start_url}")

            # 执行任务
            result = await agent.run()

            # 提取结果
            final_result = {
                "success": True,
                "result": result.final_result() if hasattr(result, 'final_result') else str(result),
                "screenshots": [],
                "error": None
            }

            # 保存截图（如果启用）
            if save_screenshots:
                try:
                    page = await browser.get_current_page()
                    screenshot_path = f"/tmp/browser_screenshot_{asyncio.get_event_loop().time()}.png"
                    await page.screenshot(path=screenshot_path)
                    final_result["screenshots"].append(screenshot_path)
                    logger.info(f"截图已保存: {screenshot_path}")
                except Exception as e:
                    logger.warning(f"保存截图失败: {e}")

            # 关闭浏览器
            await browser.close()

            logger.info("浏览器任务执行成功")
            return final_result

        except Exception as e:
            logger.error(f"浏览器任务执行失败: {e}", exc_info=True)
            return {
                "success": False,
                "result": None,
                "screenshots": [],
                "error": str(e)
            }

    def execute_sync(self, task: str, start_url: Optional[str] = None) -> Dict[str, Any]:
        """
        同步执行浏览器任务（包装异步方法）

        Args:
            task: 任务描述
            start_url: 起始 URL

        Returns:
            Dict: 执行结果
        """
        return asyncio.run(self.execute(task, start_url))


# 便捷函数
def create_browser_agent(**kwargs) -> BrowserAgent:
    """
    创建 BrowserAgent 实例的便捷函数

    Args:
        **kwargs: 传递给 BrowserAgent 的参数

    Returns:
        BrowserAgent: 浏览器 Agent 实例
    """
    return BrowserAgent(**kwargs)


async def search_with_browser(query: str, max_results: int = 5) -> str:
    """
    使用浏览器搜索（作为搜索工具的兜底）

    Args:
        query: 搜索关键词
        max_results: 最多返回结果数

    Returns:
        str: 搜索结果（格式化文本）
    """
    agent = BrowserAgent()

    task = f"""
    访问百度搜索引擎，搜索关键词: {query}

    要求：
    1. 打开 https://www.baidu.com
    2. 在搜索框输入关键词并点击搜索
    3. 提取前 {max_results} 个搜索结果的标题、链接和摘要
    4. 返回结构化的搜索结果
    """

    result = await agent.execute(task, start_url="https://www.baidu.com")

    if result["success"]:
        return result["result"]
    else:
        return f"搜索失败: {result['error']}"


async def extract_place_info(place_name: str, city: str) -> Dict[str, Any]:
    """
    使用浏览器提取地点信息（作为地图工具的兜底）

    Args:
        place_name: 地点名称
        city: 城市名称

    Returns:
        Dict: 地点信息
    """
    agent = BrowserAgent()

    task = f"""
    访问百度地图，搜索地点: {city} {place_name}

    要求：
    1. 打开 https://map.baidu.com
    2. 搜索 "{city} {place_name}"
    3. 提取地点的以下信息：
       - 名称
       - 地址
       - 评分（如果有）
       - 营业时间（如果有）
       - 电话（如果有）
    4. 返回 JSON 格式的数据
    """

    result = await agent.execute(task, start_url="https://map.baidu.com")

    if result["success"]:
        return {"success": True, "data": result["result"]}
    else:
        return {"success": False, "error": result["error"]}


# 示例使用
if __name__ == "__main__":
    # 示例 1: 基本使用
    async def test_basic():
        agent = BrowserAgent(headless=False)  # 可见模式，方便调试

        result = await agent.execute(
            task="访问 https://www.baidu.com，搜索'北京旅游景点'，提取前3个结果的标题",
            start_url="https://www.baidu.com"
        )

        print("执行结果:", result)

    # 示例 2: 使用便捷函数
    async def test_search():
        results = await search_with_browser("上海美食推荐", max_results=5)
        print("搜索结果:", results)

    # 运行测试
    # asyncio.run(test_basic())
    # asyncio.run(test_search())

    print("BrowserAgent 模块加载成功")
    print("使用示例:")
    print("  agent = BrowserAgent()")
    print("  result = await agent.execute('你的任务描述')")
