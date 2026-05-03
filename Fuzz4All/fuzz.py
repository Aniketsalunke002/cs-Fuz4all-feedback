"""Main script to run the fuzzing process."""

import hashlib
import json
import os
import time

import click
from rich.traceback import install

install()

from rich.progress import (
    BarColumn,
    MofNCompleteColumn,
    Progress,
    TextColumn,
    TimeElapsedColumn,
)

from Fuzz4All.make_target import make_target_with_config
from Fuzz4All.target.target import CompileStatus, FResult, Target
from Fuzz4All.util.util import load_config_file

try:
    from Fuzz4All.repair.repair import (
        normalize_error_signature,
        repair_config_from_dict,
        repair_llm,
        should_repair,
    )

    HAS_REPAIR = True
except ImportError:
    HAS_REPAIR = False
    from types import SimpleNamespace

    def repair_config_from_dict(d):
        return SimpleNamespace(
            enabled=False,
            max_attempts=1,
            template_id="T1",
            include_stderr=True,
            timeout_sec=3,
            cache=False,
            error_gate="compile_error",
            max_tokens=512,
            temperature=0.7,
        )

    def repair_llm(*args, **kwargs):
        return SimpleNamespace(code="", prompt="", raw_output="")

    def should_repair(*args, **kwargs):
        return False

    def normalize_error_signature(s):
        return s or ""


def is_ollama_model(model_name):
    return model_name.startswith("ollama/") or model_name in ["llama2", "starcoder"]


def write_to_file(fo, file_name):
    try:
        with open(file_name, "w", encoding="utf-8") as f:
            f.write(fo)
    except Exception:
        pass


def _base_id_from_fuzz_name(name: str) -> int:
    """Extract base program id from filename (e.g. 42.fuzz -> 42, 42_r1.fuzz -> 42)."""
    base = name.replace(".fuzz", "").split("_r")[0]
    try:
        return int(base)
    except ValueError:
        return -1


def _load_repair_cache(output_folder: str) -> dict:
    path = os.path.join(output_folder, "repair_cache.json")
    if os.path.exists(path):
        try:
            with open(path, "r", encoding="utf-8") as f:
                return json.load(f)
        except Exception:
            pass
    return {}


def _save_repair_cache(output_folder: str, cache: dict):
    path = os.path.join(output_folder, "repair_cache.json")
    try:
        with open(path, "w", encoding="utf-8") as f:
            json.dump(cache, f, indent=2)
    except Exception:
        pass


def _sha256_text(text: str) -> str:
    return hashlib.sha256(text.encode("utf-8")).hexdigest()


def _append_record(records_path: str, record: dict):
    try:
        with open(records_path, "a", encoding="utf-8") as rf:
            rf.write(json.dumps(record) + "\n")
    except Exception:
        pass


def _status_name(status) -> str:
    return status.name if hasattr(status, "name") else str(status)


