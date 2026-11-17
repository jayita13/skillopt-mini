# Results from live runs

All numbers below come from real calls to the Groq free tier on 17 November 2026. The full
console output, every proposed edit, and every model answer are committed in
[`runs/`](../runs/).

## Setup

| | |
|---|---|
| Task | bank-statement line → ledger entry ([`tasks/transactions.py`](../tasks/transactions.py)) |
| Target model (frozen) | `openai/gpt-oss-20b`, reasoning effort low, temperature 0 |
| Optimizer model | `openai/gpt-oss-120b` |
| Data | 24 train / 12 validation / 24 test lines, plus a separate 16-line November statement |
| Grading | a row is correct only if date, amount (to the cent), currency and category all match |

The statement lines are **generated**, not taken from real accounts. The generator
reproduces the formats of Irish/EU bank exports (card payments, direct debits, Revolut CSV
rows, £/$ card spend, refunds, salary credits, transfers, fees), so no personal data is
involved. The November statement was written by hand and includes merchants and phrasings
that never appear in training.

## Headline

| Run | Held-out test (exact) | Held-out test (fields) | November statement |
|---|---|---|---|
| Seed skill (2 lines) | **0%** | 44–46% | **0 / 16** |
| Run 1: 2 epochs | 58% | 89% | 10 / 16 |
| Run 2: 3 epochs + "no invented labels" rule for the optimizer | **79%** | **93%** | **11 / 16** |

Same frozen model throughout. Only the skill text changed.

Run 2: 249 model calls, about 157K tokens, 15.9 minutes, $0 on the free tier.

## Training trace (run 2)

| Step | Edits allowed | Proposed change (abridged) | Validation | Decision |
|---|---|---|---|---|
| start | | 2-line seed skill | 0% | |
| 1 | 3 | sign rule: `CR` / `REFUND` positive, everything else negative; date formats | 0% → 33% | ✅ kept |
| 2 | 3 | add `utilities`; two-digit years are 20YY; no year means 2026 | 33% → 58% | ✅ kept |
| 3 | 3 | currency, transfer and fee rules (combined) | 58% → 50% | ❌ rolled back |
| 4 | 2 | `$` → USD, `£` → GBP; fee keywords → `fees` | 58% → 75% | ✅ kept |
| 5 | 2 | broad transfer keywords including "card payment" | 75% → 42% | ❌ rolled back |
| 6 | 2 | transfer keywords, narrower | 75% → 75% (tie) | ❌ rolled back |
| 7 | 1 | transfer keywords again | 75% → 50% | ❌ rolled back |
| 8 | 1 | standalone word `TO` → `transfer`; grocery chain keywords | 75% → 83% | ✅ kept |
| 9 | 1 | stricter `CR` / `REFUND` matching | 83% → 83% (tie) | ❌ rolled back |

Steps 5–7 show why the gate matters. The optimizer kept trying an over-broad transfer rule
that would have mislabelled ordinary card payments, and the validation set caught it each
time. In step 8 it found the narrow version (`TO <name>`) that works.

The learned skill is in [`skills/transactions.md`](../skills/transactions.md), about 300 words.

## Deployment on the unseen November statement

Excerpt from `python ledger.py statements/nov2026.csv --compare`:

```
== BEFORE: seed skill   correct rows: 0/16
✗ 2023-11-01       62.35 EUR  Groceries  01/11 POS TESCO STORES 3124 DUBLIN 2 62,35
✗ 2027-11-26     1150.00 EUR  RENT       07-11-26 TO S OBRIEN RENT 1.150,00
✗ 2023-11-11       20.00 EUR  Card Top‑u 11/11 POS LEAP CARD TOPUP DUBLIN 2 20,00

== AFTER: trained skill (transactions.md)   correct rows: 11/16
✓ 2026-11-01      -62.35 EUR  groceries  01/11 POS TESCO STORES 3124 DUBLIN 2 62,35
✓ 2026-11-03      -27.90 EUR  dining     03/11/2026 CARD PAYMENT UBER *EATS 27,90
✓ 2026-11-07    -1150.00 EUR  transfer   07-11-26 TO S OBRIEN RENT 1.150,00
✓ 2026-11-12       -8.45 GBP  dining     12 NOV CARD PRET A MANGER £8.45
```

Before training, the spend report has 15 inconsistent category labels ("Food & Drink",
"RENT", "Card Top‑up", "Groceries" vs "groceries", …), wrong years, and spending shown as
money coming in. After training it uses the
team's 10 categories with correct signs.

### The 5 rows still wrong, and why

| Line | Got | Expected | Cause |
|---|---|---|---|
| `DD ELECTRIC IRELAND … 96,12` | +96.12 | −96.12 | ignored its own "negative unless CR" rule on this line |
| `05/11 SEPA CREDIT … SALARY NOV … CR` | 2026-**05-11** | 2026-11-05 | read the date month-first despite the day-first rule |
| `DD EIR BROADBAND …` | `fees` | `utilities` | "broadband" isn't among the learned utility keywords |
| `11/11 POS LEAP CARD TOPUP …` | `transfer` | `transport` | "top-up" was linked to transfers |
| `12-11-26 REVOLUT**TOPUP* 200,00` | `income` | `transfer` | top-ups were rare in training |

These are the honest limits of a short run on a small model. The skill learns the policy
that the training examples show, and only partly generalises to phrasings it never saw.
More varied training lines, more epochs, or a stronger target model would close most of the
gap.

## Run 1 vs run 2

Run 1's optimizer invented a fallback category, `unknown`, which isn't in the team's list.
Five November rows ended up there. Run 2 added a general rule to the optimizer
instructions: labels must come from the expected answers, with no invented fallbacks. That
removed every `unknown`, and three more epochs added further gains.

## Reproduce

```bash
make train    # about 16 min, writes runs/transactions-<timestamp>/ and skills/transactions.md
make demo     # about 2 min
```

Results vary a little between runs. The target model is called at temperature 0, but the
optimizer's edits and the gateway's batching are not perfectly deterministic.
