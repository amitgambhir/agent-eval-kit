# /eval-report

Aggregate every JSON file in `results/` into a cross-run summary — pass rate
trends, per-category rates, critical failure list, recurring recommendation
themes.

1. Read [CLAUDE.md](../../CLAUDE.md) in full before doing anything else.
2. Execute the **`/eval-report`** workflow defined there.

Output: `results/summary-YYYY-MM-DD.md`.

This is a meta-report — it's how you track drift and regression patterns
across multiple runs. It does not replace `generate_report.py`, which
handles per-run HTML reports.
