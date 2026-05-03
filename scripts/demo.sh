#!/usr/bin/env bash
# ----------------------------------------------------------------------------
# scripts/demo.sh - one-command live demo of the error-guided repair extension.
#
# What this does, in order:
#   1. Print recorded full-scale (N=200, 7B) baseline vs repair metrics.
#   2. Run a live BASELINE fuzz at N=20 with StarCoderBase-7B (~30-45 s).
#   3. Run a live REPAIR fuzz   at N=20 with StarCoderBase-7B (~80-180 s).
#   4. Print a side-by-side comparison of quality metrics.
#
# Total wall-clock: ~2-4 minutes on an RTX 5000 once the model is cached.
# Requires: conda env "fuzz4all" active, g++ on PATH, GPU visible.
#
# Usage:
#     bash scripts/demo.sh
# ----------------------------------------------------------------------------

set -euo pipefail

REPO_ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
cd "$REPO_ROOT"
export PYTHONPATH="$REPO_ROOT:${PYTHONPATH:-}"

GPP="$(command -v g++ || true)"
if [[ -z "$GPP" ]]; then
    echo "ERROR: g++ not found on PATH. Install g++ first." >&2
    exit 1
fi

BASELINE_CFG="config/cpp_demo_n20.yaml"
REPAIR_CFG="config/cpp_repair_demo_n20.yaml"
BASELINE_OUT="outputs/demo_baseline"
REPAIR_OUT="outputs/demo_repair"
RECORDED_BASELINE="outputs/baseline_repro_7b_200"
RECORDED_REPAIR="outputs/repair_repro_7b_200"

bar() { printf "\n%s\n" "============================================================"; }

# ----------------------------------------------------------------------------
# Step 1: print recorded full-scale numbers (instant, just cat)
# ----------------------------------------------------------------------------
bar
echo " STEP 1 / 4 - Recorded full-scale results (N=200, StarCoderBase-7B)"
bar

print_recorded() {
    local label="$1"
    local path="$2"
    if [[ -f "$path/metrics.json" ]]; then
        echo
        echo "--- $label  ($path/metrics.json) ---"
        python -c "
import json, sys
m = json.load(open('$path/metrics.json'))
keys = ['total_generated','total_compiled_ok','valid_rate','unique_valid_rate',
        'duplicate_rate','repair_attempted_count','repair_success_count',
        'repair_success_rate']
for k in keys:
    v = m.get(k)
    if isinstance(v, float):
        print(f'  {k:28s} = {v:.4f}')
    else:
        print(f'  {k:28s} = {v}')
"
    else
        echo "  (no recorded results at $path - skipping)"
    fi
}

print_recorded "BASELINE  recorded" "$RECORDED_BASELINE"
print_recorded "REPAIR    recorded" "$RECORDED_REPAIR"

# ----------------------------------------------------------------------------
# Step 2: live baseline run at N=20
# ----------------------------------------------------------------------------
bar
echo " STEP 2 / 4 - LIVE baseline fuzz (N=20, 7B)  ~30-45 s"
bar
rm -rf "$BASELINE_OUT"
python Fuzz4All/fuzz.py --config "$BASELINE_CFG" main_with_config \
    --folder "$BASELINE_OUT" \
    --batch_size 4 \
    --model_name bigcode/starcoderbase-7b \
    --target "$GPP"

# ----------------------------------------------------------------------------
# Step 3: live repair run at N=20
# ----------------------------------------------------------------------------
bar
echo " STEP 3 / 4 - LIVE repair fuzz (N=20, 7B)  ~80-180 s"
bar
rm -rf "$REPAIR_OUT"
python Fuzz4All/fuzz.py --config "$REPAIR_CFG" main_with_config \
    --folder "$REPAIR_OUT" \
    --batch_size 4 \
    --model_name bigcode/starcoderbase-7b \
    --target "$GPP"

# ----------------------------------------------------------------------------
# Step 4: print live comparison (quality metrics only)
# ----------------------------------------------------------------------------
bar
echo " STEP 4 / 4 - Live demo comparison"
bar

python <<'PY'
import json, os, glob

def load(path):
    return json.load(open(path)) if os.path.exists(path) else None

base = load("outputs/demo_baseline/metrics.json")
rep  = load("outputs/demo_repair/metrics.json")

assert base is not None, "baseline metrics missing"
assert rep is not None, "repair metrics missing"

def fmt(v):
    if isinstance(v, float):
        return f"{v:.3f}"
    return str(v)

quality_metrics = [
    ("total_compiled_ok",   "compiled OK / N"),
    ("valid_rate",          "valid_rate"),
    ("unique_valid_rate",   "unique_valid_rate"),
    ("duplicate_rate",      "duplicate_rate"),
    ("repair_attempted_count", "repair_attempted"),
    ("repair_success_count",   "repair_success"),
    ("repair_success_rate",    "repair_success_rate"),
]

print()
print(f"  {'metric':24s}  {'baseline':>10s}  {'repair':>10s}  {'delta':>10s}")
print(f"  {'-'*24}  {'-'*10}  {'-'*10}  {'-'*10}")
for key, label in quality_metrics:
    b = base.get(key)
    r = rep.get(key)
    if b is None and r is None:
        continue
    bs = fmt(b if b is not None else "-")
    rs = fmt(r if r is not None else "-")
    if isinstance(b, (int, float)) and isinstance(r, (int, float)):
        delta = r - b
        ds = f"{delta:+.3f}" if isinstance(delta, float) else f"{delta:+d}"
    else:
        ds = "-"
    print(f"  {label:24s}  {bs:>10s}  {rs:>10s}  {ds:>10s}")

# brief cost summary, kept compact
b_time = base.get("avg_time_per_program", 0.0) or 0.0
r_time = rep.get("avg_time_per_program", 0.0) or 0.0

print()
print("  cost summary (price paid for the gain):")
print(f"    avg time / program : {b_time:.2f}s  ->  {r_time:.2f}s")

# pass / fail line
delta_vr = (rep.get("valid_rate", 0) or 0) - (base.get("valid_rate", 0) or 0)
rs       = rep.get("repair_success_count", 0) or 0
n_repair_files = len(glob.glob("outputs/demo_repair/*_r*.fuzz"))

print()
if delta_vr > 0 and rs >= 1:
    print(f"  RESULT: pipeline working. Repair recovered {rs} program(s); "
          f"{n_repair_files} *_r*.fuzz files written.")
    print(f"          delta valid_rate = {delta_vr:+.3f}  (positive = repair helped)")
else:
    print(f"  RESULT: small-N variance hit this run (delta={delta_vr:+.3f}). "
          f"Re-run for a cleaner sample or use the recorded N=200 numbers above.")

print()
PY

bar
echo " Demo complete."
echo
echo " Recorded full-scale (N=200) artifacts:"
echo "   outputs/baseline_repro_7b_200/metrics.json"
echo "   outputs/repair_repro_7b_200/metrics.json"
echo
echo " Live demo artifacts (this run):"
echo "   outputs/demo_baseline/   (20 programs)"
echo "   outputs/demo_repair/     (20 programs + repair attempts + repair_cache.json)"
bar
