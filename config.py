"""
配置管理模块

LLM 多 provider 兜底路由：
  1. 按 PROVIDER_PRIORITY 顺序，选第一个设置了 Key 的 provider
  2. DEFAULT_LLM_PROVIDER 可把某个 provider 置顶
  3. 所有 provider 均无 Key 时启动报警（不崩溃）
  4. 运行时调用失败时通过 get_llm_fallback() 切换下一个
"""
import os
import logging
from pathlib import Path
from dotenv import load_dotenv

load_dotenv()

logger = logging.getLogger(__name__)

PROJECT_ROOT = Path(__file__).parent

# ── Provider 配置表 ───────────────────────────────────────────
_PROVIDERS = {
    "deepseek": (
        "DEEPSEEK_API_KEY",
        "https://api.deepseek.com/v1",
        "DEEPSEEK_MODEL",
        "deepseek-chat",
    ),
    "openai": (
        "OPENAI_API_KEY",
        os.getenv("OPENAI_API_BASE", "https://api.openai.com/v1"),
        "OPENAI_MODEL",
        "gpt-4",
    ),
    "nvidia": (
        "NVIDIA_API_KEY",
        "https://integrate.api.nvidia.com/v1",
        "NVIDIA_MODEL",
        "meta/llama-3.1-70b-instruct",
    ),
    "baidu_oneapi": (
        "BAIDU_ONEAPI_KEY",
        "https://oneapi-comate.baidu-int.com/v1",
        "BAIDU_ONEAPI_MODEL",
        "ERNIE-4.0-8K",
    ),
    "custom": (
        "CUSTOM_API_KEY",
        os.getenv("CUSTOM_BASE_URL", ""),
        "CUSTOM_MODEL",
        os.getenv("CUSTOM_MODEL", ""),
    ),
}

_DEFAULT_PRIORITY = ["deepseek", "openai", "nvidia", "baidu_oneapi", "custom"]
_preferred = os.getenv("DEFAULT_LLM_PROVIDER", "").lower()


def _build_available() -> list:
    order = (
        [_preferred] + [p for p in _DEFAULT_PRIORITY if p != _preferred]
        if _preferred in _PROVIDERS
        else _DEFAULT_PRIORITY
    )
    available = []
    for name in order:
        if name not in _PROVIDERS:
            continue
        key_env, base_url, model_env, default_model = _PROVIDERS[name]
        key = os.getenv(key_env, "")
        if key:
            available.append({
                "name": name,
                "api_key": key,
                "base_url": base_url,
                "model": os.getenv(model_env, default_model),
            })
    return available


AVAILABLE_PROVIDERS = _build_available()

if not AVAILABLE_PROVIDERS:
    logger.warning(
        "[config] 未检测到任何 LLM Key！请在 .env 中至少填入一个，"
        "例如取消注释 DEEPSEEK_API_KEY=sk-xxx"
    )
    AVAILABLE_PROVIDERS = [{
        "name": "openai",
        "api_key": "",
        "base_url": "https://api.openai.com/v1",
        "model": "gpt-4",
    }]

_primary = AVAILABLE_PROVIDERS[0]
OPENAI_API_KEY  = _primary["api_key"]
OPENAI_API_BASE = _primary["base_url"]
OPENAI_MODEL    = _primary["model"]
TEMPERATURE     = 0.7

logger.info(
    f"[config] 主 LLM: {_primary['name']} / {OPENAI_MODEL} "
    f"| 备用: {[p['name'] for p in AVAILABLE_PROVIDERS[1:]]}"
)


def get_llm(streaming: bool = False):
    """返回主 provider 的 ChatOpenAI 实例"""
    from langchain_openai import ChatOpenAI
    p = AVAILABLE_PROVIDERS[0]
    return ChatOpenAI(
        model=p["model"],
        temperature=TEMPERATURE,
        openai_api_key=p["api_key"],
        openai_api_base=p["base_url"],
        streaming=streaming,
    )


def get_llm_fallback(exclude: list = None, streaming: bool = False):
    """
    跳过 exclude 中的 provider，返回 (ChatOpenAI实例, provider_name)。
    所有 provider 均失败时返回 (None, None)。
    """
    from langchain_openai import ChatOpenAI
    exclude = exclude or []
    for p in AVAILABLE_PROVIDERS:
        if p["name"] not in exclude:
            logger.info(f"[config] 切换到备用 LLM: {p['name']} / {p['model']}")
            return ChatOpenAI(
                model=p["model"],
                temperature=TEMPERATURE,
                openai_api_key=p["api_key"],
                openai_api_base=p["base_url"],
                streaming=streaming,
            ), p["name"]
    logger.error("[config] 所有 LLM provider 均不可用")
    return None, None


# ── RAG 配置 ──────────────────────────────────────────────────
VECTOR_DB_PATH  = PROJECT_ROOT / "knowledge" / "vector_db"
RAW_DATA_PATH   = PROJECT_ROOT / "knowledge" / "raw_data"
EMBEDDING_MODEL = os.getenv("EMBEDDING_MODEL", "BAAI/bge-small-zh-v1.5")
TOP_K_RESULTS   = 5

# ── 工具 API 配置 ─────────────────────────────────────────────
OPENWEATHER_API_KEY  = os.getenv("OPENWEATHER_API_KEY", "")
BAIDU_MAPS_API_KEY   = os.getenv("BAIDU_MAPS_API_KEY", "")
BRAVE_SEARCH_API_KEY = os.getenv("BRAVE_SEARCH_API_KEY", "")
SERPER_API_KEY       = os.getenv("SERPER_API_KEY", "")

# ── 输出目录 ──────────────────────────────────────────────────
OUTPUT_DIR  = PROJECT_ROOT / "output"
REPORTS_DIR = OUTPUT_DIR / "reports"
SOCIAL_DIR  = OUTPUT_DIR / "social"

for dir_path in [VECTOR_DB_PATH, RAW_DATA_PATH, REPORTS_DIR, SOCIAL_DIR]:
    dir_path.mkdir(parents=True, exist_ok=True)

# ── 系统参数 ──────────────────────────────────────────────────
LOG_LEVEL      = os.getenv("LOG_LEVEL", "INFO")
MAX_ITERATIONS = int(os.getenv("MAX_ITERATIONS", "10"))
AGENT_TIMEOUT  = int(os.getenv("AGENT_TIMEOUT", "300"))

SYSTEM_PROMPT_TEMPLATE = """你是一个专业的{role}。
你的职责是：{responsibility}
请基于以下上下文信息，完成用户的请求。

上下文信息：
{context}

用户需求：
{user_input}
"""
