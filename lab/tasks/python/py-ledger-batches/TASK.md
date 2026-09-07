# Extend a durable ledger with idempotent batches

Preserve existing `deposit STATE` and `balances STATE`. Deposit reads `{"account":A,"amount":N}`
(nonempty string, positive integer excluding booleans), adds funds, and returns balances.
Invalid deposits return `invalid deposit`. Missing files represent `{"balances":{},"receipts":{}}`.

Add `batch STATE`, reading exactly `{"id":ID,"transfers":[...]}`. ID must be a nonempty string
and transfers a nonempty list, otherwise `invalid batch`. Each transfer contains exactly
`from`, `to`, `amount`: distinct nonempty string accounts and positive integer excluding booleans;
failures return `invalid transfer`. For new IDs, validate and apply each transfer in order, permitting funds received earlier
in the batch to be spent later. Missing source accounts have zero funds. Insufficient available
funds returns `insufficient funds`. Zero balances remain present. On any failure, state bytes
must stay unchanged; only a complete successful batch is persisted.

Persist receipts by ID as `{"transfers":original_list,"balances":result_at_commit}`. Repeating
the same ID with an equal transfer list returns that recorded result, even after later deposits,
and does not write or reapply transfers. For existing IDs, validate every transfer's fields and types
before comparing the list; invalid transfers still return `invalid transfer`. Do not check available
funds again on a valid replay. A reused ID with different valid transfers returns `id conflict`.
Save the entire state as sorted-key compact JSON with default ASCII escapes and final LF.
No crashes, simultaneous writers, malformed preexisting state, or external banking are in scope.


Deliver changes in `src/` and, optionally, `tests/`. Use only the Python 3.12 standard library. Run `python -m unittest discover -s tests` from the project directory. The CLI is `python src/main.py` followed by the arguments below. It is also run from arbitrary working directories: data paths are relative to that working directory. Successful commands emit one JSON value and exit 0. Listed validation failures emit `{"error":"<message>"}` and exit 2. JSON whitespace and object-key order do not matter; array order and file bytes do. Do not add external services, network calls, dependencies, or unrelated features.
