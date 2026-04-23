"""Generate an HTML report and terminal summary from an eval results JSON file.

Usage:
    python scripts/generate_report.py results/<file>.json

Exits with code 1 if any verdict has severity=critical and verdict=FAIL — this
is the signal used by the CI workflow to fail a PR check.
"""

from __future__ import annotations

import json
import sys
from pathlib import Path

from jinja2 import Environment, FileSystemLoader, select_autoescape

REPO_ROOT = Path(__file__).resolve().parent.parent
TEMPLATE_DIR = REPO_ROOT / "schema"
TEMPLATE_NAME = "report-template.html"

CATEGORY_ORDER = [
    "role-adherence",
    "escalation",
    "output-format",
    "handoff",
    "scope",
    "confidence",
]

# ANSI color codes for terminal output — disabled when stdout isn't a tty
# (e.g. piped to a file or running in a CI log that doesn't interpret escapes)
if sys.stdout.isatty():
    RESET = "\033[0m"
    BOLD = "\033[1m"
    DIM = "\033[2m"
    GREEN = "\033[32m"
    YELLOW = "\033[33m"
    RED = "\033[31m"
    MAGENTA = "\033[35m"
    CYAN = "\033[36m"
else:
    RESET = BOLD = DIM = GREEN = YELLOW = RED = MAGENTA = CYAN = ""


def load_results(path: Path) -> dict:
    with path.open() as f:
        data = json.load(f)
    if "verdicts" not in data or "agent" not in data:
        raise ValueError(
            f"{path} is missing required top-level keys 'agent' and 'verdicts'. "
            "See schema/verdict-format.md."
        )
    return data


def summarize_by_category(verdicts: list[dict]) -> list[dict]:
    summary = []
    for cat in CATEGORY_ORDER:
        cat_verdicts = [v for v in verdicts if v.get("category") == cat]
        total = len(cat_verdicts)
        passed = sum(1 for v in cat_verdicts if v.get("verdict") == "PASS")
        has_critical = any(
            v.get("severity") == "critical" and v.get("verdict") == "FAIL"
            for v in cat_verdicts
        )
        summary.append(
            {
                "name": cat,
                "total": total,
                "passed": passed,
                "pct": round((passed / total) * 100) if total else 0,
                "has_critical": has_critical,
            }
        )
    return summary


def build_context(data: dict) -> dict:
    verdicts = data["verdicts"]
    total = len(verdicts)
    passed = sum(1 for v in verdicts if v.get("verdict") == "PASS")
    partial = sum(1 for v in verdicts if v.get("verdict") == "PARTIAL")
    failed = sum(1 for v in verdicts if v.get("verdict") == "FAIL")
    critical_failures = [
        v
        for v in verdicts
        if v.get("severity") == "critical" and v.get("verdict") == "FAIL"
    ]
    return {
        "agent": data["agent"],
        "run_date": data.get("run_date", ""),
        "total": total,
        "passed": passed,
        "partial": partial,
        "failed": failed,
        "critical": len(critical_failures),
        "pass_rate": round((passed / total) * 100) if total else 0,
        "categories": summarize_by_category(verdicts),
        "verdicts": verdicts,
        "critical_failures": critical_failures,
    }


def render_html(context: dict) -> str:
    env = Environment(
        loader=FileSystemLoader(str(TEMPLATE_DIR)),
        autoescape=select_autoescape(["html"]),
    )
    template = env.get_template(TEMPLATE_NAME)
    return template.render(**context)


def print_terminal_summary(ctx: dict) -> None:
    bar_width = 30
    filled = int(bar_width * ctx["pass_rate"] / 100) if ctx["total"] else 0
    bar = GREEN + "█" * filled + DIM + "░" * (bar_width - filled) + RESET

    print()
    print(f"{BOLD}Agent Eval — {ctx['agent']}{RESET}  {DIM}{ctx['run_date']}{RESET}")
    print(f"  {ctx['passed']}/{ctx['total']} pass  {bar}  {ctx['pass_rate']}%")
    print()

    print(f"{BOLD}Category{RESET}")
    for cat in ctx["categories"]:
        if cat["total"] == 0:
            line = f"  {cat['name']:<18} {DIM}—{RESET}"
        else:
            color = GREEN if cat["passed"] == cat["total"] else YELLOW
            if cat["has_critical"]:
                color = RED
            line = (
                f"  {cat['name']:<18} "
                f"{color}{cat['passed']}/{cat['total']}{RESET}  "
                f"{DIM}{cat['pct']}%{RESET}"
            )
            if cat["has_critical"]:
                line += f"  {MAGENTA}CRITICAL{RESET}"
        print(line)
    print()

    if ctx["critical_failures"]:
        print(f"{BOLD}{MAGENTA}Critical failures — review before merging{RESET}")
        for v in ctx["critical_failures"]:
            print(
                f"  {RED}✗{RESET} {CYAN}{v['category']}{RESET}  "
                f"{DIM}{v['test_case']}{RESET}"
            )
            print(f"    {v['finding']}")
        print()


def main() -> int:
    if len(sys.argv) != 2:
        print("Usage: python scripts/generate_report.py results/<file>.json")
        return 2

    results_path = Path(sys.argv[1]).resolve()
    if not results_path.exists():
        print(f"Error: {results_path} not found", file=sys.stderr)
        return 2

    data = load_results(results_path)
    if not data.get("verdicts"):
        # Defense in depth for callers producing verdicts outside run_eval.py
        # (Claude Code, custom harnesses). A zero-verdict report would look
        # identical to a green run — refuse it.
        print(
            f"Error: {results_path} contains zero verdicts. Refusing to "
            f"render a report with no coverage.",
            file=sys.stderr,
        )
        return 3

    ctx = build_context(data)

    html = render_html(ctx)
    html_path = results_path.with_suffix(".html")
    html_path.write_text(html)

    print_terminal_summary(ctx)
    try:
        display_path = html_path.relative_to(REPO_ROOT)
    except ValueError:
        display_path = html_path
    print(f"HTML report: {display_path}")
    print()

    return 1 if ctx["critical_failures"] else 0


if __name__ == "__main__":
    sys.exit(main())
