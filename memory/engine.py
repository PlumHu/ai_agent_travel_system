"""
MemoryEngine —— 记忆治理层（source of truth）
=============================================
所有治理逻辑集中于此，依赖 MemoryStore 抽象做存取，与具体后端解耦：
  - 记忆抽取     : 正则 + 可选 LLM 辅助
  - 冲突检测     : 新旧画像矛盾时记录并提醒
  - 动态重要性   : 根据语气/否定/重复评分（1~5）
  - 记忆衰减     : importance * exp(-λ*days) + LRU + 容量上限
  - context 拼装 : 画像 + 历史行程 + 相关记忆 + 冲突提醒

换存储后端（SqliteStore / Mem0Store）时，本文件完全不动。
"""
import json
import logging
import math
import re
from datetime import datetime
from typing import Any, Dict, List, Optional

from memory.store.base import MemoryStore

logger = logging.getLogger(__name__)

# 衰减参数
_DECAY_LAMBDA = 0.05
_EFFECTIVE_IMPORTANCE_FLOOR = 0.5
_MAX_MEMORIES = 500


class MemoryEngine:
    """记忆治理引擎。治理逻辑的唯一归属地。"""

    def __init__(self, store: MemoryStore, user_id: str = "default",
                 llm=None, max_context_items: int = 5,
                 enforce_capacity: bool = True):
        """
        Args:
            store: 存取后端（SqliteStore / Mem0Store）
            user_id: 用户标识
            llm: 可选 LLM，用于辅助实体提取
            max_context_items: get_memory_context 语义检索返回上限
            enforce_capacity: 是否执行容量上限清理（Mem0 后端可关，避免双重治理）
        """
        self.store = store
        self.user_id = user_id
        self.llm = llm
        self.max_context_items = max_context_items
        self.enforce_capacity = enforce_capacity

    # ── 写入：抽取 + 治理 ─────────────────────────────────────
    def extract_and_save(self, user_message: str, assistant_message: str) -> Dict[str, Any]:
        """从一轮对话提取实体并保存（正则 + 可选 LLM，含冲突检测与动态重要性）。"""
        extracted = self._extract_entities(user_message, assistant_message)

        if self.llm is not None:
            try:
                llm_extracted = self._llm_extract_entities(user_message, assistant_message)
                extracted = self._merge_extractions(extracted, llm_extracted)
            except Exception as e:
                logger.warning(f"[MemoryEngine] LLM 提取失败，仅用正则: {e}")

        # 更新画像（含冲突检测）
        if extracted.get("destinations"):
            self.update_profile("recent_destinations",
                                json.dumps(extracted["destinations"], ensure_ascii=False))
        if extracted.get("budget"):
            self.update_profile("budget_range", extracted["budget"])
        if extracted.get("travel_style"):
            self.update_profile("travel_style",
                                json.dumps(extracted["travel_style"], ensure_ascii=False))
        if extracted.get("departure_city"):
            self.update_profile("departure_city", extracted["departure_city"])
        if extracted.get("companions"):
            self.update_profile("companions", extracted["companions"])

        # 保存偏好记忆（动态重要性评分）
        for dest in extracted.get("destinations", []):
            importance = self.score_importance("destination", dest, user_message)
            self.store.add_memory("preference", f"用户对目的地 {dest} 感兴趣",
                                  source=user_message[:100], importance=importance)

        for neg in extracted.get("negative_preferences", []):
            self.store.add_memory("preference", f"用户明确不喜欢：{neg}",
                                  source=user_message[:100], importance=4)

        # 向量存储
        self.store.add_vector(
            f"用户: {user_message}\n助手: {assistant_message}",
            metadata={"type": "dialogue",
                      "destinations": ",".join(extracted.get("destinations", [])),
                      "created_at": datetime.now().isoformat()},
        )
        return extracted

    def update_profile(self, key: str, value: str) -> None:
        """更新画像字段，更新前做冲突检测（治理逻辑，不在 Store）。"""
        old_value = self.store.get_profile_value(key)
        if old_value is not None and self._detect_conflict(key, old_value, value):
            self.store.supersede_conflicts(key)      # 同 key 旧未决先解决
            self.store.add_conflict(key, old_value, value)
            logger.info(f"[MemoryEngine] 检测到偏好冲突 key={key}: {old_value} → {value}")
        self.store.set_profile_value(key, value)

    def score_importance(self, entity_type: str, value: str, source_text: str) -> int:
        """动态重要性评分（1~5）。规则逐字保留原实现。"""
        score = 3
        negative_markers = ["不喜欢", "不要", "避免", "讨厌", "不想", "别"]
        if any(m in source_text for m in negative_markers):
            return 4
        emphasis_markers = ["一定要", "必须", "最重要", "特别", "务必", "重点"]
        if any(m in source_text for m in emphasis_markers):
            score += 2
        try:
            if self.store.memory_exists_like(value):
                score += 1
        except Exception:
            pass
        return max(1, min(5, score))

    # ── 读取：context 拼装 ────────────────────────────────────
    def get_memory_context(self, query: str = "") -> str:
        """拼装注入 Prompt 的记忆文本：画像 + 历史行程 + 相关记忆 + 冲突提醒。"""
        parts = []

        # 1. 用户画像
        profile = self.store.get_profile()
        if profile:
            label_map = {
                "departure_city": "常用出发城市", "budget_range": "预算偏好",
                "travel_style": "旅行风格", "recent_destinations": "近期感兴趣目的地",
                "companions": "同行人员",
            }
            lines = []
            for k, label in label_map.items():
                if k in profile:
                    val = profile[k]
                    try:
                        val = "、".join(json.loads(val))
                    except Exception:
                        pass
                    lines.append(f"  - {label}：{val}")
            if lines:
                parts.append("【用户偏好】\n" + "\n".join(lines))

        # 2. 历史行程（最近 3 条）
        trips = self.store.get_trips(limit=3)
        if trips:
            lines = []
            for t in trips:
                line = f"  - {t['destination']}"
                if t.get("days"):
                    line += f"（{t['days']}天）"
                if t.get("rating"):
                    line += f" 评分{t['rating']}/5"
                lines.append(line)
            parts.append("【历史行程】\n" + "\n".join(lines))

        # 3. 相关记忆（向量优先，否则关键词降级）
        if query and self.store.vector_available():
            related = self.store.search_vector(query, top_k=self.max_context_items)
            if related:
                parts.append("【相关历史对话】\n" + "\n".join(f"  - {r}" for r in related[:3]))
        elif query:
            related = self.store.search_memories_by_keyword(query.split()[:3])
            if related:
                parts.append("【相关记忆】\n" + "\n".join(f"  - {r['content']}" for r in related[:3]))

        # 4. 偏好变化提醒（冲突）
        conflicts = self.store.get_pending_conflicts()
        if conflicts:
            label_map = {
                "budget_range": "预算", "travel_style": "旅行风格",
                "companions": "同行人员", "departure_city": "出发城市",
                "recent_destinations": "目的地偏好",
            }
            lines = []
            for c in conflicts[:3]:
                label = label_map.get(c["key"], c["key"])
                lines.append(f"  - {label}：曾为「{c['old_value']}」，现在似乎变为「{c['new_value']}」，建议向用户确认")
            parts.append("【偏好变化提醒】（请主动与用户确认以下变化）\n" + "\n".join(lines))

        if not parts:
            return ""
        return "[长期记忆]\n" + "\n\n".join(parts)

    # ── 衰减 ─────────────────────────────────────────────────
    def decay_memories(self) -> Dict[str, int]:
        """时间衰减 + 容量上限清理。策略在 Engine，删除由 Store 执行。"""
        now = datetime.now()
        scored = []
        for m in self.store.all_memories():
            ref_time = m.get("last_accessed_at") or m.get("created_at")
            try:
                days = max(0.0, (now - datetime.fromisoformat(ref_time)).total_seconds() / 86400)
            except Exception:
                days = 0.0
            effective = (m.get("importance") or 3) * math.exp(-_DECAY_LAMBDA * days)
            scored.append((m["id"], effective))

        to_remove = [mid for mid, eff in scored if eff < _EFFECTIVE_IMPORTANCE_FLOOR]
        if to_remove:
            self.store.delete_memories(to_remove)

        survivors = [(mid, eff) for mid, eff in scored if eff >= _EFFECTIVE_IMPORTANCE_FLOOR]
        capacity_removed = 0
        if self.enforce_capacity and len(survivors) > _MAX_MEMORIES:
            survivors.sort(key=lambda x: x[1])
            overflow = survivors[: len(survivors) - _MAX_MEMORIES]
            self.store.delete_memories([mid for mid, _ in overflow])
            capacity_removed = len(overflow)

        result = {
            "decayed_removed": len(to_remove),
            "capacity_removed": capacity_removed,
            "remaining": self.store.count_memories(),
        }
        logger.info(f"[MemoryEngine] 记忆衰减完成: {result}")
        return result

    # ── 冲突检测（内部治理）───────────────────────────────────
    def _detect_conflict(self, key: str, old_value: str, new_value: str) -> bool:
        if old_value == new_value:
            return False
        if key == "budget_range":
            old_num, new_num = self._parse_number(old_value), self._parse_number(new_value)
            if old_num and new_num and old_num > 0:
                return abs(new_num - old_num) / old_num >= 0.3
            return False
        if key in ("travel_style", "recent_destinations"):
            old_set, new_set = self._parse_list_set(old_value), self._parse_list_set(new_value)
            if old_set and new_set:
                return len(old_set & new_set) == 0
            return False
        if key in ("companions", "departure_city"):
            return old_value != new_value
        return False

    @staticmethod
    def _parse_number(text: str) -> Optional[float]:
        m = re.search(r"([0-9]+(?:\.[0-9]+)?)", str(text))
        return float(m.group(1)) if m else None

    @staticmethod
    def _parse_list_set(text: str) -> set:
        try:
            parsed = json.loads(text)
            if isinstance(parsed, list):
                return set(parsed)
        except Exception:
            pass
        return {text}

    # ── 实体抽取 ─────────────────────────────────────────────
    def _extract_entities(self, user_msg: str, assistant_msg: str) -> Dict[str, Any]:
        text = user_msg + " " + assistant_msg
        result: Dict[str, Any] = {}
        dests = re.findall(r"(?:去|到|前往|游览|目的地[是为]?)\s*([^\s，。,\.！？]{2,4})", text)
        _stop = {"旅游", "旅行", "出发", "一下", "一趟", "哪里", "什么", "地方"}
        dests = [d for d in dests if d not in _stop]
        if dests:
            result["destinations"] = list(dict.fromkeys(dests))
        budget_match = re.search(r"预算[约大概是为]?\s*([0-9]+)\s*[元万]?", text)
        if budget_match:
            result["budget"] = budget_match.group(1) + "元"
        style_keywords = ["自然", "文化", "美食", "购物", "历史", "海滩", "徒步",
                          "摄影", "亲子", "蜜月", "背包", "奢华", "民宿", "露营"]
        styles = [k for k in style_keywords if k in text]
        if styles:
            result["travel_style"] = styles
        companion_map = {"一个人": "独行", "朋友": "朋友", "家人": "家庭",
                         "孩子": "亲子", "老人": "家庭", "情侣": "情侣", "蜜月": "情侣"}
        for kw, label in companion_map.items():
            if kw in text:
                result["companions"] = label
                break
        depart_match = re.search(r"从\s*([^\s，。]{2,4})\s*(?:出发|飞|坐)", text)
        if depart_match:
            result["departure_city"] = depart_match.group(1)
        return result

    def _llm_extract_entities(self, user_msg: str, assistant_msg: str) -> Dict[str, Any]:
        from langchain_core.messages import HumanMessage, SystemMessage
        prompt = f"""从以下对话中提取用户的旅行偏好实体，包括隐含偏好和明确的否定偏好。

用户: {user_msg}
助手: {assistant_msg}

请以 JSON 格式输出（无法确定的字段省略）：
```json
{{
  "destinations": ["明确提到想去的地方"],
  "budget": "预算数字+元，如 5000元",
  "travel_style": ["风格标签，含隐含偏好，如 人少、小众、轻松、深度游"],
  "companions": "独行/朋友/家庭/亲子/情侣 之一",
  "departure_city": "出发城市",
  "negative_preferences": ["明确不喜欢/想避免的，如 人多、爬山、坐大巴"]
}}
```
只输出 JSON，不要解释。"""
        response = self.llm.invoke([
            SystemMessage(content="你是旅行偏好分析助手，擅长从对话中提取显性和隐性偏好。"),
            HumanMessage(content=prompt),
        ])
        text = response.content
        m = re.search(r"```(?:json)?\s*(\{.*?\})\s*```", text, re.DOTALL)
        parsed = json.loads(m.group(1) if m else text.strip())
        for lf in ("destinations", "travel_style", "negative_preferences"):
            v = parsed.get(lf)
            if v and not isinstance(v, list):
                parsed[lf] = [v]
        return parsed

    @staticmethod
    def _merge_extractions(base: Dict[str, Any], extra: Dict[str, Any]) -> Dict[str, Any]:
        merged = dict(base)
        for f in ("destinations", "travel_style", "negative_preferences"):
            combined = list(base.get(f, []) or []) + list(extra.get(f, []) or [])
            if combined:
                merged[f] = list(dict.fromkeys(combined))
        for f in ("budget", "companions", "departure_city"):
            if not merged.get(f) and extra.get(f):
                merged[f] = extra[f]
        return merged
