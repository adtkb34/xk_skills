#!/usr/bin/env python3
"""Build a readable HTML dashboard from priority-intake-backlog (md + items csv)."""

from __future__ import annotations

import argparse
import csv
import html
import json
import re
import sys
from datetime import date, timedelta
from datetime import datetime, timezone
from pathlib import Path


DECISION_HEADER = re.compile(r"^\|\s*#\s*\|", re.I)
PARENT_LINK = re.compile(r"^(RICE-[A-Z]+-\d+)(?::(\d+)%)?$")
DATE_ISO = re.compile(r"^\d{4}-\d{2}-\d{2}$")
TEMPLATE_PATH = Path(__file__).with_name("backlog-dashboard.template.html")

BACKLOG_STEM = "priority-intake-backlog"
ITEMS_CSV_SUFFIX = ".items.csv"
EXECUTIONS_CSV_SUFFIX = ".executions.csv"
SCHEDULE_ANCHOR = re.compile(
    r"^(\d{4}-\d{2}-\d{2})(?:[T ](\d{2}:\d{2})(?::\d{2})?)?$"
)
TIME_ONLY = re.compile(r"^\d{2}:\d{2}(?::\d{2})?$")

DAYS_PER_WEEK = 7
DAYS_PER_MONTH = 30

ITEMS_CSV_COLUMNS = [
    "id", "title", "level", "status", "reach", "impact", "confidence", "effort",
    "impact_slice", "parent_links", "blocks", "blocked_by", "ledger_ref", "notes",
]

EXECUTIONS_CSV_COLUMNS = [
    "id", "task_id", "start_date", "end_date", "start_time", "end_time", "status", "notes",
]

EXECUTION_STATUSES = frozenset({"pending", "running", "success", "failed", "cancelled"})

# CSV header (lowercase) → internal field key used by compute pipeline
CSV_FIELD_MAP = {
    "level": "Level",
    "status": "Status",
    "reach": "Reach",
    "impact": "Impact",
    "confidence": "Confidence",
    "effort": "Effort",
    "impact_slice": "impact_slice",
    "parent_links": "Parent_links",
    "blocks": "Blocks",
    "blocked_by": "Blocked_by",
    "ledger_ref": "Ledger_ref",
    "notes": "Notes",
}


def backlog_md_in_dir(backlog_dir: Path) -> Path:
    """Resolve priority-intake-backlog.md inside a backlog directory."""
    return backlog_dir / f"{BACKLOG_STEM}.md"


def items_csv_path(md_path: Path) -> Path:
    return md_path.with_name(f"{md_path.stem}{ITEMS_CSV_SUFFIX}")


def executions_csv_path(md_path: Path) -> Path:
    return md_path.with_name(f"{md_path.stem}{EXECUTIONS_CSV_SUFFIX}")


def normalize_cell(val: str | None) -> str:
    if val is None:
        return ""
    v = val.strip()
    if v in ("—", "-", "–"):
        return ""
    return v


def row_to_fields(row: dict[str, str]) -> dict[str, str]:
    fields: dict[str, str] = {}
    for csv_key, field_key in CSV_FIELD_MAP.items():
        val = normalize_cell(row.get(csv_key, ""))
        if val:
            fields[field_key] = val
    return fields


def read_items_rows(csv_path: Path) -> list[dict[str, str]]:
    if not csv_path.is_file():
        return []
    text = csv_path.read_text(encoding="utf-8-sig")
    reader = csv.DictReader(text.splitlines())
    if not reader.fieldnames:
        raise ValueError(f"CSV has no header row: {csv_path}")
    rows: list[dict[str, str]] = []
    for row in reader:
        item_id = normalize_cell(row.get("id", ""))
        if not item_id:
            continue
        rows.append({col: normalize_cell(row.get(col, "")) for col in ITEMS_CSV_COLUMNS})
    return rows


def write_items_rows(csv_path: Path, rows: list[dict[str, str]]) -> None:
    csv_path.parent.mkdir(parents=True, exist_ok=True)
    with csv_path.open("w", encoding="utf-8-sig", newline="") as fh:
        writer = csv.DictWriter(fh, fieldnames=ITEMS_CSV_COLUMNS, extrasaction="ignore")
        writer.writeheader()
        writer.writerows(rows)


