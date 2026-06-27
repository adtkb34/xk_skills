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


ITEM_HEADER = re.compile(r"^###\s+(RICE-[A-Z]+-\d+)\s+[—–-]\s+(.+)$")
TABLE_ROW = re.compile(r"^\|\s*(.+?)\s*\|\s*(.+?)\s*\|$")
DECISION_HEADER = re.compile(r"^\|\s*#\s*\|", re.I)
PARENT_LINK = re.compile(r"^(RICE-[A-Z]+-\d+)(?::(\d+)%)?$")
DATE_ISO = re.compile(r"^\d{4}-\d{2}-\d{2}$")
TEMPLATE_PATH = Path(__file__).with_name("backlog-dashboard.template.html")

COMPUTED_MD_FIELDS = frozenset({
    "RICE", "RICE_norm", "Score", "Effective_RICE", "Reach_source", "Impact_source",
})

BACKLOG_STEM = "priority-intake-backlog"
ITEMS_CSV_SUFFIX = ".items.csv"
EXECUTIONS_CSV_SUFFIX = ".executions.csv"
SCHEDULE_ANCHOR = re.compile(
    r"^(\d{4}-\d{2}-\d{2})(?:[T ](\d{2}:\d{2})(?::\d{2})?)?$"
)
TIME_ONLY = re.compile(r"^\d{2}:\d{2}(?::\d{2})?$")

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


def parse_markdown_table_row(line: str) -> tuple[str, str] | None:
    m = TABLE_ROW.match(line.strip())
    if not m:
        return None
    key, val = m.group(1).strip(), m.group(2).strip()
    if key in ("---", "Field", "Rank", "#") or set(key) <= {"-"}:
        return None
    key = re.sub(r"\*\*(.+?)\*\*", r"\1", key)
    val = re.sub(r"\*\*(.+?)\*\*", r"\1", val)
    val = val.strip("`")
    return key, val


def parse_float(val: str) -> float:
    try:
        return float(re.sub(r"[^\d.]", "", val) or "0")
    except ValueError:
        return 0.0


def parse_confidence(val: str) -> float:
    n = parse_float(val)
    return n if n > 0 else 80.0


def parse_effort_days(effort_str: str) -> float:
    if not effort_str or effort_str.strip() in ("—", "-", ""):
        return 0.0
    s = effort_str.lower()
    num = parse_float(effort_str)
    if num <= 0:
        return 0.0
    if "month" in s or "月" in s:
        return num * 20.0
    if "week" in s or "周" in s:
        return num * 5.0
    return num


def effort_for_rice(level: str, effort_days: float) -> float:
    minimum = 0.5 if level == "Task" else 2.5
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
                "schedule_error": "start_date requires parseable Effort (at least 0.5 person-day)",
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


DECISION_SECTION_HEADERS = frozenset({
    "## Confirmed decisions",
    "## \u5df2\u786e\u8ba4\u51b3\u7b56",  # legacy
})
IMPLEMENTATION_ORDER_MARKERS = (
    "**Implementation order**",
    "**\u5b9e\u65bd\u987a\u5e8f**",  # legacy
)
IMPLEMENTATION_ORDER_PREFIXES = (
    "**Implementation order**:",
    "**Implementation order**: ",
    "**\u5b9e\u65bd\u987a\u5e8f**\uff1a",  # legacy fullwidth colon
    "**\u5b9e\u65bd\u987a\u5e8f**:",  # legacy
)


def parse_decisions_md(text: str) -> tuple[list[str], str]:
    lines = text.splitlines()
    decisions: list[str] = []
    implementation_order = ""
    in_decisions = False
    decision_cols: list[str] = []

    for line in lines:
        stripped = line.strip()

        if stripped in DECISION_SECTION_HEADERS:
            in_decisions = True
            decision_cols = []
            continue

        if stripped.startswith("## ") and stripped not in DECISION_SECTION_HEADERS:
            in_decisions = False

        if in_decisions and any(stripped.startswith(m) for m in IMPLEMENTATION_ORDER_MARKERS):
            for prefix in IMPLEMENTATION_ORDER_PREFIXES:
                if stripped.startswith(prefix):
                    implementation_order = stripped[len(prefix):].strip()
                    break
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


