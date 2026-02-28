"""
[INPUT]: agent.kernel (Kernel), subprocess, os, signal, agent.tools._truncate
[OUTPUT]: register()
[POS]: bash 工具 — 沙箱化 shell 命令执行；超时 + 进程树清理 + tail 截断
[PROTOCOL]: 变更时更新此头部，然后检查 CLAUDE.md
"""

from __future__ import annotations

import os
import signal
import subprocess
from pathlib import Path

from agent.tools._truncate import truncate_tail


# ─────────────────────────────────────────────────────────────────────────────
# 常量
# ─────────────────────────────────────────────────────────────────────────────

_DEFAULT_TIMEOUT = 30


# ─────────────────────────────────────────────────────────────────────────────
# 注册
# ─────────────────────────────────────────────────────────────────────────────

def register(kernel: object, cwd: Path | None = None) -> None:
    """向 Kernel 注册 bash 工具"""

    work_dir = str((cwd or Path.cwd()).resolve())

    def bash_handler(args: dict) -> dict:
        command = args["command"]
        timeout = args.get("timeout", _DEFAULT_TIMEOUT)

        try:
            proc = subprocess.Popen(
                command,
                shell=True,
                stdout=subprocess.PIPE,
                stderr=subprocess.STDOUT,
                cwd=work_dir,
                preexec_fn=os.setsid,
            )
        except OSError as e:
            return {"error": f"启动失败: {e}"}

        try:
            stdout, _ = proc.communicate(timeout=timeout)
        except subprocess.TimeoutExpired:
            # 杀死整个进程组
            try:
                os.killpg(os.getpgid(proc.pid), signal.SIGKILL)
            except OSError:
                pass
            proc.wait()
            # 收集已有输出
            partial = proc.stdout.read() if proc.stdout else b""
            output = partial.decode("utf-8", errors="replace")
            tr = truncate_tail(output)
            return {
                "error": f"命令超时 ({timeout}s)",
                "output": tr.content,
                "truncated": tr.truncated,
                "total_lines": tr.total_lines,
            }

        output = stdout.decode("utf-8", errors="replace")
        tr = truncate_tail(output)

        result: dict = {
            "exit_code": proc.returncode,
            "output": tr.content,
        }
        if tr.truncated:
            result["truncated"] = True
            result["total_lines"] = tr.total_lines
        if proc.returncode != 0:
            result["error"] = f"退出码: {proc.returncode}"
        return result

    kernel.tool(
        name="bash",
        description=(
            "执行 shell 命令。返回 stdout + exit_code。"
            "超时默认 30 秒。长输出自动截断（保留末尾）。"
        ),
        parameters={
            "type": "object",
            "properties": {
                "command": {"type": "string", "description": "shell 命令"},
                "timeout": {"type": "integer", "description": "超时秒数（默认 30）"},
                "description": {"type": "string", "description": "命令描述（供追踪用）"},
            },
            "required": ["command"],
        },
        handler=bash_handler,
    )