def fuzz(
    target: Target,
    number_of_iterations: int,
    total_time: int,
    output_folder: str,
    resume: bool,
    otf: bool,
    repair_config=None,
    max_llm_calls: int = 10000,
):
    if repair_config is None:
        repair_config = repair_config_from_dict({})
    repair_enabled = HAS_REPAIR and repair_config.enabled

    target.initialize()

    records_path = os.path.join(output_folder, "records.jsonl")
    repair_cache = _load_repair_cache(output_folder) if repair_config.cache else {}
    metrics = {
        "total_generated": 0,
        "total_compiled_ok": 0,
        "unique_generated_hashes": set(),
        "unique_valid_hashes": set(),
        "total_failures": 0,
        "unique_failure_signatures": set(),
        "repair_attempted_count": 0,
        "repair_success_count": 0,
        "cache_hit_count": 0,
        "cache_miss_count": 0,
        "llm_calls": 0,
        "generation_llm_calls": 0,
        "repair_llm_calls": 0,
        "program_times": [],
    }
    budget_exhausted = False

    with Progress(
        TextColumn("Fuzzing • [progress.percentage]{task.percentage:>3.0f}%"),
        BarColumn(),
        MofNCompleteColumn(),
        TextColumn("•"),
        TimeElapsedColumn(),
    ) as p:
        task = p.add_task("Fuzzing", total=number_of_iterations)
        count = 0
        start_time = time.time()

        if resume:
            existing = [f for f in os.listdir(output_folder) if f.endswith(".fuzz")]
            n_existing = [
                _base_id_from_fuzz_name(f)
                for f in existing
                if _base_id_from_fuzz_name(f) >= 0
            ]
            if n_existing:
                count = max(n_existing) + 1
            log = f" (resuming from {count})"
            p.console.print(log)

        p.update(task, advance=count)

        while count < number_of_iterations and time.time() - start_time < total_time * 3600:
            if metrics["llm_calls"] >= max_llm_calls:
                budget_exhausted = True
                p.console.print("\n[!] LLM Call Budget Exhausted! Stopping generation.")
                break
                
            metrics["llm_calls"] += 1  # one generation batch call
            metrics["generation_llm_calls"] += 1
            fos = target.generate()
            if not fos:
                target.initialize()
                continue
            prev = []
            for fo in fos:
                if count >= number_of_iterations:
                    break

                program_id = count
                file_name = os.path.join(output_folder, f"{program_id}.fuzz")
                write_to_file(fo, file_name)
                count += 1
                p.update(task, advance=1)
                metrics["total_generated"] += 1

                program_start = time.perf_counter()
                program_hash = _sha256_text(fo)
                metrics["unique_generated_hashes"].add(program_hash)
                program_bytes = len(fo.encode("utf-8"))
                timestamp = time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime())

                if not otf:
                    _append_record(
                        records_path,
                        {
                            "program_id": program_id,
                            "is_repair": False,
                            "repair_attempt_index": None,
                            "compile_status": "NOT_VALIDATED",
                            "signature": "",
                            "exit_code": 0,
                            "elapsed_sec": 0.0,
                            "program_hash": program_hash,
                            "bytes": program_bytes,
                            "llm_calls_used": 1,
                            "timestamp": timestamp,
                        },
                    )
                    continue

                vr = target.validate_individual(file_name)
                compile_status = _status_name(vr.status)
                signature = vr.signature or ""
                exit_code = vr.exit_code

                _append_record(
                    records_path,
                    {
                        "program_id": program_id,
                        "is_repair": False,
                        "repair_attempt_index": None,
                        "compile_status": compile_status,
                        "signature": signature[:500] if signature else "",
                        "exit_code": exit_code,
                        "elapsed_sec": round(vr.elapsed_sec, 4),
                        "program_hash": program_hash,
                        "bytes": program_bytes,
                        "llm_calls_used": 1,
                        "timestamp": timestamp,
                    },
                )

                target.parse_validation_message(vr.fresult, vr.message, file_name)

                if vr.status == CompileStatus.OK:
                    metrics["total_compiled_ok"] += 1
                    metrics["unique_valid_hashes"].add(program_hash)
                    prev.append((FResult.SAFE, fo))
                    metrics["program_times"].append(time.perf_counter() - program_start)
                    continue

                metrics["total_failures"] += 1
                metrics["unique_failure_signatures"].add(signature)

                repair_success = False
                if repair_enabled and should_repair(vr, repair_config.error_gate):
                    metrics["repair_attempted_count"] += 1
                    cache_key = normalize_error_signature(signature)
                    cached_code = None
                    used_cache_first = False
                    if repair_config.cache and cache_key:
                        cached_code = repair_cache.get(cache_key)
                        if cached_code:
                            metrics["cache_hit_count"] += 1
                            used_cache_first = True
                        else:
                            metrics["cache_miss_count"] += 1

                    for attempt in range(1, repair_config.max_attempts + 1):
                        llm_calls_this_attempt = 0
                        repair_prompt = ""
                        repair_raw = ""
                        if attempt == 1 and cached_code:
                            repaired_code = cached_code
                        else:
                            if metrics["llm_calls"] >= max_llm_calls:
                                budget_exhausted = True
                                break
                            
                            metrics["llm_calls"] += 1
                            metrics["repair_llm_calls"] += 1
                            llm_calls_this_attempt = 1
                            
                            try:
                                result = repair_llm(
                                    target,
                                    fo,
                                    vr.stderr or vr.message,
                                    repair_config,
                                )
                                repaired_code = result.code
                                repair_prompt = result.prompt
                                repair_raw = result.raw_output
                                if repaired_code:
                                    if repair_config.cache and cache_key and not used_cache_first:
                                        repair_cache[cache_key] = repaired_code
                            except Exception:
                                repaired_code = ""

                        if not repaired_code:
                            continue

                        repair_file = os.path.join(output_folder, f"{program_id}_r{attempt}.fuzz")
                        write_to_file(repaired_code, repair_file)
                        repair_hash = _sha256_text(repaired_code)
                        repair_bytes = len(repaired_code.encode("utf-8"))
                        vr_repair = target.validate_individual(repair_file)
                        repair_status = _status_name(vr_repair.status)
                        repair_signature = vr_repair.signature or ""

                        _append_record(
                            records_path,
                            {
                                "program_id": program_id,
                                "is_repair": True,
                                "repair_attempt_index": attempt,
                                "compile_status": repair_status,
                                "signature": repair_signature[:500] if repair_signature else "",
                                "exit_code": vr_repair.exit_code,
                                "elapsed_sec": round(vr_repair.elapsed_sec, 4),
                                "program_hash": repair_hash,
                                "bytes": repair_bytes,
                                "llm_calls_used": llm_calls_this_attempt,
                                "timestamp": time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime()),
                                "repair_input_program": fo,
                                "repair_input_stderr": vr.stderr or vr.message,
                                "repair_prompt_sent": repair_prompt,
                                "repair_output_raw": repair_raw,
                            },
                        )

                        if vr_repair.status != CompileStatus.OK and repair_signature:
                            metrics["unique_failure_signatures"].add(repair_signature)

                        if vr_repair.status == CompileStatus.OK:
                            repair_success = True
                            metrics["repair_success_count"] += 1
                            metrics["total_compiled_ok"] += 1
                            metrics["unique_valid_hashes"].add(repair_hash)
                            prev.append((FResult.SAFE, repaired_code))
                            target.parse_validation_message(
                                vr_repair.fresult, vr_repair.message, repair_file
                            )
                            break
                    
                    if budget_exhausted:
                        break

                if not repair_success:
                    prev.append((vr.fresult, fo))

                metrics["program_times"].append(time.perf_counter() - program_start)
                
            if budget_exhausted:
                break

            if repair_config.cache and repair_cache:
                _save_repair_cache(output_folder, repair_cache)
            target.update(prev=prev)

    total = metrics["total_generated"]
    ok = metrics["total_compiled_ok"]
    unique_generated = len(metrics["unique_generated_hashes"])
    unique_valid = len(metrics["unique_valid_hashes"])
    failures = metrics["total_failures"]
    unique_fail = len(metrics["unique_failure_signatures"])
    times = metrics["program_times"]
    avg_time = sum(times) / len(times) if times else 0.0
    metrics_out = {
        "total_generated": total,
        "total_compiled_ok": ok,
        "valid_rate": ok / total if total else 0.0,
        "unique_valid_rate": unique_valid / total if total else 0.0,
        "duplicate_rate": 1.0 - (unique_generated / total) if total else 0.0,
        "total_failures": failures,
        "unique_failure_count": unique_fail,
        "repair_attempted_count": metrics["repair_attempted_count"],
        "repair_success_count": metrics["repair_success_count"],
        "repair_success_rate": (
            metrics["repair_success_count"] / metrics["repair_attempted_count"]
            if metrics["repair_attempted_count"]
            else 0.0
        ),
        "cache_hit_count": metrics["cache_hit_count"],
        "cache_miss_count": metrics["cache_miss_count"],
        "avg_time_per_program": round(avg_time, 4),
        "llm_overhead": metrics["llm_calls"] / max(ok, 1),
        "generation_llm_calls": metrics["generation_llm_calls"],
        "repair_llm_calls": metrics["repair_llm_calls"],
        "max_llm_calls": max_llm_calls,
        "budget_exhausted": budget_exhausted,
    }
    metrics_path = os.path.join(output_folder, "metrics.json")
    try:
        with open(metrics_path, "w", encoding="utf-8") as mf:
            json.dump(metrics_out, mf, indent=2)
    except Exception:
        pass


