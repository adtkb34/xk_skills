# Changelog

All notable changes to **rice-priority-intake** are documented here.

Format based on [Keep a Changelog](https://keepachangelog.com/en/1.1.0/).

## [1.0.0] - 2026-06-28

Initial release.

### Added

- Confirm-first RICE priority intake: one user request → one backlog item by default.
- Backlog layout under `docs/backlog/`: `.md` (decisions only), `.items.csv`, `.executions.csv`, generated `.html`.
- `build_html.py`: RICE / Score / Summary, flow chart, kanban, calendar, multi-parent attribution rollup.
- `build_html.py --serve` and `backlog_server.py`: browser editor that saves items and executions to CSV.
- Dashboard form widgets: Tom Select, Flatpickr, Treeselect parent tree.
- Effort model: numeric **days** in CSV; UI input in days / weeks / months with level-based defaults (7 days/week, 30 days/month).
- English-only skill docs and dashboard UI.
- Directory-only CLI: `build_html.py docs/backlog` (not a `.md` file path).
- Calendar chips: `time + title` on one line, CSS ellipsis when overflow.

[1.0.0]: https://github.com/adtkb34/xk_skills/releases/tag/v1.0.0
