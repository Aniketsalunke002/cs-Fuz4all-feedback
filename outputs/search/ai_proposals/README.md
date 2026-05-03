# AI proposals — search-loop evidence

This folder records the **AI-driven search loop** described in the project README
(`§AI search script`). It is the on-disk evidence that an LLM was used as the
proposal engine between search rounds, and that its proposals were then evaluated
automatically under the same fixed evaluator (`tools/evaluate_candidate.py`).

We used Claude (Anthropic's LLM) as the proposal engine in the AI search loop.
After each round, the evaluator summarized ranked candidate metrics and common
failure signatures, and the LLM proposed the next batch of repair-policy
configurations within the fixed candidate schema. These proposed configurations
were then evaluated automatically under the same fixed evaluator. Across two
rounds, we evaluated 12 candidates in total; the AI-proposed second-round
ablations helped validate the repair-policy choices underlying the 7B headline
result.

## Loop shape

```
candidates/round_NN.json
        │
        ▼
tools/run_search_round.py        ── evaluates each candidate with the fixed evaluator
        │
        ├─► outputs/search/eval_<name>/         (per-candidate run logs + metrics)
        ├─► outputs/search/search_log.jsonl     (one row per evaluated candidate)
        └─► outputs/search/next_prompt.md       (ranked metrics + failure signatures)
                │
                ▼
        LLM proposal (Claude)                  ── reads next_prompt.md, proposes the next JSON batch
                │
                ▼
        candidates/round_(NN+1).json           (committed to repo)
```

The proposal step is the only one that requires a human-in-the-loop; everything
else is automated.

## Files in this folder

| File | What it records |
|---|---|
| `round_01_to_round_02.md` | Full transition between round 1 and round 2: the round-1 evaluator summary fed to the LLM, the LLM-proposed `round_02.json`, and the round-2 outcome. |

## Provenance

- Round-1 candidates (3): hand-written at midterm to sanity-check the harness — see
  [`candidates/round_01.json`](../../../candidates/round_01.json).
- Round-2 candidates (9): proposed by Claude after round 1 — see
  [`candidates/round_02.json`](../../../candidates/round_02.json) and the transition
  document `round_01_to_round_02.md`.
- Per-candidate metrics for all 12 candidates: appended to
  [`outputs/search/search_log.jsonl`](../search_log.jsonl).
- Latest evaluator feedback: [`outputs/search/next_prompt.md`](../next_prompt.md).
