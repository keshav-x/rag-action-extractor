import json
import re
from typing import List, Optional
import pandas as pd
from models import ActionItem, ActionItemList


def clean_json_markdown(raw_text: str) -> str:
    """
    Cleans markdown formatting such as ```json ... ``` blocks from LLM responses
    to ensure valid JSON parsing.
    """
    text = raw_text.strip()
    # Match markdown fence anywhere in the text
    fence_match = re.search(r"```(?:json)?\s*([\s\S]*?)\s*```", text, re.IGNORECASE)
    if fence_match:
        return fence_match.group(1).strip()
    if text.startswith("```"):
        text = re.sub(r"^```[a-zA-Z]*\n?", "", text)
        text = re.sub(r"\n?```$", "", text).strip()
    return text


def parse_action_items(raw_text: str) -> List[ActionItem]:
    """
    Resilient parser that extracts action items from various LLM response formats:
    - Standard ActionItemList JSON: {"action_items": [...]}
    - Direct JSON Array: [...]
    - Single JSON object: {"task": ...}
    - Markdown-fenced JSON blocks
    - Plain text task lists (fallback)
    Never crashes on empty strings or malformed syntax.
    """
    if not raw_text or not raw_text.strip():
        return []

    cleaned = clean_json_markdown(raw_text)

    # 1. Try candidates for JSON parsing
    candidates = []

    # Look for { ... }
    obj_match = re.search(r"\{[\s\S]*\}", cleaned)
    if obj_match:
        candidates.append(obj_match.group(0))

    # Look for [ ... ]
    arr_match = re.search(r"\[[\s\S]*\]", cleaned)
    if arr_match:
        candidates.append(arr_match.group(0))

    candidates.append(cleaned)

    for cand in candidates:
        if not cand.strip():
            continue
        try:
            data = json.loads(cand)
            if isinstance(data, dict):
                # Format: {"action_items": [...]}
                if "action_items" in data and isinstance(data["action_items"], list):
                    items = []
                    for it in data["action_items"]:
                        if isinstance(it, dict) and "task" in it and it["task"]:
                            items.append(ActionItem(
                                task=str(it.get("task", "")).strip(),
                                owner=str(it.get("owner", "")).strip() if it.get("owner") else None,
                                deadline=str(it.get("deadline", "")).strip() if it.get("deadline") else None,
                                priority=str(it.get("priority", "")).strip() if it.get("priority") else None,
                                source=str(it.get("source", "")).strip(),
                            ))
                    if items:
                        return items
                # Format: Single object {"task": ...}
                elif "task" in data and data["task"]:
                    return [ActionItem(
                        task=str(data.get("task", "")).strip(),
                        owner=str(data.get("owner", "")).strip() if data.get("owner") else None,
                        deadline=str(data.get("deadline", "")).strip() if data.get("deadline") else None,
                        priority=str(data.get("priority", "")).strip() if data.get("priority") else None,
                        source=str(data.get("source", "")).strip(),
                    )]
            # Format: Array [{"task": ...}]
            elif isinstance(data, list):
                items = []
                for it in data:
                    if isinstance(it, dict) and "task" in it and it["task"]:
                        items.append(ActionItem(
                            task=str(it.get("task", "")).strip(),
                            owner=str(it.get("owner", "")).strip() if it.get("owner") else None,
                            deadline=str(it.get("deadline", "")).strip() if it.get("deadline") else None,
                            priority=str(it.get("priority", "")).strip() if it.get("priority") else None,
                            source=str(it.get("source", "")).strip(),
                        ))
                if items:
                    return items
        except Exception:
            continue

    # 2. Fallback: Parse numbered or bulleted plain text lines if JSON parsing failed
    fallback_items = []
    for line in raw_text.splitlines():
        line_clean = line.strip()
        if re.match(r"^(\d+[\.\)]|\-|\*)\s+", line_clean):
            task_text = re.sub(r"^(\d+[\.\)]|\-|\*)\s+", "", line_clean).strip()
            if len(task_text) > 8:
                fallback_items.append(ActionItem(
                    task=task_text,
                    owner=None,
                    deadline=None,
                    priority="Medium",
                    source=task_text,
                ))

    return fallback_items


def get_priority_label(priority: Optional[str]) -> str:
    """
    Returns clean priority label without emojis.
    """
    if not priority:
        return "Medium"
    p = priority.strip().lower()
    if "high" in p or "urgent" in p or "critical" in p:
        return "High"
    elif "med" in p:
        return "Medium"
    elif "low" in p:
        return "Low"
    return priority.strip().capitalize()


def get_priority_emoji(priority: Optional[str]) -> str:
    return get_priority_label(priority)


def action_items_to_df(items: List[ActionItem], include_source: bool = True) -> pd.DataFrame:
    """
    Converts list of ActionItem instances into a clean pandas DataFrame.
    """
    cols = ["Priority", "Task", "Owner", "Deadline"]
    if include_source:
        cols.append("Source Quote")

    if not items:
        return pd.DataFrame(columns=cols)

    records = []
    for item in items:
        rec = {
            "Priority": get_priority_label(item.priority),
            "Task": item.task,
            "Owner": item.owner if item.owner else "Unassigned",
            "Deadline": item.deadline if item.deadline else "Not specified",
        }
        if include_source:
            rec["Source Quote"] = item.source
        records.append(rec)
    return pd.DataFrame(records)


def export_to_csv(items: List[ActionItem]) -> bytes:
    """
    Exports action items to UTF-8 CSV bytes.
    """
    df = action_items_to_df(items, include_source=True)
    return df.to_csv(index=False).encode("utf-8")


def export_to_json(items: List[ActionItem]) -> str:
    """
    Exports action items to formatted JSON string.
    """
    raw_data = [item.model_dump() for item in items]
    return json.dumps(raw_data, indent=2)


def export_to_markdown(items: List[ActionItem]) -> str:
    """
    Exports action items to a clean markdown checklist.
    """
    lines = ["# Action Items\n"]
    for i, item in enumerate(items, 1):
        p = get_priority_label(item.priority)
        owner = item.owner if item.owner else "Unassigned"
        deadline = item.deadline if item.deadline else "Not specified"
        lines.append(f"- [ ] **{item.task}**")
        lines.append(f"  - Priority: {p} | Owner: {owner} | Due: {deadline}")
        lines.append(f"  - Quote: \"{item.source}\"\n")
    return "\n".join(lines)
