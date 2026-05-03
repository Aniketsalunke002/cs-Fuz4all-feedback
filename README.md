# Fuzz4All + Error-Guided Repair

Course project for **CS7602 / CS8602: Using AI to Explore a Security Research Problem**.  
Built on top of [Fuzz4All (ICSE '24)](https://arxiv.org/abs/2308.04748) by Xia et al.

This repo adds:

- an **error-guided repair** pass for failed C++ generations,
- a small **evaluator** for scoring fixed candidates,
- and a **search harness** to try different repair-policy settings.

### Start here

- **Small demo (1B, N = 50):** [Installation and reduced-scale demo](#installation-and-reduced-scale-demo-1b-n--50). Follow **Steps 1–9** as written. Steps marked **Optional** (HPC, PyTorch pin, Hugging Face) can be skipped if your machine is already set up.
- **Main numbers (no GPU needed to read them):** [Recorded 7B full-scale results](#recorded-7b-full-scale-results-main-run), i.e. the saved `metrics.json` files under `outputs/`.
- **Repo layout:** [Repository structure](#repository-structure).

### Table of contents

1. [Overview](#overview) ([Limitations](#limitations))
2. [Installation and reduced-scale demo (1B, N = 50)](#installation-and-reduced-scale-demo-1b-n--50)
3. [Notes for the live N=50 table](#notes-for-the-live-n50-table)
4. [Recorded 7B full-scale results (main run)](#recorded-7b-full-scale-results-main-run)
5. [Repository structure](#repository-structure)
6. [References](#references)

---

## Overview

### What problem does this solve?

LLM fuzzers usually throw away anything that does not compile.

> Can we use compiler output (`stderr`) as a hint to fix near-miss programs instead of dropping them?

**Yes**, at least in our setup: feeding `g++` errors back into the model bumps how many generated programs compile.

### Why this matters for security

Compiler fuzzing is one way to shake out ICEs, miscompiles, and other bugs that matter for toolchains.

If more generations compile, more of them can go through later checks. Repair is basically “try to salvage the compile failures” so you get more usable inputs per batch.

### Limitations

- **Repair** uses compiler errors so the generated file is more likely to pass our usual compile check (`g++ -c`, **C++23**). Nothing is linked or run for that test.

**Semantic correctness:** A program can compile and still be wrong or meaningless. This project does **not** measure semantic correctness: nothing in the pipeline checks “does it mean or do the right thing.” That is a **limitation** of compile-only fuzzing and compile-only repair. Metrics such as `valid_rate` and repair counts only reflect **compiler success**, not correctness of behavior or meaning.

---

## Installation and reduced-scale demo (1B, N = 50)

This walkthrough is **StarCoderBase-1B**, **N = 50** (lighter than the **7B @ N = 200** run in [Recorded 7B full-scale results](#recorded-7b-full-scale-results-main-run)).

Use a machine with an **NVIDIA GPU** and **CUDA** if you can. **CPU-only** is usually too slow to be practical for this demo.

Typical setups:

- a GPU node on campus HPC, or
- a Linux box with a decent NVIDIA card.

**C++compiler (`g++`):** The demo calls `g++` as the compile oracle (`--target "$(command -v g++)"`). Check:

```bash
command -v g++ && g++ --version
```

If `g++` is missing, install a toolchain (pick one that matches your OS):

```bash
# Debian / Ubuntu
sudo apt update && sudo apt install -y build-essential

# RHEL / Fedora (dnf)
sudo dnf install -y gcc-c++
```

On **HPC**, compilers are often provided via modules (names vary by site), e.g. `module avail gcc` then `module load <gcc-module>` before re-running the check.

These instructions start with an optional HPC allocation step; **skip Step 1** if you already have a GPU machine.

**This walkthrough:** baseline vs repair at **N = 50** with `bigcode/starcoderbase-1b`, then the comparison table in steps 7–9.

**Optional: Step 1, HPC only (Slurm / GPU node)**

### 1. (HPC only) Get a compute node

The login node is shared and slow. Reserve a workstation first.

1. SSH into your cluster or HPC. Your prompt will look like `<user>@zap-fe-1` or similar.
2. (Recommended) Start a `tmux` session so an SSH disconnect does **not** kill your work:
  ```bash
   tmux new -s fuzzdemo
  ```
   To detach later: press `Ctrl-b` then `d`. To reattach: `tmux attach -t fuzzdemo`.
3. Reserve a workstation with Slurm
  ```bash
  salloc -N1 -n24
  ```
   Wait until you see `salloc: Granted job allocation` and the prompt switches to a workstation hostname (e.g. `ws-l1-001`). **Do not run anything heavy until you see this.**
4. Confirm the GPU:
  Note **Driver Version** and **CUDA Version** in the header (you’ll match PyTorch to that later). You should see your GPU name, e.g. `NVIDIA RTX 5000 Ada Generation`, 32 GB.

If you are on a personal Linux machine that already has `g++` and an NVIDIA GPU, skip this section.

---

### 2. Conda environment (Python 3.10)

The project pins older packages (e.g. `pandas==2.0.3`) that fail on Python **3.13**. Use **3.10**.

1. Create the env (one time per machine):
  ```bash
   conda create -n fuzz4all python=3.10 -y
  ```
2. Activate it:
  ```bash
   conda activate fuzz4all
  ```
3. Verify the interpreter is the new env (not `base` / 3.13):
  ```bash
   python --version
   which python
  ```
   You should see **Python 3.10.x** and a path under `.../envs/fuzz4all/...`. If not, you are not in the env; go back to step 2.

---

### 3. Install project dependencies

Run inside the activated `fuzz4all` env, from the **repo root**:

1. Go to the repo root (where `setup.py` lives):
  ```bash
   cd /path/to/fuzz4all-cs-final
  ```
2. Upgrade packaging tools (prevents the `pkg_resources` / `Failed to build pandas` errors):
  ```bash
   python -m pip install --upgrade pip setuptools wheel
  ```
3. Install Python requirements:
  ```bash
   python -m pip install -r requirements.txt
  ```
4. Install this project itself in editable mode (registers `Fuzz4All` as a package):
  ```bash
   python -m pip install -e .
  ```
5. Quick sanity check (should print versions, no import error):
  ```bash
   python -c "import torch, pandas; print('ok', torch.__version__, pandas.__version__)"
  ```

---

**Optional: Step 4, GPU-matching PyTorch (CUDA)**

### 4. Install a GPU-matching PyTorch (CUDA 12.x)

The `torch` from `requirements.txt` may not match the lab’s NVIDIA driver and you will see **The NVIDIA driver on your system is too old** at runtime. Replace it with the CUDA build that matches `nvidia-smi`.

1. Uninstall the PyTorch packages that `requirements.txt` already installed so you can replace them with a build that matches your GPU driver:
  ```bash
   pip uninstall -y torch torchvision torchaudio
  ```
2. Install the CUDA 12.4 wheel (matches `CUDA Version: 12.4` from `nvidia-smi`):
  ```bash
   pip install torch torchvision torchaudio --index-url https://download.pytorch.org/whl/cu124
  ```
   If `nvidia-smi` shows a different CUDA (e.g. 11.8), use the wheel index from [pytorch.org/get-started/locally](https://pytorch.org/get-started/locally/). Example for 11.8: `--index-url https://download.pytorch.org/whl/cu118`.
3. Verify CUDA is visible inside Python:
  ```bash
   python -c "import torch; print(torch.__version__); print('cuda:', torch.cuda.is_available()); print(torch.cuda.get_device_name(0))"
  ```
   You should see three lines similar to:
   (Exact version and GPU name will match your machine.) If the second line is `cuda: False`, fix this **before** the fuzz runs or the job will fail once it hits the GPU.

---

**Optional: Step 5, Hugging Face (gated 1B model)**

### 5. Hugging Face: account, model access, token, terminal

`bigcode/starcoderbase-1b` is **gated**. You need a Hugging Face account, click through the licence on the model page, and use a token that can read gated repos.

#### 5a. Browser steps

1. Go to [huggingface.co/join](https://huggingface.co/join) and **create a free account** (skip if you already have one).
2. Log in at [huggingface.co](https://huggingface.co).
3. Open the model page **while logged in**: [https://huggingface.co/bigcode/starcoderbase-1b](https://huggingface.co/bigcode/starcoderbase-1b).
4. If the page shows **“Agree and access repository”** (or “You need to agree to share your contact information…”), click it and accept. After this, you should be able to see the **Files and versions** tab without a gate banner.
5. Open [https://huggingface.co/settings/tokens](https://huggingface.co/settings/tokens) → **Create new token**.
  - Choose **Classic** (not Fine-grained).
  - Permission: **Read**.
  - Click create, then **copy** the full `hf_…` string. *You only see it once; stash it somewhere safe.*

> Why classic Read? Fine-grained tokens often report `canReadGatedRepos: false` and silently fail to download `starcoderbase-1b`.

#### 5b. Terminal steps (inside the `fuzz4all` env)

1. Make sure the Hugging Face client is installed:
  ```bash
   pip install -U "huggingface_hub[cli]"
  ```
2. Set the token in this shell. Run:
  ```bash
   read -s HF_TOKEN && export HF_TOKEN
  ```
   After you press **Enter**, the shell waits at a silent prompt: paste the **full** `hf_...` token there, then press **Enter** again. Nothing appears while you paste (normal for `read -s`).
3. Confirm the variable is set and looks reasonable:
  ```bash
   echo ${#HF_TOKEN}
  ```
   You should see a non-trivial number (e.g. **30+**), **not** `0` or `4`.
4. Confirm Hugging Face accepts the token:
  ```bash
   python -c "from huggingface_hub import whoami; print(whoami())"
  ```
   You should see your Hugging Face username in the output.
5. Confirm the gated model is downloadable end-to-end (downloads one tiny file):
  ```bash
   python -c "from huggingface_hub import hf_hub_download; hf_hub_download('bigcode/starcoderbase-1b', 'config.json')"
  ```
   On success it prints a path under `~/.cache/huggingface/...`. If you see **401/403** here, repeat **5a step 4** (accept on the model page) and **5a step 5** (Classic Read token).

> The token is **per shell**. New terminal = run `read -s HF_TOKEN && export HF_TOKEN` again.

---

### 6. Confirm the N=50 configs

The two configs should already say `num: 50`. Double-check:

```bash
grep '^  num:' config/cpp_smoke_n50.yaml config/cpp_repair_smoke_n50.yaml
```

Expected output (both lines must say **50**):

```
config/cpp_smoke_n50.yaml:  num: 50
config/cpp_repair_smoke_n50.yaml:  num: 50
```

If either says `10`, edit the file and change `num: 10` to `num: 50` before continuing.

---

### 7. Baseline run (50 programs, no repair)

```bash
rm -rf outputs/baseline_n50_1b

python Fuzz4All/fuzz.py --config config/cpp_smoke_n50.yaml main_with_config \
  --folder outputs/baseline_n50_1b \
  --batch_size 2 \
  --model_name bigcode/starcoderbase-1b \
  --target "$(command -v g++)"
```

What to look for:

- A progress bar that reaches **50/50** at the end.
- Under `outputs/baseline_n50_1b/` you should see `metrics.json`, `records.jsonl`, and `*.fuzz` files.

---

### 8. Repair run (50 programs, with stderr-guided repair)

```bash
rm -rf outputs/repair_n50_1b

python Fuzz4All/fuzz.py --config config/cpp_repair_smoke_n50.yaml main_with_config \
  --folder outputs/repair_n50_1b \
  --batch_size 2 \
  --model_name bigcode/starcoderbase-1b \
  --target "$(command -v g++)"
```

What to look for:

- Progress reaches **50/50**.
- `outputs/repair_n50_1b/` should also have `repair_cache.json` and accepted `*_r1.fuzz` / `*_r2.fuzz` files.
- Repair runs slower than baseline because failed compiles trigger extra model calls.

---

### 9. Comparison table

```bash
export BASE_DIR=outputs/baseline_n50_1b
export REP_DIR=outputs/repair_n50_1b

BASE_DIR="$BASE_DIR" REP_DIR="$REP_DIR" python <<'PY'
import json, glob, os
base = json.load(open(os.path.join(os.environ["BASE_DIR"], "metrics.json")))
rep = json.load(open(os.path.join(os.environ["REP_DIR"], "metrics.json")))
rep_dir = os.environ["REP_DIR"]

def fmt(v):
    if isinstance(v, float):
        return f"{v:.3f}"
    return str(v)

rows = [
    ("total_compiled_ok", "compiled OK / N"),
    ("valid_rate", "valid_rate"),
    ("unique_valid_rate", "unique_valid_rate"),
    ("duplicate_rate", "duplicate_rate"),
    ("repair_attempted_count", "repair_attempted"),
    ("repair_success_count", "repair_success"),
    ("repair_success_rate", "repair_success_rate"),
]
print()
print(f"  {'metric':24s}  {'baseline':>10s}  {'repair':>10s}  {'delta':>10s}")
print(f"  {'-'*24}  {'-'*10}  {'-'*10}  {'-'*10}")
for key, label in rows:
    b, r = base.get(key), rep.get(key)
    if b is None and r is None:
        continue
    bs = fmt(b if b is not None else "-")
    rs = fmt(r if r is not None else "-")
    if isinstance(b, (int, float)) and isinstance(r, (int, float)):
        d = r - b
        ds = f"{d:+.3f}" if isinstance(d, float) else f"{d:+d}"
    else:
        ds = "-"
    print(f"  {label:24s}  {bs:>10s}  {rs:>10s}  {ds:>10s}")
bt = base.get("avg_time_per_program", 0) or 0
rt = rep.get("avg_time_per_program", 0) or 0
print()
print("  cost summary:")
print(f"    avg time / program : {bt:.2f}s  ->  {rt:.2f}s")
dv = (rep.get("valid_rate", 0) or 0) - (base.get("valid_rate", 0) or 0)
rsucc = rep.get("repair_success_count", 0) or 0
n = len(glob.glob(os.path.join(rep_dir, "*_r*.fuzz")))
print()
print(f"  delta valid_rate = {dv:+.3f}  |  repair_success = {rsucc}  |  *_r*.fuzz count = {n}")
print()
PY
```

You should see a small table (`baseline`, `repair`, `delta`) plus a short line with `delta valid_rate`, `repair_success`, and how many `*_r*.fuzz` files landed on disk.

---

### Notes for the live N=50 table

- The 1B model is random and N=50 is tiny, so one run can show a negative Δ `valid_rate` by luck. For a quick “is repair actually firing?” check, look for `repair_attempted_count > 0`, `repair_success_count > 0`, and `*_r*.fuzz` under `outputs/repair_n50_1b/`.
- The **serious** comparison is still **7B, N = 200** below (`baseline_repro_7b_200` vs `repair_repro_7b_200`).

---

## Recorded 7B full-scale results (main run)

These folders are **7B @ N = 200**. Steps 7–9 above are **1B @ N = 50** (same pipeline, smaller model and budget).

The comparison we care about is **StarCoderBase-7B**, **N = 200**, in `outputs/baseline_repro_7b_200/` and `outputs/repair_repro_7b_200/`. A full 7B fuzz needs a lot of VRAM and time (roughly **~28 GB** and **~1.5 h** per condition on our box). **N = 200** is one fuzz job of 200 programs per side. `**--batch_size`** only limits how many candidates each `generate()` returns; repair can stack more model calls on top when compiles fail (we used `max_attempts: 2` in YAML).

**Inspect pre-recorded metrics (no GPU needed):**

```bash
python -m json.tool outputs/baseline_repro_7b_200/metrics.json
python -m json.tool outputs/repair_repro_7b_200/metrics.json
```

Main fields to peek at: `valid_rate`, `unique_valid_rate`, `repair_success_rate`.


| Run                                                                                                                                           | `valid_rate` (base → repair) | `unique_valid_rate` (base → repair) | `repair_success_rate` |
| --------------------------------------------------------------------------------------------------------------------------------------------- | ---------------------------- | ----------------------------------- | --------------------- |
| Midterm: `[outputs/baseline_7b_200/](outputs/baseline_7b_200)`, `[outputs/repair_7b_200/](outputs/repair_7b_200)`                             | 0.605 → **0.735** (Δ +0.130) | 0.485 → **0.690** (Δ +0.205)        | 0.459                 |
| Final repro: `[outputs/baseline_repro_7b_200/](outputs/baseline_repro_7b_200)`, `[outputs/repair_repro_7b_200/](outputs/repair_repro_7b_200)` | 0.595 → **0.800** (Δ +0.205) | 0.490 → **0.655** (Δ +0.165)        | 0.535                 |


Both runs move the same way (Δ `valid_rate` about +0.13 to +0.21), so the bump is not a one-off fluke.

Each output folder has `metrics.json`, `records.jsonl` (per gen / repair try), raw `*.fuzz`, repaired `*_r1.fuzz` / `*_r2.fuzz` when accepted, and `repair_cache.json` (dedupe by error signature).

---

## Repository structure

The assignment wants **code + README**, plus evaluator, search bits, and configs. Rough map:


| Expectation                 | Where it lives in this repo                                                                                                                                                                                      |
| --------------------------- | ---------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------- |
| **Evaluator**               | `tools/evaluate_candidate.py` (fixed-budget evaluation); compile/validation logic in `Fuzz4All/target/` and repair scoring in `Fuzz4All/repair/repair.py`. See `docs/COURSE_PROJECT.md` for metrics and options. |
| **Search scripts**          | `tools/run_search_round.py` (search harness); repair-policy **candidates** in `candidates/` (JSON files and materialized YAML under `candidates/materialized/`); search logs and prompts in `outputs/search/`.   |
| **Configuration & prompts** | YAML **configs** under `config/` (baseline, repair, smoke, demo variants); **prompts** under `prompts/repair/` (templates `T1.txt`–`T6.txt`).                                                                    |


```text
fuzz4all-cs-final/
├── Fuzz4All/
│   ├── fuzz.py                      # main fuzzing loop (with repair hook)
│   ├── make_target.py
│   ├── model.py
│   ├── repair/
│   │   └── repair.py                # repair stage + RepairConfig + templates
│   ├── target/
│   │   ├── target.py                # ValidationResult, CompileStatus
│   │   └── CPP/
│   │       └── CPP.py               # g++ -c compile-only oracle
│   └── util/
├── prompts/
│   └── repair/
│       └── T1.txt … T6.txt          # completion-style repair templates
├── tools/
│   ├── evaluate_candidate.py        # fixed-budget evaluator
│   └── run_search_round.py          # search harness for repair configs
├── scripts/
│   └── demo.sh                      # reproduction (N=20, 7B)
├── config/
│   ├── cpp_demo.yaml                # baseline       (N = 200, 7B)
│   ├── cpp_repair_demo.yaml         # repair         (N = 200, 7B)
│   ├── cpp_demo_n20.yaml            # baseline       (N = 20,  7B)
│   ├── cpp_repair_demo_n20.yaml     # repair         (N = 20,  7B)
│   ├── cpp_smoke.yaml               # 1B smoke       (pipeline check)
│   ├── cpp_repair_smoke.yaml
│   ├── cpp_smoke_n50.yaml           # HPC / README demo (N = 50, 1B)
│   ├── cpp_repair_smoke_n50.yaml
│   ├── ablation/                    # upstream Fuzz4All ablation configs
│   ├── targeted/
│   ├── full_run/
│   └── documentation/               # per-language prompt docs (upstream)
├── candidates/
│   ├── round_01.json
│   ├── round_03.json                # main 7B search grid (`r3_*` candidates)
│   └── materialized/                # YAMLs materialized from candidate JSON
├── docs/
│   └── COURSE_PROJECT.md            # extension docs (metrics, options)
├── outputs/                         # pre-recorded fuzz/search runs (paths used in this README)
├── README.md                        # this file
├── README_artifact.md               # original ICSE '24 artifact instructions
├── requirements.txt
└── setup.py
```

---

## References

- Original paper: [Fuzz4All: Universal Fuzzing with Large Language Models (arXiv:2308.04748)](https://arxiv.org/abs/2308.04748)
- Original artifact: [Zenodo 10456883](https://doi.org/10.5281/zenodo.10456883)
- Course-extension docs: [docs/COURSE_PROJECT.md](docs/COURSE_PROJECT.md)

```bibtex
@inproceedings{fuzz4all,
  title     = {Fuzz4All: Universal Fuzzing with Large Language Models},
  author    = {Xia, Chunqiu Steven and Paltenghi, Matteo and Tian, Jia Le and Pradel, Michael and Zhang, Lingming},
  booktitle = {Proceedings of the 46th International Conference on Software Engineering},
  series    = {ICSE '24},
  year      = {2024}
}
```

