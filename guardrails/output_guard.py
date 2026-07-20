"""
输出安全护栏
=============
在 Agent 输出返回给用户之前进行安全检查。

检查项：
  1. 幻觉检测（Agent 声称做了不可能的事）
  2. PII 泄露检测（确保输出不含用户敏感信息原文）
  3. 格式合规检查
  4. 输出长度限制
  5. 置信度标记
"""
import logging
import re
from dataclasses import dataclass, field
from typing import List, Optional

from guardrails.config import GuardrailsConfig

logger = logging.getLogger(__name__)


@dataclass
class OutputGuardResult:
    """输出检查结果"""
    passed: bool = True              # 是否通过检查
    sanitized_output: str = ""       # 处理后的输出
    has_warnings: bool = False       # 是否有警告
    warnings: List[str] = field(default_factory=list)
    blocked_reason: str = ""         # 拦截原因（passed=False 时有值）
    confidence_level: str = "high"   # 输出置信度：high / medium / low


class OutputGuard:
    """
    输出安全过滤器

    使用方式：
        guard = OutputGuard()
        result = guard.check(agent_output, context={"user_input": ...})
        if not result.passed:
            return error_response(result.blocked_reason)
        # 使用 result.sanitized_output
    """

    def __init__(self, config: Optional[GuardrailsConfig] = None):
        self.config = config or GuardrailsConfig()

    def check(
        self,
        output: str,
        context: dict = None,
    ) -> OutputGuardResult:
        """
        执行全部输出安全检查。

        Args:
            output: Agent 生成的输出文本
            context: 上下文信息（可包含 user_input, user_pii 等）

        Returns:
            OutputGuardResult
        """
        context = context or {}
        result = OutputGuardResult(sanitized_output=output)

        # 1. 输出长度检查
        if len(output) > self.config.max_output_length:
            result.sanitized_output = output[:self.config.max_output_length]
            result.warnings.append(
                f"输出过长（{len(output)} 字符），已截断至 {self.config.max_output_length} 字符"
            )
            result.has_warnings = True

        # 2. 幻觉检测
        if self.config.enable_hallucination_check:
            hallucinations = self._check_hallucination(output)
            if hallucinations:
                # 不拦截，但添加免责声明
                disclaimer = "\n\n⚠️ **注意**：本系统仅提供旅行规划建议，不具备实际预订功能。如需预订请前往相关平台操作。"
                result.sanitized_output = result.sanitized_output + disclaimer
                result.warnings.extend(hallucinations)
                result.has_warnings = True
                result.confidence_level = "low"
                logger.warning(f"[OutputGuard] 幻觉检测: {hallucinations}")

        # 3. PII 泄露检测
        if self.config.enable_pii_leak_check:
            pii_leaks = self._check_pii_leak(output, context)
            if pii_leaks:
                result.warnings.extend(pii_leaks)
                result.has_warnings = True
                logger.warning(f"[OutputGuard] PII 泄露警告: {pii_leaks}")

        # 4. 置信度评估
        confidence = self._assess_confidence(output)
        result.confidence_level = confidence
        if confidence == "low":
            result.sanitized_output += "\n\n📝 *以上信息仅供参考，建议出行前核实最新情况。*"
            result.has_warnings = True
            result.warnings.append("输出置信度较低，已添加参考标记")

        return result

    def _check_hallucination(self, output: str) -> List[str]:
        """
        检测输出中的幻觉（Agent 声称做了不可能的事）。

        Returns:
            检测到的幻觉描述列表
        """
        issues = []

        for pattern in self.config.hallucination_patterns:
            if pattern in output:
                issues.append(f"检测到幻觉表述: '{pattern}'")

        # 额外模式检测
        hallucination_regexes = [
            (r"订单[号编]?\s*[:：]?\s*[A-Z0-9]{6,}", "生成了虚假订单号"),
            (r"确认码\s*[:：]?\s*[A-Z0-9]{6,}", "生成了虚假确认码"),
            (r"已发送(?:邮件|短信|通知)", "声称发送了消息"),
        ]

        for regex, desc in hallucination_regexes:
            if re.search(regex, output):
                issues.append(f"检测到幻觉: {desc}")

        return issues

    def _check_pii_leak(self, output: str, context: dict) -> List[str]:
        """
        检测输出中是否包含用户的敏感信息。

        检查：输出中不应包含身份证号、银行卡号等模式。
        """
        issues = []

        # 检测输出中的 PII 模式
        pii_patterns = [
            (r'\b\d{6}(?:19|20)\d{2}(?:0[1-9]|1[0-2])(?:0[1-9]|[12]\d|3[01])\d{3}[\dXx]\b', "身份证号"),
            (r'\b\d{4}[\s-]?\d{4}[\s-]?\d{4}[\s-]?\d{4}(?:[\s-]?\d{1,3})?\b', "银行卡号"),
        ]

        for pattern, pii_type in pii_patterns:
            if re.search(pattern, output):
                issues.append(f"输出中检测到 {pii_type}，存在泄露风险")

        return issues

    def _assess_confidence(self, output: str) -> str:
        """
        评估输出的置信度。

        判断依据：
        - 包含大量"可能"、"也许"、"不确定" → low
        - 包含具体价格但来源不明 → medium
        - 正常输出 → high
        """
        low_confidence_indicators = [
            "不确定", "可能过时", "无法确认", "建议核实",
            "信息可能有误", "仅供参考", "未能查询到",
        ]

        medium_confidence_indicators = [
            "模拟数据", "mock", "降级", "搜索失败",
            "参考价格", "估算",
        ]

        output_lower = output.lower()

        low_count = sum(1 for p in low_confidence_indicators if p in output)
        medium_count = sum(1 for p in medium_confidence_indicators if p in output_lower)

        if low_count >= 2:
            return "low"
        elif medium_count >= 2 or low_count >= 1:
            return "medium"
        return "high"
