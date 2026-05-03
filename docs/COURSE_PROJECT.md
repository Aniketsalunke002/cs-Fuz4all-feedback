# Course Project: Error-Guided Repair Extension

This document describes how to run the baseline, repair-enabled fuzzing, the evaluator, and the AI-driven search harness. All of this runs on HPC without Docker and does not require GPT-4 or any paid API.

## Prerequisites

- Conda env: `conda activate fuzz4all`
- Run from repo root: `~/fuzz4all` (or your clone path)
- C++ compiler (e.g. `g++`) available as the target binary

## Run baseline (no repair)

Same behavior as before the extension when repair is disabled:

```bash
python Fuzz4All/fuzz.py --config config/cpp_demo.yaml main_with_config \
  --folder outputs/baseline_run \
  --batch_size 10 \
  --model_name bigcode/starcoderbase \
  --target /usr/bin/g++
```

- No `repair` section in config, or `repair.enabled: false`, keeps baseline unchanged.
- Outputs: `outputs/baseline_run/*.fuzz`, `log.txt`, `log_generation.txt`, `log_validation.txt`, `records.jsonl`, `metrics.json`.

## Run with repair enabled

```bash
python Fuzz4All/fuzz.py --config config/cpp_repair_demo.yaml main_with_config \
  --folder outputs/repair_run \
  --batch_size 10 \
  --model_name bigcode/starcoderbase \
  --target /usr/bin/g++
```

- Uses the same local LLM (StarCoder/Ollama) for both generation and repair.
- When a program fails to compile and repair is enabled, the pipeline may create `*_r1.fuzz`, `*_r2.fuzz` (repaired attempts). If repair succeeds, that program counts as valid.
- `metrics.json` will include `repair_attempted_count`, `repair_success_count`, `cache_hit_count`, `cache_miss_count`.
- With `repair.cache: true`, repeated failure signatures reuse cached repairs.

## Config: repair section

In any YAML config you can add:

```yaml
repair:
  enabled: true
  max_attempts: 2
  template_id: T1
  include_stderr: true
  error_gate: "compile_error"
  cache: true
  timeout_sec: 3
  max_tokens: 512
  temperature: 0.7
```

- **template_id**: T1 (minimal patch) … T6 (timeout defense). Default T1.
- **error_gate**: which failures trigger repair: `compile_error`, `ice`, `crash`, `timeout`, `all_non_timeout`, etc.

## Metrics and logs

- **records.jsonl**: One JSON object per program (and per repair attempt). Fields: `program_id`, `is_repair`, `repair_attempt_index`, `compile_status`, `signature`, `exit_code`, `elapsed_sec`, `program_hash`, `bytes`, `llm_calls_used`, `timestamp`.
- **metrics.json**: End-of-run summary: `total_generated`, `total_compiled_ok`, `valid_rate`, `unique_valid_rate`, `duplicate_rate`, `total_failures`, `unique_failure_count`, `repair_attempted_count`, `repair_success_count`, `repair_success_rate`, `cache_hit_count`, `cache_miss_count`, `avg_time_per_program`.
- **Note on `unique_failure_count`**: counts distinct failure signatures across *all* generation and repair attempts in the run, so it can exceed `total_failures` (which counts programs whose final disposition is "failed"). For example, a program that triggers two distinct compile errors during its repair attempts but is ultimately recovered contributes 0 to `total_failures` and up to 2 to `unique_failure_count`.

## Evaluate a candidate config

Fixed budget, repeated runs, mean/std of metrics:

```bash
python tools/evaluate_candidate.py --candidate candidates/c1.yaml --out outputs/eval_c1 --budget_programs 2000 --repeats 3
```

- Runs the fuzzing pipeline with the given candidate YAML; each run uses `budget_programs` as the program budget.
- Outputs:
  - `outputs/eval_c1/run_0`, `run_1`, `run_2`: full logs and `metrics.json` per run.
  - `outputs/eval_c1/summary.csv`: one row per repeat.
  - `outputs/eval_c1/summary_mean_std.json`: mean and std for each metric.

The evaluator is intended to stay stable: metric names are not changed once established.

## AI-driven search round

1. Put a round file (e.g. `candidates/round_01.json`) with a list of candidates:

```json
[
  {"name": "c1", "gen": {"llm": {"batch_size": 10}}, "repair": {"enabled": true, "max_attempts": 1}},
  {"name": "c2", "gen": {}, "repair": {"enabled": false}}
]
```

2. Run the round:

```bash
python tools/run_search_round.py --round candidates/round_01.json --budget_programs 500 --repeats 1
```

- For each candidate, a YAML is materialized under `candidates/materialized/<name>.yaml`, then `evaluate_candidate.py` is run.
- Results are appended to `outputs/search/search_log.jsonl`.
- After all candidates, `outputs/search/next_prompt.md` is generated with:
  - A compact table of top/bottom candidates and their metrics
  - Sample failure signature clusters
  - Instructions for an AI to propose the next round in the same JSON format

You can copy `next_prompt.md` into ChatGPT/Cursor and paste the next round JSON back (e.g. `candidates/round_03.json`). No paid API is called from the code.

## Safety and resource limits

- **Timeouts**: Compilation validation uses a 5-second timeout; repair does not run the compiler indefinitely.
- **File size**: Truncation is applied to stderr (e.g. 20 lines / 4 KB) and to signatures to avoid huge logs.
- **HPC**: Run on compute nodes (e.g. via Slurm). Request sufficient memory (e.g. `--mem=64G` or more for large models) and a reasonable time limit. Use a smaller `batch_size` (e.g. 10) if you hit OOM.
- **No Docker**: All paths and commands assume a local setup; no container paths are required.
