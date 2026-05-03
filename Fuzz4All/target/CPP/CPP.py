import re
import subprocess
import time
from typing import List, Union

import torch

from Fuzz4All.target.target import (
    CompileStatus,
    FResult,
    Target,
    ValidationResult,
    _truncate_stderr,
)
from Fuzz4All.util.Logger import LEVEL
from Fuzz4All.util.util import comment_remover

class CPPTarget(Target):
    def __init__(self, **kwargs):
        super().__init__(**kwargs)
        self.SYSTEM_MESSAGE = "You are a C++ Fuzzer"
        if kwargs["template"] == "fuzzing_with_config_file":
            config_dict = kwargs["config_dict"]
            self.prompt_used = self._create_prompt_from_config(config_dict)
            self.config_dict = config_dict
        else:
            raise NotImplementedError

    def write_back_file(self, code):
        try:
            with open(
                "/tmp/temp{}.cpp".format(self.CURRENT_TIME), "w", encoding="utf-8"
            ) as f:
                f.write(code)
        except:
            pass
        return "/tmp/temp{}.cpp".format(self.CURRENT_TIME)

    def wrap_prompt(self, prompt: str) -> str:
        return f"/* {prompt} */\n{self.prompt_used['separator']}\n{self.prompt_used['begin']}"

    def wrap_in_comment(self, prompt: str) -> str:
        return f"/* {prompt} */"

    def filter(self, code) -> bool:
        clean_code = code.replace(self.prompt_used["begin"], "").strip()
        if self.prompt_used["target_api"] not in clean_code:
            return False
        return True

    def clean(self, code: str) -> str:
        code = comment_remover(code)
        return code

    # remove any comments, or blank lines
    def clean_code(self, code: str) -> str:
        code = comment_remover(code)
        code = "\n".join(
            [
                line
                for line in code.split("\n")
                if line.strip() != "" and line.strip() != self.prompt_used["begin"]
            ]
        )
        return code

    @staticmethod
    def _normalize_signature(stderr: str, exit_code: int, timed_out: bool) -> str:
        """Normalize failure output for clustering: strip paths, line/column, temp names; add category tag."""
        if timed_out:
            return "TIMEOUT"
        if not stderr:
            if exit_code != 0 and exit_code < 0:
                return "CRASH"
            return "UNKNOWN"
        s = stderr
        s_lower = s.lower()
        if "internal compiler error" in s_lower or "ice" in s_lower:
            first_line = s.strip().split("\n")[0] if s.strip() else ""
            first_line = re.sub(r":\d+:\d+", ":N:M", first_line)
            first_line = re.sub(r"/[^\s]+\.cpp", "<file>.cpp", first_line)
            first_line = re.sub(r"/tmp/temp[^\s]*", "<tmp>", first_line)
            return "ICE:" + first_line[:200]
        if "segmentation fault" in s_lower or "segfault" in s_lower or (exit_code != 0 and exit_code < 0):
            return "CRASH"
        lines = s.strip().split("\n")
        first_line = lines[0] if lines else ""
        first_line = re.sub(r":\d+:\d+", ":N:M", first_line)
        first_line = re.sub(r"/[^\s:]+\.cpp", "<file>.cpp", first_line)
        first_line = re.sub(r"/tmp/temp[^\s]*", "<tmp>", first_line)
        return "COMPILE:" + first_line[:300]

    def validate_compiler(self, compiler, filename) -> ValidationResult:
        out_obj = f"/tmp/out{self.CURRENT_TIME}.o"
        start = time.perf_counter()
        timed_out = False
        stderr_text = ""
        exit_code_val = 0
        try:
            result = subprocess.run(
                f"{compiler} -x c++ -std=c++23 -O0 -fdiagnostics-color=never -c {filename} -o {out_obj}",
                shell=True,
                capture_output=True,
                encoding="utf-8",
                timeout=5,
                text=True,
            )
            exit_code_val = result.returncode
            stderr_text = result.stderr or ""
        except subprocess.TimeoutExpired:
            timed_out = True
            exit_code_val = -1
            stderr_text = "timed out"
            pname = f"'{filename}'"
            subprocess.run(
                ["ps -ef | grep " + pname + " | grep -v grep | awk '{print $2}'"],
                shell=True,
            )
            subprocess.run(
                [
                    "ps -ef | grep "
                    + pname
                    + " | grep -v grep | awk '{print $2}' | xargs -r kill -9"
                ],
                shell=True,
            )
        elapsed = time.perf_counter() - start

        if timed_out:
            sig = self._normalize_signature("", -1, True)
            return ValidationResult(
                status=CompileStatus.TIMEOUT,
                exit_code=-1,
                elapsed_sec=elapsed,
                stderr=stderr_text,
                signature=sig,
            )

        if exit_code_val != 0:
            stderr_lower = (stderr_text or "").lower()
            if "internal compiler error" in stderr_lower:
                status = CompileStatus.ICE
            elif "segmentation fault" in stderr_lower or exit_code_val < 0:
                status = CompileStatus.CRASH
            else:
                status = CompileStatus.COMPILE_ERROR
            sig = self._normalize_signature(stderr_text, exit_code_val, False)
            return ValidationResult(
                status=status,
                exit_code=exit_code_val,
                elapsed_sec=elapsed,
                stderr=_truncate_stderr(stderr_text),
                signature=sig,
            )

        return ValidationResult(
            status=CompileStatus.OK,
            exit_code=0,
            elapsed_sec=elapsed,
            stderr="",
            signature="",
        )

    def validate_individual(self, filename) -> ValidationResult:
        return self.validate_compiler(self.target_name, filename)