def next_item_id(level: str, existing_ids: set[str]) -> str:
    level_key = level.strip().upper() or "TASK"
    prefix = f"RICE-{level_key}-"
    nums = []
    for item_id in existing_ids:
        if item_id.startswith(prefix):
            match = re.search(r"-(\d+)$", item_id)
            if match:
                nums.append(int(match.group(1)))
    return f"{prefix}{(max(nums, default=0) + 1):03d}"


def item_body_to_row(body: dict, existing_ids: set[str], *, item_id: str | None = None) -> dict[str, str]:
    title = normalize_cell(body.get("title", ""))
    if not title:
        raise ValueError("title is required")
    level = normalize_cell(body.get("level", "")) or "Task"
    if level not in {"Epic", "Feature", "Story", "Task"}:
        raise ValueError("level must be Epic, Feature, Story, or Task")

    resolved_id = normalize_cell(item_id or body.get("id", ""))
    if not resolved_id:
        resolved_id = next_item_id(level, existing_ids)
    if resolved_id in existing_ids:
        raise ValueError(f"duplicate id: {resolved_id}")

    parent_links = normalize_cell(body.get("parent_links", ""))
    row = {col: "" for col in ITEMS_CSV_COLUMNS}
    row["id"] = resolved_id
    row["title"] = title
    row["level"] = level
    row["status"] = normalize_cell(body.get("status", "")) or "intake"
    row["confidence"] = normalize_cell(body.get("confidence", ""))
    row["effort"] = normalize_effort_storage(body, level)
    row["impact_slice"] = normalize_cell(body.get("impact_slice", ""))
    row["parent_links"] = parent_links
    row["blocks"] = normalize_cell(body.get("blocks", ""))
    row["blocked_by"] = normalize_cell(body.get("blocked_by", ""))
    row["ledger_ref"] = normalize_cell(body.get("ledger_ref", ""))
    row["notes"] = normalize_cell(body.get("notes", ""))
    if parent_links:
        row["reach"] = ""
        row["impact"] = ""
    else:
        row["reach"] = normalize_cell(body.get("reach", ""))
        row["impact"] = normalize_cell(body.get("impact", ""))
    return row


def read_executions_rows(csv_path: Path) -> list[dict[str, str]]:
    if not csv_path.is_file():
        return []
    text = csv_path.read_text(encoding="utf-8-sig")
    reader = csv.DictReader(text.splitlines())
    if not reader.fieldnames:
        raise ValueError(f"CSV has no header row: {csv_path}")
    rows: list[dict[str, str]] = []
    for row in reader:
        ex_id = normalize_cell(row.get("id", ""))
        if not ex_id:
            continue
        rows.append({col: normalize_cell(row.get(col, "")) for col in EXECUTIONS_CSV_COLUMNS})
    return rows


def write_executions_rows(csv_path: Path, rows: list[dict[str, str]]) -> None:
    csv_path.parent.mkdir(parents=True, exist_ok=True)
    with csv_path.open("w", encoding="utf-8-sig", newline="") as fh:
        writer = csv.DictWriter(fh, fieldnames=EXECUTIONS_CSV_COLUMNS, extrasaction="ignore")
        writer.writeheader()
        writer.writerows(rows)


def next_execution_id(existing_ids: set[str]) -> str:
    nums = []
    for ex_id in existing_ids:
        if ex_id.startswith("EXEC-"):
            match = re.search(r"-(\d+)$", ex_id)
            if match:
                nums.append(int(match.group(1)))
    return f"EXEC-{(max(nums, default=0) + 1):03d}"


