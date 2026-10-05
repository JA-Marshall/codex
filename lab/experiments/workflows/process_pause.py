"""Linux process-tree pause with PID ownership checks, including nested namespaces."""

import os
from pathlib import Path
import signal
import time


def process_stat(pid):
    try:
        fields = Path(f"/proc/{pid}/stat").read_text().rsplit(")", 1)[1].split()
        return fields[0], int(fields[1]), fields[19]
    except (FileNotFoundError, ProcessLookupError):
        return None


class ProcessPause:
    def __init__(self, process):
        self.process = process
        self.members = {}
        self.paused = False

    def _tree(self):
        root = self.process.identity
        if root is None:
            raise RuntimeError("runtime has no verified namespace identity")
        state = process_stat(root["pid"])
        if not state or state[2] != root["start_ticks"] or state[0] in ("Z", "X"):
            raise RuntimeError("runtime ownership lost")
        if os.readlink(f"/proc/{root['pid']}/ns/pid") != root["namespace"]:
            raise RuntimeError("runtime namespace changed")
        all_processes = {}
        for path in Path("/proc").iterdir():
            if path.name.isdigit():
                stat = process_stat(int(path.name))
                if stat:
                    all_processes[int(path.name)] = stat
        owned = {root["pid"]: state}
        while True:
            children = {pid: stat for pid, stat in all_processes.items()
                        if stat[1] in owned and pid not in owned}
            if not children:
                return owned
            owned.update(children)

    def _signal(self, pid, ticks, sig):
        # pidfd pins the process before checking its start identity, so a PID
        # recycled between inspection and delivery can never receive a signal.
        try:
            fd = os.pidfd_open(pid)
        except ProcessLookupError:
            return
        try:
            stat = process_stat(pid)
            if stat and stat[2] == ticks and stat[0] not in ("Z", "X"):
                signal.pidfd_send_signal(fd, sig)
        finally:
            os.close(fd)

    def freeze(self, deadline):
        while time.monotonic() < deadline:
            tree = self._tree()
            for pid, stat in tree.items():
                self.members[pid] = stat[2]
                self._signal(pid, stat[2], signal.SIGSTOP)
            after = self._tree()
            # Re-enumeration catches children forked while stopping parents.
            if all(pid in self.members and self.members[pid] == stat[2]
                   and stat[0] in ("T", "t", "Z", "X")
                   for pid, stat in after.items()):
                self.paused = True
                return {"processes": len(after), "namespace": self.process.identity,
                        "quiescent": True}
            time.sleep(0.01)
        raise TimeoutError("runtime did not quiesce within pause deadline")

    def verify(self):
        if not self.paused:
            raise RuntimeError("runtime is not paused")
        tree = self._tree()
        if not all(self.members.get(pid) == stat[2] and stat[0] in ("T", "t", "Z", "X")
                   for pid, stat in tree.items()):
            raise RuntimeError("paused runtime advanced or changed ownership")

    def resume(self):
        self.verify()
        for pid, ticks in reversed(list(self.members.items())):
            self._signal(pid, ticks, signal.SIGCONT)
        self.members.clear()
        self.paused = False

    def terminate(self):
        # Kill namespace init, which tears down every nested descendant even
        # when stopped. Never resume on an uncertain/crashed handoff.
        root = self.process.identity
        if root:
            self._signal(root["pid"], root["start_ticks"], signal.SIGKILL)
