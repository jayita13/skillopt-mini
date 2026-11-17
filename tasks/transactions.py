"""Live use case: normalise raw bank-statement lines into ledger entries.

A finance team exports statements from several banks (AIB/BoI-style text exports, card
feeds, Revolut CSVs). Every line must become one ledger row:

    {"date": "YYYY-MM-DD", "amount": -45.2, "currency": "EUR", "category": "groceries"}

The team's BOOKKEEPING POLICY decides the labels. The starting skill never mentions it;
SkillOpt has to recover it from failed rollouts:

  1. Dates are DAY-first (03/04 = 3 April). No year means the statement year, 2026.
     Two-digit years mean 20YY.
  2. EUR lines use a decimal COMMA and dot thousands (1.234,56). Card lines with £ or $
     use a decimal dot.
  3. Money out is NEGATIVE. Money in (lines marked CR, refunds, salary) is POSITIVE.
  4. Currency is an ISO code. No symbol means EUR. £ is GBP and $ is USD.
  5. category is exactly one of: groceries, dining, transport, travel, software,
     utilities, income, refund, transfer, fees. House quirks: any refund is "refund"
     whatever the merchant; Uber Eats is dining but an Uber trip is transport; flights and
     hotels are travel, local trips are transport; Revolut top-ups and payments TO a person
     are transfers.
  6. Reply with the JSON object only.
"""
from __future__ import annotations

import json
import random

TASK_NAME = "bank-statement line -> ledger entry"
STATEMENT_YEAR = 2026
CATEGORIES = ["groceries", "dining", "transport", "travel", "software",
              "utilities", "income", "refund", "transfer", "fees"]

SEED_SKILL = (
    "# Skill: bank transaction normaliser\n"
    "- Read the bank statement line and return a JSON object with the keys "
    "date, amount, currency and category.\n"
)

TASK_BRIEF = ("a smaller model reads before it converts ONE raw bank-statement line into a "
              "JSON ledger entry with keys date, amount, currency, category")

MON = ["JAN", "FEB", "MAR", "APR", "MAY", "JUN", "JUL", "AUG", "SEP", "OCT", "NOV", "DEC"]

# merchant text as it appears on the statement -> house category
MERCHANTS = {
    "groceries": ["TESCO STORES 3124", "LIDL IRELAND 0457", "ALDI STORES 112", "DUNNES STORES",
                  "SUPERVALU RATHMINES", "CENTRA 2231"],
    "dining": ["STARBUCKS GRAFTON ST", "BUTLERS CHOC CAFE", "DELIVEROO.IE", "UBER *EATS",
               "JUST EAT.IE", "BEWLEYS CAFE"],
    "transport": ["UBER *TRIP", "LEAP CARD TOPUP", "FREENOW*RIDE", "IRISH RAIL WEB", "DUBLIN BUS"],
    "travel": ["RYANAIR 4FG8H2", "AER LINGUS EI5TRK", "BOOKING.COM HOTEL", "AIRBNB * HMQ2"],
    "software": ["AWS EMEA", "GITHUB, INC.", "NOTION LABS", "OPENAI *CHATGPT", "FIGMA MONTHLY"],
    "utilities": ["ELECTRIC IRELAND", "BORD GAIS ENERGY", "EIR BROADBAND", "VODAFONE IE",
                  "VIRGIN MEDIA IE"],
}
FX_MERCHANTS = {  # card spend abroad, shown in the original currency
    "GBP": [("TFL TRAVEL CH", "transport"), ("PRET A MANGER", "dining"),
            ("SAINSBURYS S/MKT", "groceries"), ("EASYJET", "travel")],
    "USD": [("AWS US", "software"), ("SLACK T0123", "software"), ("ANTHROPIC", "software"),
            ("DELTA AIR", "travel")],
}
CITIES = ["DUBLIN 2", "DUBLIN 6", "CORK", "GALWAY", "LIMERICK"]
PEOPLE = ["J MURPHY", "A KELLY", "S OBRIEN", "C WALSH", "R BYRNE"]
EMPLOYERS = ["ACME ANALYTICS LTD", "DATAWORKS IRL", "NORTHWIND TECH"]
AMOUNT_RANGE = {"groceries": (8, 160), "dining": (3, 65), "transport": (2, 60),
                "travel": (40, 900), "software": (5, 400), "utilities": (30, 220)}


def eu(x: float) -> str:
    """1234.5 -> '1.234,50' (Irish/EU bank export style)."""
    whole, frac = f"{x:,.2f}".split(".")
    return whole.replace(",", ".") + "," + frac


def _ambiguous_day(rng, month):
    # day <= 12 and != month, so reading the date month-first gives a WRONG answer
    return rng.choice([d for d in range(1, 13) if d != month])


