"""Persistent cross-session memory storage and retrieval for the API harness."""

from __future__ import annotations

import re
from pathlib import Path
from typing import Any

from shared.storage import load_memories, save_memories


class MemoryStore:
    """Stores and retrieves persistent scheduling rules and task preferences across sessions."""

    def __init__(self, data_dir: Path | str | None = None) -> None:
        self.data_dir = data_dir

    def load_all(self) -> list[dict[str, Any]]:
        """Load all persisted memory records from disk."""
        memories = load_memories(self.data_dir)
        print(f"[memory.py] Loaded {len(memories)} memory item(s) from disk")
        return memories

    def extract_and_store(self, user_message: str, session_id: str) -> list[dict[str, Any]]:
        """Detect persistent scheduling rules or preferences in user input and save them."""
        print("[memory.py] Inspecting user message for persistent scheduling rules/preferences")
        lower_msg = user_message.lower()
        existing = load_memories(self.data_dir)
        existing_rules = {m.get("rule", "").lower() for m in existing}
        added: list[dict[str, Any]] = []

        patterns = [
            (
                r"never\s+schedule\w*.*friday|no\s+tasks\s+on\s+friday",
                "No Friday tasks: strictly never schedule any tasks on Fridays.",
                ["friday", "fridays"],
            ),
            (
                r"do\s+not\s+schedule\s+work\s+tasks\s+on\s+weekend|no\s+work.*weekend|saturday\s+or\s+sunday",
                "No weekend work: strictly do not schedule work tasks on weekends (Saturday or Sunday).",
                ["saturday", "sunday", "weekend", "weekends"],
            ),
            (
                r"no\s+meetings\s+before\s+10",
                "Morning focus rule: no meetings scheduled before 10:00 AM.",
                ["morning", "before 10"],
            ),
        ]

        for regex, canonical_rule, forbidden in patterns:
            if re.search(regex, lower_msg) and canonical_rule.lower() not in existing_rules:
                entry = {
                    "session_id": session_id,
                    "category": "scheduling_restriction",
                    "rule": canonical_rule,
                    "forbidden_days": forbidden,
                    "keywords": ["schedule", "scheduling", "rule", "restriction", "work", "task"] + forbidden,
                }
                existing.append(entry)
                existing_rules.add(canonical_rule.lower())
                added.append(entry)

        if not added and ("remember" in lower_msg or "never schedule" in lower_msg):
            sentences = re.split(r"[.!\n]+", user_message)
            for sent in sentences:
                if "?" in sent:
                    continue
                s_lower = sent.lower()
                if any(k in s_lower for k in ("please remember", "remember that", "i never schedule", "i do not schedule")):
                    rule_text = sent.strip()
                    if rule_text and rule_text.lower() not in existing_rules:
                        entry = {
                            "session_id": session_id,
                            "category": "user_preference",
                            "rule": rule_text,
                            "forbidden_days": [],
                            "keywords": re.findall(r"[a-zA-Z]{3,}", s_lower),
                        }
                        existing.append(entry)
                        existing_rules.add(rule_text.lower())
                        added.append(entry)

        if added:
            save_memories(existing, self.data_dir)
            print(f"[memory.py] Persisted {len(added)} new memory item(s) to disk")
        else:
            print("[memory.py] No new persistent memories detected in this turn")
        return added

    def retrieve_relevant(self, query: str) -> list[dict[str, Any]]:
        """Retrieve only memory entries relevant to the current turn."""
        all_memories = load_memories(self.data_dir)
        if not all_memories:
            print("[memory.py] Memory store is empty (0 items retrieved)")
            return []

        q_lower = query.lower()
        scheduling_action = any(
            kw in q_lower
            for kw in (
                "add", "task", "tasks", "schedule", "due", "friday", "saturday",
                "sunday", "weekend", "work", "rule", "rules", "restriction",
                "remember", "holiday", "deadline", "meeting", "deployment",
            )
        )

        selected: list[dict[str, Any]] = []
        for item in all_memories:
            is_rule = item.get("category") == "scheduling_restriction"
            keywords = item.get("keywords", [])
            keyword_hit = any(k in q_lower for k in keywords)
            if keyword_hit or (is_rule and scheduling_action):
                selected.append(item)

        print(
            f"[memory.py] Retrieved {len(selected)}/{len(all_memories)} relevant memory item(s) for turn"
        )
        return selected
