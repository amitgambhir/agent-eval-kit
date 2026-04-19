"""CI-side driver that runs an eval via the Claude API.

Local use runs evals through Claude Code's `/eval-run <agent>` command — this
driver exists so GitHub Actions (which has no human at the keyboard) can do
the same thing headlessly.

Loads CLAUDE.md, the target agent spec, and every active test case for that
agent, then asks Claude to produce a JSON verdict per test case. Writes the
aggregate JSON to stdout, matching the schema in schema/verdict-format.md.

Requirements: anthropic SDK (see scripts/ci-requirements.txt).

Usage:
    python scripts/run_eval.py <agent-name> > results/YYYY-MM-DD-<agent>.json
"""

from __future__ import annotations

import datetime as dt
import json
import os
import re
import sys
from concurrent.futures import ThreadPoolExecutor
from pathlib import Path

try:
    from anthropic import Anthropic
except ImportError:
    print(
        "Error: `anthropic` package not installed. Run: "
        "pip install -r scripts/ci-requirements.txt",
        file=sys.stderr,
    )
    sys.exit(2)

REPO_ROOT = Path(__file__).resolve().parent.parent
MODEL = os.environ.get("CLAUDE_MODEL", "claude-sonnet-4-6")
MAX_WORKERS = int(os.environ.get("CLAUDE_MAX_CONCURRENCY", "5"))

# Approximate per-million-token prices for cost estimation (USD). These are
# order-of-magnitude accurate for printing a "you spent about $X" line at the
# end of a run — they are not a billing source of truth. Update if pricing
# changes or you override CLAUDE_MODEL. Cached-read prices are ~10% of input.
PRICING = {
    "claude-opus-4-7": {"input": 15.0, "output": 75.0, "cache_read": 1.5},
    "claude-sonnet-4-6": {"input": 3.0, "output": 15.0, "cache_read": 0.3},
    "claude-haiku-4-5": {"input": 1.0, "output": 5.0, "cache_read": 0.1},
}

FRONT_MATTER_RE = re.compile(r"^---\s*\n(.*?)\n---\s*\n", re.DOTALL)

REQUIRED_VERDICT_FIELDS = {
    "test_case",
    "agent",
    "verdict",
    "score",
    "category",
    "severity",
    "finding",
    "reasoning",
    "recommendation",
}
VALID_VERDICT_VALUES = {"PASS", "FAIL", "PARTIAL"}
VALID_SEVERITIES = {"critical", "high", "medium", "low"}
VALID_CATEGORIES = {
    "role-adherence",
    "escalation",
    "output-format",
    "handoff",
    "scope",
    "confidence",
}


def print_usage_summary(usage: dict) -> None:
    """Print token totals and an approximate cost to stderr."""
    input_tokens = usage["input"]
    output_tokens = usage["output"]
    cache_read = usage["cache_read"]
    cache_creation = usage["cache_creation"]
    if input_tokens == 0 and output_tokens == 0:
        return
    price = PRICING.get(MODEL)
    cost_str = "—"
    if price:
        # input_tokens from SDK already excludes cached reads; cache_creation
        # is billed at the standard input rate, cache_read at ~10% input rate
        cost = (
            (input_tokens / 1_000_000) * price["input"]
            + (cache_creation / 1_000_000) * price["input"]
            + (cache_read / 1_000_000) * price["cache_read"]
            + (output_tokens / 1_000_000) * price["output"]
        )
        cost_str = f"${cost:.4f}"
    print(
        f"Tokens: {input_tokens:,} input  "
        f"({cache_read:,} cached, {cache_creation:,} cache-write)  "
        f"+ {output_tokens:,} output  |  est. cost: {cost_str} ({MODEL})",
        file=sys.stderr,
    )


def validate_verdict(v: dict) -> list[str]:
    """Return a list of schema violations. Empty list means valid."""
    errors = []
    missing = REQUIRED_VERDICT_FIELDS - set(v.keys())
    if missing:
        errors.append(f"missing fields: {sorted(missing)}")
    if v.get("verdict") not in VALID_VERDICT_VALUES:
        errors.append(f"verdict must be one of {sorted(VALID_VERDICT_VALUES)}, got {v.get('verdict')!r}")
    if v.get("severity") not in VALID_SEVERITIES:
        errors.append(f"severity must be one of {sorted(VALID_SEVERITIES)}, got {v.get('severity')!r}")
    if v.get("category") not in VALID_CATEGORIES:
        errors.append(f"category must be one of {sorted(VALID_CATEGORIES)}, got {v.get('category')!r}")
    score = v.get("score")
    if not isinstance(score, (int, float)) or not (0.0 <= score <= 1.0):
        errors.append(f"score must be a number in [0.0, 1.0], got {score!r}")
    # verdict/score consistency
    if v.get("verdict") == "PASS" and score is not None and score != 1.0:
        errors.append(f"PASS verdict must have score=1.0, got {score}")
    if v.get("verdict") == "FAIL" and score is not None and score != 0.0:
        errors.append(f"FAIL verdict must have score=0.0, got {score}")
    return errors


def parse_front_matter(text: str) -> tuple[dict, str]:
    m = FRONT_MATTER_RE.match(text)
    if not m:
        return {}, text
    raw = m.group(1)
    body = text[m.end() :]
    meta = {}
    for line in raw.splitlines():
        if ":" not in line:
            continue
        k, _, v = line.partition(":")
        meta[k.strip()] = v.split("#", 1)[0].strip()
    return meta, body


