---
name: rice-priority-intake
description: >-
  Runs RICE priority intake for hierarchical product backlogs with multi-parent
  attribution. Asks structured questions, scores Reach/Impact/Confidence/Effort,
  rolls up Epic→Feature→Story→Task, and sorts the backlog. Use when the user
  submits a new requirement, asks what to build first, mentions RICE, priority
  intake, backlog ranking, or prioritization for material-demand-dashboard or
  similar products.
---

# RICE Priority Intake

Automate **Priority Intake**: every new requirement gets a short interview, a RICE score, parent links, and a ranked position in the backlog.

## When to run

Trigger on:

- New feature / bug / improvement requests
- "先做哪个" / "排优先级" / "RICE 打分"
- Updates to `core-feature-ledger.md` that need ordering
- Cross-cutting work that serves multiple Epics or Features

Do **not** replace Skill 104 prompt refinement. RICE decides **order**; Skill 104 decides **readiness to implement**.

## Artifacts

| File | Purpose |
| --- | --- |
| `projects/<slug>/.ai-factory/00-intake/priority-intake-backlog.md` | **决策** — 已确认决策、实施顺序 |
| `projects/<slug>/.ai-factory/00-intake/priority-intake-backlog.items.csv` | **原始数据** — Items 表格（一行一条）；仅存访谈输入，**不含**计算列 |
| `projects/<slug>/.ai-factory/00-intake/priority-intake-backlog.html` | **计算视图** — build 生成：Score、Summary、日历、rollup |
| `projects/<slug>/.ai-factory/00-intake/core-feature-ledger.md` | P0/P1 truth; sync Priority column from RICE rank |

Create `priority-intake-backlog.md` and `priority-intake-backlog.items.csv` on first intake if missing. Use templates in [reference.md](reference.md).

**维护规则**：只改 `.md`（原始字段）；改完后运行 `build_html.py` 刷新 HTML。**禁止**在 md 写入 RICE/Score/Summary；**禁止**手改 `.html`。

## Viewing the backlog

**看有哪些任务**

1. **CSV + Markdown（源文件）** — `.items.csv` 为 Items 表格；`.md` 为决策；**无 Summary 表**。
2. **HTML（推荐浏览）** — `priority-intake-backlog.html`：**流程图**、**优先级**（build 生成 Summary）、**看板**、**日历**、**决策**；点击打开详情抽屉（含计算区）。

**生成 HTML**

```bash
python .cursor/skills/rice-priority-intake/scripts/build_html.py \
  projects/material-demand-dashboard/.ai-factory/00-intake/priority-intake-backlog.md
```

输出默认写到同目录 `priority-intake-backlog.html`。指定输出路径：

```bash
python .cursor/skills/rice-priority-intake/scripts/build_html.py path/to/backlog.md -o path/to/report.html
```

每次 intake 写完 `.md` 后，**应自动运行**上述脚本并告知用户 HTML 路径。用户可用浏览器或 `open_resource` 打开。

**不会单独再产一份 Word/PDF**；聊天里的「Priority Intake」回复是即时摘要，持久内容只在 `.md` + 生成的 `.html`。

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
- **Child re-estimates full parent Reach** — sibling Tasks each claim the same满额 Reach/Impact → child RICE inflates above parent
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
- [ ] Step 2: Classify level + parents
- [ ] Step 3: RICE interview
- [ ] Step 4: Score + multi-parent attribution (compute in reply / build — **not** in md)
- [ ] Step 4.5: Normalize (Score = norm × 100 — **build only**)
- [ ] Step 5: Write backlog row (**raw fields only**)
- [ ] Step 5.5: Schedule (optional — `start_date` or `end_date`)
- [ ] Step 6: Run build_html + recommend from HTML Summary
- [ ] Step 7: Sync core-feature-ledger if applicable
```

### Step 1: Parse requirement

Extract: title, type (Epic/Feature/Story/Task/Bug/Chore), user outcome, affected surfaces, P0/P1 hint, dependencies, requester urgency.

### Step 2: Classify level + parents

Ask when unclear:

1. **Level** — Epic / Feature / Story / Task?
2. **Parents** — zero, one, or many? List each parent ID from the backlog.
3. **If multiple parents** — value split (must sum to 100%): e.g. 60% dashboard, 40% export.

Rules:

- Shared platform/API work → usually **Task** or **Story** with **multi-parent links**.
- User-facing capability → **Feature** or **Story** under one primary Epic.
- Strategic theme → **Epic**.

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
- Assign `impact_slice` per sibling so Σ slice ≤ 1; Reach typically inherits parent满额 (same users).
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

Single parent 100% + slice 0.4 → `norm = norm(parent) × 0.4` → **guaranteed ≤ parent**.

All of Step 4–4.5 runs in **`build_html.py`** and intake chat replies — **never persisted in md**.

### Step 5: Write backlog row (raw only)

Append one CSV row to `priority-intake-backlog.items.csv` using [reference.md](reference.md) column template. Update decisions in `.md` when needed.

**Root item** (no `parent_links`): `Level`, `Status`, `Reach`, `Impact`, `Confidence`, `Effort`, `Blocks`, `Blocked_by`, `Ledger_ref`, `Notes`, optional `start_date` or `end_date`.

**Child item** (has `parent_links`): `Level`, `Status`, `Confidence`, `Effort`, `impact_slice`, `Parent_links`, `Blocks`, `Blocked_by`, `Notes`, optional schedule — **omit** `Reach`/`Impact`.

**Forbidden in csv/md**: `RICE`, `RICE_norm`, `Score`, `Effective_RICE`, `Reach_source`, `Impact_source`, `## Summary` table.

ID pattern: `RICE-<LEVEL>-<NNN>`.

### Step 5.5: Schedule (optional)

Ask: need calendar? **start date** or **deadline**?

| Rule | Detail |
|---|---|
| Anchor | Set **only** `start_date` **or** `end_date` (`YYYY-MM-DD`), not both |
| `start_date` | Must have parseable `Effort` (person-days) |
| `end_date` | `Effort` optional — milestone if omitted; range if present |
| No dates | Item omitted from calendar; listed under「未排期」 |

Calendar span computed by build (natural days). See reference.

### Step 6: Re-rank + recommend

1. Run `build_html.py`; read **HTML** Summary (Score descending).
2. Sibling Tasks: raw RICE from build (implementation order).
3. Prefer **ready** leaf Tasks; calendar for timeboxed work.
4. Top 5 actionable in chat reply (may cite computed Score).
5. Confirm md has **no computed columns** before finishing.

### Step 7: Sync ledger

If item maps to `core-feature-ledger.md`:

- Set `Priority` column to P0/P1/P2 from RICE band (reference) **or** keep explicit P0 and note RICE rank in Notes.
- Never downgrade P0 without explicit user approval (AI Product Factory rule).

## Response format

After each intake, reply with:

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
