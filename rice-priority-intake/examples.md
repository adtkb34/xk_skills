# RICE Priority Intake — Examples

## Example 0: Single task, no decomposition (default)

### User request

> Add an export button to the material dashboard — this is a task.

### Agent behavior

1. Default `Level = Task` from user's words — **do not** create Story/Epic parents or sibling Tasks.
2. Interview Reach / Impact / Confidence / Effort for this one item.
3. Show draft summary (Step 4.9) — **wait for Approve**.
4. After approval, append **one** row to `docs/backlog/priority-intake-backlog.items.csv`.

### Step 2 classification

| Field | Value |
| --- | --- |
| Level | Task |
| Parents | none (unless user links to an existing ID) |

### Draft CSV row (shown before write)

```csv
RICE-TASK-007,Material dashboard export button,Task,intake,24,1,80%,2,,,,,,"Write after user confirms"
```

### What NOT to do

- Do not create `RICE-STORY-…` + 3 sibling Tasks from this one sentence.
- Do not write to `.ai-factory/00-intake/` — use `docs/backlog/`.

---

## Example A: Single parent 100% (planned order Story → Task)

### User request

> Change "create purchase requisition" to "create planned order".

### Step 2 classification

| Field | Value |
| --- | --- |
| Level | Task |
| Parents | `RICE-STORY-001:100%` |
| Siblings | TASK-005 (frontend), TASK-006 (cleanup logic), TASK-004 (MES) — impact slices 0.4 / 0.35 / 0.25 |

> **Anti-pattern note**: The sibling list is **pre-existing backlog context** for this Story — not auto-created from one user message. A single request like "change create purchase requisition to create planned order" should produce **one** Task row (this one), not TASK-004/005/006 together.

### Parent scores (already in backlog)

`RICE-STORY-001`: Reach=120, Impact=2, Confidence=80%, Effort=6 → **RICE=32**

### Step 3 interview (child with parent — no full Reach/Impact)

| Q | A |
| --- | --- |
| impact_slice | 0.4 — frontend entry and config account for ~40% of Story value |
| Confidence | 90% — UI pattern exists |
| Effort | 2 (days) |
| Blocked by | — |

Schedule via `.executions.csv` (multiple runs):

```csv
id,task_id,start_date,end_date,status,notes
EXEC-005-1,RICE-TASK-005,2026-07-01,,pending,Initial development
EXEC-005-2,RICE-TASK-005,2026-07-08,,pending,Integration retry
```

### Raw CSV row (persisted — item definition only)

```csv
RICE-TASK-005,Planned order: frontend entry/modal/config,Task,ready,,,90%,2,0.4,RICE-STORY-001:100%,,,,,,"…"
```

### After build_html (HTML only — not in md)

```
Reach_c  = 120 × 100% = 120
Impact_c = 2 × 100% × 0.4 = 0.8
RICE_c   = (120 × 0.8 × 0.9) / 2 = 43.2

contribution → STORY-001 = 43.2 × 100% = 43.2

RICE_norm = 1.0 × 100% × 0.4 = 0.4 → Score = 40
Calendar: EXEC-005-1 → 2026-07-01 … 2026-07-02; EXEC-005-2 → 2026-07-08 … 2026-07-09 (2 days each)
```

### Why Task Score < Story Score

- **Score** (display): Story **100**, Task-005 **40** — child always ≤ parent.
- **RICE raw**: Task 43.2 vs Story 32 — use only for sibling Task ordering, not cross-layer compare.
- Story **effective** raw = max(32, 43.2+50.4+6) ≈ 99.6 — audit for rollup only.

---

## Example B: Multi-parent 60/40 (material aggregation API)

### User request

> Build a material aggregation API for both the multi-region live dashboard and historical report export.

### Step 2 classification

| Field | Value |
| --- | --- |
| Level | Task |
| Parents | `RICE-FEAT-010` 60%, `RICE-FEAT-011` 40% |

### Parent scores (hypothetical)

| Parent | Reach | Impact |
| --- | --- | --- |
| RICE-FEAT-010 Multi-region live dashboard | 480 | 2 |
| RICE-FEAT-011 Historical report export | 200 | 1 |

### Step 3 interview

| Q | A |
| --- | --- |
| Confidence | 80% — pattern exists in `demand-engine.ts` |
| Effort | 5 (days) |
| Blocked by | — |
| Blocks | both parent Features |

Reach/Impact **not** re-estimated — derived from parents.

### Step 4 score

