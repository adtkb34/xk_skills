# RICE Priority Intake — Examples

## Example A: Single parent 100% (计划订单 Story → Task)

### User request

> 创建采购申请改成创建计划订单。

### Step 2 classification

| Field | Value |
| --- | --- |
| Level | Task |
| Parents | `RICE-STORY-001:100%` |
| Siblings | TASK-005 (前端), TASK-006 (清逻辑), TASK-004 (MES) — impact slices 0.4 / 0.35 / 0.25 |

### Parent scores (already in backlog)

`RICE-STORY-001`: Reach=120, Impact=2, Confidence=80%, Effort=6 → **RICE=32**

### Step 3 interview (child with parent — no full Reach/Impact)

| Q | A |
| --- | --- |
| impact_slice | 0.4 — 前端入口与配置占 Story 价值约 40% |
| Confidence | 90% — UI pattern exists |
| Effort | 2 person-days |
| Blocked by | — |

Schedule via `.executions.csv` (multiple runs):

```csv
id,task_id,start_date,end_date,status,notes
EXEC-005-1,RICE-TASK-005,2026-07-01,,pending,首轮开发
EXEC-005-2,RICE-TASK-005,2026-07-08,,pending,联调重试
```

### Raw CSV row (persisted — item definition only)

```csv
RICE-TASK-005,计划订单：前端入口/弹窗/配置,Task,ready,,,90%,2 person-days,0.4,RICE-STORY-001:100%,,,,,,"…"
```

### After build_html (HTML only — not in md)

```
Reach_c  = 120 × 100% = 120
Impact_c = 2 × 100% × 0.4 = 0.8
RICE_c   = (120 × 0.8 × 0.9) / 2 = 43.2

contribution → STORY-001 = 43.2 × 100% = 43.2

RICE_norm = 1.0 × 100% × 0.4 = 0.4 → Score = 40
Calendar: EXEC-005-1 → 2026-07-01 … 2026-07-02; EXEC-005-2 → 2026-07-08 … 2026-07-09 (2 person-days each)
```

### Why Task Score < Story Score

- **Score** (display): Story **100**, Task-005 **40** — child always ≤ parent.
- **RICE raw**: Task 43.2 vs Story 32 — use only for sibling Task ordering, not cross-layer compare.
- Story **effective** raw = max(32, 43.2+50.4+6) ≈ 99.6 — audit for rollup only.

---

## Example B: Multi-parent 60/40 (物料聚合 API)

### User request

> 做一个物料聚合 API，同时给「多区域实时看板」和「历史报表导出」用。

### Step 2 classification

| Field | Value |
| --- | --- |
| Level | Task |
| Parents | `RICE-FEAT-010` 60%, `RICE-FEAT-011` 40% |

### Parent scores (hypothetical)

| Parent | Reach | Impact |
| --- | --- | --- |
| RICE-FEAT-010 多区域实时看板 | 480 | 2 |
| RICE-FEAT-011 历史报表导出 | 200 | 1 |

### Step 3 interview

| Q | A |
| --- | --- |
| Confidence | 80% — pattern exists in `demand-engine.ts` |
| Effort | 5 person-days |
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
| TASK-005 前端 | 0.4 | 2d | 43.2 | **40** |
| TASK-006 清逻辑 | 0.35 | 1.5d | 50.4 | **35** |
| TASK-004 MES | 0.25 | 3d | 6.0 | **25** |

Σ impact_slice = 1.0. Story Score = **100** (root max). Σ sibling Score = 100.

```
Story effective (raw) = max(32, 43.2 + 50.4 + 6.0) = 99.6
```

**Key**: `100%` in `parent_links` = full child RICE rolls up to parent; `impact_slice` = share of parent value for **Score** propagation.

---

## Example 2: New Feature intake (no parent_links)

### User request

> 总览页加「按供应商维度」缺料汇总。

### Classification

| Field | Value |
| --- | --- |
| Level | Feature |
| Parent | Epic: 物料风险可视化的深化 |
| Ledger | new P1 candidate |

### Interview (full — no parent_links on Feature scoring)

| Dimension | Value |
| --- | --- |
| Reach | 12 users × 20 sessions/q = 240 |
| Impact | 1 |
| Confidence | 50% — supplier dimension not in current API |
| Effort | 3 person-weeks = 15 person-days |

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
## Priority Intake: 物料聚合 API

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
1. RICE-TASK-003 物料聚合 API — Score 80 (raw 94.2)
2. RICE-FEAT-010 多区域实时看板 UI — 45 (after TASK-003)
3. RICE-FEAT-008 替换料批量配置 — 22
4. RICE-STORY-005 导出 CSV 列映射 — 18
5. RICE-FEAT-011 历史报表导出 — 15 (after TASK-003)

### Open questions
- 聚合 API 是否需按区域分片缓存？
```
