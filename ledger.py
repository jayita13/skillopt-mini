"""ledger.py: deploy a trained skill on a real statement and produce a ledger + spend report.

    python ledger.py statements/nov2026.csv                 # trained skill (skills/transactions.md)
    python ledger.py statements/nov2026.csv --compare       # side by side with the untrained seed skill

Input CSV needs a `line` column (the raw statement text). If it also has expected_* columns
(an answer key), each row is graded. Writes <statement>.ledger.csv next to the input.
Only the skill text differs between the two columns: same frozen model, same prompt.
"""
from __future__ import annotations

import argparse
import csv
from collections import defaultdict
from pathlib import Path

from tasks import transactions as task
from skillopt_mini import HERE, LLM, TARGET_MODEL


def run(llm, skill: str, rows: list[dict]) -> list[dict]:
    out = []
    for r in rows:
        raw = llm.chat(TARGET_MODEL, skill, task.user_message({"input": r["line"]}), max_tokens=700)
        got = task.parse(raw) or {}
        rec = {"line": r["line"], **{f: got.get(f, "") for f in task.FIELDS}, "raw": raw}
        if r.get("expected_date"):
            item = {"expected": {"date": r["expected_date"], "amount": float(r["expected_amount"]),
                                 "currency": r["expected_currency"], "category": r["expected_category"]}}
            rec["ok"], _ = task.check(raw, item)
        out.append(rec)
        print("." if rec.get("ok", True) else "x", end="", flush=True)
    print()
    return out


def report(title: str, recs: list[dict]) -> None:
    graded = [r for r in recs if "ok" in r]
    print(f"\n== {title}" + (f"   correct rows: {sum(r['ok'] for r in graded)}/{len(graded)}" if graded else ""))
    print(f"{'':2}{'date':<11} {'amount':>10} {'cur':<4} {'category':<10} line")
    for r in recs:
        mark = "" if "ok" not in r else ("✓ " if r["ok"] else "✗ ")
        amt = r["amount"]
        amt = f"{amt:>10.2f}" if isinstance(amt, (int, float)) else f"{str(amt)[:10]:>10}"
        print(f"{mark:2}{str(r['date'])[:11]:<11} {amt} {str(r['currency'])[:4]:<4} "
              f"{str(r['category'])[:10]:<10} {r['line'][:58]}")
    totals = defaultdict(float)
    for r in recs:
        try:
            totals[(str(r["currency"]), str(r["category"]))] += float(r["amount"])
        except (TypeError, ValueError):
            totals[("?", "unparseable")] += 0
    print("  spend report:", ", ".join(f"{cat} {cur} {v:,.2f}" for (cur, cat), v in sorted(totals.items())))


def main():
    ap = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    ap.add_argument("statement", type=Path)
    ap.add_argument("--skill", type=Path, default=HERE / "skills" / "transactions.md")
    ap.add_argument("--compare", action="store_true", help="also run the untrained seed skill")
    args = ap.parse_args()

    rows = list(csv.DictReader(args.statement.open(newline="")))
    llm = LLM()
    if args.compare:
        print(f"seed skill    ({len(rows)} lines) ", end="")
        report("BEFORE: seed skill", run(llm, task.SEED_SKILL, rows))
    print(f"trained skill ({len(rows)} lines) ", end="")
    recs = run(llm, args.skill.read_text(), rows)
    report(f"AFTER: trained skill ({args.skill.name})", recs)

    out = args.statement.with_suffix(".ledger.csv")
    with out.open("w", newline="") as f:
        w = csv.DictWriter(f, fieldnames=["line", *task.FIELDS] + (["ok"] if "ok" in recs[0] else []),
                           extrasaction="ignore")
        w.writeheader()
        w.writerows(recs)
    print(f"\nwrote {out.name}   model calls: {llm.calls}   tokens: {llm.tokens}")


if __name__ == "__main__":
    main()