def execution_body_to_row(
    body: dict,
    existing_ids: set[str],
    valid_task_ids: set[str],
    *,
    execution_id: str | None = None,
) -> dict[str, str]:
    task_id = normalize_cell(body.get("task_id", ""))
    if not task_id:
        raise ValueError("task_id is required")
    if task_id not in valid_task_ids:
        raise ValueError(f"unknown task_id: {task_id}")

    start_date = normalize_cell(body.get("start_date", ""))
    end_date = normalize_cell(body.get("end_date", ""))
    if start_date and end_date:
        raise ValueError("set start_date or end_date, not both")

    start_time = normalize_cell(body.get("start_time", ""))
    end_time = normalize_cell(body.get("end_time", ""))
    if start_date:
        date_part, embedded_time = parse_schedule_anchor(start_date)
        if not date_part:
            raise ValueError("invalid start_date (use YYYY-MM-DD or YYYY-MM-DDTHH:MM)")
        start_date = start_date if "T" in start_date or " " in start_date else date_part
        if embedded_time and not start_time:
            start_time = embedded_time
    if end_date:
        date_part, embedded_time = parse_schedule_anchor(end_date)
        if not date_part:
            raise ValueError("invalid end_date (use YYYY-MM-DD or YYYY-MM-DDTHH:MM)")
        end_date = end_date if "T" in end_date or " " in end_date else date_part
        if embedded_time and not end_time:
            end_time = embedded_time

    if start_time and not TIME_ONLY.match(start_time):
        raise ValueError("invalid start_time (use HH:MM)")
    if end_time and not TIME_ONLY.match(end_time):
        raise ValueError("invalid end_time (use HH:MM)")

    status = normalize_cell(body.get("status", "")) or "pending"
    if status not in EXECUTION_STATUSES:
        raise ValueError(f"status must be one of: {', '.join(sorted(EXECUTION_STATUSES))}")

    resolved_id = normalize_cell(execution_id or body.get("id", ""))
    if not resolved_id:
        resolved_id = next_execution_id(existing_ids)
    if resolved_id in existing_ids:
        raise ValueError(f"duplicate id: {resolved_id}")

    row = {col: "" for col in EXECUTIONS_CSV_COLUMNS}
    row["id"] = resolved_id
    row["task_id"] = task_id
    row["start_date"] = start_date
    row["end_date"] = end_date
    row["start_time"] = start_time
    row["end_time"] = end_time
    row["status"] = status
    row["notes"] = normalize_cell(body.get("notes", ""))
    return row


def api_payload(data: dict) -> dict:
    return {
        "items": data["items"],
        "summary": data["summary"],
        "decisions": data.get("decisions", []),
        "implementationOrder": data.get("implementationOrder", ""),
    }


def parse_items_csv(csv_path: Path) -> list[dict]:
    text = csv_path.read_text(encoding="utf-8-sig")
    reader = csv.DictReader(text.splitlines())
    if not reader.fieldnames:
        raise ValueError(f"CSV has no header row: {csv_path}")

    items: list[dict] = []
    for row in reader:
        item_id = normalize_cell(row.get("id", ""))
        title = normalize_cell(row.get("title", ""))
        if not item_id:
            continue
        items.append({
            "id": item_id,
            "title": title,
            "fields": row_to_fields(row),
        })
    return items


def parse_executions_csv(csv_path: Path) -> list[dict]:
    text = csv_path.read_text(encoding="utf-8-sig")
    reader = csv.DictReader(text.splitlines())
    if not reader.fieldnames:
        raise ValueError(f"CSV has no header row: {csv_path}")

    executions: list[dict] = []
    for row in reader:
        ex_id = normalize_cell(row.get("id", ""))
        task_id = normalize_cell(row.get("task_id", ""))
        if not ex_id or not task_id:
            continue
        executions.append({
            "id": ex_id,
            "task_id": task_id,
            "start_date": normalize_cell(row.get("start_date", "")),
            "end_date": normalize_cell(row.get("end_date", "")),
            "start_time": normalize_cell(row.get("start_time", "")),
            "end_time": normalize_cell(row.get("end_time", "")),
            "status": normalize_cell(row.get("status", "")) or "pending",
            "notes": normalize_cell(row.get("notes", "")),
        })
    return executions


def build_calendar_slots(item: dict) -> list[dict]:
    slots: list[dict] = []
    for ex in item.get("executions", []):
        ex_sch = ex.get("schedule")
        if ex_sch and ex_sch.get("mode") not in (None, "none"):
            slots.append({
                "slot_id": ex["id"],
                "label": ex["id"].split("-")[-1],
                "schedule": ex_sch,
                "start_time": ex_sch.get("start_time"),
            })
    return slots


def attach_executions(items: list[dict], executions: list[dict]) -> None:
    by_id = {item["id"]: item for item in items}
    for item in items:
        item["executions"] = []

    for ex in executions:
        task = by_id.get(ex["task_id"])
        if not task:
            continue
        effort = task["fields"].get("Effort", "")
        ex["schedule"] = resolve_schedule({
            "start_date": ex.get("start_date", ""),
            "end_date": ex.get("end_date", ""),
            "start_time": ex.get("start_time", ""),
            "end_time": ex.get("end_time", ""),
            "Effort": effort,
        })
        task["executions"].append(ex)

    for item in items:
        item["calendar_slots"] = build_calendar_slots(item)


