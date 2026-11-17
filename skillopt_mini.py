"""skillopt_mini.py: the SkillOpt loop in one small file, on a free LLM gateway.

    rollout (forward) -> reflect (backward) -> bounded edit (learning rate) -> validation gate

The target model never changes. Only the skill text (a Markdown file) is trained.
The core loop of Microsoft Research's SkillOpt (arXiv:2605.23904), scaled down to run on a
free tier. Parallel reflection, edit ranking, the slow/meta update and agent harnesses are
left out; docs/official-vs-mini.md says why. For the full method: pip install skillopt

    python skillopt_mini.py                       # live: bank statement -> ledger (default task)
    python skillopt_mini.py --task dates          # live: the small date-format task
    python skillopt_mini.py --task dates --mock   # offline, no API key

The file reads top to bottom in the order of the loop:
    LLM client -> 1. rollout -> 2. reflect -> 3. apply_edits (+ learning rate) -> 4. val_score -> main()
Tasks (data + grading) live in tasks/. See docs/how-it-works.md for a walkthrough.
"""
from __future__ import annotations

import argparse
import hashlib
import json
import math
import os
import random
import re
import sys
import time
from datetime import datetime
from pathlib import Path

import tasks

HERE = Path(__file__).resolve().parent


def load_env(path: Path = HERE / ".env") -> None:
    """Minimal .env loader (KEY=VALUE lines). Real environment variables win."""
    if path.exists():
        for line in path.read_text().splitlines():
            if "=" in line and not line.lstrip().startswith("#"):
                k, v = line.split("=", 1)
                os.environ.setdefault(k.strip(), v.strip().strip('"').strip("'"))


load_env()

# ---- configuration (any OpenAI-compatible gateway works; Groq's free tier is the default) ----
BASE_URL = os.getenv("LLM_BASE_URL", "https://api.groq.com/openai/v1")
API_KEY = os.getenv("LLM_API_KEY") or os.getenv("GROQ_API_KEY", "")
TARGET_MODEL = os.getenv("TARGET_MODEL", "openai/gpt-oss-20b")        # frozen model being adapted
OPTIMIZER_MODEL = os.getenv("OPTIMIZER_MODEL", "openai/gpt-oss-120b")  # edits the skill, training only
REASONING_EFFORT = os.getenv("REASONING_EFFORT", "low")                # set "" for non-reasoning models
MIN_GAP_S = float(os.getenv("MIN_SECONDS_BETWEEN_CALLS", "2.0"))       # free tier: 30 req/min per model
TOKEN_HEADROOM = int(os.getenv("TOKEN_HEADROOM", "2500"))              # wait for the TPM window below this

BATCH = 8                 # rollout batch size
LR_MAX, LR_MIN = 3, 1     # textual learning rate: max edits per step, cosine-decayed

OPTIMIZER_PROMPT = """You improve a SKILL: instructions that {brief}.
You get the current skill, failed attempts (input, model output, expected answer) and a few successes.
Find the COMMON patterns behind the failures and propose AT MOST {L} edits that fix them.
- Write general rules that will hold for unseen inputs. Never copy specific inputs or answers.
- When the expected answers use a fixed vocabulary or format, state it explicitly.
- Labels must come ONLY from values seen in the expected answers. Never invent a fallback
  label (such as "unknown" or "other"); tell the model to pick the closest allowed label instead.
- Every output field the expected answers contain must always be filled in.
- Do not repeat what the skill already says. Keep the skill short and precise.
- Do not re-propose anything under "Rejected earlier": those edits lowered the validation score.
Reply with JSON only, no prose:
{{"edits": [{{"op": "append", "content": "- new rule"}},
            {{"op": "replace", "target": "exact existing text", "content": "new text"}},
            {{"op": "delete", "target": "exact existing text"}}]}}"""


def _seconds(s: str) -> float:
    """Groq reset headers look like '929ms', '7.66s' or '1m26.4s'."""
    total = 0.0
    for num, unit in re.findall(r"([\d.]+)(ms|m|s|h)", s or ""):
        total += float(num) * {"ms": 0.001, "s": 1, "m": 60, "h": 3600}[unit]
    return total


