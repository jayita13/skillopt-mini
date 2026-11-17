"""A tiny task with an automatic check: turn messy date strings into ISO dates.

The labels follow four HOUSE RULES that are never written in the starting skill.
The optimizer has to discover them from failed rollouts, which is the whole point:

  1. Numeric dates are DAY-first:      03/04/2026  -> 2026-04-03
  2. Two-digit years mean 20YY:        05.11.25    -> 2025-11-05
  3. No year given means 2026:         March 7     -> 2026-03-07
  4. Answer with YYYY-MM-DD and nothing else.
"""
from __future__ import annotations

import random

MONTHS = ["January", "February", "March", "April", "May", "June", "July",
          "August", "September", "October", "November", "December"]


def _ordinal(n: int) -> str:
    suffix = "th" if 11 <= n % 100 <= 13 else {1: "st", 2: "nd", 3: "rd"}.get(n % 10, "th")
    return f"{n}{suffix}"


def _item(rng: random.Random) -> dict:
    kind = rng.choice(["dmy4", "dmy4", "dmy2", "dot2", "noyear_full", "noyear_short", "ordinal", "iso_slash"])
    year = rng.choice([2024, 2025, 2026, 2027])
    month = rng.randint(1, 12)
    if kind in ("dmy4", "dmy2", "dot2"):
        # Day <= 12 and day != month, so a month-first reading gives a WRONG answer.
        day = rng.choice([d for d in range(1, 13) if d != month])
    else:
        day = rng.randint(1, 28)

    if kind == "dmy4":
        text = f"{day:02d}/{month:02d}/{year}"
    elif kind == "dmy2":
        text = f"{day}/{month}/{year % 100:02d}"
    elif kind == "dot2":
        text = f"{day:02d}.{month:02d}.{year % 100:02d}"
    elif kind == "noyear_full":
        year, text = 2026, f"{MONTHS[month - 1]} {day}"
    elif kind == "noyear_short":
        year, text = 2026, f"{day} {MONTHS[month - 1][:3]}"
    elif kind == "ordinal":
        text = f"the {_ordinal(day)} of {MONTHS[month - 1]}, {year}"
    else:  # already year-first, the easy case
        text = f"{year}/{month:02d}/{day:02d}"

    return {"input": text, "expected": f"{year:04d}-{month:02d}-{day:02d}"}


TASK_NAME = "messy date -> ISO date"
SEED_SKILL = "# Skill: date normaliser\n- Convert the date in the message to ISO format.\n"
TASK_BRIEF = "a smaller model reads before it converts one date string into an answer"


def user_message(item: dict) -> str:
    return f"Date: {item['input']}"


def check(output: str, item: dict) -> tuple[bool, float]:
    ok = output.strip() == item["expected"]
    return ok, float(ok)


def show_expected(item: dict) -> str:
    return item["expected"]


def make_splits(seed: int = 42, n_train: int = 16, n_val: int = 10, n_test: int = 20):
    """Deterministic, non-overlapping train / validation / test splits."""
    rng = random.Random(seed)
    items, seen = [], set()
    while len(items) < n_train + n_val + n_test:
        it = _item(rng)
        if it["input"] not in seen:
            seen.add(it["input"])
            items.append(it)
    return items[:n_train], items[n_train:n_train + n_val], items[n_train + n_val:]


if __name__ == "__main__":
    for name, split in zip(("train", "val", "test"), make_splits()):
        print(f"--- {name} ({len(split)})")
        for it in split:
            print(f"  {it['input']:<28} -> {it['expected']}")
