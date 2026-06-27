# RICE Priority Intake — Reference

## Impact scale

| Value | Label | Meaning |
| --- | --- | --- |
| 3 | Massive | Core workflow transformation; P0 risk reduction |
| 2 | High | Major metric or daily-workflow improvement |
| 1 | Medium | Clear value; noticeable but not transformative |
| 0.5 | Low | Nice-to-have; edge cases |
| 0.25 | Minimal | Polish, internal-only, tiny audience |

## Confidence scale

| % | When to use |
| --- | --- |
| 100 | Shipped similar work; data or prototype exists |
| 80 | Strong product intuition; partial analogies |
| 50 | Hypothesis; needs spike or user validation |

## Reach guidance (material-demand-dashboard)

| Audience | Typical reach / quarter |
| --- | --- |
| All planners (daily) | Active user count × ~60 working days |
| Regional leads | Users in that region × weekly sessions |
| Integration/backend | Downstream systems or batch jobs per month |
| Admin/settings | % of users who open settings monthly |

Use **events per quarter** when user count is unknown (e.g. "export runs", "risk alerts viewed").

## Effort units

**CSV `effort` column**: numeric **days** only (e.g. `14`, `3.5`) — no unit suffix.

**UI / intake interview** — pick a display unit by level; convert before writing CSV:

| Level | Typical input unit | Example input → CSV |
| --- | --- | --- |
| Epic | months | 2 months → `60` |
| Feature | weeks | 3 weeks → `21` |
| Story | days | 6 days → `6` |
| Task | days | 2 days → `2` |

Convert: 1 month = 30 days; 1 week = 7 days.

## Priority bands (sync to ledger)

| RICE (Feature-level equivalent) | Suggested Priority |
| --- | --- |
| ≥ 50 | P0 candidate (confirm against ledger) |
| 20 – 49 | P1 |
| 5 – 19 | P2 |
| < 5 | P3 / backlog |

Feature RICE is the reference band. Scale Task RICE only for within-Task sorting unless attributed rollup elevates a parent.

## Raw backlog schema

**`priority-intake-backlog.md`** holds decisions; **`priority-intake-backlog.items.csv`** holds item rows (human-editable inputs only); **`priority-intake-backlog.executions.csv`** holds schedule/execution rows (1:N via `task_id`). `build_html.py` computes RICE, Score, Summary, calendar spans, rollup.

### Allowed fields

| Field | Root item | Child (`parent_links`) |
| --- | --- | --- |
| `Level`, `Status` | yes | yes |
| `Reach`, `Impact` | yes | **no** (inherited) |
| `Confidence`, `Effort` | yes | yes |
| `impact_slice` | — | yes when siblings share parent |
| `Parent_links` | optional | yes |
| `Blocks`, `Blocked_by`, `Ledger_ref`, `Notes` | yes | yes |

**Schedule is not on item rows** — all `start_date` / `end_date` live only in `.executions.csv`.

### Forbidden in csv/md

`RICE`, `RICE_norm`, `Score`, `Effective_RICE`, `Reach_source`, `Impact_source`, `## Summary` table.

### Schedule rules (executions only)

| Input | Linked task `effort` | build calendar |
| --- | --- | --- |
| neither date | — | Unscheduled |
| `start_date` only | required | range: start … start+N−1 days |
| `end_date` only | optional | milestone, or range if Effort set |
| both dates | — | **invalid** |

Dates: `YYYY-MM-DD`. Span uses **natural days** from linked item's parsed `Effort`.

### Executions schema

**`priority-intake-backlog.executions.csv`** — one row per execution / schedule slot:

```csv
id,task_id,start_date,end_date,start_time,end_time,status,notes
EXEC-001,RICE-TASK-005,2026-07-01,,09:00,,pending,Initial schedule
EXEC-002,RICE-TASK-005,2026-07-08T14:30,,,,pending,Retry after integration
```

