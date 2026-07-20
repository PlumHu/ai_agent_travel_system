"""
ParseAgent 测试
测试用户意图解析和参数提取功能
"""
import unittest
import sys
from pathlib import Path

# 添加项目根目录到路径
sys.path.insert(0, str(Path(__file__).parent.parent))

from state import create_initial_state
from agents.parse_agent import ParseAgent


class TestParseAgent(unittest.TestCase):
    """ParseAgent 测试类"""

    def setUp(self):
        """测试前准备"""
        self.agent = ParseAgent()

    def test_parse_destination_intent(self):
        """测试目的地意图解析"""
        input_data = {
            "user_input": "我想去大理旅游"
        }

        result = self.agent.run_standalone(input_data)

        self.assertTrue(result["success"])
        self.assertIn("destination", result["data"])
        self.assertEqual(result["data"]["destination"], "大理")

    def test_parse_budget(self):
        """测试预算解析"""
        input_data = {
            "user_input": "我预算5000元，想去云南玩"
        }

        result = self.agent.run_standalone(input_data)

        self.assertTrue(result["success"])
        self.assertIn("budget", result["data"])

    def test_parse_dates(self):
        """测试日期解析"""
        input_data = {
            "user_input": "我7月1号到7月5号想去旅游"
        }

        result = self.agent.run_standalone(input_data)

        self.assertTrue(result["success"])
        # 检查日期是否被正确提取

    def test_parse_preferences(self):
        """测试偏好解析"""
        input_data = {
            "user_input": "我喜欢自然风光和美食"
        }

        result = self.agent.run_standalone(input_data)

        self.assertTrue(result["success"])
        self.assertIn("preferences", result["data"])

    def test_empty_input(self):
        """测试空输入"""
        input_data = {
            "user_input": ""
        }

        result = self.agent.run_standalone(input_data)

        # 应该能够处理空输入
        self.assertIsNotNone(result)


if __name__ == "__main__":
    unittest.main()
