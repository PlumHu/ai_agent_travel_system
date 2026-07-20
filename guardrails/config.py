"""
Guardrails 配置
"""
from dataclasses import dataclass, field
from typing import List


@dataclass
class GuardrailsConfig:
    """安全护栏全局配置"""

    # 输入限制
    max_input_length: int = 2000           # 最大输入字符数
    enable_injection_detection: bool = True  # 是否开启注入检测
    enable_pii_detection: bool = True       # 是否开启 PII 检测
    enable_content_safety: bool = True      # 是否开启内容安全检查

    # 输出限制
    enable_hallucination_check: bool = True  # 是否检测幻觉
    enable_pii_leak_check: bool = True       # 是否检测 PII 泄露
    max_output_length: int = 10000           # 最大输出字符数

    # 限流配置
    max_tokens_per_session: int = 50000      # 单次会话最大 token
    max_requests_per_hour: int = 30          # 每小时最大请求数
    max_tool_calls_per_request: int = 10     # 单次请求最大工具调用数

    # Prompt Injection 检测关键词
    injection_patterns: List[str] = field(default_factory=lambda: [
        "ignore previous",
        "ignore above",
        "forget your instructions",
        "disregard",
        "system:",
        "你现在是",
        "忘记之前",
        "忽略上面",
        "你不再是",
        "新的指令",
        "override",
        "jailbreak",
        "DAN mode",
    ])

    # 内容安全黑名单关键词
    unsafe_content_patterns: List[str] = field(default_factory=lambda: [
        "制造炸弹",
        "购买毒品",
        "非法入境",
        "洗钱",
        "贩卖人口",
    ])

    # 幻觉检测关键词（Agent 不应声称做了这些事）
    hallucination_patterns: List[str] = field(default_factory=lambda: [
        "我已为您预订",
        "已成功下单",
        "订单号为",
        "已付款",
        "已确认预订",
        "已帮您购买",
        "支付成功",
    ])