# evaluate against the oracle to discover any potential bugs
# used after the generation
def evaluate_all(target: Target):
    target.validate_all()


@click.group()
@click.option(
    "config_file",
    "--config",
    type=str,
    default=None,
    help="Path to the configuration file.",
)
@click.pass_context
def cli(ctx, config_file):
    """Run the main using a configuration file."""
    if config_file is not None:
        config_dict = load_config_file(config_file)
        ctx.ensure_object(dict)
        ctx.obj["CONFIG_DICT"] = config_dict


@cli.command("main_with_config")
@click.pass_context
@click.option(
    "folder",
    "--folder",
    type=str,
    default="Results/test",
    help="folder to store results",
)
@click.option(
    "cpu",
    "--cpu",
    is_flag=True,
    help="to use cpu",  # this is for GPU resource low situations where only cpu is available
)
@click.option(
    "batch_size",
    "--batch_size",
    type=int,
    default=30,
    help="batch size for the model",
)
@click.option(
    "model_name",
    "--model_name",
    type=str,
    default="bigcode/starcoderbase",
    help="model to use",
)
@click.option(
    "target",
    "--target",
    type=str,
    default="",
    help="specific target to run",
)
def main_with_config(ctx, folder, cpu, batch_size, target, model_name):
    """Run the main using a configuration file."""
    config_dict = ctx.obj["CONFIG_DICT"]
    fuzzing = config_dict["fuzzing"]
    config_dict["fuzzing"]["output_folder"] = folder
    if cpu:
        config_dict["llm"]["device"] = "cpu"
    if batch_size:
        config_dict["llm"]["batch_size"] = batch_size
    if model_name != "":
        config_dict["llm"]["model_name"] = model_name
    if target != "":
        config_dict["fuzzing"]["target_name"] = target
    print(config_dict)

    target = make_target_with_config(config_dict)
    if not fuzzing["evaluate"]:
        assert (
            not os.path.exists(folder) or fuzzing["resume"]
        ), f"{folder} already exists!"
        os.makedirs(fuzzing["output_folder"], exist_ok=True)
        repair_config = repair_config_from_dict(config_dict.get("repair"))
        fuzz(
            target=target,
            number_of_iterations=fuzzing["num"],
            total_time=fuzzing["total_time"],
            output_folder=folder,
            resume=fuzzing["resume"],
            otf=fuzzing["otf"],
            repair_config=repair_config,
            max_llm_calls=fuzzing.get("max_llm_calls", 10000),
        )
    else:
        evaluate_all(target)


if __name__ == "__main__":
    cli()