class LLM:
    """Thin wrapper over the OpenAI SDK that paces itself from the gateway's rate-limit headers."""

    def __init__(self):
        from openai import OpenAI
        if not API_KEY:
            sys.exit("Set GROQ_API_KEY (or LLM_API_KEY) in .env, or try: python skillopt_mini.py --task dates --mock")
        self.client = OpenAI(base_url=BASE_URL, api_key=API_KEY, max_retries=8, timeout=120)
        self._last: dict[str, float] = {}
        self._budget: dict[str, tuple[int, float]] = {}   # model -> (tokens left, time window resets)
        self.calls, self.tokens = 0, 0

    def chat(self, model: str, system: str, user: str, max_tokens: int) -> str:
        left, reset_at = self._budget.get(model, (10**9, 0.0))
        if left < TOKEN_HEADROOM and time.time() < reset_at:
            time.sleep(reset_at - time.time() + 0.2)
        time.sleep(max(0.0, MIN_GAP_S - (time.time() - self._last.get(model, 0.0))))
        kwargs = dict(model=model, temperature=0, max_tokens=max_tokens,
                      messages=[{"role": "system", "content": system}, {"role": "user", "content": user}])
        if REASONING_EFFORT:
            kwargs["reasoning_effort"] = REASONING_EFFORT
        raw = self.client.chat.completions.with_raw_response.create(**kwargs)
        resp, h = raw.parse(), raw.headers
        if h.get("x-ratelimit-remaining-tokens"):
            self._budget[model] = (int(float(h["x-ratelimit-remaining-tokens"])),
                                   time.time() + _seconds(h.get("x-ratelimit-reset-tokens", "")))
        self._last[model] = time.time()
        self.calls += 1
        self.tokens += getattr(resp.usage, "total_tokens", 0) or 0
        return (resp.choices[0].message.content or "").strip()


# ---- 1. forward pass: run the frozen target with the current skill and score every run ----
def rollout(llm, task, skill: str, items: list[dict]) -> list[dict]:
    runs = []
    for it in items:
        out = llm.chat(TARGET_MODEL, skill, task.user_message(it), max_tokens=700)
        ok, partial = task.check(out, it)
        runs.append({**it, "output": out, "ok": ok, "partial": partial})
        print("." if ok else "x", end="", flush=True)
    print(" ", end="", flush=True)
    return runs


def accuracy(runs: list[dict]) -> float:
    return sum(r["ok"] for r in runs) / len(runs)


def partial_score(runs: list[dict]) -> float:
    return sum(r["partial"] for r in runs) / len(runs)


# ---- 2. backward pass: the optimizer reads failures + successes and proposes edits ----
def reflect(llm, task, skill: str, runs: list[dict], rejected: list[dict], L: int) -> list[dict]:
    fails = [r for r in runs if not r["ok"]][:8]
    wins = [r for r in runs if r["ok"]][:3]
    fmt = lambda r: (f"input: {r['input']!r} | model said: {r['output'][:300]!r} | "
                     f"expected: {task.show_expected(r)}")
    user = "\n".join([
        "CURRENT SKILL:\n" + skill,
        "FAILURES:\n" + "\n".join(map(fmt, fails)),
        "SUCCESSES:\n" + ("\n".join(map(fmt, wins)) or "(none)"),
        "REJECTED EARLIER:\n" + (json.dumps(rejected[-5:], indent=1) if rejected else "(none)"),
    ])
    reply = llm.chat(OPTIMIZER_MODEL, OPTIMIZER_PROMPT.format(brief=task.TASK_BRIEF, L=L), user,
                     max_tokens=3000)
    try:
        edits = json.loads(reply[reply.index("{"): reply.rindex("}") + 1]).get("edits", [])
    except ValueError:
        print("\n   optimizer reply was not valid JSON; skipping this step")
        return []
    return [e for e in edits if isinstance(e, dict)][:L]   # <- the bound: at most L edits


# ---- 3. bounded update: apply only well-formed edits whose target exists ----
def apply_edits(skill: str, edits: list[dict]) -> tuple[str, list[dict]]:
    applied = []
    for e in edits:
        op, target, content = e.get("op"), e.get("target", ""), (e.get("content") or "").strip()
        if op == "append" and content:
            skill = skill.rstrip() + "\n" + (content if content.startswith("-") else "- " + content) + "\n"
        elif op == "replace" and target and target in skill and content:
            skill = skill.replace(target, content, 1)
        elif op == "delete" and target and target in skill:
            skill = skill.replace(target, "", 1)
        else:
            continue
        applied.append(e)
    return skill, applied


def learning_rate(step: int, total: int) -> int:
    """Cosine schedule: bigger edits early, smaller consolidation edits later."""
    t = step / max(1, total - 1)
    return round(LR_MIN + (LR_MAX - LR_MIN) * 0.5 * (1 + math.cos(math.pi * t)))


# ---- 4. validation gate (with a cache keyed by the skill's hash) ----
_val_cache: dict[str, tuple[float, float]] = {}


def val_score(llm, task, skill: str, val: list[dict]) -> tuple[float, float]:
    """Returns (partial-credit score used by the gate, exact-match accuracy)."""
    key = hashlib.sha256(skill.encode()).hexdigest()
    if key not in _val_cache:
        runs = rollout(llm, task, skill, val)
        _val_cache[key] = (partial_score(runs), accuracy(runs))
    return _val_cache[key]


def save_runs(path: Path, runs: list[dict]) -> None:
    path.write_text("\n".join(json.dumps({k: r[k] for k in ("input", "expected", "output", "ok")})
                              for r in runs) + "\n")


