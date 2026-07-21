# lna — likelihood / next-action

**A second-opinion decision layer.** Fit scores answer "is this a match?"
lna answers the question that actually orders your week: **"if I act on this
now, what's the probability it works — and what single move most raises the
odds?"**

For each item, independent LLM judges estimate:
- `likelihood` — P(success | act now), where "success" is the precise
  conditional probability your `lna.yaml` mission line defines
- `top_action` — the single highest-leverage step (one step, concrete,
  doable by you — never a list)
- `likelihood_with_action` — the odds after completing it

`leverage = with_action − likelihood` is what the output ranks by: not
"what's best" but **where effort moves the needle most**. A 45→75 with one
warm introduction outranks an 80 that no action can improve.

## Origin
I built lna for my own job search — to surface, for each role, the single
next action most likely to increase my odds of landing an interview (a
referral, a gap-closing artifact, a better-timed application) rather than just
ranking roles by fit. The mechanism generalizes to any pipeline where you have
more options than time — leads, grants, venues, deals — so it ships as a
general decision layer, but that concrete question is what it was made to answer.

This standalone skill rebuilds the likelihood-plus-next-action model I run as
one component of my private job-search pipeline — a larger, multi-module system
on my real data. Same model, rebuilt minimally with the personal inputs
stripped out.

I built it to run entirely on my Claude Code subscription and without incurring
additional costs: the judging is done by Claude Code subagents, not a billable
Anthropic API key, so a full run adds nothing to my bill.

## Why likelihood ≠ fit
Judges are explicitly instructed never to anchor on a fit score passed in
the givens. The divergence is the insight, in both directions: a
perfect-fit role at a famous company can be a long shot (cold channel,
thousand applicants), and a mediocre-fit lead can be a near-lock (past
client, warm path, urgent need). If likelihood always tracked fit, this
layer would be redundant — its value is exactly the items where they split.

## How it works
1. **emit** — `lna.yaml` (mission, actor context, calibration notes) +
   `items.json` (each item with real context and optional `givens` like
   existing scores) become a self-describing worklist; items with an
   existing record are skipped (`--rejudge` to redo).
2. **judge** — lna emits a worklist requesting N independent runs (default 3)
   and ingests whatever responses come back; *running* the judges — Claude Code
   subagents, an API, or a human — is the caller's step (one fresh read per
   run). Each run estimates both probabilities + the action. The with-action
   boost is calibrated: closing a named gap at thin competition → large; warm
   intro at a crowded target → large; framing alone → small; verification-only
   → none.
3. **ingest** — validates loud (out-of-range numbers, an "action" that
   lowers the odds, empty responses all rejected; zero valid aborts),
   averages the runs, computes leverage, and raises two advisory flags:
   `judge_disagreement` when the runs' likelihoods split wider than your
   threshold, and `actions_diverge` when the runs proposed genuinely
   different next moves — both are findings to read, never noise to average
   away. Writes `records/{id}.json` (full provenance, every run) and
   `out/next_actions.md` ranked by leverage.
4. **act, then re-judge** — do the top action, record it with `python3
   lna.py did <id> --note "..."`, then `python3 lna.py emit --rejudge`. The
   recorded note is fed back to the judge as `progress_since_last_estimate`,
   so the new estimate reflects the step you took — that's how the odds
   actually move between rounds (not by re-running identical inputs).

Verbatim `out/next_actions.md` from running the shipped example (a studio
triaging three leads) — the Markdown `**` markers are the file's own:
```
# next actions — ranked by LEVERAGE (what the action buys), then by odds

likelihood = P(success | act now); with_action = after the top action; leverage = the difference. Recommendations only — you act, this doesn't.

## lead-fern-cafe-2 — Fern Cafe — second location
- odds now **58.3** -> with action **82.3** (leverage +24.0, spread 7.0)
- **do:** Call the owner about the second location and offer the menu and signage package
- why: A credited past client who gave you her direct number is the warmest path in this list.
- headwinds: No budget or timeline confirmed; No formal vendor process yet

## lead-harbor-hotel — Harbor Hotel — lobby rebrand
- odds now **44.3** -> with action **62.3** (leverage +18.0, spread 8.0)
- **do:** Send a follow-up naming one concrete lobby and menu idea tied to the summer timeline
- why: Inbound interest is real but the intro email has gone unanswered for nine days.
- headwinds: Budget not stated; Compressed summer timeline; Unanswered intro email

## lead-brightpath — BrightPath Software — website overhaul
- odds now **22.3** -> with action **35.7** (leverage +13.4, spread 7.0) ⚠ runs proposed different actions — read the record
- **do:** Decide not to bid cold and instead find a warm introduction to the buyer before the RFP closes
- why: Seven bidders and no software references make a cold proposal a long shot.
- headwinds: No software references; Seven competing bidders; Three-week deadline
```
The warm repeat client outranks the higher-*fit* inbound lead because the
action buys more there; BrightPath's runs split on the move, so it's flagged
to read rather than averaged into a false consensus.

## What it does NOT do
- It never takes an action, sends anything, or marks anything done. The
  output is a recommendation list; `action_taken` is set by you, via
  `python3 lna.py did <item_id>` after you've actually done the thing.
- It doesn't measure fit or quality — pair it with `docket-llm` for that
  (its scored output maps straight into `givens`).
- No network, no API key. Local files in, local files out.

## Who it's for / not for
For: anyone with more options than time — sales pipelines, job searches,
grant seeking, booking outreach, deal flow — who wants "work this next, do
this first" with reasoning attached. Not for: items you have no context on
(odds need material), or anyone expecting the tool to act on its answers.

## Setup
```bash
pip install -r requirements.txt   # just pyyaml
cp examples/lna.yaml.example lna.yaml     # define YOUR mission precisely
cp examples/items.json.example items.json # your opportunities, with context
python3 lna.py emit
```
Then follow the printed next-step lines; `SKILL.md` has the full run order.
Real inputs and state (`lna.yaml`, `items.json`, `records/`, `out/`) are
git-ignored; only code and the synthetic example (a fictional design studio
triaging three leads) ship.

## Companion skills
`docket-llm` scores a queue against a rubric (fit); lna is the second
opinion on what to do about it. `tailor-artifacts` often executes the
top_action ("send a tailored pitch"), and `blind-review` checks the artifact
before it goes out. Same worklist pattern throughout — deliberately parallel
implementations, each self-contained.

---
Built with [skill-generator](https://github.com/malikwashington/skill-generator) — a factory
for human-gated LLM judgment pipelines.
