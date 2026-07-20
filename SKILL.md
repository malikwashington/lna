---
name: lna
description: "lna = likelihood / next-action — a second-opinion decision layer over any list of opportunities (leads, roles, grants, venues, deals). Where a fit score answers 'is this a match?', lna answers 'if I act NOW, what's the probability it works — and what single move most raises the odds?' Judges estimate P(success | act now), the highest-leverage top_action, and the boosted odds after it; output is a list ranked by LEVERAGE. Invoke when the user asks which of their options to work first, what to do next on a pipeline, whether something is worth pursuing now, or says /lna."
---

# lna — likelihood / next-action

Fit tells you what matches; it doesn't tell you what to *do*. lna is the
second opinion: for each item, independent judges estimate the odds of
success if you act now (`likelihood`), name the single highest-leverage step
(`top_action`), and estimate the odds after taking it
(`likelihood_with_action`). The difference between the two numbers is the
**leverage** of the action — and that's how the output ranks: not "what's
best" but "where does effort move the needle most." Recommendations only;
nothing here acts.

## When to use
- "Which of these 50 leads/roles/grants/venues do I work first?"
- "What's the one thing that would most improve my odds on X?"
- A second opinion on an already-scored queue (e.g. docket-llm output):
  fit and likelihood diverge in both directions, and the divergence is the
  insight — a perfect fit can be a long shot, a mediocre fit a near-lock.
- NOT for: scoring fit/quality against criteria (that's `docket-llm`),
  taking any action, or items with no context to reason from.

## The rules (contract)
1. `records/{item_id}.json` is the source of state: mission + config hash,
   every run's estimates, the averages, leverage, spread, flags, and
   `action_taken` once the human does the thing. `out/next_actions.md` is a
   projection of all records.
2. Dedup: `emit` skips items with an existing record (`--rejudge` to redo;
   a changed likelihood prints a loud old→new diff).
3. Human gate: this skill recommends; the human acts. When they've done the
   thing, record it: `python3 lna.py did <item_id> --note "..."` — the only
   writer of `action_taken`; the doc never marks anything done on its own.
   Re-judge afterwards (`emit --rejudge`) to see the new odds.
4. All tuning lives in `lna.yaml` — the mission (what "success" means),
   actor_context (who's acting, with what resources), calibration notes,
   runs, disagreement threshold. The mission line is load-bearing: judges
   estimate exactly the probability it defines.
5. Likelihood is DISTINCT from fit by design — judges are instructed never
   to anchor on a fit score in the givens. Two advisory findings surface run
   disagreement rather than averaging it away: `judge_disagreement` (the runs'
   likelihoods split past your threshold) and `actions_diverge` (the runs
   proposed genuinely different next moves — a coarse content-word heuristic,
   high-recall, meant to prompt a read, never touching the odds or ranking).

## What you (Claude) do when invoked
**Phase 0 — intake:**
- No `lna.yaml`? Draft it WITH the user: pin down the mission as a precise
  conditional probability ("P(booked show | outreach this week)", "P(first
  interview | apply now)"), who the actor is, and any calibration facts they
  know (channel norms, timing windows). Confirm before running.
- Build `items.json` from whatever exists — a CRM export, a scored.json from
  docket-llm (map fit scores into `givens`), a pasted list. Every item needs
  enough `context` to reason about odds; refuse bare names and say why.
- `pip install -r requirements.txt` once if missing (just pyyaml).

**The loop (you run all of it):**
```bash
# 1. emit — dedup vs records/, write the self-describing worklist
python3 lna.py emit

# 2. JUDGE — YOU are the judge: for each of the N runs (N = config `runs`),
#    spawn a FRESH subagent that reads ONLY out/lna_requests.json and writes
#    out/lna_responses_<k>.json. One subagent per run — correlated runs
#    defeat the averaging.

# 3. ingest — validate loud, average, flag disagreement, rank by leverage
python3 lna.py ingest
```

**Phase 3 — hand off (in chat):**
Present the top of `out/next_actions.md` conversationally: the 3-5 items
where an action buys the most, each as "do X, it moves your odds from A to
B". Call out judge_disagreement items explicitly — read those runs with the
user rather than trusting the average. The user picks what to do; nothing
is ever executed by the skill.

## Principles (standing instructions to the judge — generic)
- Estimate actionability, not fit; never anchor on a fit score in the givens.
- One action, concrete, doable by THIS actor. A list is a dodge.
- Boost calibration: named-gap closure at thin competition → large; warm
  intro at a crowded target → large; framing alone → +5-10; verification-only
  → none. The with-action ceiling on a cold channel stays modest.
- The `why` is one sentence a human can act on, not a summary.
