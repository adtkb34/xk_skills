---
name: rice-priority-intake
description: >-
  Runs confirm-first RICE priority intake for product backlogs. One user request
  yields one backlog item by default. Artifacts live under docs/backlog/. Asks
  structured questions, scores Reach/Impact/Confidence/Effort, supports
  Epic→Feature→Story→Task hierarchy and multi-parent attribution. Use when the
  user submits a new requirement, asks what to build first, mentions RICE,
  priority intake, backlog ranking, or prioritization.
---

# RICE Priority Intake

Run **Priority Intake (confirm-first)**: interview → draft summary → **user approval** → write one backlog row → build HTML.

## Defaults (one request = one item)

- User describes **one** requirement → create **one** backlog row for **that** requirement only.
- If user says "task", default `Level = Task` unless they specify otherwise.
- **Do not** auto-decompose into Epic / Feature / Story / sibling Tasks.
- **Do not** create missing parent rows. If `parent_links` are needed, **ask** for an existing parent ID or whether to run a **separate** parent intake.
- **Do not** invent sibling `impact_slice` splits or extra tasks from one sentence.

**Multi-row allowed only when user explicitly asks**, e.g. "split into a few tasks", "add a Story and 3 Tasks below", "create child items for this Epic".

## When to run

Trigger on:

- New feature / bug / improvement requests
- "what to build first" / "prioritize backlog" / "RICE scoring"
- Updates to `core-feature-ledger.md` that need ordering
- Cross-cutting work that serves multiple Epics or Features

Do **not** replace Skill 104 prompt refinement. RICE decides **order**; Skill 104 decides **readiness to implement**.

## Artifacts

All files live under **`docs/backlog/`** at the **current workspace root** (unless the user names a different path). **Never** default to `.ai-factory/` or `00-intake/`.

| File | Purpose |
| --- | --- |
| `docs/backlog/priority-intake-backlog.md` | **Decisions** — confirmed decisions, implementation order |
| `docs/backlog/priority-intake-backlog.items.csv` | **Raw data** — Items table (one row per item); interview inputs only, **no** computed columns |
| `docs/backlog/priority-intake-backlog.executions.csv` | **Execution / schedule** — one row per execution; `task_id` points to items |
| `docs/backlog/priority-intake-backlog.html` | **Computed view** — build output: Score, Summary, calendar, rollup |
| `docs/backlog/core-feature-ledger.md` | P0/P1 truth; sync Priority column from RICE rank |

After user approval, create `docs/backlog/` and template files (`priority-intake-backlog.md`, `.items.csv`, `.executions.csv`) if missing. Use templates in [reference.md](reference.md).

**Maintenance rules**: edit `.md` (raw fields) only; run `build_html.py` after changes to refresh HTML. **Do not** write RICE/Score/Summary into md; **do not** hand-edit `.html`.

## Viewing the backlog

**See what tasks exist**

1. **CSV + Markdown (source files)** — `.items.csv` for Items; `.executions.csv` for schedule/execution; `.md` for decisions; **no Summary table**.
2. **HTML (recommended)** — `priority-intake-backlog.html`: **flow chart**, **priority** (build-generated Summary), **board**, **calendar**, **decisions**; click to open detail drawer (includes computed section).

**Generate HTML**

```bash
python .cursor/skills/rice-priority-intake/scripts/build_html.py docs/backlog
```

Output defaults to `docs/backlog/priority-intake-backlog.html`. Specify output path:

```bash
python .cursor/skills/rice-priority-intake/scripts/build_html.py docs/backlog -o path/to/report.html
```

After user approves a write, run the script above and share the HTML path. User can open in browser or via `open_resource`.

**No separate Word/PDF** is produced; the "Priority Intake" reply in chat is an instant summary; persistent content lives only in `.md` + generated `.html`.

## Hierarchy model

```
Epic → Feature → Story → Task
```

| Level | Who gets full RICE interview | Effort authority |
| --- | --- | --- |
| Epic | Yes | Rough (quarters) |
| Feature | Yes | Weeks–months |
| Story | Abbreviated (5 questions) | Days–weeks |
| Task | Abbreviated | Days; **authoritative for scheduling** |

**Rejected patterns** (do not use):

- Same-layer-only scoring without leaf effort → hides implementation order
- **Uncoefficient parent→child copy** — copying parent Reach/Impact 1:1 without attribution % → breaks multi-parent
- **Child re-estimates full parent Reach** — sibling Tasks each claim the same full Reach/Impact → child RICE inflates above parent
- Pure bottom-up rollup of Reach/Impact without leaf Effort → unreliable at fine grain

**Adopted pattern: attributed inheritance + contribution rollup**