def parse_float(val: str) -> float:
    try:
        return float(re.sub(r"[^\d.]", "", val) or "0")
    except ValueError:
        return 0.0


def parse_confidence(val: str) -> float:
    n = parse_float(val)
    return n if n > 0 else 80.0


def parse_effort_days(effort_str: str) -> float:
    """Parse effort from CSV — numeric days only (no unit suffix)."""
    if not effort_str or effort_str.strip() in ("—", "-", ""):
        return 0.0
    s = effort_str.strip()
    if not re.match(r"^\d+(\.\d+)?$", s):
        return 0.0
    num = float(s)
    return num if num > 0 else 0.0


def default_effort_unit(level: str) -> str:
    return {
        "Epic": "months",
        "Feature": "weeks",
        "Story": "days",
        "Task": "days",
    }.get(level, "days")


def effort_amount_to_days(amount: float, unit: str) -> float:
    unit_key = unit.strip().lower()
    if unit_key == "months":
        return amount * float(DAYS_PER_MONTH)
    if unit_key == "weeks":
        return amount * float(DAYS_PER_WEEK)
    return amount


def format_effort_storage(days: float) -> str:
    if days <= 0:
        return ""
    if abs(days - round(days)) < 1e-9:
        return str(int(round(days)))
    return f"{days:.2f}".rstrip("0").rstrip(".")


def normalize_effort_storage(body: dict, level: str) -> str:
    amount_raw = normalize_cell(body.get("effort_amount", ""))
    if not amount_raw:
        return ""
    unit = normalize_cell(body.get("effort_unit", "")) or default_effort_unit(level)
    amount = parse_float(amount_raw)
    if amount <= 0:
        return ""
    return format_effort_storage(effort_amount_to_days(amount, unit))


def effort_for_rice(level: str, effort_days: float) -> float:
    minimum = 0.5 if level == "Task" else DAYS_PER_WEEK / 2.0
    return max(effort_days, minimum)


def parse_parent_links(raw: str) -> list[dict]:
    if not raw or raw.strip() in ("—", "-", ""):
        return []
    links = []
    for part in raw.split(","):
        part = part.strip()
        m = PARENT_LINK.match(part)
        if m:
            links.append({"id": m.group(1), "pct": float(m.group(2)) if m.group(2) else 100.0})
    return links


def parse_impact_slice(fields: dict) -> float:
    if "impact_slice" in fields:
        return parse_float(fields["impact_slice"])
    return 1.0


def is_root_item(parents: str) -> bool:
    return not parents or parents.strip() in ("—", "-", "")


def normalize_time(val: str) -> str | None:
    if not val or val.strip() in ("—", "-", ""):
        return None
    v = val.strip()
    if not TIME_ONLY.match(v):
        return None
    return v[:5]


def parse_schedule_anchor(val: str) -> tuple[str | None, str | None]:
    if not val or val.strip() in ("—", "-", ""):
        return None, None
    v = val.strip()
    if DATE_ISO.match(v):
        return v, None
    m = SCHEDULE_ANCHOR.match(v)
    if m:
        return m.group(1), normalize_time(m.group(2) or "")
    return None, None


def parse_date_field(val: str) -> str | None:
    date_part, _ = parse_schedule_anchor(val)
    return date_part


def add_calendar_days(iso: str, offset: int) -> str:
    d = date.fromisoformat(iso)
    return (d + timedelta(days=offset)).isoformat()


def calendar_span_days(effort_days: float) -> int:
    if effort_days < 0.5:
        return 0
    return max(1, int(round(effort_days)))


