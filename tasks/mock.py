"""Offline stand-ins for the two models, so `python skillopt_mini.py --task dates --mock` runs anywhere.

MockTarget is a naive date parser that only follows a house rule once the skill text
mentions it. MockOptimizer proposes one rule per step, including one deliberately bad
rule, so you can watch the validation gate reject it. Real learning needs real models.
"""
from __future__ import annotations

import json
import re

from tasks.dates import MONTHS

_MON = {m[:3].lower(): i + 1 for i, m in enumerate(MONTHS)}

RULES = [
    "- Answer with the date as YYYY-MM-DD only. No other words.",
    "- Numeric dates such as 03/04/2026 are DAY-first: day/month/year.",
    "- Prefer month-first for numeric dates, as in US style.",          # bad rule: the gate should reject it
    "- A two-digit year means 20YY, so 25 is 2025.",
    "- If no year is given, use 2026.",
]


def _target(skill: str, text: str) -> str:
    s = skill.lower()
    day_first = "day-first" in s and "month-first" not in s
    nums = re.findall(r"\d+", text)
    words = re.findall(r"[A-Za-z]+", text)
    month_word = next((_MON[w[:3].lower()] for w in words if w[:3].lower() in _MON), None)
    if month_word:                                   # "March 7", "7 Mar", "the 7th of March, 2025"
        day, month = int(nums[0]), month_word
        year = int(nums[1]) if len(nums) > 1 else (2026 if "no year" in s else 2025)
    elif len(nums[0]) == 4:                          # 2026/04/03
        year, month, day = map(int, nums)
    else:                                            # 03/04/26 or 03.04.2026
        a, b, y = map(int, nums)
        day, month = (a, b) if day_first else (b, a)
        year = y if y > 99 else (2000 + y if "20yy" in s else 1900 + y)
    iso = f"{year:04d}-{month:02d}-{day:02d}"
    return iso if "only" in s else f"The date is {iso}."


class MockLLM:
    def __init__(self, target_model: str):
        self.target_model, self.calls = target_model, 0

    def chat(self, model: str, system: str, user: str, max_tokens: int) -> str:
        self.calls += 1
        if model == self.target_model:
            return _target(system, user.removeprefix("Date: "))
        skill, rejected = user.split("FAILURES:")[0], user.split("REJECTED EARLIER:")[1]
        todo = [r for r in RULES if r not in skill and r not in rejected]
        return json.dumps({"edits": [{"op": "append", "content": todo[0]}] if todo else []})
