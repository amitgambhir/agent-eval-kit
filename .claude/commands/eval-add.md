# /eval-add

Interactive test case authoring. Claude walks you through the fields one at
a time and scaffolds a complete test case file in the right folder.

1. Read [CLAUDE.md](../../CLAUDE.md) in full before doing anything else.
2. Execute the **`/eval-add`** workflow defined there.

Claude will ask:
- Which agent?
- Scenario (one sentence)
- Expected behavior
- Actual output
- Category (one of 6)
- Severity (critical / high / medium / low)

Then scaffolds the file using [schema/test-case-template.md](../../schema/test-case-template.md),
sets `Status: active`, and asks whether to run `/eval-case` on it immediately.