def resolve_schedule(fields: dict) -> dict:
    start, start_time = parse_schedule_anchor(fields.get("start_date", ""))
    end, end_time = parse_schedule_anchor(fields.get("end_date", ""))
    if not start_time:
        start_time = normalize_time(fields.get("start_time", ""))
    if not end_time:
        end_time = normalize_time(fields.get("end_time", ""))
    effort_days = parse_effort_days(fields.get("Effort", ""))
    span = calendar_span_days(effort_days)

    if start and end:
        return {
            "mode": "invalid",
            "start": None,
            "end": None,
            "start_time": start_time,
            "end_time": end_time,
            "effort_days": effort_days or None,
            "schedule_error": "Cannot set both start_date and end_date",
        }
    if start:
        if span == 0:
            return {
                "mode": "invalid",
                "start": start,
                "end": None,
                "start_time": start_time,
                "end_time": end_time,
                "effort_days": None,
                "schedule_error": "start_date requires Effort ≥ 0.5 (days)",
            }
        cal_end = add_calendar_days(start, span - 1)
        return {
            "mode": "range",
            "start": start,
            "end": cal_end,
            "start_time": start_time,
            "end_time": end_time,
            "effort_days": effort_days,
            "schedule_error": None,
        }
    if end:
        if span > 0:
            cal_start = add_calendar_days(end, -(span - 1))
            return {
                "mode": "range",
                "start": cal_start,
                "end": end,
                "start_time": start_time,
                "end_time": end_time,
                "effort_days": effort_days,
                "schedule_error": None,
            }
        return {
            "mode": "milestone",
            "start": end,
            "end": end,
            "start_time": end_time or start_time,
            "end_time": end_time,
            "effort_days": None,
            "schedule_error": None,
        }
    return {
        "mode": "none",
        "start": None,
        "end": None,
        "start_time": start_time,
        "end_time": end_time,
        "effort_days": effort_days or None,
        "schedule_error": None,
    }


def ensure_inherited_metrics(item_id: str, by_id: dict, cache: dict, visiting: set[str]) -> dict:
    if item_id in cache:
        return cache[item_id]
    if item_id in visiting:
        return {"reach": 0.0, "impact": 0.0, "impact_slice": 1.0}
    visiting.add(item_id)

    item = by_id.get(item_id)
    if not item:
        return {"reach": 0.0, "impact": 0.0, "impact_slice": 1.0}

    fields = item["fields"]
    parents_raw = fields.get("Parent_links", "—")

    if is_root_item(parents_raw):
        metrics = {
            "reach": parse_float(fields.get("Reach", "0")),
            "impact": parse_float(fields.get("Impact", "0")),
            "impact_slice": 1.0,
        }
    else:
        slice_val = parse_impact_slice(fields)
        reach = 0.0
        impact = 0.0
        for link in parse_parent_links(parents_raw):
            parent_m = ensure_inherited_metrics(link["id"], by_id, cache, visiting)
            pct = link["pct"] / 100.0
            reach += parent_m["reach"] * pct
            impact += parent_m["impact"] * pct * slice_val
        metrics = {"reach": reach, "impact": impact, "impact_slice": slice_val}

    cache[item_id] = metrics
    item["computed"] = metrics
    return metrics


def inherit_reach_impact(items: list[dict]) -> None:
    by_id = {item["id"]: item for item in items}
    cache: dict[str, dict] = {}
    for item in items:
        ensure_inherited_metrics(item["id"], by_id, cache, set())


def compute_rice(items: list[dict]) -> None:
    for item in items:
        m = item.get("computed", {})
        conf = parse_confidence(item["fields"].get("Confidence", "80%"))
        effort_days = parse_effort_days(item["fields"].get("Effort", ""))
        effort = effort_for_rice(item.get("level", ""), effort_days)
        reach = m.get("reach", 0.0)
        impact = m.get("impact", 0.0)
        rice = (reach * impact * (conf / 100.0)) / effort if effort > 0 else 0.0
        item["rice_raw"] = round(rice, 2)


def compute_norm_score(items: list[dict]) -> None:
    by_id = {item["id"]: item for item in items}
    roots = [i for i in items if is_root_item(i["parents"])]
    max_raw = max((i["rice_raw"] for i in roots), default=0.0) or 1.0
    cache: dict[str, float] = {}

    def norm_for(item_id: str, visiting: set[str] | None = None) -> float:
        if item_id in cache:
            return cache[item_id]
        if visiting is None:
            visiting = set()
        if item_id in visiting:
            return 0.0
        visiting.add(item_id)

        item = by_id.get(item_id)
        if not item:
            return 0.0

        if is_root_item(item["parents"]):
            n = item["rice_raw"] / max_raw
        else:
            slice_val = parse_impact_slice(item["fields"])
            n = 0.0
            for link in parse_parent_links(item["parents"]):
                n += norm_for(link["id"], visiting) * (link["pct"] / 100.0) * slice_val

        cache[item_id] = n
        item["rice_norm"] = round(n, 4)
        item["score"] = round(n * 100, 1)
        item["rice"] = item["score"]
        return n

    for item in items:
        norm_for(item["id"])


