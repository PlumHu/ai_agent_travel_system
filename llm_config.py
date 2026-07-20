"""
统一 LLM 配置管理器
支持多种 LLM API：百度 OneAPI、英伟达、DeepSeek、OpenAI 等
"""
import os
from typing import Optional, Dict, Any, List
from openai import OpenAI
import logging

logger = logging.getLogger(__name__)


class LLMConfig:
    """LLM 配置类"""

    # 预设的 LLM 提供商配置
    PROVIDERS = {
        "baidu_oneapi": {
            "name": "百度 OneAPI（内部集成）",
            "base_url": "https://oneapi-comate.baidu-int.com/v1",
            "default_model": "ERNIE-4.0-8K",
            "env_key": "BAIDU_ONEAPI_KEY",
            "env_model": "BAIDU_ONEAPI_MODEL"
        },
        "nvidia": {
            "name": "英伟达 NIM",
            "base_url": "https://integrate.api.nvidia.com/v1",
            "default_model": "meta/llama-3.1-70b-instruct",
            "env_key": "NVIDIA_API_KEY",
            "env_model": "NVIDIA_MODEL"
        },
        "deepseek": {
            "name": "DeepSeek",
            "base_url": "https://api.deepseek.com/v1",
            "default_model": "deepseek-chat",
            "env_key": "DEEPSEEK_API_KEY",
            "env_model": "DEEPSEEK_MODEL"
        },
        "openai": {
            "name": "OpenAI",
            "base_url": "https://api.openai.com/v1",
            "default_model": "gpt-4",
            "env_key": "OPENAI_API_KEY",
            "env_model": "OPENAI_MODEL"
        },
        "qianfan": {
            "name": "百度千帆",
            "base_url": "https://aip.baidubce.com/rpc/2.0/ai_custom/v1/wenxinworkshop",
            "default_model": "ernie-bot-4",
            "env_key": "QIANFAN_API_KEY",  # 或使用 AK/SK
            "env_model": "QIANFAN_MODEL",
            "note": "千帆需要特殊认证，暂不支持 OpenAI SDK"
        },
        "custom": {
            "name": "自定义 OpenAI 兼容接口",
            "base_url": None,  # 从环境变量读取
            "default_model": None,
            "env_key": "CUSTOM_API_KEY",
            "env_model": "CUSTOM_MODEL",
            "env_base_url": "CUSTOM_BASE_URL"
        }
    }

    def __init__(
        self,
        provider: str = "baidu_oneapi",
        api_key: Optional[str] = None,
        base_url: Optional[str] = None,
        model: Optional[str] = None
    ):
        """
        初始化 LLM 配置

        Args:
            provider: 提供商名称（baidu_oneapi, nvidia, deepseek, openai, custom）
            api_key: API Key（优先级高于环境变量）
            base_url: API 端点（优先级高于环境变量）
            model: 模型名称（优先级高于环境变量）
        """
        if provider not in self.PROVIDERS:
            raise ValueError(f"不支持的 provider: {provider}，可选: {list(self.PROVIDERS.keys())}")

        self.provider = provider
        self.provider_config = self.PROVIDERS[provider]

        # 配置优先级：参数 > 环境变量 > 默认值
        self.api_key = api_key or os.getenv(self.provider_config["env_key"], "")
        self.base_url = base_url or os.getenv(
            self.provider_config.get("env_base_url", ""),
            self.provider_config["base_url"]
        )
        self.model = model or os.getenv(
            self.provider_config["env_model"],
            self.provider_config["default_model"]
        )

        # 验证配置
        if not self.api_key:
            raise ValueError(
                f"未设置 API Key，请通过参数传入或设置环境变量 {self.provider_config['env_key']}"
            )

        if provider == "custom" and not self.base_url:
            raise ValueError("自定义提供商需要设置 base_url 或环境变量 CUSTOM_BASE_URL")

        logger.info(
            f"LLM 配置初始化完成: provider={provider}, model={self.model}, "
            f"base_url={self.base_url}"
        )

    def create_client(self) -> OpenAI:
        """
        创建 OpenAI 客户端

        Returns:
            OpenAI: OpenAI SDK 客户端
        """
        return OpenAI(
            api_key=self.api_key,
            base_url=self.base_url
        )

    def chat_completion(
        self,
        messages: List[Dict[str, str]],
        temperature: float = 0.7,
        max_tokens: int = 2000,
        **kwargs
    ) -> str:
        """
        调用 LLM 完成聊天

        Args:
            messages: 消息列表 [{"role": "user", "content": "..."}]
            temperature: 温度参数
            max_tokens: 最大 token 数
            **kwargs: 其他参数传递给 OpenAI SDK

        Returns:
            str: LLM 响应内容
        """
        client = self.create_client()

        try:
            response = client.chat.completions.create(
                model=self.model,
                messages=messages,
                temperature=temperature,
                max_tokens=max_tokens,
                **kwargs
            )
            return response.choices[0].message.content
        except Exception as e:
            logger.error(f"LLM 调用失败: {e}")
            raise

    def get_info(self) -> Dict[str, Any]:
        """
        获取配置信息（脱敏）

        Returns:
            Dict: 配置信息
        """
        return {
            "provider": self.provider,
            "provider_name": self.provider_config["name"],
            "model": self.model,
            "base_url": self.base_url,
            "api_key": f"{self.api_key[:10]}..." if self.api_key else "未设置"
        }

    @classmethod
    def list_providers(cls) -> List[Dict[str, str]]:
        """
        列出所有支持的提供商

        Returns:
            List[Dict]: 提供商列表
        """
        return [
            {
                "key": key,
                "name": config["name"],
                "default_model": config["default_model"],
                "base_url": config["base_url"],
                "env_key": config["env_key"]
            }
            for key, config in cls.PROVIDERS.items()
        ]


