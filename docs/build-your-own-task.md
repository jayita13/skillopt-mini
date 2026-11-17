# Build your own task

The bank-statement task is one example. The same loop works for any workflow where a model
turns an input into an answer **and you can grade the answer with code**. This guide takes
you from idea to a trained, deployable skill.

## 1. Does your workflow fit?

Answer yes to all three:

- [ ] **One input → one answer.** A ticket → a queue, an invoice → fields, a log line → a severity.
- [ ] **Automatic check.** Code can decide whether an answer is right: exact match, field
      match, a regex, a unit test, a SQL query returning the right rows.
- [ ] **House rules the model doesn't know.** Your label names, formats, edge-case policy,
      or conventions. If a general model already gets it right, there's nothing to learn.

## 2. Ideas that fit well

| Workflow | Input → answer | Check | Typical hidden rules |
|---|---|---|---|
| Support triage | ticket → `{queue, priority}` | field match | which queue owns what; what counts as P1 |
| Invoice / receipt extraction | text → `{vendor, total, vat, due_date}` | field match, amounts to the cent | VAT-inclusive totals, date format, vendor canonical names |
| Log / alert classification | log line → severity + component | exact match | which errors are noise; component naming |
| Product categorisation | title → taxonomy node | exact match | your catalogue's taxonomy and tie-breaks |
| PII redaction | text → redacted text | diff against reference | what counts as PII in your domain |
| Text-to-SQL | question → SQL | run it; compare result rows | table conventions, fiscal year, soft-deletes |
| Commit / changelog style | diff summary → message | regex + length rules | prefixes, tense, ticket references |
| Compliance tagging | clause → risk tag | exact match | your policy's definitions |

## 3. Write the task module

```bash
cp tasks/_template.py tasks/ticket_triage.py
```

A task module defines seven names. The template has a worked example for each.

| Name | What it is |
|---|---|
| `TASK_NAME` | a short label for the console |
| `SEED_SKILL` | the starting skill, deliberately minimal (1–2 lines) |
| `TASK_BRIEF` | one phrase telling the optimizer what the skill is for |
| `make_splits(seed)` | returns `(train, validation, test)` lists of `{"input": ..., "expected": ...}` |
| `user_message(item)` | the user turn sent to the target model |
| `check(output, item)` | returns `(fully_correct: bool, partial_credit: float 0..1)` |
| `show_expected(item)` | how the right answer is shown to the optimizer |

Any file in `tasks/` with those names becomes a `--task` option automatically.

## 4. Get the data right

- **Size.** 40–60 labelled items is enough to start: about 40% train, 20% validation,
  40% test. More validation items give a steadier gate; more test items give a more
  trustworthy headline number.
- **Keep the splits disjoint.** Test items must never appear in training or validation.
- **Cover every case in every split.** If refunds only appear in the test set, the skill
  can't learn them. [`tasks/transactions.py`](../tasks/transactions.py) cycles through line
  formats so each split gets every format.
- **Use real examples if you can** (anonymised). Synthetic data is fine for a demo, but
  real inputs carry the messy variety your skill must handle.
- **Add partial credit for structured answers.** It gives the gate a finer signal than
  exact match.

## 5. Train

```bash
python skillopt_mini.py --task ticket_triage --epochs 3
```

Watch the console:
- `.` and `x` are individual answers (correct or wrong)
- `+` lines are edits that were kept; `x` lines are edits that were rolled back
- the last block shows test accuracy before and after, and the learned skill

**Cost estimate.** Each step makes about `batch (8) + 1 + validation size` calls, plus the
test set twice. With 24 / 12 / 24 items and 3 epochs, that's about 250 calls, roughly 16
minutes on the Groq free tier.

## 6. Deploy

The output is a Markdown file in `skills/<task>.md`. Use it as the system prompt wherever
you call the target model: in a script, an agent framework, or a Claude Code / Codex skill
folder. [`ledger.py`](../ledger.py) is a short (about 80 lines) example of a deployment script.

## 7. When it doesn't learn

| Symptom | Likely cause | Try |
|---|---|---|
| Every edit is rejected | validation set too small or noisy | more validation items; partial credit in `check()` |
| Validation improves but test doesn't | overfitting to validation | larger, more varied validation set |
| Skill copies specific answers | too few, too similar training items | more varied train data |
| Optimizer invents labels | vocabulary never stated | include every label in training data; see `OPTIMIZER_PROMPT` |
| Many `429` errors | rate limit | raise `MIN_SECONDS_BETWEEN_CALLS` or `TOKEN_HEADROOM` |
| Target model ignores a rule it was given | model too small for the instruction | stronger target model, or simpler phrasing in the seed |

## Using another gateway or model

Any OpenAI-compatible endpoint works. Set these in `.env`:

```bash
LLM_BASE_URL=http://localhost:11434/v1   # e.g. local Ollama
LLM_API_KEY=ollama
TARGET_MODEL=<small model id>
OPTIMIZER_MODEL=<stronger model id>
REASONING_EFFORT=                        # leave empty for non-reasoning models
```