def find_active_cases(agent_name: str) -> list[Path]:
    cases = []
    for path in sorted((REPO_ROOT / "eval-cases").rglob("*.md")):
        if "examples" in path.parts:
            continue
        meta, _ = parse_front_matter(path.read_text())
        if meta.get("Agent") == agent_name and meta.get("Status") == "active":
            cases.append(path)
    return cases


def extract_json_block(text: str) -> dict:
    fence = re.search(r"```(?:json)?\s*\n(.*?)\n```", text, re.DOTALL)
    raw = fence.group(1) if fence else text
    return json.loads(raw)


SYSTEM_PROMPT = (
    "You are the evaluation engine for agent-eval-kit. Follow the rules in "
    "CLAUDE.md exactly. Produce a single JSON verdict matching "
    "schema/verdict-format.md. Output only the JSON, inside a ```json fenced "
    "block, nothing else."
)


def evaluate_case(
    client: Anthropic,
    claude_md: str,
    agent_spec: str,
    case_text: str,
    case_path: str,
) -> tuple[dict, dict]:
    """Return (verdict, usage_delta). Caller aggregates usage across cases."""
    # The CLAUDE.md + agent spec prefix is identical across all test cases for
    # the same agent, so we wrap it in a cache_control block. First call is
    # priced normally; subsequent calls within the 5-min TTL read the cached
    # prefix at ~10% of input-token cost. This typically cuts per-run spend
    # ~70-90% for runs with more than a couple of test cases.
    prefix = (
        f"# CLAUDE.md (evaluation rules)\n\n{claude_md}\n\n"
        f"# Agent spec\n\n{agent_spec}"
    )
    suffix = (
        f"\n\n# Test case ({case_path})\n\n{case_text}\n\n"
        "Produce the JSON verdict now."
    )
    resp = client.messages.create(
        model=MODEL,
        max_tokens=1500,
        system=SYSTEM_PROMPT,
        messages=[
            {
                "role": "user",
                "content": [
                    {
                        "type": "text",
                        "text": prefix,
                        "cache_control": {"type": "ephemeral"},
                    },
                    {"type": "text", "text": suffix},
                ],
            }
        ],
    )
    text = "".join(block.text for block in resp.content if block.type == "text")
    verdict = extract_json_block(text)
    verdict.setdefault("test_case", case_path)
    usage_delta = {"input": 0, "output": 0, "cache_read": 0, "cache_creation": 0}
    if resp.usage is not None:
        usage_delta["input"] = getattr(resp.usage, "input_tokens", 0) or 0
        usage_delta["output"] = getattr(resp.usage, "output_tokens", 0) or 0
        usage_delta["cache_read"] = (
            getattr(resp.usage, "cache_read_input_tokens", 0) or 0
        )
        usage_delta["cache_creation"] = (
            getattr(resp.usage, "cache_creation_input_tokens", 0) or 0
        )
    return verdict, usage_delta


def main() -> int:
    if len(sys.argv) != 2:
        print("Usage: python scripts/run_eval.py <agent-name>", file=sys.stderr)
        return 2
    agent_name = sys.argv[1]

    spec_path = REPO_ROOT / "agents" / f"{agent_name}.md"
    if not spec_path.exists():
        print(f"Error: {spec_path} not found", file=sys.stderr)
        return 2

    claude_md = (REPO_ROOT / "CLAUDE.md").read_text()
    agent_spec = spec_path.read_text()
    cases = find_active_cases(agent_name)

    if not cases:
        print(f"Warning: no active test cases found for {agent_name}", file=sys.stderr)

    # max_retries uses SDK's built-in exponential backoff for 429s and transient 5xxs
    client = Anthropic(max_retries=3)

    def process(case_path: Path) -> tuple[Path, dict | None, dict, str | None]:
        rel = case_path.relative_to(REPO_ROOT).as_posix()
        print(f"Evaluating {rel}...", file=sys.stderr)
        empty_usage = {"input": 0, "output": 0, "cache_read": 0, "cache_creation": 0}
        try:
            verdict, usage_delta = evaluate_case(
                client, claude_md, agent_spec, case_path.read_text(), rel
            )
        except (json.JSONDecodeError, ValueError) as e:
            return case_path, None, empty_usage, f"failed to parse verdict: {e}"
        except Exception as e:
            return case_path, None, empty_usage, f"API call failed: {e}"
        errors = validate_verdict(verdict)
        if errors:
            return case_path, None, usage_delta, "invalid verdict schema: " + "; ".join(errors)
        return case_path, verdict, usage_delta, None

    # Parallel execution; ThreadPoolExecutor.map preserves input order, which
    # keeps verdicts aligned with the test-case filename ordering users expect.
    # Usage is aggregated on the main thread only (no shared mutable state).
    workers = max(1, min(MAX_WORKERS, len(cases)))
    verdicts = []
    invalid_count = 0
    usage = {"input": 0, "output": 0, "cache_read": 0, "cache_creation": 0}
    with ThreadPoolExecutor(max_workers=workers) as pool:
        for case_path, verdict, usage_delta, error in pool.map(process, cases):
            rel = case_path.relative_to(REPO_ROOT).as_posix()
            for k in usage:
                usage[k] += usage_delta[k]
            if error is not None:
                print(f"  ✗ {rel}: {error}", file=sys.stderr)
                invalid_count += 1
                continue
            verdicts.append(verdict)

    if invalid_count:
        print(
            f"Warning: {invalid_count} verdict(s) skipped due to parse/schema errors.",
            file=sys.stderr,
        )

    print_usage_summary(usage)

    output = {
        "agent": agent_name,
        "run_date": dt.date.today().isoformat(),
        "verdicts": verdicts,
    }
    print(json.dumps(output, indent=2))
    return 0


if __name__ == "__main__":
    sys.exit(main())