def compute_rollup(items: list[dict]) -> None:
    by_id = {item["id"]: item for item in items}

    for item in items:
        item["contributions"] = []
        for link in parse_parent_links(item["parents"]):
            contrib = round(item["rice_raw"] * (link["pct"] / 100.0), 2)
            item["contributions"].append({"parent_id": link["id"], "pct": link["pct"], "rice": contrib})

    for item in items:
        child_sum = sum(
            c["rice"]
            for child in items
            for c in child.get("contributions", [])
            if c["parent_id"] == item["id"]
        )
        item["effective_rice"] = round(max(item["rice_raw"], child_sum), 2)


def build_summary(items: list[dict]) -> list[dict]:
    ranked = sorted(items, key=lambda x: x["score"], reverse=True)
    rows = []
    for i, item in enumerate(ranked, 1):
        rows.append({
            "Rank": str(i),
            "ID": item["id"],
            "Title": item["title"],
            "Level": item["level"],
            "Score": str(item["score"]),
            "Status": item["status"],
            "Parents": item["parents"],
        })
    return rows


def run_compute_pipeline(items: list[dict]) -> None:
    for item in items:
        fields = item["fields"]
        item["level"] = fields.get("Level", "")
        item["status"] = fields.get("Status", "intake")
        item["parents"] = fields.get("Parent_links", "—")
        item["ledger_ref"] = fields.get("Ledger_ref", "—")
        item["notes"] = fields.get("Notes", "")
        item["blocked_by"] = fields.get("Blocked_by", "—")
        item["blocks"] = fields.get("Blocks", "—")

    inherit_reach_impact(items)
    compute_rice(items)
    compute_norm_score(items)
    compute_rollup(items)


DECISION_SECTION_HEADER = "## Confirmed decisions"
IMPLEMENTATION_ORDER_PREFIX = "**Implementation order**:"


def parse_decisions_md(text: str) -> tuple[list[str], str]:
    lines = text.splitlines()
    decisions: list[str] = []
    implementation_order = ""
    in_decisions = False
    decision_cols: list[str] = []

    for line in lines:
        stripped = line.strip()

        if stripped == DECISION_SECTION_HEADER:
            in_decisions = True
            decision_cols = []
            continue

        if stripped.startswith("## ") and stripped != DECISION_SECTION_HEADER:
            in_decisions = False

        if in_decisions and stripped.startswith(IMPLEMENTATION_ORDER_PREFIX):
            implementation_order = stripped[len(IMPLEMENTATION_ORDER_PREFIX):].strip()
            continue

        if in_decisions and DECISION_HEADER.match(stripped):
            decision_cols = [c.strip() for c in stripped.strip("|").split("|")]
            continue

        if in_decisions and decision_cols and stripped.startswith("|"):
            cells = [c.strip() for c in stripped.strip("|").split("|")]
            if len(cells) >= 2 and not all(set(c) <= {"-"} for c in cells):
                decision_text = cells[1] if len(cells) > 1 else cells[0]
                if len(cells) > 2 and cells[2]:
                    decision_text = f"{decision_text} — {cells[2]}"
                decisions.append(decision_text)

    return decisions, implementation_order


def parse_backlog(md_path: Path) -> dict:
    text = md_path.read_text(encoding="utf-8")
    decisions, implementation_order = parse_decisions_md(text)

    csv_path = items_csv_path(md_path)
    if not csv_path.is_file():
        raise FileNotFoundError(
            f"items CSV not found: {csv_path}\n"
            f"Items must live in {csv_path.name}; md holds decisions only."
        )
    items = parse_items_csv(csv_path)

    run_compute_pipeline(items)

    exec_path = executions_csv_path(md_path)
    executions = parse_executions_csv(exec_path) if exec_path.is_file() else []
    attach_executions(items, executions)

    summary_rows = build_summary(items)

    return {
        "items": items,
        "summary": summary_rows,
        "decisions": decisions,
        "implementationOrder": implementation_order,
    }


