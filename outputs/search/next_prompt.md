# Search round results

## Top candidates (by valid_rate mean)

| name | valid_rate mean |
|------|------------------|
| r3_T1_a2_wide_gate | 0.91 |
| r3_T1_a2_compile | 0.875 |
| r3_T1_a3_compile | 0.8625 |
| r3_T1_a2_highT | 0.8325 |
| r3_T2_a2_compile | 0.8275 |

## Bottom candidates

| name | valid_rate mean |
|------|------------------|
| r3_T1_a1_single | 0.7875 |
| r3_T1_a2_lowT | 0.7675 |
| r3_T3_a2_compile | 0.755 |
| r3_I1_a2_instruction | 0.745 |
| r3_baseline_no_repair | 0.6225 |

## Common failure signature samples

- `COMPILE:/home/aniket.salunke/fuzz4all-cs-final/outputs/search/eval_r3_T2_a2_compile/run_0/130_r1.fuzz: In function ‘int main()’:`
- `COMPILE:/home/aniket.salunke/fuzz4all-cs-final/outputs/search/eval_r3_T1_a2_compile/run_0/102_r2.fuzz: In function ‘int main()’:`
- `COMPILE:/home/aniket.salunke/fuzz4all-cs-final/outputs/search/eval_r3_T1_a2_lowT/run_0/171_r2.fuzz:N:M: error: redefinition of ‘int a’`
- `COMPILE:/home/aniket.salunke/fuzz4all-cs-final/outputs/search/eval_r3_I1_a2_instruction/run_0/0_r1.fuzz: In function ‘int main()’:`
- `COMPILE:/home/aniket.salunke/fuzz4all-cs-final/outputs/search/eval_r3_T1_a2_highT/run_0/43.fuzz:N:M: error: stray ‘`’ in program`
- `COMPILE:/home/aniket.salunke/fuzz4all-cs-final/outputs/search/eval_r3_I1_a2_instruction/run_0/199_r2.fuzz:N:M: error: ‘::main’ must return ‘int’`
- `COMPILE:/home/aniket.salunke/fuzz4all-cs-final/outputs/search/eval_r3_T1_a3_compile/run_0/36.fuzz:N:M: error: redefinition of ‘int main()’`
- `COMPILE:/home/aniket.salunke/fuzz4all-cs-final/outputs/search/eval_r3_T1_a2_lowT/run_0/118_r1.fuzz:N:M: error: redefinition of ‘int main()’`
- `COMPILE:/home/aniket.salunke/fuzz4all-cs-final/outputs/search/eval_r3_T1_a2_lowT/run_0/173.fuzz:N:M: error: redefinition of ‘int main()’`
- `COMPILE:In file included from /usr/include/c++/11/stop_token:35,`
- `COMPILE:/home/aniket.salunke/fuzz4all-cs-final/outputs/search/eval_r3_T2_a2_compile/run_0/155_r1.fuzz: In function ‘int main()’:`
- `COMPILE:/home/aniket.salunke/fuzz4all-cs-final/outputs/search/eval_r3_I1_a2_instruction/run_0/169.fuzz:N:M: error: stray ‘`’ in program`
- `COMPILE:/home/aniket.salunke/fuzz4all-cs-final/outputs/search/eval_r3_baseline_no_repair/run_0/152.fuzz:N:M: error: conflicting declaration of C function ‘int main()’`
- `COMPILE:/home/aniket.salunke/fuzz4all-cs-final/outputs/search/eval_r3_T3_a2_compile/run_0/54.fuzz:N:M: error: ‘array_t’ is not a template`
- `COMPILE:/home/aniket.salunke/fuzz4all-cs-final/outputs/search/eval_r3_T1_a2_lowT/run_0/164.fuzz: In function ‘int main()’:`

---

Please propose the next round of candidate configs in the same JSON format.
Format: a JSON array of objects with "name", "gen", and "repair" keys.
"gen" can override llm/fuzzing; "repair" can override repair section.
Save as candidates/round_02.json (or next number).
