"""TEMPLATE: copy this file to tasks/<your_task>.py and fill in the TODOs.

    cp tasks/_template.py tasks/ticket_triage.py
    python skillopt_mini.py --task ticket_triage

A good SkillOpt task has three things:
  1. A FROZEN model call per item: one input in, one answer out.
  2. An AUTOMATIC check: you can grade an answer with code, no human in the loop.
  3. HIDDEN RULES: the right answer depends on conventions your team knows but the
     model does not (label names, formats, edge-case policy). That is what gets learned.

The example below is a support-ticket router, to show the shape. Replace DATA with your
own labelled examples: 40-60 is enough to start (train ~40%, validation ~20%, test ~40%).
"""
from __future__ import annotations

import json
import random

# A short name shown in the console.
TASK_NAME = "support ticket -> queue + priority"

# The starting skill: deliberately minimal. Training writes the rest.
SEED_SKILL = (
    "# Skill: ticket router\n"
    "- Read the support ticket and return JSON with the keys queue and priority.\n"
)

# One phrase that completes "You improve a SKILL: instructions that ..." for the optimizer.
TASK_BRIEF = ("a smaller model reads before it routes ONE customer support ticket to a "
              "queue and a priority, answering in JSON")

# TODO: your labelled examples. `expected` can be any JSON-serialisable value.
DATA = [
    {"input": "I was charged twice for my March invoice",
     "expected": {"queue": "billing", "priority": "p2"}},
    {"input": "The whole dashboard is down for every user in our org",
     "expected": {"queue": "incidents", "priority": "p1"}},
    {"input": "How do I export my reports to CSV?",
     "expected": {"queue": "how-to", "priority": "p3"}},
    # ... add 40+ more real, anonymised examples ...
]


def make_splits(seed: int = 42):
    """Return (train, validation, test). Keep them disjoint and deterministic."""
    items = DATA[:]
    random.Random(seed).shuffle(items)
    n = len(items)
    a, b = int(n * 0.4), int(n * 0.6)
    return items[:a] or items, items[a:b] or items, items[b:] or items


def user_message(item: dict) -> str:
    """The user turn sent to the target model. The skill is the system prompt."""
    return f"Ticket: {item['input']}"


def check(output: str, item: dict) -> tuple[bool, float]:
    """Grade one answer: (fully correct?, partial credit 0..1).

    Partial credit gives the validation gate a finer signal on small validation sets.
    """
    try:
        got = json.loads(output[output.index("{"): output.rindex("}") + 1])
    except ValueError:
        return False, 0.0
    exp = item["expected"]
    hits = sum(str(got.get(k, "")).strip().lower() == str(v) for k, v in exp.items())
    return hits == len(exp), hits / len(exp)


def show_expected(item: dict) -> str:
    """How the expected answer is shown to the optimizer when it studies failures."""
    return json.dumps(item["expected"])
