"""
按用户持久化聊天记录 + 短期上下文。

存储路径：memory/data/chat_{user_id}.json
本地保留时长：默认 24 小时（超时消息自动清理；长期记忆/偏好不受影响）。
"""
from __future__ import annotations

import json
import logging
import re
from datetime import datetime, timedelta
from pathlib import Path
from typing import Any, Dict, List, Optional, Sequence, Tuple, Union

logger = logging.getLogger(__name__)

_DEFAULT_DIR = Path(__file__).parent / "data"
_SAFE_USER = re.compile(r"[^a-zA-Z0-9_\-\u4e00-\u9fff]+")

# 本地聊天保留时长
LOCAL_TTL_HOURS = 24

UiItem = Union[Tuple[str, str], List[str], Dict[str, Any]]


def normalize_user_id(user_id: str) -> str:
    """规范化用户 ID，避免非法文件名。"""
    raw = (user_id or "").strip() or "default"
    cleaned = _SAFE_USER.sub("_", raw).strip("._")
    return cleaned[:64] or "default"


def chat_path(user_id: str, data_dir: Optional[Path] = None) -> Path:
    base = Path(data_dir) if data_dir else _DEFAULT_DIR
    base.mkdir(parents=True, exist_ok=True)
    return base / f"chat_{normalize_user_id(user_id)}.json"


def list_users(data_dir: Optional[Path] = None) -> List[str]:
    """列出本地用户（聊天文件会先按 24h TTL 清理）。"""
    base = Path(data_dir) if data_dir else _DEFAULT_DIR
    if not base.exists():
        return []
    users: List[str] = []
    for p in sorted(base.glob("chat_*.json")):
        name = p.stem[len("chat_") :]
        if not name:
            continue
        load_chat(name, data_dir=base)  # 过期清理
        if chat_path(name, base).exists() and name not in users:
            users.append(name)

    for p in sorted(base.glob("memories_*.db")):
        name = p.stem[len("memories_") :]
        if name and name not in users:
            users.append(name)
    return users


def _now() -> datetime:
    return datetime.now()


def _parse_ts(value: Any) -> Optional[datetime]:
    if value is None:
        return None
    if isinstance(value, datetime):
        return value
    text = str(value).strip()
    if not text:
        return None
    try:
        return datetime.fromisoformat(text)
    except ValueError:
        return None


def _within_ttl(ts: Optional[datetime], now: Optional[datetime] = None) -> bool:
    if ts is None:
        return False
    now = now or _now()
    return ts >= now - timedelta(hours=LOCAL_TTL_HOURS)


def _empty_state(user_id: str) -> Dict[str, Any]:
    return {
        "user_id": normalize_user_id(user_id),
        "ui_history": [],
        "messages": [],
        "context": {"history": [], "summary": "", "compress_count": 0},
        "updated_at": None,
        "ttl_hours": LOCAL_TTL_HOURS,
    }


def _normalize_messages(
    raw_messages: Any,
    fallback_ui: Any = None,
    file_updated_at: Any = None,
) -> List[Dict[str, Any]]:
    """统一为 [{role, content, ts}, ...]。"""
    messages: List[Dict[str, Any]] = []
    fallback_ts = _parse_ts(file_updated_at) or _now()

    if isinstance(raw_messages, list) and raw_messages:
        for item in raw_messages:
            if isinstance(item, dict) and "role" in item and "content" in item:
                ts = _parse_ts(item.get("ts")) or fallback_ts
                messages.append(
                    {
                        "role": str(item["role"]),
                        "content": str(item["content"]),
                        "ts": ts.isoformat(timespec="seconds"),
                    }
                )
            elif isinstance(item, (list, tuple)) and len(item) >= 2:
                messages.append(
                    {
                        "role": str(item[0]),
                        "content": str(item[1]),
                        "ts": fallback_ts.isoformat(timespec="seconds"),
                    }
                )
        return messages

    # 兼容旧版 ui_history
    if isinstance(fallback_ui, list):
        for item in fallback_ui:
            if isinstance(item, dict) and "role" in item and "content" in item:
                ts = _parse_ts(item.get("ts")) or fallback_ts
                messages.append(
                    {
                        "role": str(item["role"]),
                        "content": str(item["content"]),
                        "ts": ts.isoformat(timespec="seconds"),
                    }
                )
            elif isinstance(item, (list, tuple)) and len(item) >= 2:
                messages.append(
                    {
                        "role": str(item[0]),
                        "content": str(item[1]),
                        "ts": fallback_ts.isoformat(timespec="seconds"),
                    }
                )
    return messages


