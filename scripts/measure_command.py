#!/usr/bin/env python3
"""Measure wall time, Linux process-tree peak RSS and I/O for one command."""
from __future__ import annotations

import argparse
import json
import os
from pathlib import Path
import subprocess
import time

from atomic_output import atomic_write_json


def children(pid: int) -> set[int]:
    found = {pid}
    pending = [pid]
    while pending:
        current = pending.pop()
        try:
            values = (Path(f"/proc/{current}/task/{current}/children").read_text().split())
        except OSError:
            continue
        for value in values:
            child = int(value)
            if child not in found:
                found.add(child)
                pending.append(child)
    return found


def ps_tree_rss(pid: int) -> int | None:
    try:
        output = subprocess.run(["ps", "-e", "-o", "pid=,ppid=,rss="], capture_output=True, text=True, check=True).stdout
        rows = [tuple(map(int, line.split())) for line in output.splitlines() if line.split()]
    except (OSError, subprocess.SubprocessError, ValueError):
        return None
    descendants = {pid}
    changed = True
    while changed:
        changed = False
        for child, parent, _rss in rows:
            if parent in descendants and child not in descendants:
                descendants.add(child); changed = True
    return sum(rss for current, _parent, rss in rows if current in descendants) * 1024


def snapshot(pid: int) -> tuple[int | None, int | None, int | None]:
    rss = ps_tree_rss(pid)
    read_bytes = write_bytes = 0
    io_available = False
    for current in children(pid):
        try:
            values = dict(line.split(":", 1) for line in Path(f"/proc/{current}/io").read_text().splitlines())
            read_bytes += int(values.get("read_bytes", 0))
            write_bytes += int(values.get("write_bytes", 0))
            io_available = True
        except (OSError, ValueError):
            pass
    return rss, (read_bytes if io_available else None), (write_bytes if io_available else None)


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--output", required=True)
    parser.add_argument("--cwd")
    parser.add_argument("command", nargs=argparse.REMAINDER)
    args = parser.parse_args()
    command = args.command[1:] if args.command[:1] == ["--"] else args.command
    if not command:
        parser.error("command is required after --")
    started = time.perf_counter()
    process = subprocess.Popen(command, cwd=args.cwd)
    peak_rss = peak_read = peak_write = None
    while process.poll() is None:
        rss, read_bytes, write_bytes = snapshot(process.pid)
        if rss is not None:
            peak_rss = max(peak_rss or 0, rss)
        if read_bytes is not None:
            peak_read = max(peak_read or 0, read_bytes)
        if write_bytes is not None:
            peak_write = max(peak_write or 0, write_bytes)
        time.sleep(0.1)
    report = {
        "schema": "ai-ppt-plus/command-resource-measurement/v1",
        "status": "passed" if process.returncode == 0 else "failed",
        "command": command,
        "cwd": str(Path(args.cwd).resolve()) if args.cwd else str(Path.cwd()),
        "exit_code": process.returncode,
        "wall_duration_ms": round((time.perf_counter() - started) * 1000, 3),
        "peak_rss_bytes": peak_rss,
        "read_bytes": peak_read,
        "write_bytes": peak_write,
        "resource_available": {"peak_rss": peak_rss is not None, "io": peak_read is not None and peak_write is not None},
        "sampling_interval_ms": 100,
    }
    atomic_write_json(args.output, report)
    print(json.dumps(report, ensure_ascii=False))
    return process.returncode


if __name__ == "__main__":
    raise SystemExit(main())
