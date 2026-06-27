#!/usr/bin/env python3
"""Build a readable HTML dashboard from priority-intake-backlog.md (raw fields only)."""

from __future__ import annotations

import argparse
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


def parse_date_field(val: str) -> str | None:
    if not val or val.strip() in ("—", "-", ""):
        return None
    v = val.strip()
    return v if DATE_ISO.match(v) else None


def add_calendar_days(iso: str, offset: int) -> str:
    d = date.fromisoformat(iso)
    return (d + timedelta(days=offset)).isoformat()


def calendar_span_days(effort_days: float) -> int:
    if effort_days < 0.5:
        return 0
    return max(1, int(round(effort_days)))


def resolve_schedule(fields: dict) -> dict:
    start = parse_date_field(fields.get("start_date", ""))
    end = parse_date_field(fields.get("end_date", ""))
    effort_days = parse_effort_days(fields.get("Effort", ""))
    span = calendar_span_days(effort_days)

    if start and end:
        return {
            "mode": "invalid",
            "start": None,
            "end": None,
            "effort_days": effort_days or None,
            "schedule_error": "不能同时填写 start_date 与 end_date",
        }
    if start:
        if span == 0:
            return {
                "mode": "invalid",
                "start": start,
                "end": None,
                "effort_days": None,
                "schedule_error": "有 start_date 时必须可解析 Effort（至少 0.5 person-day）",
            }
        cal_end = add_calendar_days(start, span - 1)
        return {
            "mode": "range",
            "start": start,
            "end": cal_end,
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
                "effort_days": effort_days,
                "schedule_error": None,
            }
        return {
            "mode": "milestone",
            "start": end,
            "end": end,
            "effort_days": None,
            "schedule_error": None,
        }
    return {
        "mode": "none",
        "start": None,
        "end": None,
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
    for item in items:
        item["schedule"] = resolve_schedule(item["fields"])


def parse_backlog(text: str) -> dict:
    lines = text.splitlines()
    items: list[dict] = []
    decisions: list[str] = []
    implementation_order = ""
    current: dict | None = None
    in_decisions = False
    decision_cols: list[str] = []

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
            in_decisions = False
            continue

        stripped = line.strip()

        if stripped == "## 已确认决策":
            in_decisions = True
            decision_cols = []
            continue

        if stripped.startswith("## ") and stripped != "## 已确认决策":
            in_decisions = False

        if in_decisions and stripped.startswith("**实施顺序**"):
            implementation_order = stripped.replace("**实施顺序**：", "").replace("**实施顺序**:", "").strip()
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
            continue

        if current and stripped.startswith("|"):
            row = parse_markdown_table_row(line)
            if row and row[0] not in COMPUTED_MD_FIELDS:
                current["fields"][row[0]] = row[1]

    if current:
        items.append(current)

    run_compute_pipeline(items)
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
    parser = argparse.ArgumentParser(description="Build HTML from priority-intake-backlog.md")
    parser.add_argument("input", type=Path, help="Path to priority-intake-backlog.md")
    parser.add_argument("-o", "--output", type=Path, help="Output HTML path (default: same dir, .html)")
    args = parser.parse_args()

    if not args.input.is_file():
        print(f"Error: file not found: {args.input}", file=sys.stderr)
        return 1

    text = args.input.read_text(encoding="utf-8")
    data = parse_backlog(text)
    out = args.output or args.input.with_suffix(".html")
    generated_at = datetime.now(timezone.utc).strftime("%Y-%m-%d %H:%M UTC")
    out.write_text(render_html(data, args.input.resolve(), generated_at), encoding="utf-8")
    print(f"Wrote {out} ({len(data['items'])} items)")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
