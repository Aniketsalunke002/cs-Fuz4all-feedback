# Fuzz4All + Error-Guided Repair

Course project for **CS7602 / CS8602: Using AI to Explore a Security Research Problem**.  
Built on top of [Fuzz4All (ICSE '24)](https://arxiv.org/abs/2308.04748) by Xia et al.

This repository extends Fuzz4All with:

- an **error-guided repair stage** for failed C++ generations,
- a **structured evaluator** for fixed candidate scoring,
- and an **AI-driven search harness** for exploring repair-policy configurations.

---

## Overview

### What problem does this solve?

LLM-based fuzzers discard every generated program that fails to compile.  
This project asks:

> Can compiler feedback (`stderr`) be used as a repair signal to recover partially-correct programs instead of throwing them away?

In this project, the answer is **yes**: compiler diagnostics can be turned into useful repair signals that increase the number of compilable fuzzing inputs.

### Why this matters for security

Compiler fuzzing is a practical path to surfacing security-relevant failures such as:

- internal compiler errors,
- miscompiles,
- and bugs that block deeper downstream testing.

If more generated programs compile successfully, more inputs reach later fuzzing oracles.  
The repair stage therefore improves fuzzing throughput by turning near-miss generations into usable test cases.

### Main run vs runnable demo

- **Report-scale / main quantitative result:** **StarCoderBase-7B**, **N = 200** programs per condition (baseline vs repair). Pre-recorded outputs live under `outputs/baseline_repro_7b_200/` and `outputs/repair_repro_7b_200/` (and an earlier midterm pair under `outputs/baseline_7b_200/`, `outputs/repair_7b_200/`). This is the run the write-up and tables below are anchored on.
- **README walkthrough (lighter reproduction):** **StarCoderBase-1B**, **N = 50**. A **7B × N = 20** path exists in config (`cpp_demo_n20.yaml`, etc.) but shipping full **7B × N = 20** run artefacts made the repo too large, so this document gives **copy-paste steps for 1B @ N = 50** instead—enough VRAM and time for a class demo or TA check, while the **7B @ N = 200** folders remain the primary evidence pack.

**Headline numbers (final 7B repro, N = 200, C++23, `g++ -c`):**


| Metric                | Baseline | + Repair  | Δ          |
| --------------------- | -------- | --------- | ---------- |
| `valid_rate`          | 0.595    | **0.800** | **+0.205** |
| `unique_valid_rate`   | 0.490    | **0.655** | **+0.165** |
| `repair_success_rate` | —        | 0.535     | —          |


Source: `outputs/baseline_repro_7b_200/metrics.json`, `outputs/repair_repro_7b_200/metrics.json`.

---

## Repository structure

The course asks for a repository with **code + README**, including the **evaluator**, **AI search scripts**, and **configuration** (prompts, config files, etc.). Here is how this submission maps to that:


| Expectation                 | Where it lives in this repo                                                                                                                                                                                      |
| --------------------------- | ---------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------- |
| **Evaluator**               | `tools/evaluate_candidate.py` (fixed-budget evaluation); compile/validation logic in `Fuzz4All/target/` and repair scoring in `Fuzz4All/repair/repair.py`. See `docs/COURSE_PROJECT.md` for metrics and options. |
| **AI search scripts**       | `tools/run_search_round.py` (search harness); repair-policy **candidates** in `candidates/` (JSON → materialized YAML under `candidates/materialized/`); search logs and prompts in `outputs/search/`.           |
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
│   └── run_search_round.py          # AI-driven search harness
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
│   ├── round_02.json
│   └── materialized/                # YAMLs materialized from candidate JSON
├── docs/
│   ├── COURSE_PROJECT.md            # extension docs (metrics, options)
│   └── DEMO_EXECUTION.md            # copy-paste HPC demo (same steps as README walkthrough)
├── outputs/                         # main: *_repro_7b_200/ (7B N=200); demo: baseline_n50_1b/, repair_n50_1b/; search/, eval_smoke/
├── README.md                        # this file
├── README_artifact.md               # original ICSE '24 artifact instructions
├── requirements.txt
└── setup.py
```

---

## Installation and reduced-scale demo (1B, N = 50)

The **main numbers** for this project come from **7B, N = 200** (see **Recorded 7B full-scale results** below). The steps in *this* section are a **smaller, repo-friendly** way to exercise the same pipeline end-to-end: **StarCoderBase-1B** and **N = 50**, so you do not need a 7B-class GPU block or multi-hour runs to verify repair behaviour. 

Because the project uses local models on GPU, run this on a **CUDA-enabled NVIDIA GPU** when possible. CPU-only is usually too slow to be practical.

I recommend:

- a **GPU-enabled university HPC node**, or
- a **Linux machine with a suitable NVIDIA GPU**.

These instructions start with an optional HPC allocation step; **skip Step 1** if you already have a GPU machine.

**This walkthrough’s setting:** baseline vs repair at **N = 50** with `**bigcode/starcoderbase-1b`**, then a comparison table (steps 7–9).

---

### 1. (HPC only) Get a compute node

The login node is shared and slow. Reserve a workstation first.

1. SSH into your cluster or HPC Your prompt will look like `<user>@zap-fe-1` or similar.
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
  Note the **Driver Version** and **CUDA Version** lines from the header — you will use the CUDA number in step 4. You should also see your GPU listed (e.g. `NVIDIA RTX 5000 Ada Generation`, 32 GB).

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
   You must see **Python 3.10.x** and a path under `.../envs/fuzz4all/...`.
   Then re-run step 3.

---

### 3. Install project dependencies

Run inside the activated `fuzz4all` env, from the **repo root**:

1. Go to the repo:
  ```bash
   cd /path/to/your/fuzz4all-cs-final or You should already be in root folder
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

### 4. Install a GPU-matching PyTorch (CUDA 12.x)

The `torch` from `requirements.txt` may not match the lab’s NVIDIA driver and you will see **The NVIDIA driver on your system is too old** at runtime. Replace it with the CUDA build that matches `nvidia-smi`.

1. Uninstall whatever version was installed by `requirements.txt`: if it does not match your driver
  ```bash
   pip uninstall -y torch torchvision torchaudio
  ```
2. Install the CUDA 12.4 wheel (matches `CUDA Version: 12.4` from `nvidia-smi`):
  ```bash
   pip install torch torchvision torchaudio --index-url https://download.pytorch.org/whl/cu124
  ```
   If your `nvidia-smi` shows a different CUDA (e.g. 11.8), use the matching index from [pytorch.org/get-started/locally](https://pytorch.org/get-started/locally/) — for CUDA 11.8: `--index-url https://download.pytorch.org/whl/cu118`.
3. Verify CUDA is visible inside Python:
  ```bash
   python -c "import torch; print(torch.__version__); print('cuda:', torch.cuda.is_available()); print(torch.cuda.get_device_name(0))"
  ```
   You should see something like:
   If `cuda: False`, fix this **before** the fuzz runs (you would otherwise crash mid-run).

---

### 5. Hugging Face — account, gated model, token, terminal login

The model `**bigcode/starcoderbase-1b`** is **gated**: you must have an account, accept the licence on the model page, and use a token that can read gated repositories.

#### 5a. Browser steps

1. Go to [huggingface.co/join](https://huggingface.co/join) and **create a free account** (skip if you already have one).
2. Log in at [huggingface.co](https://huggingface.co).
3. Open the model page **while logged in**: [https://huggingface.co/bigcode/starcoderbase-1b](https://huggingface.co/bigcode/starcoderbase-1b).
4. If the page shows **“Agree and access repository”** (or “You need to agree to share your contact information…”), click it and accept. After this, you should be able to see the **Files and versions** tab without a gate banner.
5. Open [https://huggingface.co/settings/tokens](https://huggingface.co/settings/tokens) → **Create new token**.
  - Choose **Classic** (not Fine-grained).
  - Permission: **Read**.
  - Click create, then **copy** the full `hf_…` string. *It is shown only once — keep it somewhere safe for now.*

> Why classic Read? Fine-grained tokens often report `canReadGatedRepos: false` and silently fail to download `starcoderbase-1b`.

#### 5b. Terminal steps (inside the `fuzz4all` env)

1. Make sure the Hugging Face client is installed:
  ```bash
   pip install -U "huggingface_hub[cli]"
  ```
2. Set the token in this shell; run the following command:
  ```bash
   read -s HF_TOKEN && export HF_TOKEN
  ```
   After `read -s HF_TOKEN && export HF_TOKEN`, press enter and then paste the **full** `hf_...` token below  and press **Enter**. Nothing will appear while pasting (that is normal).
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

> The token is **per-session**: if you open a new terminal, run `read -s HF_TOKEN && export HF_TOKEN` again.

---

### 6. Confirm the N=50 configs

The two configs ship with the repo at `**num: 50`**. Verify before running:

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
- The folder `**outputs/baseline_n50_1b/`** contains `metrics.json`, `records.jsonl`, and `*.fuzz` files.

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
- `outputs/repair_n50_1b/` additionally contains `**repair_cache.json`** and accepted `*_r1.fuzz` / `*_r2.fuzz` files (the repaired programs).
- It is normal for this to take **longer** than baseline — repair calls the LLM again per failed compile.

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

You will get a table with `baseline`, `repair`, and `delta` columns plus a one-line summary of `delta valid_rate`, `repair_success`, and the count of `*_r*.fuzz` files written.

---

### 10. Inspecting the main 7B, N = 200 results (no GPU needed)

The **primary** baseline vs repair comparison for this project is **StarCoderBase-7B** at **N = 200** (pre-recorded under `outputs/baseline_repro_7b_200/` and `outputs/repair_repro_7b_200/`). Steps 7–9 above are the **1B @ N = 50** runnable demo; they are **not** the main statistical run, but they exercise the same repair machinery on cheaper hardware.

7B @ N = 200 needs substantial VRAM and time (on the order of **~28 GB** and **~1.5 h** per full fuzz on our hardware; **15B** is even heavier). **N = 200** means **one** fuzz job of 200 programs per condition, not 30 repeated jobs; the CLI default **`--batch_size 30`** only caps how many candidates each **`generate()`** call returns, and repair can add extra LLM calls per failure (typically `max_attempts: 2` in the YAML config).

```bash
python -m json.tool outputs/baseline_repro_7b_200/metrics.json
python -m json.tool outputs/repair_repro_7b_200/metrics.json
```

When reading those files, focus on **`valid_rate`**, **`unique_valid_rate`**, and **`repair_success_rate`**.

---

### Notes for the live N=50 table

- The 1B model is **stochastic** and N=50 is small. A single live run can show **Δ valid_rate < 0** by chance; what proves the repair stage is working in **any** run is `repair_attempted_count > 0`, `repair_success_count > 0`, and the `*_r*.fuzz` files written under `outputs/repair_n50_1b/`.
- **Report-scale evidence** for the project is the **7B, N = 200** metrics in **step 10** and the **Recorded 7B full-scale results** section (`baseline_repro_7b_200` vs `repair_repro_7b_200`).

---

## Recorded 7B full-scale results (main run)

Pre-recorded **7B @ N = 200** outputs—the same setting as the headline table in **Overview**.


| Run                                                                                                                                            | `valid_rate` (base → repair) | `unique_valid_rate` (base → repair) | `repair_success_rate` |
| ---------------------------------------------------------------------------------------------------------------------------------------------- | ---------------------------- | ----------------------------------- | --------------------- |
| Midterm — `[outputs/baseline_7b_200/](outputs/baseline_7b_200)`, `[outputs/repair_7b_200/](outputs/repair_7b_200)`                             | 0.605 → **0.735** (Δ +0.130) | 0.485 → **0.690** (Δ +0.205)        | 0.459                 |
| Final repro — `[outputs/baseline_repro_7b_200/](outputs/baseline_repro_7b_200)`, `[outputs/repair_repro_7b_200/](outputs/repair_repro_7b_200)` | 0.595 → **0.800** (Δ +0.205) | 0.490 → **0.655** (Δ +0.165)        | 0.535                 |


Both runs land in the same direction with similar magnitude (Δ `valid_rate` between +0.130 and +0.205) — the repair gain is real, not a single-run artefact.

Each output folder contains: `metrics.json`, `records.jsonl` (one row per generation and per repair attempt), the original `*.fuzz` files, the accepted repair files (`*_r1.fuzz`, `*_r2.fuzz`), and `repair_cache.json` (signature → cached repair).

---

## References

- Original paper: [Fuzz4All: Universal Fuzzing with Large Language Models — arXiv:2308.04748](https://arxiv.org/abs/2308.04748)
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

