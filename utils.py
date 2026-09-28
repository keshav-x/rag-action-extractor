import json
import re
from typing import List, Optional
import pandas as pd
from models import ActionItem


def clean_json_markdown(raw_text: str) -> str:
    """
    Cleans markdown formatting such as ```json ... ``` blocks from LLM responses
    to ensure valid JSON parsing.
    """
    text = raw_text.strip()
    if text.startswith("```"):
        text = re.sub(r"^```[a-zA-Z]*\n?", "", text)
        text = re.sub(r"\n?```$", "", text).strip()
    return text


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


# Backward compatibility alias
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