1. **No `parent_links`** (Epic / root Story / Feature): full RICE interview at that layer.
2. **With `parent_links`**: Reach/Impact **derived from parents × attribution %**; Confidence/Effort interviewed on the child.
3. **Multi-parent**: each parent weighted by `ai%`; splits must sum to 100%.
4. **Rollup**: `contribution_rice(C → Pi) = RICE(C) × (ai / 100)`; Effort counted **once** on the leaf.

Details and formulas: [reference.md](reference.md). Worked examples: [examples.md](examples.md).

## Intake workflow

Copy and track:

```
Priority Intake:
- [ ] Step 1: Parse requirement
- [ ] Step 2: Confirm title + level (+ parents only if needed)
- [ ] Step 3: RICE interview
- [ ] Step 4: Score + multi-parent attribution (compute in reply / build — **not** in md)
- [ ] Step 4.5: Normalize (Score = norm × 100 — **build only**)
- [ ] Step 4.9: Present draft summary; wait for explicit user approval
- [ ] Step 5: Write backlog row (**raw fields only** — only after approval)
- [ ] Step 5.5: Schedule (optional — rows in `.executions.csv` only)
- [ ] Step 6: Run build_html + recommend from HTML Summary
- [ ] Step 7: Sync core-feature-ledger if applicable (with user approval)
```

### Step 1: Parse requirement

Extract: title, type (Epic/Feature/Story/Task/Bug/Chore), user outcome, affected surfaces, P0/P1 hint, dependencies, requester urgency.

### Step 2: Confirm title + level (+ parents only if needed)

1. Confirm **single item title** and **level** — default from the user's words (e.g. "task" → Task).
2. **Only if** the user referenced a parent or wants linkage — ask for existing parent ID(s) from the backlog.
3. **If multiple parents** — value split (must sum to 100%): e.g. 60% dashboard, 40% export.

Do **not** pressure the user to pick Epic vs Feature for every request. Do **not** create parent rows or sibling Tasks unless explicitly requested.

Use `AskQuestion` when available; otherwise ask conversationally in one batch (max 2 rounds).

### Step 3: RICE interview

Ask only what you cannot infer from codebase + `core-feature-ledger.md` + `prd.md`.

**Epic / Feature (full)** — always interview all four dimensions:

| Dimension | Question |
| --- | --- |
| Reach | How many users/sessions/events per quarter? |
| Impact | 3=massive … 0.25=minimal (see reference) |
| Confidence | 100% / 80% / 50% — what evidence supports this? |
| Effort | Person-weeks or person-months to ship |

**Story / Task — no `parent_links`** — abbreviated interview (all four dimensions):

| Dimension | Question |
| --- | --- |
| Reach | Who touches this when done? (count or % of active users) |
| Impact | Same scale; default 1 if unclear |
| Confidence | Default 80% unless novel/architectural |
| Effort | Person-days |

**Story / Task — with `parent_links`** — **skip full Reach/Impact estimation**:

1. Confirm each parent ID and attribution `ai%` (Σai = 100%).
2. If **sibling Tasks** share one parent → ask **impact_slice** per child (0–1; Σ slice ≤ 1 for that parent). See Step 4.
3. Interview **Confidence** and **Effort** on the child only.
4. Reach/Impact are computed in Step 4 from parent scores × coefficients.

Always ask: **blocked by?** / **blocks?** / **deadline or season?**

### Step 4: Score + multi-parent attribution

**Base formula**

```
RICE = (Reach × Impact × Confidence%) / Effort
```

Effort minimum: **0.5 person-day** for Task, **0.5 person-week** for Story+.

**Attributed inheritance** (child `C`, parents `P1…Pn`, splits `a1…an`, Σai = 100):

```
Reach_c  = Σ Reach(Pi) × (ai / 100)
Impact_c = Σ Impact(Pi) × (ai / 100) × impact_slice_i   // default impact_slice = 1
RICE_c   = (Reach_c × Impact_c × Confidence%) / Effort_c
```

Single parent at 100% is the special case: `Reach_c = Reach(P1)`, `Impact_c = Impact(P1) × impact_slice`.

**Sibling Tasks** under the same parent:

- `parent_links` `100%` means **all of this child's RICE rolls up to that parent** — not exclusive ownership of 100% parent value.
- Assign `impact_slice` per sibling so Σ slice ≤ 1; Reach typically inherits parent full (same users).
- **Do not** write derived Reach/Impact or RICE into md — `build_html.py` computes them.

**Contribution rollup** (unchanged):

```
contribution_rice(C → Pi) = RICE_c × (ai / 100)
parent_rollup_rice(Pi)    = max(own_direct_rice(Pi), Σ contribution_rice(C → Pi))
```

Effort is **not** multiplied per parent — counted once on `C`.

### Step 4.5: Normalize (display score)

Keep **two scores** — do not conflate them:

| Field | Range | Purpose |
| --- | --- | --- |
| `RICE` | unbounded raw | Sibling sort within level; rollup contributions |
| `RICE_norm` | 0–1 | Tree priority; child always ≤ parent (single-parent) |
| `Score` | 0–100 | **Display** = `RICE_norm × 100` |