def render_html(
    data: dict,
    source: Path,
    generated_at: str,
    *,
    editor_enabled: bool = False,
) -> str:
    if not TEMPLATE_PATH.is_file():
        raise FileNotFoundError(f"Template not found: {TEMPLATE_PATH}")

    template = TEMPLATE_PATH.read_text(encoding="utf-8")
    payload = api_payload(data)
    return (
        template.replace("__DATA_JSON__", json.dumps(payload, ensure_ascii=False))
        .replace("__SOURCE__", html.escape(source.name))
        .replace("__GENERATED_AT__", html.escape(generated_at))
        .replace("__EDITOR_ENABLED__", "true" if editor_enabled else "false")
    )


def resolve_backlog_dir(backlog_dir: Path) -> Path:
    if not backlog_dir.exists():
        raise FileNotFoundError(f"path not found: {backlog_dir}")
    if not backlog_dir.is_dir():
        raise ValueError(
            f"expected a directory, not a file: {backlog_dir}\n"
            f"Pass the backlog folder (e.g. docs/backlog), not {BACKLOG_STEM}.md."
        )
    md_path = backlog_md_in_dir(backlog_dir)
    if not md_path.is_file():
        raise FileNotFoundError(
            f"backlog file not found: {md_path}\n"
            f"Expected {BACKLOG_STEM}.md inside {backlog_dir}."
        )
    return md_path


def build_backlog_html(
    backlog_dir: Path,
    output: Path | None = None,
    *,
    editor_enabled: bool = False,
) -> tuple[Path, dict]:
    md_path = resolve_backlog_dir(backlog_dir)
    data = parse_backlog(md_path)
    out = output or md_path.with_suffix(".html")
    generated_at = datetime.now(timezone.utc).strftime("%Y-%m-%d %H:%M UTC")
    csv_path = items_csv_path(md_path)
    exec_path = executions_csv_path(md_path)
    source_parts = [md_path.name]
    if csv_path.is_file():
        source_parts.append(csv_path.name)
    if exec_path.is_file():
        source_parts.append(exec_path.name)
    source_label = " + ".join(source_parts)
    out.write_text(
        render_html(data, Path(source_label), generated_at, editor_enabled=editor_enabled),
        encoding="utf-8",
    )
    return out, data


def append_item_row(backlog_dir: Path, body: dict) -> dict:
    md_path = resolve_backlog_dir(backlog_dir)
    csv_path = items_csv_path(md_path)
    rows = read_items_rows(csv_path)
    existing_ids = {row["id"] for row in rows}
    row = item_body_to_row(body, existing_ids)
    rows.append(row)
    write_items_rows(csv_path, rows)
    _, data = build_backlog_html(backlog_dir, editor_enabled=True)
    return api_payload(data)


def append_execution_row(backlog_dir: Path, body: dict) -> dict:
    md_path = resolve_backlog_dir(backlog_dir)
    items_path = items_csv_path(md_path)
    exec_path = executions_csv_path(md_path)
    item_rows = read_items_rows(items_path)
    valid_task_ids = {row["id"] for row in item_rows}
    if not valid_task_ids:
        raise ValueError("no items in backlog — add an item before scheduling executions")

    exec_rows = read_executions_rows(exec_path)
    existing_ids = {row["id"] for row in exec_rows}
    row = execution_body_to_row(body, existing_ids, valid_task_ids)
    exec_rows.append(row)
    write_executions_rows(exec_path, exec_rows)
    _, data = build_backlog_html(backlog_dir, editor_enabled=True)
    return api_payload(data)


def main() -> int:
    parser = argparse.ArgumentParser(description="Build HTML from priority-intake-backlog")
    parser.add_argument(
        "backlog_dir",
        type=Path,
        help="Backlog directory (e.g. docs/backlog)",
    )
    parser.add_argument("-o", "--output", type=Path, help="Output HTML path (default: <backlog_dir>/priority-intake-backlog.html)")
    parser.add_argument(
        "--serve",
        action="store_true",
        help="Start local server with CSV save (add items and executions from the HTML UI)",
    )
    parser.add_argument("--port", type=int, default=8765, help="Port for --serve (default: 8765)")
    args = parser.parse_args()

    try:
        html_path, data = build_backlog_html(args.backlog_dir, args.output, editor_enabled=args.serve)
    except (FileNotFoundError, ValueError) as exc:
        print(f"Error: {exc}", file=sys.stderr)
        return 1

    print(f"Wrote {html_path} ({len(data['items'])} items)")

    if args.serve:
        from backlog_server import run_server

        run_server(args.backlog_dir.resolve(), args.port, html_path)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
