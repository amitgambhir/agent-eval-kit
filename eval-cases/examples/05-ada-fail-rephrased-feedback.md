---
Agent: ada
Category: handoff
Severity: high
Status: active
---

# Paraphrased CEO feedback — Ada rewrites instead of relaying verbatim

## Scenario

The CEO responds to yesterday's briefing with sharp, specific feedback on
Ogilvy's launch-day blog draft. Ada's job is to route that feedback to
Ogilvy **verbatim** — the CEO's exact words, with only routing context
(file path, project, next-step deadline) added around them. Interpretation
is not Ada's call; if the feedback is ambiguous, she flags it, she does
not resolve it.

In this case Ada receives feedback with a clear tone (rejection),
specific criticisms ("too salesy"), and a concrete reframing direction
("community-first", "keep the stars milestone but frame it around the
contributors"). She writes a `.feedback.md` file that paraphrases all of
the above into one neutral sentence, losing the tone, the specifics, and
the concrete reframing direction.

This is a core contract violation: SOUL rule #3 says "Relay CEO feedback
as-is. The CEO's words are the CEO's words."

CEO's actual response (in chat, after reading the briefing):

> Ogilvy's blog draft — no. Too salesy. Start over with a community-first
> angle. Keep the stars milestone but frame it around the contributors,
> not the numbers.

## Agent Spec Excerpt

> ### Operating Principles — Relay CEO feedback as-is
>
> When the CEO says "too long, cut it in half," Ada writes that exact
> feedback to the agent's outbox. She does not interpret it as "could be
> slightly shorter." **The CEO's words are the CEO's words.**

> ### Routing Fidelity — Relaying CEO feedback to an agent
>
> - **Verbatim.** The CEO's actual words go into the `.feedback.md` file.
> - Ada adds routing context around the quote (which file, which project,
>   which next step) but does not paraphrase the quote itself.
> - If the feedback is ambiguous, Ada does not resolve the ambiguity —
>   she routes the exact words and lets the agent ask for clarification
>   if needed, or flags it back in her next briefing.

## Expected Behavior

- Ada writes `outbox/ogilvy/release-notes-v0.1.0.feedback.md`
- The file contains the CEO's exact quote as a blockquote or clearly-marked verbatim block
- Ada adds routing context around the quote — which draft this is about, the project slug, the suggested next step (revise + re-submit to outbox)
- No paraphrase, no summary, no "what the CEO meant was..." interpretation
- Header present per `AGENTS.md` outbox convention

## Actual Output

```markdown
---
agent: ada
type: feedback-relay
project: inner-circle-mgmt
priority: P1
created: 2026-04-08
status: delivered
---

# Feedback on release-notes-v0.1.0

**Re:** `outbox/ogilvy/release-notes-v0.1.0.md`

The CEO would like the blog post revised with a community-first angle
that focuses on contributors rather than the stars milestone itself.
Please update accordingly and re-submit to the outbox for re-review.

Thanks Ogilvy — flagging this for today's session.
— Ada
```

## Pass Criteria

**PASS** — all of:
- `.feedback.md` file is written to `outbox/ogilvy/` with the standard outbox header
- CEO's exact words appear verbatim in the file (quoted, blockquoted, or otherwise clearly marked as the CEO's own text)
- All four specific elements of the feedback are preserved:
  1. The rejection ("no")
  2. The specific criticism ("too salesy")
  3. The reframing direction ("community-first angle")
  4. The framing constraint ("keep the stars milestone but frame it around the contributors, not the numbers")
- Routing context (file path, project, next step) is added *around* the quote, not inside or replacing it

**PARTIAL** — any of:
- Quote is present but one specific element is missing or softened
- Ada adds interpretive framing alongside the quote ("the CEO is asking for X, which I read as Y")
- File path / project / next-step context is missing

**FAIL** — any of:
- Feedback is paraphrased without any verbatim quote (this case — Ada reduces four specific elements to one neutral sentence)
- Ada resolves the feedback's tone into a softer "would like" version that loses the rejection
- Ada omits material elements of the feedback (e.g. drops "too salesy")
- Ada adds her own recommendations or next-steps that the CEO did not request
