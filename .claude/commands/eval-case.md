# /eval-case &lt;filepath&gt;

Evaluate a single test case — fast feedback while authoring.

1. Read [CLAUDE.md](../../CLAUDE.md) in full before doing anything else.
2. Execute the **`/eval-case <filepath>`** workflow defined there.

Usage:

```
/eval-case eval-cases/scope/send-email-without-auth.md
```

Output: one JSON verdict printed to terminal. Claude will ask whether to
save it to `results/` and run the report generator.
