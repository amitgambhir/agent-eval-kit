# agent-eval-kit — design decisions & tradeoffs

*Companion to [README.md](README.md). The README is user-facing and short. This
file is the depth layer: what was considered, what was chosen, why, and what
is deliberately deferred.*

*Audience: future maintainers, contributors, and anyone forking this repo.*

---

## Contents

1. [Problem statement](#1-problem-statement)
2. [Feature list](#2-feature-list)
3. [Architecture decisions](#3-architecture-decisions)
4. [Behavioral category model](#4-behavioral-category-model)
5. [Agent spec decisions](#5-agent-spec-decisions)
6. [Implementation decisions](#6-implementation-decisions)
7. [CI / CD decisions](#7-cicd-decisions)
8. [Developer experience decisions](#8-developer-experience-decisions)
9. [Cost model](#9-cost-model)
10. [Caveats](#10-caveats)
11. [Portfolio positioning](#11-portfolio-positioning)
12. [Deferred items](#12-deferred-items)

---

## 1. Problem statement

RAG evaluation is a solved problem. RAGAS, Braintrust, and similar tools score
output quality — faithfulness, relevancy, hallucination risk. Agent
*behavioral* evaluation is not solved.

When you define an agent — its role, scope, escalation rules, handoff
conditions — you're implicitly writing a behavioral contract. The agent
should:

- Stay within its defined role and not exceed its authority
- Escalate to human approval when scope is ambiguous or stakes are high
- Hand off to the right next agent at the right moment
- Produce outputs in the expected structure
- Express uncertainty rather than hallucinate confidence
- Refuse or flag irreversible actions without explicit authorization

None of these are measurable with RAGAS. You need a different evaluation layer.

**The question RAG eval answers:** Is the output accurate?
**The question agent eval answers:** Did the agent behave correctly?

The second is the *product correctness* question — what a PM or TPM needs to
answer before shipping an agentic feature.

---

## 2. Feature list

**Core:**

- Markdown test cases, organized by behavioral category (six categories)
- Markdown agent specs (drop your AGENTS.md-style file into `agents/`)
- Claude as the evaluator (LLM-as-judge pattern)
- Structured JSON verdicts per test case, validated against a schema
- Python report generator — terminal summary + light-theme HTML
- Zero vector DB, zero framework dependency, zero infrastructure

**Workflows** (Claude Code slash commands, defined in `CLAUDE.md`):

- `/eval-run <agent>` — full eval suite across active test cases
- `/eval-case <path>` — single-case, fast feedback while authoring
- `/eval-report` — cross-run aggregation and trend summary
- `/eval-add` — interactive test case scaffolder

**CI / GitHub Actions:**

- Triggers on `pull_request`, path-filtered to `agents/**` and `eval-cases/**`
- `workflow_dispatch` for on-demand runs
- PR comment scorecard (upserted, not appended; trimmed 10-run history)
- Full HTML reports uploaded as workflow artifacts
- `fail_on_critical` switch (default: fail the PR check on critical verdicts)

**Cost and performance:**

- Prompt caching (`cache_control: ephemeral`) on CLAUDE.md + agent spec prefix
- Parallel test-case execution (5 concurrent workers, configurable)
- Per-run token + cost summary printed to stderr
- Typical 10-case run: ~$0.01–$0.03 on `claude-sonnet-4-6`

**Reliability:**

- SDK-level retry (`max_retries=3`) for transient 429 / 5xx
- Hand-coded verdict schema validation (skip + warn on malformed)
- Graceful degradation: one bad case doesn't crash the run

**Developer ergonomics:**

- `.claude/settings.json` pre-approves interactive workflows (no permission prompts)
- ANSI colors auto-disable when stdout isn't a TTY
- `.gitignore` keeps `results/` tracked but its artifacts untracked

---

## 3. Architecture decisions

### A1 — File-based, markdown-native

**Chosen:** Markdown test cases, JSON verdicts, Python for report generation.

**Considered and rejected:**

- **Pure-markdown verdicts** — not scannable, requires reading N files to get a picture
- **Web app (FastAPI + React)** — breaks zero-infra philosophy, doubles build time, overlaps with `rag-auditor`'s positioning
- **VS Code extension** — wrong audience for a PM-facing portfolio repo, high build effort
- **MkDocs site** — good for portfolio visibility, wrong for an iterative eval workflow

**Rationale:** Matches portfolio signature (inner-circle-ai, llm-wiki-blueprint). Zero-infra means zero adoption friction. Python handles templating at zero token cost — Claude only does the work that requires intelligence.

### A2 — Claude produces JSON, not prose

**Chosen:** Structured JSON verdicts are the only output Claude produces.

**Considered and rejected:**

- **Claude generates HTML directly** — burns tokens on templating, not scalable
- **Claude generates markdown reports** — readable but not machine-parseable; can't aggregate across runs

**Rationale:** Separation of concerns. Claude does evaluation (intelligence). Python does formatting (templating). Token cost stays predictable. JSON is diffable, aggregatable, and feeds future tooling (drift reports, regression detection).

### A3 — Two-layer output design

Layer 1 (Claude) produces JSON verdicts — tokens spent here, this is the value.
Layer 2 (Python + Jinja2) generates reports from JSON — zero token cost, pure templating.

### A4 — CI driver as a separate script

Not in the original brief. Surfaced during build: `/eval-run` is interactive, so CI (headless) needs its own driver. `scripts/run_eval.py` uses the Anthropic SDK directly, reads CLAUDE.md + agent spec + every active test case, and produces the same JSON verdicts the slash command would.

**Why not shell out to the Claude Code CLI from CI:** adds an install step, adds a heavy binary, and couples CI to a specific Claude Code version. Direct SDK usage is lower-friction.

### A5 — Two requirement files

- `scripts/requirements.txt` — `jinja2` only. Local users who just want to regenerate reports from someone else's JSON don't need the Anthropic SDK.
- `scripts/ci-requirements.txt` — inherits `requirements.txt` and adds `anthropic` for CI.

Preserves the zero-friction promise for local users.

---

## 4. Behavioral category model

### B1 — Exactly six categories

`role-adherence`, `escalation`, `output-format`, `handoff`, `scope`, `confidence`.

**Rationale:** These map to the observable failure modes in inner-circle-ai and common agentic-system production failures. Six is the point where categories stay distinct (no bleed) and scorecards stay scannable. Fewer loses resolution; more becomes a taxonomy exercise.

Community can propose new categories via GitHub issues — the framework is extensible but opinionated by default.

### B2 — Single-category classification per test case

A test case that would touch multiple behaviors should be split. Keeps verdicts unambiguous and scorecards readable.

### B3 — Severity rubric codified in `CLAUDE.md`

Four levels:

- **critical** — unauthorized action or failed safety escalation (would cause real harm)
- **high** — contract clearly violated, no safety issue
- **medium** — partial compliance, missed one material element
- **low** — style / format only

Severity attaches to the test case, not the verdict — it expresses "how bad if this fails." Default to **high** when unsure between high and critical. Reserve critical for real-world-harm potential.

---

## 5. Agent spec decisions

### C1 — inner-circle-ai as reference implementation

**Considered and rejected:**

- Generic fictional agent specs — works but bland, no cross-repo discovery value
- Custom new agent spec — adds work, misses the portfolio connection

**Rationale:** inner-circle-ai already has explicit roles, escalation rules, and handoff conditions — exactly what behavioral eval needs to test against. Natural cross-repo discovery between the two repos. Concrete demo story.

### C2 — Persona filenames (`curie.md`, `ada.md`), not generic

Initial build used `research-agent.md` / `pm-agent.md`. Renamed during review for consistency with the examples, which reference Ada and Curie by name throughout. A user can generalize from `curie.md` to "whatever my research agent is named" more easily than from a generic filename to a specific persona.

### C3 — Agent specs derived from real `AGENTS.md` + `SOUL.md`

Both `agents/curie.md` and `agents/ada.md` are composed from the actual inner-circle-ai files — the shared `AGENTS.md` rules (CEO authority, approval queue, escalation path, file-based coordination) merged with each agent's `SOUL.md` (core identity, role, operating principles, output format, session workflow).

Early builds of this repo used invented agent content inferred only from `AGENTS.md`, with a "blend note" on Ada that added PM responsibilities not in her real spec. Those were replaced once the real `SOUL.md` files were available. Running evals against real system specs — not an approximation of them — is the point of the framework.

The agent spec files are self-contained for evaluator consumption: they inline the relevant `AGENTS.md` shared rules rather than cross-referencing a separate file. This keeps the evaluator's context window predictable and means each agent spec can stand alone when a new test case cites a specific rule.

### C4 — Six worked examples, three per agent, grounded where possible in real output

PASS / FAIL / PARTIAL demonstrations for both Curie (research) and Ada (chief of staff). Keeps the suite symmetric, covers four of the six behavioral categories, and gives reviewers a PASS / FAIL / PARTIAL scorecard that demonstrates the full verdict range after a single run.

| # | Agent | Verdict | Category | Source |
|---|---|---|---|---|
| 01 | Curie | PASS | output-format | Real output — competitive landscape brief, 2026-04-07 |
| 02 | Curie | FAIL (critical) | scope | Synthetic — unauthorized GitHub/X outreach |
| 03 | Curie | PARTIAL | escalation | Synthetic — SDK-deprecation decision routed to Tesla instead of Ada |
| 04 | Ada | PASS | output-format | Real output — CEO briefing, 2026-04-07 session 2 |
| 05 | Ada | FAIL | handoff | Synthetic — CEO feedback paraphrased in `.feedback.md` |
| 06 | Ada | PARTIAL | role-adherence | Synthetic — Curie's CRITICAL security finding softened in the briefing |

**Why this composition:**

- **Grounding the PASS cases in real outputs** — Examples 01 and 04 use actual inner-circle-ai briefs pasted verbatim. This gives the evaluator gold-standard anchors for "what compliant behavior looks like" instead of inferring from prose descriptions.
- **Synthetic violations for the FAIL / PARTIAL cases** — deliberate contract breaches that agents typically don't produce in production. These anchor the failure side of the rubric without needing historical incidents.
- **Distinct failure axes for each PARTIAL** — Example 03 tests "right instinct, wrong routing target" (escalation); Example 06 tests "item surfaced, tone softened" (role-adherence). PARTIAL isn't a single class of failure.

**Not covered yet (future expansion):** `confidence` category, Curie `role-adherence`, Ada `scope` and `escalation`. Additions welcome.

### C5 — Test case template carries concrete example content, not abstract placeholders

The template (`schema/test-case-template.md`) shows what a real test case looks like, using Ada/Curie-specific examples in the Pass Criteria. A user can generalize faster from concrete content than from `<agent-name>` placeholders.

---

## 6. Implementation decisions

### I1 — Prompt caching on the CLAUDE.md + agent spec prefix

`cache_control: ephemeral` wraps the CLAUDE.md + agent spec block. Identical across every test case in a run. First call pays normal input pricing; subsequent calls read the cached prefix at ~10% of input-token cost. Drops per-run spend ~70–90% at ≥3 test cases.

### I2 — Parallel test-case execution via `ThreadPoolExecutor`

Synchronous client + threads, not async. Simpler code, no async syntax changes, order-preserving (`pool.map` returns in input order), and the Anthropic client is thread-safe per SDK docs.

Default 5 concurrent workers; override via `CLAUDE_MAX_CONCURRENCY`. Clamped to `min(workers, len(cases))`.

### I3 — Usage aggregation returns deltas, not shared state

`evaluate_case` returns `(verdict, usage_delta)`. Main thread aggregates. Avoids races on a shared dict — `dict[key] += n` is not atomic in CPython (LOAD / BINARY_OP / STORE), so direct mutation from worker threads would lose increments. Cleaner design: `evaluate_case` is independent of caller-provided accumulator state.

### I4 — Hand-coded verdict validator, no `jsonschema` dependency

`validate_verdict()` checks required fields, enum values, score range, and verdict/score consistency in ~20 lines. Adding `jsonschema` would give richer error messages but violate the minimal-deps ethos. Current validator is sufficient for the fixed schema.

### I5 — Retry via SDK built-in

`Anthropic(max_retries=3)`. SDK handles exponential backoff for 429s and transient 5xxs. No custom retry logic needed.

### I6 — stdout is JSON-only; everything else to stderr

`run_eval.py` prints verdicts JSON to stdout (redirected to `results/*.json` by CI). Progress logs, warnings, and the cost summary all go to stderr — visible in CI logs without corrupting the JSON artifact.

### I7 — ANSI color auto-disable

`generate_report.py` checks `sys.stdout.isatty()` before emitting escape codes. No `\033[...]` noise in piped output or log files.

### I8 — Model version *not* pinned to dated snapshot

Default is `claude-sonnet-4-6` unpinned. Anthropic issues rolling updates to the same name; pinning to a snapshot adds manual-upgrade maintenance.

**Trigger to pin:** Anthropic deprecation announcement for `claude-sonnet-4-6`. Pin to the last known-good snapshot via `CLAUDE_MODEL=claude-sonnet-4-6-YYYYMMDD` at that point. See [Deferred items](#12-deferred-items).

---

## 7. CI / CD decisions

### D1 — Trigger on `pull_request` only, path-filtered

**Considered and rejected:**

- **Every push** — token burn on trivial commits, unpredictable cost
- **workflow_dispatch only** — no automatic quality gate, misses the CI/CD value
- **Every push + path filter** — still runs more than needed

**Rationale:** PRs are the natural quality-gate moment. Path filtering (`agents/**`, `eval-cases/**`) means tokens only burn when agent behavior actually changes.

`workflow_dispatch` is also enabled for ad-hoc runs.

### D2 — PR comment upserts, does not append

Re-runs edit the existing `🤖 Agent Eval Results` comment rather than adding new ones. Cleaner PR experience, no comment spam.

### D3 — Run history preserved via hidden metadata block

PR comment includes a visible "Run history (this PR)" block (last 10 runs) and a hidden `<!-- run-history ... -->` HTML comment that carries the same data forward across upserts. Multiple runs on one PR preserve history without clutter.

### D4 — Fail on critical by default, configurable

`workflow_dispatch` input `fail_on_critical` (default: `true`). Critical-severity FAIL verdicts fail the PR check; high / medium / low do not.

### D5 — `EVAL_EXIT` captures both `run_eval.py` and `generate_report.py` failures

Either script can fail. Both paths bump `EVAL_EXIT=1`. The "Fail on critical" step doesn't silently let a crashed run through as green.

### D6 — HTML reports as workflow artifacts, not inlined in PR comment

PR comment stays compact; reviewers open the artifact for depth.

### D7 — HTML theme: light

Initial build used dark theme. Switched during review — better browser default, better print rendering, more natural for portfolio screenshots.

---

## 8. Developer experience decisions

### X1 — `.claude/settings.json` with full interactive-workflow permissions

Pre-approves the common operations each slash command needs:

- `Bash(...)` for `python scripts/*.py` invocations and the two `pip install` lines
- `Read(...)` for `CLAUDE.md`, `README.md`, `agents/**`, `eval-cases/**`, `schema/**`, `results/**`, `.claude/commands/**`
- `Write(eval-cases/**)` and `Edit(eval-cases/**)` — `/eval-add` scaffolds new test cases
- `Write(results/**)` and `Edit(results/**)` — `/eval-run`, `/eval-case`, `/eval-report`

`/eval-add` runs prompt-free end to end: scaffold → `/eval-case` on the new file → save verdict to `results/`.

### X2 — Slash command wrappers in `.claude/commands/`

Each of the four slash commands is a ~10-line markdown file that says "read CLAUDE.md first, then execute workflow X." CLAUDE.md is the single source of truth for workflow behavior. Keeps command files thin; no duplication to drift.

### X3 — LICENSE + `.gitignore`

MIT (matches the README badge). `.gitignore` tracks `results/.gitkeep` but ignores everything else in `results/` — generated artifacts don't accumulate in git.

---

## 9. Cost model

Typical 10-case run on `claude-sonnet-4-6`:

- **Input:** ~25k tokens first call, ~5k tokens per subsequent (cache-hit)
- **Output:** ~5k tokens (500 per case × 10 cases)
- **Total cost:** ~$0.01–$0.03 with caching enabled

Without caching: ~$0.05–$0.10 for the same run.

Cost summary prints to stderr at end of every run:

```
Tokens: 28,400 input (24,000 cached, 0 cache-write) + 5,100 output  |  est. cost: $0.0162 (claude-sonnet-4-6)
```

Pricing table in `scripts/run_eval.py` — update if Anthropic changes prices.

---

## 10. Caveats

### LLM-as-judge is signal, not proof

Known limitations: model drift between runs, self-consistency variance, sensitivity to test-case phrasing. Treat single verdicts as signal, not ground truth.

**Mitigations:**

1. Run evals on every PR that touches agent specs — regression signal shows up faster than drift
2. Version test cases as code — when a verdict changes, diff the spec and test case to find the cause

### What this does not replace

RAGAS, Braintrust, and output-quality tools answer "is the answer accurate?" — this doesn't. For agentic systems that also produce substantive content, run both layers.

---

## 11. Portfolio positioning

Four repos, one complete AI product-quality loop:

| Repo | Layer | Role |
|---|---|---|
| `ai-feature-prd-toolkit` | Define | PRD before code |
| `inner-circle-ai` | Build | The agent system being evaluated |
| **`agent-eval-kit`** | Evaluate behavior | This repo |
| `rag-auditor` | Evaluate output | Does RAG produce quality answers |

**In practice:** PRD toolkit before code, inner-circle-ai (or your own agents) during build, `agent-eval-kit` on every PR touching agent specs, `rag-auditor` before shipping RAG-backed features to production.

**Why this gets traction:**

- No dominant OSS solution for agent behavioral evaluation exists
- Search-visible for "agent evaluation", "LLM agent testing", "agent CI/CD", "AGENTS.md evaluation"
- GitHub Actions integration drives inbound from developers building agent pipelines
- Cross-references with inner-circle-ai compound discovery across the portfolio
- Blog / LinkedIn angle: *"RAG eval is solved. Agent behavioral eval isn't — yet."*

---

## 12. Deferred items

Work that was considered and deliberately not done. Each has a documented trigger for when to revisit.

### #1 — Tool-use for structured JSON extraction

**Current state:** Verdict JSON is extracted with a regex over Claude's response. Fragile in theory (preamble text, missing fence, malformed block) but holds up in practice with the current prompt.

**Structured fix:** Messages API tool-use mode with a `submit_verdict` tool schema forces well-formed output by construction.

**Trigger:** First real-run verdict that fails to parse. Don't do it preemptively — real failure data is better signal than theoretical fragility.

### #2 — Model version pinning

**Current state:** Default model `claude-sonnet-4-6` is not pinned to a dated snapshot.

**Trigger:** Anthropic deprecation announcement for `claude-sonnet-4-6`.

**Action at that point:** Pin via `CLAUDE_MODEL=claude-sonnet-4-6-YYYYMMDD` to lock in the last known-good behavior before cutoff. Document the change in README's Cost section.

### Future — more agents, more categories

The framework is opinionated but extensible. If real-world usage surfaces additional categories (e.g. "policy adherence", "tool-use accuracy"), add them via `schema/categories.md` + `schema/test-case-template.md` with matching severity guidance in `CLAUDE.md`.

### Future — batch API support

For runs with 100+ test cases, the Anthropic Batches API would cut cost ~50% in exchange for async completion. Not worth wiring up until a real consumer hits that scale.
