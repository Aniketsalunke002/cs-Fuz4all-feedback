"""Error-guided repair stage: use LLM + compiler stderr to repair failed programs."""

import os
import re
from dataclasses import dataclass
from pathlib import Path
from typing import Any, Dict, Optional

from Fuzz4All.target.target import CompileStatus, Target, ValidationResult


@dataclass
class RepairResult:
    code: str
    prompt: str
    raw_output: str


@dataclass
class RepairConfig:
    enabled: bool = False
    max_attempts: int = 1
    template_id: str = "T1"
    include_stderr: bool = True
    timeout_sec: int = 3
    cache: bool = False
    error_gate: str = "compile_error"
    max_tokens: int = 512
    temperature: float = 0.7


def should_repair(validation_result: ValidationResult, error_gate: str) -> bool:
    """Return True if this failure type should trigger repair."""
    if validation_result.status == CompileStatus.OK:
        return False
    gate = (error_gate or "compile_error").lower()
    if gate == "all_non_timeout":
        return validation_result.status != CompileStatus.TIMEOUT
    if gate == "compile_error":
        return validation_result.status == CompileStatus.COMPILE_ERROR
    if gate == "ice":
        return validation_result.status == CompileStatus.ICE
    if gate == "crash":
        return validation_result.status == CompileStatus.CRASH
    if gate == "timeout":
        return validation_result.status == CompileStatus.TIMEOUT
    if gate == "syntax" or gate == "type":
        return validation_result.status == CompileStatus.COMPILE_ERROR
    return validation_result.status == CompileStatus.COMPILE_ERROR


def _default_template_dir() -> Path:
    """Default directory for repair templates (prompts/repair relative to repo root)."""
    cwd = Path.cwd()
    if (cwd / "prompts" / "repair").exists():
        return cwd / "prompts" / "repair"
    script_dir = Path(__file__).resolve().parent
    repo = script_dir.parent.parent
    return repo / "prompts" / "repair"


def _comment_out_program(program_text: str) -> str:
    """Convert program lines to C++ comment lines for completion-style prompts."""
    lines = program_text.strip().split("\n")
    return "\n".join(f"// {line}" for line in lines)


def _extract_seed_line(program_text: str) -> str:
    """Extract the first meaningful line to seed the completion (e.g. #include)."""
    for line in program_text.strip().split("\n"):
        stripped = line.strip()
        if stripped.startswith("#include"):
            return stripped
        if stripped and not stripped.startswith("//") and not stripped.startswith("/*"):
            return stripped
    return "#include <iostream>"


def _first_stderr_line(stderr_text: str) -> str:
    """Extract the first non-empty error line from stderr."""
    if not stderr_text:
        return "compilation error"
    for line in stderr_text.strip().split("\n"):
        line = line.strip()
        if "error:" in line.lower():
            return line[:200]
    first = stderr_text.strip().split("\n")[0]
    return first[:200] if first else "compilation error"


def build_repair_prompt(
    template_id: str,
    program_text: str,
    stderr_text: str,
    template_dir: Optional[os.PathLike] = None,
) -> str:
    """Load template and fill in program and stderr. Returns the prompt string."""
    template_dir = Path(template_dir) if template_dir else _default_template_dir()
    path = template_dir / f"{template_id}.txt"
    if not path.exists():
        fallback = template_dir / "T1.txt"
        path = fallback if fallback.exists() else path
    try:
        template = path.read_text(encoding="utf-8")
    except Exception:
        template = (
            "// Original C++ code (has compilation error):\n"
            "{commented_program}\n"
            "// Compiler error: {stderr_first_line}\n"
            "// Fixed version of the code above:\n"
            "{seed_line}"
        )
    commented = _comment_out_program(program_text)
    seed = _extract_seed_line(program_text)
    first_err = _first_stderr_line(stderr_text)

    prompt = (
        template
        .replace("{commented_program}", commented)
        .replace("{stderr_first_line}", first_err)
        .replace("{seed_line}", seed)
        .replace("{program}", program_text)
        .replace("{stderr}", stderr_text[:4000] if stderr_text else "(no stderr)")
    )
    return prompt


def extract_program_from_model_output(text: str) -> str:
    """Strip markdown code fences and extra commentary; return C++ code only."""
    if not text or not text.strip():
        return ""
    s = text.strip()
    if "```" in s:
        parts = re.split(r"```\w*\n?", s)
        for part in parts:
            part = part.strip()
            if part and ("#include" in part or "int main" in part or "class " in part or "template" in part):
                return part
        match = re.search(r"```(?:cpp|c\+\+)?\s*\n(.*?)```", s, re.DOTALL)
        if match:
            return match.group(1).strip()
        first = re.search(r"```(?:cpp|c\+\+)?\s*\n(.*)", s, re.DOTALL)
        if first:
            return first.group(1).strip()
    code_lines = []
    for line in s.split("\n"):
        stripped = line.strip()
        if stripped.startswith("//") and ("Original" in stripped or "error:" in stripped.lower() or "Fixed" in stripped):
            continue
        code_lines.append(line)
    result = "\n".join(code_lines).strip()
    return result if result else s


def normalize_error_signature(signature: str) -> str:
    """Normalize signature for cache key (light normalization)."""
    if not signature:
        return ""
    return signature.strip()[:500]


def repair_llm(
    target: Target,
    program_text: str,
    stderr_text: str,
    config: RepairConfig,
    template_dir: Optional[os.PathLike] = None,
) -> RepairResult:
    """Call LLM once to produce repaired program; return RepairResult."""
    prompt = build_repair_prompt(
        config.template_id,
        program_text,
        stderr_text if config.include_stderr else "",
        template_dir=template_dir,
    )
    seed = _extract_seed_line(program_text)
    raw = target.generate_single(
        prompt,
        max_length=config.max_tokens,
        temperature=config.temperature,
    )
    full_output = seed + "\n" + raw if raw else ""
    repaired_code = extract_program_from_model_output(full_output)
    return RepairResult(code=repaired_code, prompt=prompt, raw_output=raw or "")


def repair_config_from_dict(d: Optional[Dict[str, Any]]) -> RepairConfig:
    """Build RepairConfig from YAML config section."""
    if not d:
        return RepairConfig(enabled=False)
    return RepairConfig(
        enabled=bool(d.get("enabled", False)),
        max_attempts=int(d.get("max_attempts", 1)),
        template_id=str(d.get("template_id", "T1")),
        include_stderr=bool(d.get("include_stderr", True)),
        timeout_sec=int(d.get("timeout_sec", 3)),
        cache=bool(d.get("cache", False)),
        error_gate=str(d.get("error_gate", "compile_error")),
        max_tokens=int(d.get("max_tokens", 512)),
        temperature=float(d.get("temperature", 0.7)),
    )