| Column | Required | Notes |
| --- | --- | --- |
| `id` | yes | e.g. `EXEC-001` |
| `task_id` | yes | Must match `id` in `.items.csv` |
| `start_date` / `end_date` | optional | Set **only one**; `YYYY-MM-DD` or `YYYY-MM-DDTHH:MM` |
| `start_time` / `end_time` | optional | `HH:MM` if not embedded in date; calendar chip shows time on start day |
| `status` | optional | `pending` \| `running` \| `success` \| `failed` \| `cancelled` (default `pending`) |
| `notes` | optional | Free text |

- One task → many execution rows (1:N).
- Calendar shows all execution slots; unscheduled = task has no valid execution rows.

## Backlog file template

All files live under **`docs/backlog/`** at the workspace root (unless the user specifies another path).

**`docs/backlog/priority-intake-backlog.md`** — decisions only:

```markdown
# Priority Intake Backlog

> Raw data only. Items live in `priority-intake-backlog.items.csv` in the same directory; multiple runs in `priority-intake-backlog.executions.csv`. Open the built .html for ranking, scores, and calendar.

## Confirmed decisions

| # | Decision |
| --- | --- |
| 1 | … |

**Implementation order**: …
```

**`docs/backlog/priority-intake-backlog.items.csv`** — one row per item (UTF-8 with BOM for Excel):

```csv
id,title,level,status,reach,impact,confidence,effort,impact_slice,parent_links,blocks,blocked_by,ledger_ref,notes
RICE-STORY-001,Title,Story,ready,120,2,80%,6,,,,,,"Notes…"
RICE-TASK-NNN,Child task,Task,ready,,,90%,2,0.4,RICE-STORY-001:100%,,,,"Notes…"
```

| Column | Root | Child (`parent_links`) |
| --- | --- | --- |
| `id`, `title`, `level`, `status` | required | required |
| `reach`, `impact` | yes | leave empty (inherited) |
| `confidence`, `effort` | yes (`effort` = days, number) | yes |
| `impact_slice` | empty | yes when siblings share parent |
| `parent_links` | empty | e.g. `RICE-STORY-001:100%` |
| `blocks`, `blocked_by`, `ledger_ref`, `notes` | optional | optional |

Empty cell = not set. Quote `notes` when it contains commas.

**`docs/backlog/priority-intake-backlog.executions.csv`** — header only until first schedule:

```csv
id,task_id,start_date,end_date,start_time,end_time,status,notes
```

## Row template (quick append — child Task CSV line)

```csv
RICE-TASK-NNN,Title,Task,intake,,,80%,3,0.4,RICE-STORY-001:100%,,,,"Notes…"
```

## Row template (quick append — execution CSV line)

```csv
EXEC-NNN,RICE-TASK-NNN,2026-07-01,,pending,
```

## Attributed inheritance scoring

When `parent_links` is non-empty, **do not** re-interview full Reach/Impact on the child. Derive from parents × attribution %, then compute RICE with child Confidence/Effort.

| Scenario | Reach_c | Impact_c | impact_slice |
| --- | --- | --- | --- |
| Single parent 100% | `Reach(P) × 1` | `Impact(P) × 1 × slice` | 1 if only child; else Σ slice ≤ 1 across siblings |
| Multi-parent Σai=100% | `Σ Reach(Pi) × ai%` | `Σ Impact(Pi) × ai% × slice` | Usually 1 (value split is in ai%) |
| Sibling Tasks, same parent | Inherit parent Reach full | `Impact(P) × slice` per sibling | Σ slice ≤ 1 per parent |

```
function inherited_reach(child):
  return sum(parent.reach * (pct / 100) for parent, pct in child.parent_links)

function inherited_impact(child, impact_slice=1):
  return sum(parent.impact * (pct / 100) * impact_slice
             for parent, pct in child.parent_links)

function score_child(child, impact_slice=1):
  reach = inherited_reach(child)
  impact = inherited_impact(child, impact_slice)
  return rice(reach, impact, child.confidence, child.effort)
```

**Two layers of coefficients**

