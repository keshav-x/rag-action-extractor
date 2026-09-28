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


def get_priority_emoji(priority: Optional[str]) -> str:
    """
    Returns an appropriate emoji tag for a priority level.
    """
    if not priority:
        return "⚪ Medium"
    p = priority.strip().lower()
    if "high" in p or "urgent" in p or "critical" in p:
        return "🔴 High"
    elif "med" in p:
        return "🟡 Medium"
    elif "low" in p:
        return "🟢 Low"
    return f"⚪ {priority}"


def action_items_to_df(items: List[ActionItem], include_source: bool = False) -> pd.DataFrame:
    """
    Converts a list of ActionItem instances into a clean pandas DataFrame.
    By default, excludes ultra-long source context from compact table views to prevent horizontal clipping.
    """
    cols = ["Priority", "Task", "Owner", "Deadline"]
    if include_source:
        cols.append("Source Context")

    if not items:
        return pd.DataFrame(columns=cols)

    records = []
    for item in items:
        rec = {
            "Priority": get_priority_emoji(item.priority),
            "Task": item.task,
            "Owner": item.owner if item.owner else "Unassigned",
            "Deadline": item.deadline if item.deadline else "Not specified",
        }
        if include_source:
            rec["Source Context"] = item.source
        records.append(rec)
    return pd.DataFrame(records)


def export_to_csv(items: List[ActionItem]) -> bytes:
    """
    Exports a list of ActionItem objects to UTF-8 CSV bytes, including full source context.
    """
    df = action_items_to_df(items, include_source=True)
    return df.to_csv(index=False).encode("utf-8")


def export_to_json(items: List[ActionItem]) -> str:
    """
    Exports a list of ActionItem objects to formatted JSON string.
    """
    raw_data = [item.model_dump() for item in items]
    return json.dumps(raw_data, indent=2)
