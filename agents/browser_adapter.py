"""BrowserAgent → BaseAgent 适配器，供 AgentManager 独立调用。"""
from typing import Any, Dict

from agents.base_agent import BaseAgent


class BrowserAgentAdapter(BaseAgent):
    """把 BrowserAgent 适配为 BaseAgent。"""

    def __init__(self, headless: bool = True):
        super().__init__("BrowserAgent")
        self.headless = headless
        self._inner = None

    def _get_inner(self):
        if self._inner is None:
            from agents.browser_agent import BROWSER_USE_AVAILABLE, BrowserAgent

            if not BROWSER_USE_AVAILABLE:
                raise RuntimeError(
                    "browser-use 未安装，请运行: "
                    "pip install browser-use && playwright install chromium"
                )
            self._inner = BrowserAgent(headless=self.headless)
        return self._inner

    def execute(self, state: Dict[str, Any]) -> Dict[str, Any]:
        task = state.get("user_input") or state.get("task") or ""
        start_url = state.get("start_url")
        if not task:
            state["error"] = "缺少浏览器任务描述"
            return state
        try:
            result = self._get_inner().execute_sync(task, start_url=start_url)
            state["_browser_result"] = result
            if not result.get("success"):
                state["error"] = result.get("error") or "浏览器任务失败"
        except Exception as e:
            state["error"] = str(e)
            state["_browser_result"] = {"success": False, "error": str(e)}
        return state

    def _extract_output(self, state: Dict[str, Any]) -> Dict[str, Any]:
        return state.get("_browser_result") or {
            "success": False,
            "error": state.get("error"),
        }