def _prune_messages(
    messages: List[Dict[str, Any]],
    now: Optional[datetime] = None,
) -> List[Dict[str, Any]]:
    now = now or _now()
    kept: List[Dict[str, Any]] = []
    for msg in messages:
        ts = _parse_ts(msg.get("ts"))
        if ts is None:
            # 无时间戳：视为刚刚写入，保留并补戳
            msg = {
                "role": str(msg.get("role", "user")),
                "content": str(msg.get("content", "")),
                "ts": now.isoformat(timespec="seconds"),
            }
            kept.append(msg)
            continue
        if _within_ttl(ts, now):
            kept.append(
                {
                    "role": str(msg.get("role", "user")),
                    "content": str(msg.get("content", "")),
                    "ts": ts.isoformat(timespec="seconds"),
                }
            )
    return kept


def _messages_to_ui(messages: List[Dict[str, Any]]) -> List[Tuple[str, str]]:
    return [(m["role"], m["content"]) for m in messages]


def _context_from_messages(
    messages: List[Dict[str, Any]],
    previous_context: Optional[Dict[str, Any]] = None,
    pruned: bool = False,
) -> Dict[str, Any]:
    """用保留下来的消息重建短期上下文；若发生过期裁剪则丢弃旧摘要。"""
    history = [{"role": m["role"], "content": m["content"]} for m in messages]
    if pruned or not previous_context:
        return {"history": history, "summary": "", "compress_count": 0}
    return {
        "history": history or list(previous_context.get("history") or []),
        "summary": previous_context.get("summary", "") if history else "",
        "compress_count": int(previous_context.get("compress_count") or 0) if history else 0,
    }


def _align_timestamps(
    ui_history: Sequence[UiItem],
    previous_messages: List[Dict[str, Any]],
) -> List[Dict[str, Any]]:
    """把当前 UI 历史与旧消息对齐，尽量保留原时间戳。"""
    now = _now()
    result: List[Dict[str, Any]] = []
    for i, item in enumerate(ui_history):
        if isinstance(item, dict):
            role = str(item.get("role", "user"))
            content = str(item.get("content", ""))
            explicit_ts = _parse_ts(item.get("ts"))
        else:
            role = str(item[0])
            content = str(item[1])
            explicit_ts = None

        ts = explicit_ts
        if ts is None and i < len(previous_messages):
            prev = previous_messages[i]
            if prev.get("role") == role and prev.get("content") == content:
                ts = _parse_ts(prev.get("ts"))
        if ts is None:
            ts = now
        result.append(
            {
                "role": role,
                "content": content,
                "ts": ts.isoformat(timespec="seconds"),
            }
        )
    return result


