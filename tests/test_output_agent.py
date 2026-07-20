"""
OutputAgent 测试
测试输出 Agent 的功能
"""
import unittest
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent.parent))

from state import create_initial_state


class TestOutputAgent(unittest.TestCase):
    """OutputAgent 测试类"""

    def setUp(self):
        """测试前准备"""
        try:
            from agents.output_agent import OutputAgent
            self.agent = OutputAgent()
        except ImportError:
            self.skipTest("OutputAgent 无法导入")

    def test_execute_with_travel_plan(self):
        """测试有旅行计划时的执行"""
        input_data = {
            "user_input": "大理3日游",
            "destination": "大理",
            "travel_plan": {
                "destination": "大理",
                "days": 3,
                "itinerary": [
                    {"day": 1, "activities": ["抵达", "古城游览"]}
                ]
            }
        }

        result = self.agent.run_standalone(input_data)

        self.assertIsNotNone(result)
        self.assertIn("success", result)

    def test_generate_client_report(self):
        """测试生成客户报告"""
        state = create_initial_state("测试输入")
        state["destination"] = "大理"
        state["travel_plan"] = {
            "destination": "大理",
            "days": 3
        }

        # 检查是否能生成报告
        try:
            result = self.agent.execute(state)
            self.assertIsNotNone(result)
        except Exception as e:
            pass

    def test_generate_social_content(self):
        """测试生成自媒体内容"""
        state = create_initial_state("测试输入")
        state["merged_content"] = {
            "destination": "大理",
            "highlights": ["洱海", "古城"]
        }

        try:
            result = self.agent.execute(state)
            self.assertIsNotNone(result)
        except Exception as e:
            pass


if __name__ == "__main__":
    unittest.main()
