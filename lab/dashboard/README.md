# Muse experiment monitor

A local, read-only view of the existing campaign files. It refreshes every five
seconds and shows prepared batches, completed results, observed activity, task
types, phase history and recorded test outcomes. Clicking a trial opens details.

On this Windows machine, run `./lab/dashboard/open-dashboard.ps1` in PowerShell.
It starts the observer in Ubuntu and opens <http://127.0.0.1:8787>. Run it again
to reopen the same observer. The harness continues independently of this page.

For other devices on the same local network, run
`./lab/dashboard/open-dashboard.ps1 -Lan`. It prints this PC's LAN URL and starts
a Windows proxy bound to that address, accepting clients only from its local
IPv4 subnet. `-LanAddress <local-ip>` selects a particular adapter. The current
address is <http://192.168.68.52:8787>; a DHCP address change can change this URL.
The Windows Python firewall permission already allows this PC's private network.
This does not configure router forwarding or internet access. The same read-only
views are available to devices on the selected subnet, with no login.

Or run the server directly on the machine containing the campaign records:

```sh
python3 lab/dashboard/server.py --port 8787
```

Defaults are `~/.cache/codex-lab-campaigns` and `~/.cache/codex-lab-timing`.
Override these with `--campaign-root` and `--timing-root`. Python 3.10+ and a
current browser are sufficient; there are no frontend packages or model calls.
The underlying server binds to loopback and exposes only GET/HEAD views and fixed static
assets. It never starts, cancels, retries or edits experiments and does not serve
raw logs, prompts, private test contents or provider credentials.

“In progress” means an unfinished trial has recent recorded activity. “Quiet”
means no activity for two minutes; neither proves whether its process is alive.
Completed host elapsed excludes setup and grading. While a trial is unfinished,
its elapsed time can include setup, as identified in its details. All elapsed
times include provider waiting. Queue wait appears only from an existing timing
audit; missing values stay unknown. Stopped phases are shutdown records, not test
pass verdicts. No estimated finish time is invented.

Backend checks: `python3 -m unittest discover -s lab/dashboard -p 'test_*.py'`.
The dashboard is separate from frozen campaign inputs and binary releases.
