# Parallel prepared-run batches

The batch coordinator launches independent Codex lab hosts and bounds their active work. A host waiting for human approval holds its checkout lock but consumes no execution slot. An amendment waits independently; other approved conditions keep running. No core agent-loop, model/provider, TUI, sandbox or session-lifecycle changes are required.

## Run a batch

Build the updated `codex-lab` binary from `codex-rs` with `cargo build -p codex-lab-runtime --bin codex-lab`. Keep experimental binaries in versioned locations rather than pointing frozen experiments at a mutable Cargo build output. The existing real-host validation and examples use Linux/WSL; the Python coordinator also has subprocess tests on Windows.

Prepare each condition with the existing `codex-lab prepare` command, using separate clean checkouts and distinct run IDs. For representation experiments, prepare one canonical plan and import those exact bytes into the other condition with `--plan-file`. Preparation does not approve implementation. Use the same pinned binary/settings for preparation and execution.

Create a JSON input manifest, for example:

```json
{
  "schema_version": 1,
  "binary": "/absolute/path/to/versioned/codex-lab",
  "runs": [
    {"run_id": "trial-md", "prepared": "/absolute/path/to/runs/md-prepared/evidence/prepared.json"},
    {"run_id": "trial-json", "prepared": "/absolute/path/to/runs/json-prepared/evidence/prepared.json"}
  ]
}
```

Paths are absolute or relative to the manifest. Optional `binary_sha256` and per-run `prepared_sha256` fields enforce expected bytes. The coordinator always records the actual hashes, interpreter, scheduler source hashes and effective job limit. Provider credentials come from the normal child environment and dedicated Codex home; never put them in the manifest.

From the repository root:

```sh
python3.12 lab/experiments/run_batch.py /absolute/path/to/batch-input.json --jobs 4 --output /absolute/path/to/batches/trial-001
```

`--jobs` defaults to 2 and accepts 1–32. Each batch has at most 32 host processes, including those waiting for review. All hosts enter the existing `run-prepared` validation/review path; only a human decision can release one into execution. Jobs count the interval from a dispatched decision through the next quiescent review request or process exit. This includes any replanning after rejection and amendment preparation, not just implementation model calls.

The terminal prints each full approval target and a path to `RUN_ID/review-NN.json`. Read its rendered plan and target, then enter a decision against that current request:

```text
trial-md 1 approve <displayed content_sha256>
trial-json 1 approve <displayed content_sha256>
```

These are separate human decisions. If a slot is unavailable, the decision waits in memory; an unrelated unanswered review does not block it. The coordinator sends the exact full target and request number through that child's private stdin. The child checks both before applying its existing decision parser and human approval state transition. Matching canonical plan hashes alone cannot authorize another run.

Other commands use the same run/request prefix: `reject <reason>`, `edit <absolute canonical JSON path>`, or `abort`. A rejection may invoke the planner and therefore requires a slot. Editing never approves the edited plan. Each subsequent review has a new request number and needs a new human decision. Approval records are audit data; the coordinator never loads them as authority or resumes them after a restart.

## Artifacts, cancellation and limits

The fresh output directory contains `batch.json`, timestamped `events.jsonl`, `result.json`, and per-host stdout/stderr logs and review request files. Child run artifacts remain in their existing run directories. Events record starts, queued/sent decisions, active job counts, reviews and exits. Final exit codes include null for conditions never launched. A batch succeeds only when all hosts exit successfully and no channel/startup error or cancellation occurred. Host success is still distinct from independently evaluated task success.

Closing input discards unsent decisions, closes review channels and waits for existing hosts to exit. Ctrl+C requests the same drain and returns failure. A running phase is not force-killed; an existing host can finish its approved work or stop at its next review. There is no crash resume, automatic retry or approval reuse. Process exit alone does not establish tool shutdown: use the existing evaluator's shutdown checks before evaluating each terminal candidate.

Input and output are bounded: 64 KiB input manifests/descriptors, 32 reviews per host, 512 KiB rendered plan content, 4 MiB protocol frames, 8 MiB stdout and 1 MiB retained stderr per host, and 4,096 human commands of at most 16,384 characters. Oversized stdout/protocol input fails that channel closed. Stderr beyond its retained limit is drained and truncated. The child retains its own existing phase/context limits. This runner introduces no cumulative token or spend cap.

Conflicting or nested checkouts, shared Git lock directories, duplicate run IDs, existing destinations and output paths overlapping protected inputs are refused before launch. The runtime still owns its repository lock, full prepared-input validation and sandbox policies. Raw model data and credentials should remain local.

Concurrency changes resource contention, provider queuing and wall time. Record the batch artifact alongside comparisons, and keep the job limit and provider limits constant when testing another variable. The existing `codex-lab compare` command does not yet ingest batch scheduling metadata automatically. Do not treat a serial/parallel cost comparison as a representation-only comparison.

## Validation and remaining scope

Subprocess tests prove actual overlap, the job bound, progress around initial/amendment review waits, stale/cross-run decision refusal, isolated failures, EOF drain, cancellation before launch, bounded output and preflight conflict/pin checks. A real-host integration test uses two Codex processes and mock model endpoints: the approved host completes while the other stays unapproved with zero model calls; sending the completed host's response to the waiting host is rejected.

No new paid model experiment or previous task approval is included in this implementation. Automatic evaluation scheduling, repeated-run generation, crash recovery, a graphical review interface and comparison ingestion of batch metadata remain future work. Existing frozen pilot results retain their original serial scheduling labels.