def _item(rng: random.Random, kind: str) -> dict:
    month = rng.randint(1, 12)
    day = _ambiguous_day(rng, month) if kind in ("pos", "card", "dd", "refund", "salary", "transfer", "fee") \
        else rng.randint(1, 28)
    year = STATEMENT_YEAR
    cur = "EUR"

    if kind in ("pos", "card", "dd", "revolut"):
        cat = {"dd": "utilities"}.get(kind) or rng.choice(
            ["groceries", "dining", "transport"] if kind == "pos"            # in-store terminals
            else ["groceries", "dining", "transport", "travel", "software"])
        merchant = rng.choice(MERCHANTS[cat])
        amt = round(rng.uniform(*AMOUNT_RANGE[cat]), 2)
        if kind == "pos":
            text = f"{day:02d}/{month:02d} POS {merchant} {rng.choice(CITIES)} {eu(amt)}"
        elif kind == "card":
            year = rng.choice([2025, 2026])
            text = f"{day:02d}/{month:02d}/{year} CARD PAYMENT {merchant} {eu(amt)}"
        elif kind == "dd":
            year = rng.choice([2025, 2026])
            text = f"DD {merchant} REF{rng.randint(10000, 99999)} {day:02d}.{month:02d}.{year % 100:02d} {eu(amt)}"
        else:  # Revolut-style export: ISO date, explicit sign, dot decimal
            year = rng.choice([2025, 2026])
            text = f"{year}-{month:02d}-{day:02d},Card Payment,{merchant.title()},-{amt:.2f},EUR"
        amount = -amt
    elif kind == "fx":
        cur = rng.choice(["GBP", "USD"])
        merchant, cat = rng.choice(FX_MERCHANTS[cur])
        amt = round(rng.uniform(4, 300), 2)
        text = f"{day} {MON[month - 1]} CARD {merchant} {'£' if cur == 'GBP' else '$'}{amt:.2f}"
        amount = -amt
    elif kind == "refund":
        src = rng.choice(["groceries", "dining", "travel", "software"])
        amt = round(rng.uniform(*AMOUNT_RANGE[src]), 2)
        year = rng.choice([2025, 2026])
        text = f"REFUND {rng.choice(MERCHANTS[src])} {day:02d}/{month:02d}/{year % 100:02d} {eu(amt)} CR"
        cat, amount = "refund", amt
    elif kind == "salary":
        amt = round(rng.uniform(2800, 6500), 2)
        text = f"{day:02d}/{month:02d} SEPA CREDIT {rng.choice(EMPLOYERS)} SALARY {MON[month - 1]} {eu(amt)} CR"
        cat, amount = "income", amt
    elif kind == "transfer":
        amt = round(rng.uniform(10, 1200), 2)
        year = rng.choice([2025, 2026])
        memo = rng.choice(["RENT", "DINNER", "GIFT", "TICKETS", ""])
        if rng.random() < 0.3:
            text = f"{day:02d}-{month:02d}-{year % 100:02d} REVOLUT**TOPUP* {eu(amt)}"
        else:
            text = f"{day:02d}-{month:02d}-{year % 100:02d} TO {rng.choice(PEOPLE)} {memo} {eu(amt)}".replace("  ", " ")
        cat, amount = "transfer", -amt
    else:  # fee
        amt = round(rng.uniform(0.5, 18), 2)
        text = f"{day:02d}/{month:02d} " + rng.choice(["FX FEE NON-EUR TXN", "ACCOUNT MAINT FEE",
                                                       "CARD ANNUAL FEE", "UNPAID ITEM CHARGE"]) + f" {eu(amt)}"
        cat, amount = "fees", -amt

    expected = {"date": f"{year:04d}-{month:02d}-{day:02d}", "amount": round(amount, 2),
                "currency": cur, "category": cat}
    return {"input": text, "expected": expected}


KINDS = ["pos", "card", "dd", "revolut", "fx", "refund", "salary", "transfer", "fee", "pos", "fx", "card"]


def make_splits(seed: int = 42, n_train: int = 24, n_val: int = 12, n_test: int = 24):
    """Deterministic, non-overlapping splits, stratified over the statement line formats."""
    rng = random.Random(seed)
    items, seen, i = [], set(), 0
    while len(items) < n_train + n_val + n_test:
        it = _item(rng, KINDS[i % len(KINDS)])
        i += 1
        if it["input"] not in seen:
            seen.add(it["input"])
            items.append(it)
    # items cycle through KINDS, so each contiguous slice covers every format
    return items[:n_train], items[n_train:n_train + n_val], items[n_train + n_val:]


def user_message(item: dict) -> str:
    return f"Statement line: {item['input']}"


def parse(output: str) -> dict | None:
    try:
        obj = json.loads(output[output.index("{"): output.rindex("}") + 1])
        return obj if isinstance(obj, dict) else None
    except ValueError:
        return None


FIELDS = ("date", "amount", "currency", "category")


def check(output: str, item: dict) -> tuple[bool, float]:
    """Exact match on all four fields (amount to the cent). Also returns partial credit."""
    got, exp = parse(output), item["expected"]
    if got is None:
        return False, 0.0
    hits = 0
    for f in FIELDS:
        g = got.get(f)
        if f == "amount":
            try:
                ok = abs(float(g) - exp[f]) < 0.005
            except (TypeError, ValueError):
                ok = False
        else:
            ok = str(g).strip() == exp[f]
        hits += ok
    return hits == len(FIELDS), hits / len(FIELDS)


def show_expected(item: dict) -> str:
    return json.dumps(item["expected"])


if __name__ == "__main__":
    for name, split in zip(("train", "val", "test"), make_splits()):
        print(f"--- {name} ({len(split)})")
        for it in split:
            print(f"  {it['input']:<62} -> {show_expected(it)}")
