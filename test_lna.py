#!/usr/bin/env python3
"""Offline tests for lna.py — canned fixtures, no network, no API key.
Run: python3 test_lna.py"""

import contextlib
import io
import json
import os
import shutil
import sys
import tempfile

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import lna  # noqa: E402

PASS = 0


def ok(cond, label):
    global PASS
    assert cond, label
    PASS += 1
    print(f"  ok - {label}")


CONFIG = """\
mission: "P(win | act now)"
actor_context: "a small studio"
calibration:
  - "warm paths beat documents"
runs: 2
disagreement_spread: 20
"""

ITEMS = {"items": [
    {"id": "a1", "title": "one", "context": "warm past client", "givens": {"fit": 70}},
    {"id": "a2", "title": "two", "context": "cold rfp, 7 bidders", "givens": {"fit": 88}},
]}


def resp(lk, lwa, action="call the owner"):
    return {"likelihood": lk, "likelihood_with_action": lwa, "top_action": action,
            "why": "warm path", "headwinds": ["timing"], "action_rationale": "direct"}


@contextlib.contextmanager
def sandbox():
    d = tempfile.mkdtemp(prefix="lna-test-")
    old = os.getcwd()
    os.chdir(d)
    try:
        yield d
    finally:
        os.chdir(old)
        shutil.rmtree(d, ignore_errors=True)


def write(path, content):
    os.makedirs(os.path.dirname(path) or ".", exist_ok=True)
    with open(path, "w", encoding="utf-8") as fh:
        fh.write(content if isinstance(content, str) else json.dumps(content))


def run_main(argv):
    out, err = io.StringIO(), io.StringIO()
    code = 0
    with contextlib.redirect_stdout(out), contextlib.redirect_stderr(err):
        try:
            code = lna.main(argv)
        except SystemExit as e:
            code = e.code if isinstance(e.code, int) else 1
    return code, out.getvalue(), err.getvalue()


def test_inputs_and_emit():
    print("inputs + emit")
    with sandbox():
        write("items.json", ITEMS)
        # colon-trap mission
        write("lna.yaml", CONFIG.replace('"P(win | act now)"', "\n  note: nested"))
        code, _, err = run_main(["emit"])
        ok(code != 0 and "mapping" in err, "dict mission trap fails loud")
        write("lna.yaml", CONFIG)
        # unsafe id / dup / empty context
        write("items.json", {"items": [{"id": "../x", "context": "c"}]})
        code, _, err = run_main(["emit"])
        ok(code != 0 and "filenames" in err, "unsafe id rejected")
        write("items.json", {"items": [{"id": "a1", "context": " "}]})
        code, _, err = run_main(["emit"])
        ok(code != 0 and "context" in err, "empty context refused")
        write("items.json", ITEMS)
        code, _, _ = run_main(["emit"])
        wl = json.load(open("out/lna_requests.json"))
        ok(code == 0 and "mission" in wl and "instructions" in wl
           and wl["requests"]["a2"]["givens"]["fit"] == 88,
           "worklist self-describing; givens travel")
        # dedup + --rejudge
        write("records/a1.json", {"item_id": "a1"})
        run_main(["emit"])
        ok(set(json.load(open("out/lna_requests.json"))["requests"]) == {"a2"},
           "dedup skips recorded items")
        run_main(["emit", "--rejudge"])
        ok(set(json.load(open("out/lna_requests.json"))["requests"]) == {"a1", "a2"},
           "--rejudge includes existing")


def test_response_validation():
    print("response validation")
    ids = {"a1"}
    valid, _ = lna.validate_responses(
        {"responses": {"responses": {"a1": resp(50, 70)}}}, ids)
    ok(set(valid) == {"a1"}, "double-wrapped responses auto-unwrap")
    for label, bad in [
            ("likelihood out of range", resp(150, 160)),
            ("with_action out of range", resp(50, 400)),
            ("action lowers the odds", resp(70, 50)),
            ("empty top_action", resp(50, 70, action="  "))]:
        valid, probs = lna.validate_responses({"a1": bad}, ids)
        ok(valid == {} and probs, f"{label} rejected")
    valid, _ = lna.validate_responses({"a1": resp(60, 60)}, ids)
    ok(set(valid) == {"a1"}, "no-boost (equal) is legitimate")
    # an item literally named "responses" is NOT swallowed by the unwrapper
    valid, _ = lna.validate_responses({"responses": resp(50, 70)}, {"responses"})
    ok(set(valid) == {"responses"},
       "item id 'responses' judged, not treated as a wrapper")


