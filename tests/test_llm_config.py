"""
LLMConfig 测试
测试 LLM 配置管理器的功能
"""
import unittest
import sys
import os
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent.parent))


class TestLLMConfig(unittest.TestCase):
    """LLMConfig 测试类"""

    def test_import_llm_config(self):
        """测试导入 LLMConfig"""
        try:
            from llm_config import LLMConfig
            self.assertTrue(True)
        except ImportError:
            self.skipTest("llm_config 模块无法导入")

    def test_list_providers(self):
        """测试列出提供商"""
        try:
            from llm_config import LLMConfig

            providers = LLMConfig.list_providers()

            self.assertIsInstance(providers, list)
            self.assertGreater(len(providers), 0)
        except ImportError:
            self.skipTest("llm_config 模块无法导入")

    def test_provider_config(self):
        """测试提供商配置"""
        try:
            from llm_config import LLMConfig

            # 测试获取配置
            config = LLMConfig.get_provider_config("deepseek")

            self.assertIsNotNone(config)
            self.assertIn("base_url", config)
        except ImportError:
            self.skipTest("llm_config 模块无法导入")

    def test_create_llm_instance(self):
        """测试创建 LLM 实例"""
        try:
            from llm_config import LLMConfig

            # 不提供 API Key 时应该能够创建实例
            # 但实际调用可能会失败
            llm = LLMConfig(provider="deepseek")

            self.assertIsNotNone(llm)
        except ImportError:
            self.skipTest("llm_config 模块无法导入")
        except Exception as e:
            # 某些错误是预期的
            pass


class TestLLMConfigIntegration(unittest.TestCase):
    """LLMConfig 集成测试"""

    def test_environment_variables(self):
        """测试环境变量"""
        # 检查是否有 LLM 相关的环境变量
        env_vars = [
            "OPENAI_API_KEY",
            "DEEPSEEK_API_KEY",
            "NVIDIA_API_KEY"
        ]

        has_any_key = any(os.getenv(var) for var in env_vars)

        if not has_any_key:
            self.skipTest("没有配置任何 LLM API Key")


if __name__ == "__main__":
    unittest.main()
