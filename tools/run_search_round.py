#!/usr/bin/env python3
"""
AI-driven search harness: evaluate a list of candidate configs from a JSON file,
then generate next_prompt.md for an AI to propose the next round.
No paid API in code.
"""

import argparse
import copy
import json
import os
import subprocess
import sys
from pathlib import Path


def load_json(path: str) -> list:
    with open(path, "r", encoding="utf-8") as f:
        return json.load(f)


def load_yaml(path: str) -> dict:
    import yaml
    with open(path, "r", encoding="utf-8") as f:
        return yaml.safe_load(f)


def save_yaml(data: dict, path: str):
    import yaml
    with open(path, "w", encoding="utf-8") as f:
        yaml.dump(data, f, default_flow_style=False, allow_unicode=True)


def main():
    parser = argparse.ArgumentParser(description="Run search round: evaluate candidates and generate next_prompt.md")
    parser.add_argument("--round", required=True, help="Path to round JSON (e.g. candidates/round_01.json)")
    parser.add_argument("--base_config", default="config/cpp_demo.yaml", help="Base YAML to merge with candidate gen/repair")
    parser.add_argument("--budget_programs", type=int, default=500, help="Programs per evaluation run")
    parser.add_argument("--repeats", type=int, default=1, help="Repeats per candidate")
    args = parser.parse_args()

    repo_root = str(Path(__file__).resolve().parent.parent)
    search_out = os.path.join(repo_root, "outputs", "search")
    materialized_dir = os.path.join(repo_root, "candidates", "materialized")
    os.makedirs(search_out, exist_ok=True)
    os.makedirs(materialized_dir, exist_ok=True)

    candidates = load_json(args.round)
    if not isinstance(candidates, list):
        candidates = [candidates]
    base = load_yaml(os.path.join(repo_root, args.base_config))

    log_path = os.path.join(search_out, "search_log.jsonl")
    results = []

    llm_keys = {"temperature", "batch_size", "model_name", "max_length", "device", "model_folder", "additional_eos_tokens"}
    fuzzing_keys = {"num", "total_time", "resume", "otf", "evaluate", "log_level", "prompt_strategy", "output_folder", "target_name"}

    for c in candidates:
        name = c.get("name", "unknown")
        gen = c.get("gen", {})
        repair = c.get("repair", {})
        config = copy.deepcopy(base)
        if gen:
            for k, v in gen.items():
                if k == "llm" and isinstance(v, dict):
                    config.setdefault("llm", {}).update(v)
                elif k == "fuzzing" and isinstance(v, dict):
                    config.setdefault("fuzzing", {}).update(v)
                elif k == "target" and isinstance(v, dict):
                    config.setdefault("target", {}).update(v)
                elif k in llm_keys:
                    config.setdefault("llm", {})[k] = v
                elif k in fuzzing_keys:
                    config.setdefault("fuzzing", {})[k] = v
                else:
                    config[k] = v
        if repair:
            config.setdefault("repair", {}).update(repair)
        mat_path = os.path.join(materialized_dir, f"{name}.yaml")
        save_yaml(config, mat_path)

        eval_out = os.path.join(search_out, f"eval_{name}")
        cmd = [
            sys.executable,
            os.path.join(repo_root, "tools", "evaluate_candidate.py"),
            "--candidate", mat_path,
            "--out", eval_out,
            "--budget_programs", str(args.budget_programs),
            "--repeats", str(args.repeats),
        ]
        subprocess.run(cmd, cwd=repo_root, check=True)

        metrics_path = os.path.join(eval_out, "summary_mean_std.json")
        metrics = {}
        if os.path.exists(metrics_path):
            with open(metrics_path, "r", encoding="utf-8") as f:
                metrics = json.load(f)
        row = {"name": name, "metrics": metrics, "eval_out": eval_out}
        results.append(row)
        with open(log_path, "a", encoding="utf-8") as lf:
            lf.write(json.dumps(row) + "\n")

    valid_rates = []
    for r in results:
        m = r.get("metrics", {})
        vr = m.get("valid_rate", {})
        if isinstance(vr, dict) and vr.get("mean") is not None:
            valid_rates.append((r["name"], vr["mean"]))
        else:
            valid_rates.append((r["name"], None))
    valid_rates.sort(key=lambda x: (x[1] is None, -(x[1] or 0)))
    top = valid_rates[:5]
    bottom = valid_rates[-5:] if len(valid_rates) >= 5 else valid_rates

    signatures = set()
    for r in results:
        rec_path = os.path.join(r["eval_out"], "run_0", "records.jsonl")
        if os.path.exists(rec_path):
            with open(rec_path, "r", encoding="utf-8") as f:
                for line in f:
                    try:
                        rec = json.loads(line)
                        sig = rec.get("signature", "")
                        if sig:
                            signatures.add(sig[:200])
                    except Exception:
                        pass
    common_sigs = list(signatures)[:15]

    next_md = os.path.join(search_out, "next_prompt.md")
    with open(next_md, "w", encoding="utf-8") as f:
        f.write("# Search round results\n\n")
        f.write("## Top candidates (by valid_rate mean)\n\n")
        f.write("| name | valid_rate mean |\n|------|------------------|\n")
        for name, vr in top:
            f.write(f"| {name} | {vr} |\n")
        f.write("\n## Bottom candidates\n\n")
        f.write("| name | valid_rate mean |\n|------|------------------|\n")
        for name, vr in bottom:
            f.write(f"| {name} | {vr} |\n")
        f.write("\n## Common failure signature samples\n\n")
        for sig in common_sigs:
            f.write(f"- `{sig}`\n")
        f.write("\n---\n\n")
        f.write("Please propose the next round of candidate configs in the same JSON format.\n")
        f.write("Format: a JSON array of objects with \"name\", \"gen\", and \"repair\" keys.\n")
        f.write("\"gen\" can override llm/fuzzing; \"repair\" can override repair section.\n")
        f.write("Save as candidates/round_NN.json (use the next free round number).\n")

    print(f"Wrote {next_md}")


if __name__ == "__main__":
    main()