def test_ingest_leverage_and_disagreement():
    print("ingest: leverage ranking + disagreement")
    with sandbox():
        write("lna.yaml", CONFIG)
        write("items.json", ITEMS)
        run_main(["emit"])
        # zero valid aborts
        write("out/lna_responses_1.json", {"responses": {}})
        code, _, err = run_main(["ingest"])
        ok(code != 0 and "zero valid" in err, "zero-valid ingest aborts loud")
        ok(not os.path.exists("records/a1.json"), "aborted ingest wrote nothing")
        # a1: judges agree, big leverage; a2: judges split 30 on likelihood
        write("out/lna_responses_1.json", {"responses": {
            "a1": resp(50, 80), "a2": resp(70, 75)}})
        write("out/lna_responses_2.json", {"responses": {
            "a1": resp(54, 84), "a2": resp(40, 45)}})
        code, out_s, _ = run_main(["ingest"])
        ok(code == 0, "ingest succeeds")
        r1 = json.load(open("records/a1.json"))
        ok(r1["likelihood"] == 52.0 and r1["likelihood_with_action"] == 82.0
           and r1["leverage"] == 30.0, "averages + leverage computed in code")
        ok(r1["flags"] == [], "agreeing judges: no flag")
        r2 = json.load(open("records/a2.json"))
        ok("judge_disagreement" in r2["flags"] and r2["run_spread"] == 30.0,
           "30-point split flagged, not averaged away silently")
        ok("ATTN" in out_s, "disagreement called out loud at ingest")
        doc = open("out/next_actions.md").read()
        ok(doc.index("a1") < doc.index("a2"),
           "ranked by leverage: +30 outranks the flagged low-leverage item")
        ok("judges disagreed" in doc, "flag visible in the actions doc")
        ok("Recommendations only" in doc or "you act" in doc,
           "doc states the human gate")
        # re-ingest diffs loudly and preserves created_at
        created = r1["created_at"]
        write("out/lna_responses_2.json", {"responses": {
            "a1": resp(80, 90), "a2": resp(40, 45)}})
        code, out_s, _ = run_main(["ingest"])
        r1b = json.load(open("records/a1.json"))
        ok("CHANGED a1" in out_s and r1b["created_at"] == created,
           "re-judge prints old->new diff, created_at preserved")
        # runs agreeing on odds but split on the ACTION are flagged
        write("out/lna_responses_1.json", {"responses": {
            "a1": resp(50, 70, action="call the owner"),
            "a2": resp(40, 45)}})
        write("out/lna_responses_2.json", {"responses": {
            "a1": resp(52, 72, action="send a portfolio"),
            "a2": resp(40, 45)}})
        run_main(["ingest"])
        r1c = json.load(open("records/a1.json"))
        ok("actions_diverge" in r1c["flags"],
           "split top_action flagged even when the odds agree")
        ok("different actions" in open("out/next_actions.md").read(),
           "action divergence visible in the doc")
        # `did` is the human's affordance: sets action_taken + refreshes the doc
        code, out_s, _ = run_main(["did", "a1", "--note", "called; she wants a quote"])
        r1d = json.load(open("records/a1.json"))
        ok(code == 0 and r1d["action_taken"]["note"] == "called; she wants a quote",
           "did records the human's action")
        ok("action taken" in open("out/next_actions.md").read(),
           "doc reflects the taken action")
        code, _, err = run_main(["did", "nope"])
        ok(code != 0 and "no record" in err, "did on unknown id fails loud")
        # malformed record (no top_actions) + no --note: clean die, not a traceback
        write("records/broken.json", {"item_id": "broken"})
        code, _, err = run_main(["did", "broken"])
        ok(code != 0 and "--note" in err, "did on malformed record dies with guidance")
        code, _, _ = run_main(["did", "broken", "--note", "called them"])
        ok(code == 0, "did on malformed record works when --note supplies the text")


def test_cold_start():
    print("cold start")
    with sandbox():
        write("lna.yaml", CONFIG)
        code, _, err = run_main(["ingest"])
        ok(code != 0 and "emit" in err, "ingest before emit fails with guidance")
        write("items.json", ITEMS)
        run_main(["emit"])
        code, _, err = run_main(["ingest"])
        ok(code != 0 and "judge" in err, "ingest before judging fails with guidance")


