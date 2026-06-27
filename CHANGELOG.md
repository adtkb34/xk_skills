# Changelog

All notable changes to this repository are documented here.

Format based on [Keep a Changelog](https://keepachangelog.com/en/1.1.0/).

## [1.0.0] - 2026-06-28

Initial release of **rice-priority-intake**.

### Added

- RICE priority intake skill: confirm-first workflow, one request → one backlog item by default.
- Backlog artifacts under `docs/backlog/`: `.md` (decisions), `.items.csv`, `.executions.csv`, generated `.html`.
- `build_html.py`: RICE / Score / Summary, flow chart, kanban, calendar, multi-parent attribution rollup.
- `build_html.py --serve`: local dashboard editor with CSV save (`backlog_server.py`).
- HTML UI: Tom Select, Flatpickr, Treeselect (parent tree); add items and executions from the browser.
- Effort schema: numeric **days** in CSV; UI accepts days / weeks / months with level-based defaults (7 days/week, 30 days/month).

### Changed

- Skill docs and dashboard UI are English-only.
- `build_html` accepts a backlog **directory** only (not a `.md` file path).
- Calendar chips show `time + title` with CSS ellipsis overflow.

### Removed

- Backward-compatibility paths: items-in-md parsing, Chinese md headers, `person-*` effort strings, legacy effort unit parsing.

[1.0.0]: https://github.com/adtkb34/xk_skills/releases/tag/v1.0.0