**Root items** (no `parent_links`):

```
RICE_max = max(RICE among all root items in this backlog scope)
RICE_norm(root) = RICE(root) / RICE_max
```

**Child items**:

```
RICE_norm(C) = Σ RICE_norm(Pi) × (ai / 100) × impact_slice
Score(C)     = RICE_norm(C) × 100
```

Single parent 100% + slice 0.4 → `norm = norm(parent) × 0.4` → **guaranteed ≤ parent**.

All of Step 4–4.5 runs in **`build_html.py`** and intake chat replies — **never persisted in md**.

### Step 4.9: Confirm draft (required before any write)

Present the full draft in chat:

- Title, level, scorecard (Reach / Impact / Confidence / Effort / RICE / Score)
- `parent_links` and `impact_slice` (if any)
- Proposed CSV row (exact fields)
- Whether `docs/backlog/` or template files will be created

Ask: **Approve / Edit / Cancel** (`AskQuestion` when available).

**Forbidden before approval**: creating directories, writing `.md` / `.csv`, running `build_html.py`, syncing ledger.

On **Edit** — revise and re-show. On **Cancel** — stop without writing.

### Step 5: Write backlog row (raw only — after approval)

Append **one** CSV row to `docs/backlog/priority-intake-backlog.items.csv` using [reference.md](reference.md) column template. Update decisions in `.md` when needed.

**Root item** (no `parent_links`): `Level`, `Status`, `Reach`, `Impact`, `Confidence`, `Effort`, `Blocks`, `Blocked_by`, `Ledger_ref`, `Notes`.

**Child item** (has `parent_links`): `Level`, `Status`, `Confidence`, `Effort`, `impact_slice`, `Parent_links`, `Blocks`, `Blocked_by`, `Notes` — **omit** `Reach`/`Impact`.

**Schedule** — never on the item row. Append to `priority-intake-backlog.executions.csv`: `id`, `task_id`, `start_date` or `end_date`, `status`, `notes`.

**Forbidden in csv/md**: `RICE`, `RICE_norm`, `Score`, `Effective_RICE`, `Reach_source`, `Impact_source`, `## Summary` table.

ID pattern: `RICE-<LEVEL>-<NNN>`.

### Step 5.5: Schedule (optional)

Ask: need calendar? **start date** or **deadline**? Append rows to `.executions.csv` only.

| Rule | Detail |
|---|---|
| Where | **Only** `priority-intake-backlog.executions.csv` — **never** `start_date`/`end_date` on item rows |
| Anchor | Set **only** `start_date` **or** `end_date` per row (`YYYY-MM-DD`), not both |
| `start_date` | Linked task must have parseable `Effort` (person-days) |
| `end_date` | `Effort` optional — milestone if omitted; range if present |
| Multiple runs | One execution row per run/slot (same `task_id`) |
| No rows | Task omitted from calendar; listed under "Unscheduled" |

Calendar span computed by build (natural days). See reference.

### Step 6: Re-rank + recommend

1. Run `build_html.py`; read **HTML** Summary (Score descending).
2. Sibling Tasks: raw RICE from build (implementation order).
3. Prefer **ready** leaf Tasks; calendar for timeboxed work.
4. Top 5 actionable in chat reply (may cite computed Score).
5. Confirm md has **no computed columns** before finishing.

### Step 7: Sync ledger (with user approval)

If item maps to `docs/backlog/core-feature-ledger.md`, ask before updating:

- Set `Priority` column to P0/P1/P2 from RICE band (reference) **or** keep explicit P0 and note RICE rank in Notes.
- Never downgrade P0 without explicit user approval.

## Response format

**Before approval (Step 4.9)** — show draft using the template below, ending with **Approve / Edit / Cancel**.

**After approval** — reply with persisted summary:

```markdown
## Priority Intake: [Title]

**Level**: … | **Score**: … / 100 | **Rank**: #N in Summary

### Scorecard
| Reach | Impact | Confidence | Effort | RICE (raw) | Score |
| … | … | … | … | … | … |

### Inheritance
- Reach: … (e.g. `STORY-001:120×100%`)
- Impact: … (e.g. `STORY-001:2×100%×slice0.4`)

### Parents (rollup)
- [Parent ID] — …% attribution → contribution RICE …

### Recommendation
[1–2 sentences: do now / queue after X / split / descope]

### Updated top 5 (actionable)
1. …
…

### Open questions
- …
```

## Escalation

Stop and ask the user when:

- P0 in ledger but RICE bottom quartile
- Multi-parent splits unclear and effort differs 3×+ by parent
- Effort > 2 person-months at Feature+ without Epic parent
- Duplicate or overlaps existing backlog ID

## Additional resources

- Scales, templates, rollup rules: [reference.md](reference.md)
- Material-demand-dashboard example: [examples.md](examples.md)
