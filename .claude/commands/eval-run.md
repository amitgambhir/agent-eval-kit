# /eval-run &lt;agent-name&gt;

Run the full eval suite for one agent.

1. Read [CLAUDE.md](../../CLAUDE.md) in full before doing anything else — it
   defines the evaluation rules, verdict format, and severity guidelines you
   must follow.
2. Execute the **`/eval-run <agent-name>`** workflow defined there.

Usage:

```
/eval-run curie
```

Output: a JSON file at `results/YYYY-MM-DD-<agent-name>.json`.
Then the user runs `python scripts/generate_report.py results/<file>.json` to
produce the HTML report and terminal summary.