```
Reach_c  = 480×0.6 + 200×0.4 = 368
Impact_c = 2×0.6 + 1×0.4 = 1.6
RICE_c   = (368 × 1.6 × 0.8) / 5 ≈ 94.2

Assume FEAT-010 norm=1.0, FEAT-011 norm=0.5 (hypothetical roots):
RICE_norm = 1.0×0.6 + 0.5×0.4 = 0.8 → Score = 80

Contributions:
  → FEAT-010: 94.2 × 0.6 ≈ 56.5
  → FEAT-011: 94.2 × 0.4 ≈ 37.7
```

| Field | Value |
| --- | --- |
| Reach_source | `FEAT-010:480×60% + FEAT-011:200×40%` |
| Impact_source | `FEAT-010:2×60% + FEAT-011:1×40%` |

**Contrast with old leaf-score model** (independent Reach=500, Impact=2 → RICE=160): inheritance weights Reach/Impact by each parent's actual scores; rollup coefficients unchanged.

### Step 6 recommendation

Ship **before** standalone UI polish on either Feature — shared Task ranks high among Tasks and raises both parents' rollup.

---

## Example C: Three sibling Tasks under one Story

Same parent `RICE-STORY-001` (Reach=120, Impact=2). Each Task has `parent_links: RICE-STORY-001:100%` (rollup weight), but **impact_slice** splits value:

| Task | impact_slice | Effort | RICE raw | Score |
| --- | --- | --- | --- | --- |
| TASK-005 Frontend | 0.4 | 2d | 43.2 | **40** |
| TASK-006 Cleanup logic | 0.35 | 1.5d | 50.4 | **35** |
| TASK-004 MES | 0.25 | 3d | 6.0 | **25** |

Σ impact_slice = 1.0. Story Score = **100** (root max). Σ sibling Score = 100.

```
Story effective (raw) = max(32, 43.2 + 50.4 + 6.0) = 99.6
```

**Key**: `100%` in `parent_links` = full child RICE rolls up to parent; `impact_slice` = share of parent value for **Score** propagation.

---

## Example 2: New Feature intake (no parent_links)

### User request

> Add a shortage summary by supplier dimension on the overview page.

### Classification

| Field | Value |
| --- | --- |
| Level | Feature |
| Parent | Epic: Deepening material risk visibility |
| Ledger | new P1 candidate |

### Interview (full — no parent_links on Feature scoring)

| Dimension | Value |
| --- | --- |
| Reach | 12 users × 20 sessions/q = 240 |
| Impact | 1 |
| Confidence | 50% — supplier dimension not in current API |
| Effort | 3 weeks → 21 days in CSV |

```
RICE = (240 × 1 × 0.5) / 15 = 8
```

### Recommendation

Queue after high-RICE Tasks that unblock P0 surfaces. Spike supplier data source (0.5–1 day) before committing — Confidence may rise to 80%.

---

## Example 3: P0 vs RICE conflict

### Situation

`P0-LATEST-001` implemented. New request: Kingdee live OPO sync (`P1-BACKEND-001`, deferred).

| Field | Value |
| --- | --- |
| RICE | (30 × 3 × 0.5) / 40 = 1.125 |

### Escalation output

Ledger says P1 but user previously deferred backend. RICE bottom quartile. **Ask user**: revive P1 now, keep deferred, or descope to read-only mock?

Do not auto-promote to P0 based on Impact alone.

---

## Example 4: Full intake response (multi-parent)

```markdown
## Priority Intake: Material aggregation API

**Level**: Task | **Score**: 80 | **RICE raw**: 94.2 | **Rank**: #1 among Task (by raw)

### Scorecard
| Reach | Impact | Confidence | Effort | RICE (raw) | Score |
| 368 (inherited) | 1.6 (inherited) | 80% | 5 pd | 94.2 | 80 |

### Inheritance
- Reach: FEAT-010:480×60% + FEAT-011:200×40% = 368
- Impact: FEAT-010:2×60% + FEAT-011:1×40% = 1.6

### Parents (rollup)
- RICE-FEAT-010 — 60% → 56.5
- RICE-FEAT-011 — 40% → 37.7

### Recommendation
Implement next: single API unblocks two Features; do not duplicate query logic in each UI.

### Updated top 5 (actionable)
1. RICE-TASK-003 Material aggregation API — Score 80 (raw 94.2)
2. RICE-FEAT-010 Multi-region live dashboard UI — 45 (after TASK-003)
3. RICE-FEAT-008 Substitute material batch config — 22
4. RICE-STORY-005 Export CSV column mapping — 18
5. RICE-FEAT-011 Historical report export — 15 (after TASK-003)

### Open questions
- Does the aggregation API need per-region sharded cache?
```
