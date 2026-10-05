"""Linux PID-namespace entry point. Never run outside the owned namespace."""

import json
import ctypes
import os
from pathlib import Path
import sys


def main():
    status = Path("/proc/self/status").read_text()
    pids = next(
        line.split()[1:] for line in status.splitlines() if line.startswith("NSpid:")
    )
    if len(pids) < 2 or pids[-1] != "1":
        raise RuntimeError("session must be PID 1 in a new namespace")
    identity = {
        "pid": int(pids[0]),
        "namespace": os.readlink("/proc/self/ns/pid"),
        "start_ticks": Path("/proc/self/stat")
        .read_text()
        .rsplit(")", 1)[1]
        .split()[19],
    }
    with Path(sys.argv[1]).open("x") as marker:
        json.dump(identity, marker)
    if os.readlink("/proc/self/ns/mnt") == sys.argv[2]:
        raise RuntimeError("a private mount namespace is required")
    # /proc must describe this PID namespace. Leaving the host's proc mount in
    # place makes nested Codex/bwrap look up namespace-local PIDs on the host.
    libc = ctypes.CDLL(None, use_errno=True)
    if libc.mount(b"proc", b"/proc", b"proc", 2 | 4 | 8, None) != 0:
        raise OSError(ctypes.get_errno(), "mounting session procfs failed")
    os.execv(sys.argv[3], sys.argv[3:])


if __name__ == "__main__":
    main()