def load_chat(user_id: str, data_dir: Optional[Path] = None) -> Dict[str, Any]:
    """加载用户聊天状态（自动丢弃超过 24h 的本地消息）。"""
    path = chat_path(user_id, data_dir)
    if not path.exists():
        return _empty_state(user_id)

    try:
        with open(path, "r", encoding="utf-8") as f:
            data = json.load(f)
    except Exception as e:
        logger.warning(f"[ChatStore] 加载失败 {path}: {e}")
        return _empty_state(user_id)

    now = _now()
    messages = _normalize_messages(
        data.get("messages"),
        fallback_ui=data.get("ui_history"),
        file_updated_at=data.get("updated_at"),
    )
    before = len(messages)
    messages = _prune_messages(messages, now=now)
    pruned = len(messages) != before

    # 整文件也过期且无有效消息 → 删除
    updated_at = _parse_ts(data.get("updated_at"))
    if not messages and updated_at is not None and not _within_ttl(updated_at, now):
        try:
            path.unlink(missing_ok=True)
            logger.info(f"[ChatStore] 已删除过期聊天文件: {path}")
        except Exception as e:
            logger.warning(f"[ChatStore] 删除过期文件失败 {path}: {e}")
        return _empty_state(user_id)

    context = _context_from_messages(
        messages,
        previous_context=data.get("context"),
        pruned=pruned,
    )
    state = {
        "user_id": data.get("user_id") or normalize_user_id(user_id),
        "ui_history": _messages_to_ui(messages),
        "messages": messages,
        "context": context,
        "updated_at": data.get("updated_at"),
        "ttl_hours": LOCAL_TTL_HOURS,
    }

    # 若发生了裁剪，回写精简后的文件
    if pruned:
        try:
            save_chat(
                user_id,
                state["ui_history"],
                context=context,
                data_dir=data_dir,
                messages=messages,
            )
        except Exception as e:
            logger.warning(f"[ChatStore] 回写裁剪结果失败: {e}")

    return state


def save_chat(
    user_id: str,
    ui_history: Sequence[UiItem],
    context: Optional[Dict[str, Any]] = None,
    data_dir: Optional[Path] = None,
    messages: Optional[List[Dict[str, Any]]] = None,
) -> Path:
    """保存用户聊天记录与短期上下文（写入前按 24h TTL 裁剪）。"""
    path = chat_path(user_id, data_dir)
    previous_messages: List[Dict[str, Any]] = []
    if path.exists():
        try:
            with open(path, "r", encoding="utf-8") as f:
                old = json.load(f)
            previous_messages = _normalize_messages(
                old.get("messages"),
                fallback_ui=old.get("ui_history"),
                file_updated_at=old.get("updated_at"),
            )
        except Exception:
            previous_messages = []

    if messages is None:
        messages = _align_timestamps(ui_history, previous_messages)
    messages = _prune_messages(messages)

    # 若调用方没给 context，或消息被裁剪，用消息重建
    if context is None:
        context = _context_from_messages(messages, pruned=True)
    else:
        # 保证 context.history 不长于保留消息
        context = {
            "history": context.get("history")
            or [{"role": m["role"], "content": m["content"]} for m in messages],
            "summary": context.get("summary", ""),
            "compress_count": int(context.get("compress_count") or 0),
        }
        if len(context["history"]) > len(messages):
            context["history"] = [
                {"role": m["role"], "content": m["content"]} for m in messages
            ]

    payload = {
        "user_id": normalize_user_id(user_id),
        "ui_history": [[m["role"], m["content"]] for m in messages],
        "messages": messages,
        "context": context,
        "updated_at": _now().isoformat(timespec="seconds"),
        "ttl_hours": LOCAL_TTL_HOURS,
    }
    tmp = path.with_suffix(".tmp")
    with open(tmp, "w", encoding="utf-8") as f:
        json.dump(payload, f, ensure_ascii=False, indent=2)
    tmp.replace(path)
    return path


def clear_chat(user_id: str, data_dir: Optional[Path] = None) -> None:
    """清空某用户聊天文件（长期记忆不动）。"""
    path = chat_path(user_id, data_dir)
    if path.exists():
        path.unlink()
        logger.info(f"[ChatStore] 已清空聊天: {path}")


def purge_expired(data_dir: Optional[Path] = None) -> int:
    """扫描并清理所有超过 24h 的本地聊天，返回删除文件数。"""
    base = Path(data_dir) if data_dir else _DEFAULT_DIR
    if not base.exists():
        return 0
    removed = 0
    for p in list(base.glob("chat_*.json")):
        name = p.stem[len("chat_") :]
        before_exists = p.exists()
        load_chat(name, data_dir=base)  # 内部会裁剪/删文件
        if before_exists and not p.exists():
            removed += 1
    return removed