def parse_items_md_legacy(text: str) -> list[dict]:
    """Legacy: ### RICE-… — title + per-item Field|Value tables."""
    lines = text.splitlines()
    items: list[dict] = []
    current: dict | None = None

    for line in lines:
        header = ITEM_HEADER.match(line.strip())
        if header:
            if current:
                items.append(current)
            current = {
                "id": header.group(1),
                "title": header.group(2).strip(),
                "fields": {},
            }
            continue

        if current and line.strip().startswith("|"):
            row = parse_markdown_table_row(line)
            if row and row[0] not in COMPUTED_MD_FIELDS:
                current["fields"][row[0]] = row[1]

    if current:
        items.append(current)
    return items


def parse_backlog(md_path: Path) -> dict:
    text = md_path.read_text(encoding="utf-8")
    decisions, implementation_order = parse_decisions_md(text)

    csv_path = items_csv_path(md_path)
    if csv_path.is_file():
        items = parse_items_csv(csv_path)
    else:
        items = parse_items_md_legacy(text)

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


def render_html(data: dict, source: Path, generated_at: str) -> str:
    if not TEMPLATE_PATH.is_file():
        raise FileNotFoundError(f"Template not found: {TEMPLATE_PATH}")

    template = TEMPLATE_PATH.read_text(encoding="utf-8")
    payload = {
        "items": data["items"],
        "summary": data["summary"],
        "decisions": data.get("decisions", []),
        "implementationOrder": data.get("implementationOrder", ""),
    }
    return (
        template.replace("__DATA_JSON__", json.dumps(payload, ensure_ascii=False))
        .replace("__SOURCE__", html.escape(source.name))
        .replace("__GENERATED_AT__", html.escape(generated_at))
    )


def main() -> int:
    parser = argparse.ArgumentParser(description="Build HTML from priority-intake-backlog")
    parser.add_argument(
        "backlog_dir",
        type=Path,
        help="Backlog directory (e.g. docs/backlog)",
    )
    parser.add_argument("-o", "--output", type=Path, help="Output HTML path (default: <backlog_dir>/priority-intake-backlog.html)")
    args = parser.parse_args()

    if not args.backlog_dir.exists():
        print(f"Error: path not found: {args.backlog_dir}", file=sys.stderr)
        return 1

    if not args.backlog_dir.is_dir():
        print(
            f"Error: expected a directory, not a file: {args.backlog_dir}\n"
            f"Pass the backlog folder (e.g. docs/backlog), not {BACKLOG_STEM}.md.",
            file=sys.stderr,
        )
        return 1

    md_path = backlog_md_in_dir(args.backlog_dir)
    if not md_path.is_file():
        print(
            f"Error: backlog file not found: {md_path}\n"
            f"Expected {BACKLOG_STEM}.md inside {args.backlog_dir}.",
            file=sys.stderr,
        )
        return 1

    data = parse_backlog(md_path)
    out = args.output or md_path.with_suffix(".html")
    generated_at = datetime.now(timezone.utc).strftime("%Y-%m-%d %H:%M UTC")
    csv_path = items_csv_path(md_path)
    exec_path = executions_csv_path(md_path)
    source_parts = [md_path.name]
    if csv_path.is_file():
        source_parts.append(csv_path.name)
    if exec_path.is_file():
        source_parts.append(exec_path.name)
    source_label = " + ".join(source_parts)
    out.write_text(render_html(data, Path(source_label), generated_at), encoding="utf-8")
    print(f"Wrote {out} ({len(data['items'])} items)")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
