"""
[INPUT]: subprocess, sys, os, argparse, pathlib, json, importlib.metadata
[OUTPUT]: main — athenaclaw-harness CLI 入口（update/status/version/start 子命令）
[POS]: 进程生命周期管理层：幂等更新 + 自动回滚 + 健康检查 + 服务检测 + 监督模式
[PROTOCOL]: 变更时更新此头部，然后检查 CLAUDE.md
"""

from __future__ import annotations

import argparse
import json
import os
import subprocess
import sys
from pathlib import Path


# ─────────────────────────────────────────────────────────────────────────────
# 常量
# ─────────────────────────────────────────────────────────────────────────────

EXIT_UPDATE = 42


# ─────────────────────────────────────────────────────────────────────────────
# git 辅助
# ─────────────────────────────────────────────────────────────────────────────

def _install_dir() -> Path:
    raw = os.getenv("ATHENACLAW_INSTALL_DIR")
    if raw:
        return Path(raw).expanduser().resolve()
    here = Path(__file__).resolve().parent
    for p in (here, here.parent, here.parent.parent):
        if (p / ".git").is_dir():
            return p
    return here


def _run_git(*args: str, cwd: Path | None = None) -> subprocess.CompletedProcess:
    return subprocess.run(
        ["git", *args],
        capture_output=True,
        text=True,
        cwd=str(cwd or _install_dir()),
    )


def _current_commit() -> str:
    r = _run_git("rev-parse", "HEAD")
    return r.stdout.strip() if r.returncode == 0 else "unknown"


def _current_tag() -> str:
    r = _run_git("describe", "--tags", "--always")
    return r.stdout.strip() if r.returncode == 0 else _current_commit()[:8]


def _current_branch() -> str:
    r = _run_git("rev-parse", "--abbrev-ref", "HEAD")
    return r.stdout.strip() if r.returncode == 0 else "unknown"


def _git_fetch() -> bool:
    r = _run_git("fetch", "--tags", "--prune")
    return r.returncode == 0


def _commits_behind() -> int:
    branch = _current_branch()
    r = _run_git("rev-list", f"HEAD..origin/{branch}", "--count")
    if r.returncode != 0:
        return -1
    return int(r.stdout.strip())


def _git_pull_ff() -> bool:
    r = _run_git("pull", "--ff-only")
    return r.returncode == 0


def _git_checkout(ref: str) -> bool:
    r = _run_git("checkout", ref)
    return r.returncode == 0


# ─────────────────────────────────────────────────────────────────────────────
# pip / health
# ─────────────────────────────────────────────────────────────────────────────

def _pip_install() -> bool:
    d = _install_dir()
    r = subprocess.run(
        [sys.executable, "-m", "pip", "install", "-e", str(d), "--quiet"],
        capture_output=True,
        text=True,
    )
    return r.returncode == 0


def _health_check() -> tuple[bool, str | None]:
    r = subprocess.run(
        [sys.executable, "-c", "import athenaclaw; print('ok')"],
        capture_output=True,
        text=True,
        timeout=30,
    )
    if r.returncode == 0 and "ok" in r.stdout:
        return True, None
    err = r.stderr.strip() or r.stdout.strip() or "import failed"
    return False, err


# ─────────────────────────────────────────────────────────────────────────────
# 版本
# ─────────────────────────────────────────────────────────────────────────────

def _package_version() -> str:
    try:
        from importlib.metadata import version
        return version("athenaclaw")
    except Exception:
        return "unknown"


# ─────────────────────────────────────────────────────────────────────────────
# 服务检测
# ─────────────────────────────────────────────────────────────────────────────

_SERVICE_PATTERNS = [
    ("cli", "athenaclaw.interfaces.cli"),
    ("telegram", "athenaclaw.interfaces.telegram"),
    ("discord", "athenaclaw.interfaces.discord"),
    ("worker", "athenaclaw.automation.worker"),
]


def _detect_running_services() -> list[dict]:
    services = []
    for name, pattern in _SERVICE_PATTERNS:
        r = subprocess.run(
            ["pgrep", "-f", pattern],
            capture_output=True,
            text=True,
        )
        if r.returncode == 0:
            pids = [p for p in r.stdout.strip().split("\n") if p]
            if pids:
                services.append({"name": name, "pids": pids})
    return services


# ─────────────────────────────────────────────────────────────────────────────
# 子命令: update
# ─────────────────────────────────────────────────────────────────────────────

