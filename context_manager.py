"""
上下文管理器
处理多轮对话的上下文压缩，防止超出 LLM token 限制。

策略：
  - 滑动窗口：保留最近 KEEP_RECENT 轮完整对话
  - LLM 摘要：超出窗口的历史用 LLM 压缩为一条摘要消息
  - 降级兜底：LLM 不可用时截断最旧的消息
  - 长期记忆：每轮对话后自动提取实体存入 LongTermMemory（可选）
"""

import json
import logging
from collections import deque
from typing import List, Dict, Any, Optional, Tuple

logger = logging.getLogger(__name__)

# ── 配置常量 ──────────────────────────────────────────────
# 滑动窗口：保留最近 N 轮完整对话（1轮 = 1条 human + 1条 assistant）
KEEP_RECENT_TURNS = 5
# 消息条数上限（超过此数触发压缩）
MAX_MESSAGES = KEEP_RECENT_TURNS * 2 + 2   # +2 为 system + summary 预留
# 单条消息估算 token 时按字符数 / 2 粗算（中文约 1.5 字/token，保守取 2）
CHARS_PER_TOKEN = 2
# 触发压缩的 token 软上限
TOKEN_SOFT_LIMIT = 6000


class ContextManager:
    """
    多轮对话上下文管理器

    用法：
        ctx = ContextManager(llm=your_llm)

        # 每轮对话后调用
        ctx.add_turn(user_msg, assistant_msg)

        # 获取压缩后的消息列表传给 LLM
        messages = ctx.get_messages()
    """

    def __init__(
        self,
        llm=None,
        keep_recent_turns: int = KEEP_RECENT_TURNS,
        token_soft_limit: int = TOKEN_SOFT_LIMIT,
        system_prompt: str = "",
        long_term_memory=None,
    ):
        """
        Args:
            llm: LangChain ChatLLM 实例，用于摘要压缩；为 None 时降级为截断
            keep_recent_turns: 保留最近几轮完整对话
            token_soft_limit: 触发压缩的 token 软上限（估算值）
            system_prompt: 系统提示词（始终保留在首位）
            long_term_memory: LongTermMemory 实例；传入后每轮对话自动提取实体写入，
                              get_messages() 时将用户画像注入 Prompt
        """
        self.llm = llm
        self.keep_recent_turns = keep_recent_turns
        self.token_soft_limit = token_soft_limit
        self.system_prompt = system_prompt
        self.long_term_memory = long_term_memory

        # 完整历史（deque 自动丢弃最旧）
        self._history: deque = deque()
        # 压缩后的摘要文本
        self._summary: str = ""
        # 压缩次数统计
        self.compress_count: int = 0

    # ── 公共接口 ──────────────────────────────────────────

    def add_turn(self, user_message: str, assistant_message: str) -> None:
        """记录一轮对话，并同步写入长期记忆（若已配置）"""
        self._history.append({"role": "user", "content": user_message})
        self._history.append({"role": "assistant", "content": assistant_message})

        # 写入长期记忆
        if self.long_term_memory is not None:
            try:
                self.long_term_memory.extract_and_save(user_message, assistant_message)
            except Exception as e:
                logger.warning(f"[ContextManager] 长期记忆写入失败: {e}")

        if self._should_compress():
            self._compress()

    def add_user_message(self, message: str) -> None:
        """仅记录用户消息（流式场景）"""
        self._history.append({"role": "user", "content": message})
        self._pending_user_message = message

    def add_assistant_message(self, message: str) -> None:
        """记录 assistant 消息，并检查是否需要压缩；同步写入长期记忆"""
        self._history.append({"role": "assistant", "content": message})

        # 写入长期记忆（与对应的 user 消息配对）
        if self.long_term_memory is not None:
            pending = getattr(self, "_pending_user_message", "")
            if pending:
                try:
                    self.long_term_memory.extract_and_save(pending, message)
                except Exception as e:
                    logger.warning(f"[ContextManager] 长期记忆写入失败: {e}")
            self._pending_user_message = ""

        if self._should_compress():
            self._compress()

    def get_messages(self, query: str = "") -> List[Dict[str, str]]:
        """
        返回压缩后的消息列表，可直接传给 LLM。

        结构：
          [system_prompt?] + [long_term_memory?] + [summary_message?] + [recent_turns...]

        Args:
            query: 当前用户输入，用于从长期记忆中检索相关内容（可选）
        """
        messages = []

        # 1. 系统提示词
        if self.system_prompt:
            messages.append({"role": "system", "content": self.system_prompt})

        # 2. 长期记忆（注入用户画像 + 相关历史）
        if self.long_term_memory is not None:
            try:
                mem_context = self.long_term_memory.get_memory_context(query=query)
                if mem_context:
                    messages.append({"role": "system", "content": mem_context})
            except Exception as e:
                logger.warning(f"[ContextManager] 长期记忆读取失败: {e}")

        # 3. 历史摘要（短期压缩摘要）
        if self._summary:
            messages.append({
                "role": "system",
                "content": f"[对话历史摘要]\n{self._summary}"
            })

        # 4. 最近 N 轮完整对话
        recent = list(self._history)[-(self.keep_recent_turns * 2):]
        messages.extend(recent)

        return messages

    def get_stats(self) -> Dict[str, Any]:
        """返回当前上下文统计信息"""
        total_chars = sum(len(m["content"]) for m in self._history)
        return {
            "history_turns": len(self._history) // 2,
            "history_messages": len(self._history),
            "estimated_tokens": total_chars // CHARS_PER_TOKEN,
            "summary_length": len(self._summary),
            "compress_count": self.compress_count,
        }

    def reset(self) -> None:
        """清空历史（新会话时调用）"""
        self._history.clear()
        self._summary = ""
        self.compress_count = 0

    def load_state(self, state: Dict[str, Any]) -> None:
        """从持久化状态恢复（跨会话）"""
        self._history = deque(state.get("history", []))
        self._summary = state.get("summary", "")
        self.compress_count = state.get("compress_count", 0)

    def dump_state(self) -> Dict[str, Any]:
        """导出状态用于持久化"""
        return {
            "history": list(self._history),
            "summary": self._summary,
            "compress_count": self.compress_count,
        }

    # ── 内部逻辑 ──────────────────────────────────────────

    def _should_compress(self) -> bool:
        """判断是否需要压缩"""
        if len(self._history) <= self.keep_recent_turns * 2:
            return False
        total_chars = sum(len(m["content"]) for m in self._history)
        estimated_tokens = total_chars // CHARS_PER_TOKEN
        return estimated_tokens > self.token_soft_limit

    def _compress(self) -> None:
        """执行压缩：将旧消息摘要化，保留最近 N 轮"""
        keep_count = self.keep_recent_turns * 2
        all_messages = list(self._history)

        if len(all_messages) <= keep_count:
            return

        # 需要被压缩的旧消息
        old_messages = all_messages[:-keep_count]
        # 保留的新消息
        recent_messages = all_messages[-keep_count:]

        new_summary = self._summarize(old_messages)

        # 合并新旧摘要
        if self._summary:
            self._summary = f"{self._summary}\n\n{new_summary}"
        else:
            self._summary = new_summary

        # 重置 history 只保留最近 N 轮
        self._history = deque(recent_messages)
        self.compress_count += 1

        logger.info(
            f"[ContextManager] 压缩完成 #{self.compress_count}，"
            f"压缩了 {len(old_messages)} 条消息，"
            f"保留 {len(recent_messages)} 条，"
            f"摘要长度 {len(self._summary)} 字符"
        )

    def _summarize(self, messages: List[Dict[str, str]]) -> str:
        """
        将消息列表压缩为摘要文本。
        优先用 LLM，失败时降级为关键信息提取。
        """
        if self.llm is not None:
            try:
                return self._llm_summarize(messages)
            except Exception as e:
                logger.warning(f"[ContextManager] LLM 摘要失败，降级为规则提取: {e}")

        return self._rule_summarize(messages)

    def _llm_summarize(self, messages: List[Dict[str, str]]) -> str:
        """使用 LLM 生成摘要"""
        from langchain_core.messages import HumanMessage, SystemMessage

        conversation_text = "\n".join(
            f"{'用户' if m['role'] == 'user' else 'AI'}: {m['content']}"
            for m in messages
        )

        prompt = f"""请将以下旅行规划对话历史压缩为简洁摘要，保留关键信息：
- 用户的目的地、出行时间、预算、偏好
- 已确认的行程安排或推荐结果
- 用户的重要需求变更

对话历史：
{conversation_text}

请用200字以内的中文摘要，不要遗漏关键决策信息。"""

        response = self.llm.invoke([
            SystemMessage(content="你是旅行规划助手，负责总结对话历史。"),
            HumanMessage(content=prompt)
        ])
        return response.content.strip()

    def _rule_summarize(self, messages: List[Dict[str, str]]) -> str:
        """规则降级：提取关键字段构成摘要"""
        import re

        keywords = {
            "目的地": r"(去|到|前往|目的地是?)[：:]?\s*([^\s，。,\.]{2,6})",
            "时间": r"(\d{1,2}月|\d{4}-\d{2}-\d{2}|[0-9]+天)",
            "预算": r"预算[\s：:]*([0-9]+[元万]?)",
        }

        extracted: Dict[str, List[str]] = {}
        full_text = " ".join(m["content"] for m in messages)

        for key, pattern in keywords.items():
            matches = re.findall(pattern, full_text)
            if matches:
                vals = [m[-1] if isinstance(m, tuple) else m for m in matches]
                extracted[key] = list(dict.fromkeys(vals))[:3]  # 去重，最多3个

        lines = [f"[历史对话摘要（共 {len(messages)} 条）]"]
        for key, vals in extracted.items():
            lines.append(f"{key}：{'、'.join(vals)}")
        if not extracted:
            # 实在没提取到，截取头尾各一条
            if messages:
                lines.append(f"首条：{messages[0]['content'][:100]}")
            if len(messages) > 1:
                lines.append(f"末条：{messages[-1]['content'][:100]}")

        return "\n".join(lines)