def test_review_fixes():
    print("review fixes (stale-file / bool / actions_diverge)")
    # 1. emit clears response files from a PRIOR judging cycle (they would
    #    otherwise blend into the new average via ingest's glob).
    with sandbox():
        write("lna.yaml", CONFIG)
        write("items.json", ITEMS)
        run_main(["emit"])
        for k in (1, 2, 3):
            write(f"out/lna_responses_{k}.json",
                  {"responses": {"a1": resp(10, 10), "a2": resp(10, 10)}})
        run_main(["emit"])
        stale = [f for f in os.listdir("out") if f.startswith("lna_responses")]
        ok(stale == [], "emit clears stale response files from a prior cycle")

    # 2. a boolean score is rejected, never coerced to 1.0/0.0.
    with sandbox():
        write("lna.yaml", CONFIG)
        write("items.json", ITEMS)
        run_main(["emit"])
        bad = {"likelihood": True, "likelihood_with_action": 50, "top_action": "x",
               "why": "y", "headwinds": ["z"], "action_rationale": "r"}
        write("out/lna_responses_1.json", {"responses": {"a1": bad, "a2": resp(60, 70)}})
        _, _, err = run_main(["ingest"])
        ok("a1: likelihood must be a number" in err, "boolean likelihood rejected, not coerced")
        ok(not os.path.exists("records/a1.json"), "bool-rejected item writes no record")

    # 3. actions_diverge: same move reworded does NOT flag; genuine divergence does.
    with sandbox():
        write("lna.yaml", CONFIG)
        write("items.json", ITEMS)
        run_main(["emit"])
        write("out/lna_responses_1.json", {"responses": {
            "a1": resp(60, 70, "call the owner about the second location"),
            "a2": resp(60, 70, "call the owner")}})
        write("out/lna_responses_2.json", {"responses": {
            "a1": resp(60, 70, "call owner re: second location"),
            "a2": resp(60, 70, "send a portfolio deck")}})
        run_main(["ingest"])
        r1 = json.load(open("records/a1.json"))
        r2 = json.load(open("records/a2.json"))
        ok("actions_diverge" not in r1["flags"], "same-intent rewording is NOT flagged as divergence")
        ok("actions_diverge" in r2["flags"], "genuinely different actions ARE flagged")

    # 2c. synonym rewordings sharing the object word are NOT flagged (content-word overlap,
    #     stopwords dropped) — the accepted-N2 improvement.
    ok(not lna._actions_diverge(["reach out to the owner", "contact the owner"]),
       "synonym rewording sharing the object word is not flagged")
    ok(lna._actions_diverge(["call the owner", "email the venue"]),
       "genuinely different actions still flag")

    # 2d. an all-stopword action keeps its raw tokens rather than collapsing to empty
    #     (regression: it used to drop out of every comparison -> a real split unflagged).
    ok(lna._actions_diverge(["call the owner", "ask them"]),
       "all-stopword action ('ask them') still participates -> genuine split flags")
    ok(lna._actions_diverge(["ask them", "send it"]),
       "two all-stopword actions compare on raw tokens, not both-empty")
    ok(not lna._actions_diverge(["ask them", "ask them"]),
       "identical all-stopword actions do not falsely flag")

    # 3b. headwind merge collapses subsets by WORD SET, not substring — a short
    #     headwind isn't dropped for coincidentally sitting inside a longer one.
    ok(lna._merge_headwinds([{"headwinds": ["informal", "informal so far"]}]) == ["informal so far"],
       "headwind subset ('informal') collapses into its superset")
    ok(set(lna._merge_headwinds([{"headwinds": ["AI", "remaining budget"]}])) == {"AI", "remaining budget"},
       "short headwind not dropped for a coincidental mid-word substring")

    # 3c. a recorded action feeds back into a --rejudge worklist so the odds can
    #     actually move between rounds (did -> emit --rejudge -> new estimate).
    with sandbox():
        write("lna.yaml", CONFIG)
        write("items.json", ITEMS)
        write("records/a1.json", {"item_id": "a1",
                                  "action_taken": {"note": "sent the intro email", "at": "t"}})
        run_main(["emit", "--rejudge"])
        reqs = json.load(open("out/lna_requests.json"))["requests"]
        ok(reqs["a1"]["givens"].get("progress_since_last_estimate") == "sent the intro email",
           "recorded action is fed back into the re-judge request")
        ok("progress_since_last_estimate" not in reqs["a2"]["givens"],
           "an item with no recorded action gets no progress given")

    # 3d. a valid-JSON but wrong-SHAPE record does not crash --rejudge (a record read
    #     off disk is trusted only when it's the dict shape we write).
    with sandbox():
        write("lna.yaml", CONFIG)
        write("items.json", ITEMS)
        write("records/a1.json", ["not", "a", "dict"])            # JSON list
        write("records/a2.json", {"item_id": "a2", "action_taken": "done"})  # non-dict action
        code, _, _ = run_main(["emit", "--rejudge"])
        reqs = json.load(open("out/lna_requests.json"))["requests"]
        ok(code == 0 and "progress_since_last_estimate" not in reqs["a1"]["givens"]
           and "progress_since_last_estimate" not in reqs["a2"]["givens"],
           "wrong-shape records are ignored on --rejudge, never crash")

    # 4. `did` rejects a traversal id (consistency with emit's valid_id gate).
    with sandbox():
        write("lna.yaml", CONFIG)
        write("items.json", ITEMS)
        code, _, err = run_main(["did", "../escape"])
        ok(code != 0 and "invalid item id" in err, "did rejects an unsafe id")


if __name__ == "__main__":
    test_inputs_and_emit()
    test_response_validation()
    test_ingest_leverage_and_disagreement()
    test_cold_start()
    test_review_fixes()
    print(f"\nALL PASS ({PASS} checks)")
