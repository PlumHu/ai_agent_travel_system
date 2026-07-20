"""
TravelAgent 测试
测试旅行规划 Agent 的功能
"""
import unittest
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent.parent))

from state import create_initial_state
from agents.travel_agent import TravelAgent


class TestTravelAgent(unittest.TestCase):
    """TravelAgent 测试类"""

    def setUp(self):
        """测试前准备"""
        self.agent = TravelAgent()

    def test_execute_with_destination(self):
        """测试有目的地时的执行"""
        input_data = {
            "user_input": "我想去大理玩3天",
            "destination": "大理",
            "start_date": "2026-07-01",
            "end_date": "2026-07-03"
        }

        result = self.agent.run_standalone(input_data)

        self.assertIsNotNone(result)
        self.assertIn("success", result)

    def test_execute_without_destination(self):
        """测试没有目的地时的执行"""
        input_data = {
            "user_input": "我想出去玩，但不知道去哪"
        }

        result = self.agent.run_standalone(input_data)

        self.assertIsNotNone(result)

    def test_extract_output(self):
        """测试输出提取"""
        state = create_initial_state("测试输入")
        state["travel_plan"] = {
            "destination": "大理",
            "days": 3,
            "itinerary": []
        }

        output = self.agent._extract_output(state)

        self.assertIn("destination", output)


if __name__ == "__main__":
    unittest.main()