def main():
    ap = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    ap.add_argument("--task", default="transactions", choices=tasks.available())
    ap.add_argument("--mock", action="store_true", help="offline demo with fake models (dates task only)")
    ap.add_argument("--epochs", type=int, default=3)
    ap.add_argument("--seed", type=int, default=42)
    ap.add_argument("--runs-dir", type=Path, default=HERE / "runs", help="where run folders are written")
    args = ap.parse_args()

    task = tasks.load(args.task)
    if args.mock:
        if args.task != "dates":
            sys.exit("--mock only simulates the dates task: python skillopt_mini.py --task dates --mock")
        from tasks.mock import MockLLM
        llm = MockLLM(TARGET_MODEL)
    else:
        llm = LLM()

    out_dir = args.runs_dir / f"{args.task}-{datetime.now():%Y%m%d-%H%M%S}"
    out_dir.mkdir(parents=True)
    train, val, test = task.make_splits(args.seed)
    rng = random.Random(args.seed)
    skill, rejected, history = task.SEED_SKILL, [], []
    total_steps = args.epochs * math.ceil(len(train) / BATCH)
    t0 = time.time()

    print(f"task: {task.TASK_NAME}   train/val/test = {len(train)}/{len(val)}/{len(test)}")
    print(f"target={TARGET_MODEL}  optimizer={OPTIMIZER_MODEL}  gateway={'mock' if args.mock else BASE_URL}")
    print("baseline on held-out test ", end="")
    before = rollout(llm, task, skill, test)
    save_runs(out_dir / "test_before.jsonl", before)
    print(f"\nbaseline on validation    ", end="")
    cur_val, cur_val_acc = val_score(llm, task, skill, val)
    print(f"\nstart   val={cur_val_acc:.0%} (fields {cur_val:.0%})  test={accuracy(before):.0%}\n")

    step = 0
    for epoch in range(1, args.epochs + 1):
        rng.shuffle(train)
        for i in range(0, len(train), BATCH):
            step += 1
            L = learning_rate(step - 1, total_steps)
            print(f"[epoch {epoch} step {step}/{total_steps}] rollout ", end="")
            runs = rollout(llm, task, skill, train[i:i + BATCH])                   # 1. forward
            print(f"batch acc={accuracy(runs):.0%}  lr={L}")
            if all(r["ok"] for r in runs):
                print("   no failures in this batch, nothing to learn")
                continue
            edits = reflect(llm, task, skill, runs, rejected, L)                   # 2. backward
            candidate, applied = apply_edits(skill, edits)                         # 3. bounded edit
            if not applied:
                print("   no applicable edits")
                continue
            print("   validating candidate ", end="")
            cand_val, cand_acc = val_score(llm, task, candidate, val)              # 4. gate
            accepted = cand_val > cur_val                                          # strictly better
            print()
            for e in applied:
                print(f"   {'+' if accepted else 'x'} {e['op']}: {(e.get('content') or e.get('target'))[:110]}")
            print(f"   val {cur_val_acc:.0%} -> {cand_acc:.0%}  (fields {cur_val:.0%} -> {cand_val:.0%})  "
                  f"{'ACCEPTED' if accepted else 'REJECTED, rolled back'}")
            history.append({"step": step, "lr": L, "edits": applied, "val_before": cur_val,
                            "val_after": cand_val, "val_acc_after": cand_acc, "accepted": accepted})
            if accepted:
                skill, cur_val, cur_val_acc = candidate, cand_val, cand_acc
            else:
                rejected.append({"edits": applied, "val_drop": round(cur_val - cand_val, 3)})

    print("\nfinal skill on held-out test ", end="")
    after = rollout(llm, task, skill, test)
    save_runs(out_dir / "test_after.jsonl", after)
    (out_dir / "best_skill.md").write_text(skill)
    (out_dir / "run_log.json").write_text(json.dumps(history, indent=2))
    summary = {"task": args.task, "target": TARGET_MODEL, "optimizer": OPTIMIZER_MODEL,
               "test_before": accuracy(before), "test_after": accuracy(after),
               "test_fields_before": partial_score(before), "test_fields_after": partial_score(after),
               "accepted_edits": sum(h["accepted"] for h in history), "steps": len(history),
               "model_calls": llm.calls, "tokens": getattr(llm, "tokens", 0),
               "minutes": round((time.time() - t0) / 60, 1)}
    (out_dir / "summary.json").write_text(json.dumps(summary, indent=2))
    if not args.mock:  # the deployable artifact
        (HERE / "skills").mkdir(exist_ok=True)
        (HERE / "skills" / f"{args.task}.md").write_text(skill)

    print(f"\n\nTEST ACCURACY  {accuracy(before):.0%} -> {accuracy(after):.0%}   "
          f"(fields {partial_score(before):.0%} -> {partial_score(after):.0%}; model weights unchanged)")
    print(f"accepted edits: {summary['accepted_edits']}   model calls: {llm.calls}   "
          f"tokens: {summary['tokens']}   time: {summary['minutes']} min")
    print(f"wrote {out_dir}/" + ("" if args.mock else f" and skills/{args.task}.md") + "\n")
    print(skill)


if __name__ == "__main__":
    main()