# 便捷函数
def create_llm_from_env(provider: str = None) -> LLMConfig:
    """
    从环境变量创建 LLM 配置

    Args:
        provider: 提供商名称，默认自动检测

    Returns:
        LLMConfig: LLM 配置实例
    """
    # 自动检测可用的提供商
    if provider is None:
        for key, config in LLMConfig.PROVIDERS.items():
            if os.getenv(config["env_key"]):
                provider = key
                logger.info(f"自动检测到提供商: {config['name']}")
                break

        if provider is None:
            raise ValueError("未检测到任何可用的 LLM 配置，请设置相应的环境变量")

    return LLMConfig(provider=provider)


def get_available_providers() -> List[str]:
    """
    获取当前环境中可用的提供商

    Returns:
        List[str]: 可用的提供商列表
    """
    available = []
    for key, config in LLMConfig.PROVIDERS.items():
        if os.getenv(config["env_key"]):
            available.append(key)

    return available


# 示例使用
if __name__ == "__main__":
    print("=" * 60)
    print("LLM 配置管理器")
    print("=" * 60)

    # 列出所有提供商
    print("\n支持的 LLM 提供商:")
    for provider in LLMConfig.list_providers():
        print(f"  - {provider['key']}: {provider['name']}")
        print(f"    模型: {provider['default_model']}")
        print(f"    端点: {provider['base_url']}")
        print(f"    环境变量: {provider['env_key']}")
        print()

    # 检测可用提供商
    print("当前环境可用的提供商:")
    available = get_available_providers()
    if available:
        for p in available:
            print(f"  ✓ {p}")
    else:
        print("  ⚠️ 无可用提供商，请配置环境变量")

    # 示例：创建配置
    print("\n示例 1: 使用百度 OneAPI")
    try:
        llm = LLMConfig(
            provider="baidu_oneapi",
            api_key="your_key_here",
            model="ERNIE-4.0-8K"
        )
        print(f"  配置成功: {llm.get_info()}")
    except ValueError as e:
        print(f"  ⚠️ {e}")

    print("\n示例 2: 使用英伟达 API")
    try:
        llm = LLMConfig(
            provider="nvidia",
            api_key="nvapi-xxx",
            model="meta/llama-3.1-70b-instruct"
        )
        print(f"  配置成功: {llm.get_info()}")
    except ValueError as e:
        print(f"  ⚠️ {e}")

    print("\n示例 3: 自动检测")
    try:
        llm = create_llm_from_env()
        print(f"  配置成功: {llm.get_info()}")
    except ValueError as e:
        print(f"  ⚠️ {e}")