def cmd_update(version: str = "latest") -> dict:
    """幂等更新。任何步骤失败 → 自动回滚。"""
    old = _current_commit()
    print(f"[harness] current: {old[:8]}")

    try:
        print("[harness] fetching...")
        if not _git_fetch():
            raise RuntimeError("git fetch failed")

        if version == "latest":
            print("[harness] pulling latest...")
            if not _git_pull_ff():
                raise RuntimeError("git pull --ff-only failed")
        else:
            print(f"[harness] checking out {version}...")
            if not _git_checkout(version):
                raise RuntimeError(f"git checkout {version} failed")

        print("[harness] installing...")
        if not _pip_install():
            raise RuntimeError("pip install failed")

        print("[harness] health check...")
        ok, err = _health_check()
        if not ok:
            raise RuntimeError(f"health check failed: {err}")

        new = _current_commit()
        print(f"[harness] updated: {old[:8]} → {new[:8]}")
        return {"status": "ok", "old": old[:8], "new": new[:8]}

    except Exception as e:
        print(f"[harness] update failed: {e}")
        print("[harness] rolling back...")
        _git_checkout(old)
        _pip_install()
        return {"status": "failed", "error": str(e), "rolled_back_to": old[:8]}


# ─────────────────────────────────────────────────────────────────────────────
# 子命令: status
# ─────────────────────────────────────────────────────────────────────────────

def cmd_status() -> dict:
    """当前版本 + 可用更新 + 运行中的服务。"""
    tag = _current_tag()
    commit = _current_commit()[:8]
    pkg_ver = _package_version()
    _git_fetch()
    behind = _commits_behind()
    services = _detect_running_services()

    print(f"AthenaClaw {pkg_ver} (tag: {tag}, commit: {commit})")
    if behind > 0:
        print(f"Updates: {behind} commit(s) behind remote")
    elif behind == 0:
        print("Up to date")
    else:
        print("Could not check remote")

    if services:
        print("\nRunning services:")
        for svc in services:
            pids = ", ".join(svc["pids"])
            print(f"  {svc['name']:12s} PID {pids}")
    else:
        print("\nNo running services detected")

    return {
        "version": pkg_ver,
        "tag": tag,
        "commit": commit,
        "behind": behind,
        "updates_available": behind > 0,
        "running_services": services,
    }


# ─────────────────────────────────────────────────────────────────────────────
# 子命令: version
# ─────────────────────────────────────────────────────────────────────────────

def cmd_version() -> None:
    print(f"{_package_version()} ({_current_tag()})")


# ─────────────────────────────────────────────────────────────────────────────
# 子命令: start (监督模式)
# ─────────────────────────────────────────────────────────────────────────────

def cmd_start(agent_args: list[str]) -> None:
    """while-loop 监督: 启动 agent → exit 42 时 update → 重启。"""
    print(f"[harness] supervised start — install_dir={_install_dir()}")
    while True:
        cmd = [sys.executable, "-m", "athenaclaw.interfaces.cli"] + agent_args
        print(f"[harness] starting agent...")
        code = subprocess.call(cmd)

        if code == 0:
            print("[harness] agent exited normally")
            break
        elif code == EXIT_UPDATE:
            print("[harness] agent requested update+restart")
            result = cmd_update()
            if result["status"] != "ok":
                print("[harness] update failed, stopping")
                sys.exit(1)
            continue
        else:
            print(f"[harness] agent exited with code {code}")
            break


# ─────────────────────────────────────────────────────────────────────────────
# CLI 入口
# ─────────────────────────────────────────────────────────────────────────────

def main() -> None:
    parser = argparse.ArgumentParser(
        prog="athenaclaw-harness",
        description="AthenaClaw service management",
    )
    sub = parser.add_subparsers(dest="command")

    # update
    p_update = sub.add_parser("update", help="Update to latest or specific version")
    p_update.add_argument("version", nargs="?", default="latest")

    # status
    sub.add_parser("status", help="Show version, updates, running services")

    # version
    sub.add_parser("version", help="Show version number")

    # start
    p_start = sub.add_parser("start", help="Start agent in supervised mode")
    p_start.add_argument("agent_args", nargs="*", default=[])

    args = parser.parse_args()

    if args.command == "update":
        result = cmd_update(args.version)
        sys.exit(0 if result["status"] == "ok" else 1)
    elif args.command == "status":
        cmd_status()
    elif args.command == "version":
        cmd_version()
    elif args.command == "start":
        cmd_start(args.agent_args)
    else:
        parser.print_help()
        sys.exit(1)


if __name__ == "__main__":
    main()
