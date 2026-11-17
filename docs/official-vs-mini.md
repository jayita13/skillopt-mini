# The official SkillOpt and skillopt-mini

This repo is a **reproduction recipe** for the SkillOpt idea, not a replacement for the
official implementation. This page shows exactly which parts of the paper's method are
here, which are not, and why.

Sources: the paper ([arXiv:2605.23904](https://arxiv.org/abs/2605.23904)) and the
[official repository](https://github.com/microsoft/skillopt), as read on 18 November 2026.

## Why this repo exists

The paper reports that training a skill file lifted GPT-5.5's average accuracy by 23.5
points in direct chat, 24.8 inside Codex and 19.1 inside Claude Code, and that SkillOpt was
best or tied-best in all 52 model × benchmark × harness combinations it tested. Getting there takes a
frontier optimizer model, tens of millions of tokens per benchmark, and a full software
package.

Most people who want to *learn the idea* and *try it on their own workflow* have none of
that. They have a laptop, a free API key and an afternoon. skillopt-mini is built for them:
- **Keep the core mechanism intact**, so what you learn transfers to the real thing.
- **Cut everything that only pays off at scale**, so one run fits in a free tier and the
  whole loop fits on one screen of reading.
- **Show it working on a realistic task** with real API calls, so it isn't a toy.

When your use case outgrows that, move to `pip install skillopt` (see the last section).

## What is the same

These are the parts that make SkillOpt *SkillOpt*. They are all here and behave as the
paper describes:

| Mechanism | What it means | In skillopt-mini |
|---|---|---|
| Skill as trainable state | the target model is frozen; only a Markdown skill changes | ✅ `skill` in `main()` |
| Scored rollouts | the frozen target answers tasks with the current skill; code grades each answer | ✅ `rollout()` with `task.check()` |
| Optimizer-driven reflection | a separate model reads failures and successes and proposes edits | ✅ `reflect()` |
| Bounded add / delete / replace edits | edits are small, structured operations on the skill text | ✅ `apply_edits()` |
| Textual learning rate | a cap on edits per step, decaying over training | ✅ `learning_rate()`, cosine |
| Strict validation gate | keep an edit only if the held-out score strictly improves; ties rejected | ✅ in `main()` |
| Rejected-edit buffer | failed edits are fed back so the optimizer doesn't repeat them | ✅ `rejected` |
| Score cache by skill hash | the same skill is never scored twice | ✅ `_val_cache` |
| Separate train / validation / test | learn on one, gate on another, report on a third | ✅ `task.make_splits()` |
| Deployable `best_skill.md` | the output is a plain file used with the unchanged target | ✅ `skills/<task>.md` |

## What is different, and why

| Step | Official SkillOpt | skillopt-mini | Why it's left out or reduced here |
|---|---|---|---|
| **Rollouts per step** | batch of 40 tasks | batch of 8 | 40 rollouts plus a validation pass per step would take minutes per step at 8K tokens/minute |
| **Reflection** | failures and successes split into minibatches of 8, analysed by 16 parallel workers, up to 3 refinement rounds each | one optimizer call per step, seeing up to 8 failures and 3 successes | parallel workers multiply optimizer calls; a free tier allows 1,000 requests/day per model |
| **Merge edits** | proposals merged hierarchically, failure fixes and success-preserving edits first, then combined | none: one call proposes one edit set | with a single reflection call there is nothing to merge |
| **Rank and select edits** | optimizer ranks the merged pool by expected utility, keeps the top *L* | keeps the first *L* edits returned | same reason; ranking only matters when there are more candidates than the budget |
| **Learning-rate defaults** | 4 edits per step, cosine-decayed to a floor of 2 | 3 → 1 | fewer, smaller edits suit a 2-line seed skill and a 12-item validation set |
| **Rejected-edit buffer** | stores failure patterns and tried edits with score drops; reset every epoch | stores the last 5 rejected edit sets with score drops; never reset | runs are 2–3 epochs, so a per-epoch reset changes little |
| **Slow update** (epoch 2+) | re-runs 20 training tasks under last epoch's skill and this one; groups them into improved, regressed, still failing and stable; writes a protected `SLOW_UPDATE` block that step edits cannot touch (it must also pass the gate) | not implemented | needs about 40 extra rollouts per epoch plus a gated validation pass; most valuable over 4+ epochs on large data |
| **Meta skill** (epoch 2+) | optimizer-only notes on which kinds of edit helped or were rejected, added to later optimizer prompts, never shipped | not implemented | cheap, but its value grows with run length; a natural first addition (see below) |
| **Epochs and models** | 4 epochs, medium reasoning effort, GPT-5.5 as optimizer; 7 target models | 3 epochs, low reasoning effort, open `gpt-oss-120b` optimizer and `gpt-oss-20b` target | cost and free availability |
| **Harnesses** | direct chat, **Codex CLI** and **Claude Code CLI**: the skill is written to a per-task `SKILL.md` in a sandboxed workspace, and the agent's trace is returned to the optimizer | direct chat only: the skill is the system prompt | agent harnesses need sandboxes, CLI installs and trace capture, a project in itself |
| **Software around it** | 10 model backends, 6 built-in benchmarks, YAML configs, a web dashboard, and "SkillOpt-Sleep", a nightly self-improvement mode for coding agents | one OpenAI-compatible client, two example tasks | out of scope for a single readable file |

## The compute gap, in numbers

The paper reports training-token totals per benchmark for its GPT-5.5 runs. They range from
about **20.8M tokens** (OfficeQA) to **213.8M tokens** (SearchQA).

| | Tokens | Time at Groq free-tier 8,000 tokens/min |
|---|---|---|
| skillopt-mini, bank-statement run | ~157K | ~16 minutes (measured) |
| Paper, smallest reported benchmark | ~20.8M | ~43 hours |
| Paper, largest reported benchmark | ~213.8M | ~18.5 days |

That gap is the main reason the parallel, multi-round parts are missing. Every component
in the "different" table multiplies the number of model calls per step, and a free tier
caps both tokens per minute and requests per day.

## What the results here do and don't show

**They show** that the core loop works on a realistic task with real models and real API
calls. A frozen 20B model went from 0% to 79% exact accuracy on held-out bank-statement lines.
Every accepted and rejected edit is in [`runs/`](../runs/) to inspect.

**They don't show** how the full method performs. The paper's numbers come from the full
method at full scale, and nothing here reproduces or verifies them. Our test sets are small
(24 lines), our data is generated, and we use different models.

## Taking it further

**To use SkillOpt for real**, start with the official package: `pip install skillopt`. Its
README describes adding your own benchmark as a package under `skillopt/envs/<name>/`, with
an adapter, a data loader, a scored-rollout helper and a YAML config. It also has an
`openai_compatible` backend for gateways like Groq. A task you prototyped here (data plus a
`check()` function) is most of what that needs. Expect to need a paid model for runs at a
meaningful scale.

**To extend this repo**, in rough order of value per extra API call:
1. **Meta skill**: after each epoch, ask the optimizer to summarise which edits helped
   and which were rejected; add that summary to later reflection prompts.
2. **Per-epoch buffer reset**, with failure patterns stored alongside rejected edits.
3. **Parallel reflection with merge and rank**: split failures into minibatches,
   reflect on each (a thread pool is enough), then one merge call and one ranking call
   that keeps the top *L*.
4. **Slow update**: a protected section of the skill, rewritten once per epoch from a
   comparison of last epoch's skill against this one.
5. **Agent harness**: write the skill to a `SKILL.md` in a scratch workspace and run a
   coding agent CLI against it, returning its trace to the optimizer.

Pull requests that add any of these, while keeping the code readable, are welcome.