1. **Scoring** — Reach/Impact inherited from each parent × `ai%` (and × `impact_slice` for siblings).
2. **Rollup** — `contribution_rice(C → Pi) = RICE_c × (ai / 100)`.

## Normalized priority score

Display **`Score = RICE_norm × 100`** everywhere in Summary, HTML, and intake replies. Keep raw `RICE` in item detail for scheduling.

```
function rice_max_roots(items):
  roots = [i for i in items if not i.parent_links]
  return max(i.rice for i in roots) or 1

function rice_norm(item, cache, items):
  if item.id in cache: return cache[item.id]
  if not item.parent_links:
    n = item.rice / rice_max_roots(items)
  else:
    slice = item.impact_slice or 1
    n = sum(rice_norm(parent, cache, items) * (pct/100) * slice
            for parent, pct in item.parent_links)
  cache[item.id] = n
  return n

function score_display(item):
  return round(rice_norm(item) * 100, 1)
```

| Scenario | RICE_norm | Score | Child ≤ parent? |
| --- | --- | --- | --- |
| Root max raw = 32 | 32/32 = 1.0 | 100 | — |
| Child slice 0.4 under parent norm 1 | 0.4 | 40 | Yes |
| Siblings 0.4 + 0.35 + 0.25 | 0.4, 0.35, 0.25 | 40, 35, 25 | Each ≤ parent; Σ = 100 |

**Sorting rules (updated)**

1. **Summary / HTML / cross-layer**: `Score` descending.
2. **Sibling Tasks (implementation order)**: raw `RICE` descending.
3. **Epics/Features**: `parent_effective_rice` for audit; display `Score` at container level.
4. **Tie-break** (within level): lower Effort, higher Confidence, fewer `blocked_by`.

## Rollup algorithm

```
function rice(reach, impact, confidence_pct, effort):
  return (reach * impact * (confidence_pct / 100)) / effort

function score_item(item):
  if item.parent_links is empty:
    return rice(item.reach, item.impact, item.confidence, item.effort)
  reach = inherited_reach(item)
  impact = inherited_impact(item, item.impact_slice or 1)
  return rice(reach, impact, item.confidence, item.effort)

function contributions(child):
  rice_c = score_item(child)
  for each (parent, pct) in child.parent_links:
    yield parent, rice_c * (pct / 100)

function parent_effective_rice(parent):
  direct = parent.own_rice or 0
  from_children = sum(c for c in contributions(all_children_of parent))
  return max(direct, from_children)
```

## Status lifecycle

```
intake → ready → in-progress → done
              ↘ deferred
```

- `intake`: scored, not committed
- `ready`: dependencies clear, can start
- `deferred`: explicit user decision; keep score for re-evaluation

## Anti-patterns

| Anti-pattern | Fix |
| --- | --- |
| Double-counting effort on each parent | Effort once on leaf only |
| 100% attribution to two parents | Splits must sum to 100% |
| Child Task re-estimates same full Reach as parent | Inherit `Reach(P) × ai%` |
| Sibling Tasks each inherit full parent Impact | Assign `impact_slice`; Σ slice ≤ 1 per parent |
| Compare Task standalone RICE to Story standalone RICE | Use `Score` in Summary; raw RICE only within Task level |
| Display raw RICE in Summary when children exist | Show `Score` (= norm×100); raw RICE in item detail |
| Scoring every sub-task when parent is exploratory | Score parent Feature; children inherit Reach/Impact until split |
| RICE replacing P0 ledger | P0 stands; RICE sequences work within constraints |
| Writing Score/RICE/Summary into md | Raw md only; run build_html |
| Child with Reach/Impact in md | Omit; build inherits from parent |
| start_date + end_date both set on execution | Pick one anchor only |
| start_date without linked task Effort | Invalid schedule in HTML |
| start_date / end_date on item row | **Forbidden** — use `.executions.csv` |
| Auto-decompose one request into many items | One request → one row unless user explicitly asks to split |
| Write files before user approves draft | Step 4.9 confirm-first; no writes until approval |
