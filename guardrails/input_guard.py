"""
输入安全护栏
=============
在用户输入进入 Agent Pipeline 之前进行安全检查。

检查项：
  1. Prompt Injection 检测
  2. PII（个人敏感信息）检测与脱敏
  3. 内容安全检查
  4. 输入长度限制
"""
import logging
import re
from dataclasses import dataclass, field
from typing import List, Optional

from guardrails.config import GuardrailsConfig

logger = logging.getLogger(__name__)


@dataclass
class GuardResult:
    """安全检查结果"""
    blocked: bool = False           # 是否拦截（True=拒绝处理）
    sanitized_input: str = ""       # 脱敏后的输入（PII 替换为 ***）
    reason: str = ""                # 拦截原因
    warnings: List[str] = field(default_factory=list)  # 警告信息（不拦截但提示用户）
    detected_issues: List[str] = field(default_factory=list)  # 检测到的问题列表


class InputGuard:
    """
    输入安全过滤器

    使用方式：
        guard = InputGuard()
        result = guard.check(user_input)
        if result.blocked:
            return error_response(result.reason)
        # 使用 result.sanitized_input 继续处理
    """

    def __init__(self, config: Optional[GuardrailsConfig] = None):
        self.config = config or GuardrailsConfig()

    def check(self, user_input: str) -> GuardResult:
        """
        执行全部输入安全检查。

        Args:
            user_input: 用户原始输入

        Returns:
            GuardResult 包含是否拦截、脱敏后文本、警告信息
        """
        result = GuardResult(sanitized_input=user_input)

        # 1. 长度检查（最先执行，最低成本）
        if len(user_input) > self.config.max_input_length:
            result.blocked = True
            result.reason = (
                f"输入过长（{len(user_input)} 字符），"
                f"最大允许 {self.config.max_input_length} 字符。请精简后重试。"
            )
            return result

        # 2. 空输入
        if not user_input.strip():
            result.blocked = True
            result.reason = "输入不能为空"
            return result

        # 3. Prompt Injection 检测
        if self.config.enable_injection_detection:
            injection_result = self._check_injection(user_input)
            if injection_result:
                result.blocked = True
                result.reason = "检测到潜在的提示注入攻击，已拦截。如有疑问请重新表述您的旅行需求。"
                result.detected_issues.append(f"injection: {injection_result}")
                logger.warning(f"[InputGuard] Prompt Injection 拦截: {injection_result}")
                return result

        # 4. 内容安全检查
        if self.config.enable_content_safety:
            safety_result = self._check_content_safety(user_input)
            if safety_result:
                result.blocked = True
                result.reason = "输入包含不适当内容，无法处理。请输入正常的旅行规划需求。"
                result.detected_issues.append(f"unsafe_content: {safety_result}")
                logger.warning(f"[InputGuard] 内容安全拦截: {safety_result}")
                return result

        # 5. PII 检测与脱敏（不拦截，仅脱敏 + 警告）
        if self.config.enable_pii_detection:
            sanitized, pii_warnings = self._detect_and_sanitize_pii(user_input)
            if pii_warnings:
                result.sanitized_input = sanitized
                result.warnings.extend(pii_warnings)
                result.detected_issues.extend([f"pii: {w}" for w in pii_warnings])
                logger.info(f"[InputGuard] PII 脱敏: {pii_warnings}")

        return result

    def _check_injection(self, text: str) -> Optional[str]:
        """
        检测 Prompt Injection。

        使用关键词匹配 + 模式检测。
        返回匹配到的模式（用于日志），无匹配返回 None。
        """
        text_lower = text.lower()

        for pattern in self.config.injection_patterns:
            if pattern.lower() in text_lower:
                return pattern

        # 高级模式：检测伪造系统消息格式
        injection_regexes = [
            r"(?:system|系统)\s*(?::|：)\s*.{10,}",   # system: <long text>
            r"(?:assistant|AI)\s*(?::|：)\s*.{10,}",   # assistant: <long text>
            r"\[INST\].*\[/INST\]",                     # Llama 格式注入
            r"<\|(?:system|user|assistant)\|>",          # ChatML 格式注入
        ]

        for regex in injection_regexes:
            if re.search(regex, text, re.IGNORECASE):
                return f"regex: {regex[:30]}"

        return None

    def _check_content_safety(self, text: str) -> Optional[str]:
        """
        内容安全检查（关键词黑名单）。
        返回匹配的关键词，无匹配返回 None。
        """
        for pattern in self.config.unsafe_content_patterns:
            if pattern in text:
                return pattern
        return None

    def _detect_and_sanitize_pii(self, text: str) -> tuple:
        """
        检测并脱敏个人敏感信息。

        检测类型：
        - 身份证号（18位）
        - 银行卡号（16-19位）
        - 手机号（11位）
        - 邮箱地址

        Returns:
            (脱敏后文本, 警告信息列表)
        """
        warnings = []
        sanitized = text

        # 身份证号（18位：6位地址码 + 8位出生日期 + 3位序号 + 1位校验码）
        id_pattern = r'\b\d{6}(?:19|20)\d{2}(?:0[1-9]|1[0-2])(?:0[1-9]|[12]\d|3[01])\d{3}[\dXx]\b'
        if re.search(id_pattern, text):
            sanitized = re.sub(id_pattern, "***身份证已隐藏***", sanitized)
            warnings.append("检测到身份证号，已自动脱敏。请勿在对话中输入身份证号。")

        # 银行卡号（16-19位连续数字）
        bank_pattern = r'\b\d{4}[\s-]?\d{4}[\s-]?\d{4}[\s-]?\d{4}(?:[\s-]?\d{1,3})?\b'
        if re.search(bank_pattern, text):
            sanitized = re.sub(bank_pattern, "***银行卡已隐藏***", sanitized)
            warnings.append("检测到银行卡号，已自动脱敏。请勿在对话中输入银行卡号。")

        # 手机号（1开头的11位数字，中文环境中可能无 \b 边界）
        phone_pattern = r'(?<!\d)1[3-9]\d{9}(?!\d)'
        if re.search(phone_pattern, text):
            sanitized = re.sub(phone_pattern, "***手机号已隐藏***", sanitized)
            warnings.append("检测到手机号，已自动脱敏。旅行规划不需要您的手机号。")

        # 邮箱
        email_pattern = r'\b[A-Za-z0-9._%+-]+@[A-Za-z0-9.-]+\.[A-Z|a-z]{2,}\b'
        if re.search(email_pattern, text):
            sanitized = re.sub(email_pattern, "***邮箱已隐藏***", sanitized)
            warnings.append("检测到邮箱地址，已自动脱敏。")

        return sanitized, warnings
