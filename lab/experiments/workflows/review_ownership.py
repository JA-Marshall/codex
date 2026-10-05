"""Host process identities for explicit interruption after runner loss."""

import os
from pathlib import Path

from workflows.process_pause import process_stat


def host_identity(runtime):
    pid = os.getpid()
    return {"runtime": runtime, "runner": {"pid": pid, "start_ticks": process_stat(pid)[2]},
            "boot_id": Path('/proc/sys/kernel/random/boot_id').read_text().strip()}


def ownership_alive(identity):
    if not isinstance(identity, dict) or set(identity) != {"runtime", "runner", "boot_id"}:
        return False
    if any(not isinstance(identity[key], dict) or type(identity[key].get("pid")) is not int or not isinstance(identity[key].get("start_ticks"), str) for key in ("runner", "runtime")):
        return False
    if not isinstance(identity["runtime"].get("namespace"), str):
        return False
    if identity["boot_id"] != Path('/proc/sys/kernel/random/boot_id').read_text().strip():
        return False
    for key in ("runner", "runtime"):
        value = identity[key]
        stat = process_stat(value["pid"])
        if stat is None or stat[2] != value["start_ticks"] or stat[0] in ("Z", "X"):
            return False
    try:
        return os.readlink(f"/proc/{identity['runtime']['pid']}/ns/pid") == identity["runtime"]["namespace"]
    except OSError:
        return False
