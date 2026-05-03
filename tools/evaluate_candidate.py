#!/usr/bin/env python3
"""
Evaluate a candidate config with fixed budget and repeated runs.
Output: summary.csv, summary_mean_std.json, and per-run folders with full logs.
"""

import argparse
import json
import os
import subprocess
import sys
from pathlib import Path


METRIC_KEYS = [
    "total_generated",
    "total_compiled_ok",
    "valid_rate",
    "unique_valid_rate",
    "duplicate_rate",
    "total_failures",
    "unique_failure_count",
    "repair_attempted_count",
    "repair_success_count",
    "repair_success_rate",
    "cache_hit_count",
    "cache_miss_count",
    "avg_time_per_program",
    "llm_overhead",
]


def load_config(path: str) -> dict:
    with open(path, "r", encoding="utf-8") as f:
        import yaml
        return yaml.safe_load(f)


def save_config(config: dict, path: str):
    import yaml
    with open(path, "w", encoding="utf-8") as f:
        yaml.dump(config, f, default_flow_style=False, allow_unicode=True)


def run_one(candidate_path: str, run_dir: str, budget_programs: int, repo_root: str, target_binary: str = None) -> dict:
    """Run fuzzing once with candidate config; return metrics dict."""
    config = load_config(candidate_path)
    config["fuzzing"] = config.get("fuzzing", {})
    config["fuzzing"]["num"] = budget_programs
    config["fuzzing"]["total_time"] = 48
    config["fuzzing"]["resume"] = True
    config["fuzzing"]["otf"] = True
    target = target_binary or config.get("fuzzing", {}).get("target_name") or "/usr/bin/g++"
    config["fuzzing"]["target_name"] = target
    eval_config_path = os.path.join(run_dir, "eval_config.yaml")
    os.makedirs(run_dir, exist_ok=True)
    save_config(config, eval_config_path)

    cmd = [
        sys.executable,
        os.path.join(repo_root, "Fuzz4All", "fuzz.py"),
        "--config", eval_config_path,
        "main_with_config",
        "--folder", run_dir,
        "--batch_size", str(config.get("llm", {}).get("batch_size", 10)),
        "--model_name", config.get("llm", {}).get("model_name", "bigcode/starcoderbase"),
        "--target", target,
    ]
    env = os.environ.copy()
    env["PYTHONPATH"] = repo_root + os.pathsep + env.get("PYTHONPATH", "")
    subprocess.run(cmd, cwd=repo_root, env=env, check=True)

    metrics_path = os.path.join(run_dir, "metrics.json")
    if os.path.exists(metrics_path):
        with open(metrics_path, "r", encoding="utf-8") as f:
            return json.load(f)
    return {}


def main():
    parser = argparse.ArgumentParser(description="Evaluate candidate config with fixed budget")
    parser.add_argument("--candidate", required=True, help="Path to candidate YAML config")
    parser.add_argument("--out", required=True, help="Output directory (e.g. outputs/eval_c1)")
    parser.add_argument("--budget_programs", type=int, default=2000, help="Max programs per run")
    parser.add_argument("--repeats", type=int, default=3, help="Number of repeated runs")
    parser.add_argument("--target", default=None, help="Target binary (e.g. /usr/bin/g++); overrides config")
    args = parser.parse_args()

    repo_root = str(Path(__file__).resolve().parent.parent)
    os.makedirs(args.out, exist_ok=True)

    rows = []
    for r in range(args.repeats):
        run_dir = os.path.join(args.out, f"run_{r}")
        print(f"Run {r + 1}/{args.repeats} -> {run_dir}")
        metrics = run_one(args.candidate, run_dir, args.budget_programs, repo_root, args.target)
        row = {"run_id": r}
        for k in METRIC_KEYS:
            row[k] = metrics.get(k)
        rows.append(row)

    summary_path = os.path.join(args.out, "summary.csv")
    with open(summary_path, "w", encoding="utf-8") as f:
        header = ["run_id"] + METRIC_KEYS
        f.write(",".join(header) + "\n")
        for row in rows:
            f.write(",".join(str(row.get(h, "")) for h in header) + "\n")

    mean_std = {}
    for k in METRIC_KEYS:
        vals = [row.get(k) for row in rows if row.get(k) is not None]
        try:
            vals = [float(v) for v in vals]
        except (TypeError, ValueError):
            mean_std[k] = {"mean": None, "std": None}
            continue
        if not vals:
            mean_std[k] = {"mean": None, "std": None}
            continue
        n = len(vals)
        mean = sum(vals) / n
        variance = sum((x - mean) ** 2 for x in vals) / n if n > 0 else 0
        std = variance ** 0.5
        mean_std[k] = {"mean": round(mean, 6), "std": round(std, 6)}
    mean_std_path = os.path.join(args.out, "summary_mean_std.json")
    with open(mean_std_path, "w", encoding="utf-8") as f:
        json.dump(mean_std, f, indent=2)

    print(f"Wrote {summary_path} and {mean_std_path}")


if __name__ == "__main__":
    main()
