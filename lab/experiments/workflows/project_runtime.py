"""Aggregate actual increment receipts without losing unknowns or stop failures."""


def aggregate_runtime(receipts, run_id):
    if not receipts:
        raise ValueError("no increment receipts")
    result = dict(receipts[-1])
    result["increment_runtime_receipts"] = receipts
    usage = dict(receipts[-1]["usage"])
    usage["run_id"] = run_id
    for name in (
        "requests",
        "observed_tokens",
        "observed_input_tokens",
        "observed_output_tokens",
        "observed_cached_input_tokens",
        "charged_tokens",
        "reserved_tokens",
        "unknown_requests",
        "in_flight",
    ):
        values = [receipt["usage"][name] for receipt in receipts]
        usage[name] = None if any(value is None for value in values) else sum(values)
    result["usage"] = usage
    result["fidelity"] = {
        "complete": all(receipt["fidelity"]["complete"] for receipt in receipts),
        "increments": [receipt["fidelity"] for receipt in receipts],
    }
    result["provider_handlers_stopped"] = all(
        receipt["provider_handlers_stopped"] is True for receipt in receipts
    )
    result["process"] = dict(
        result["process"],
        stop_status="confirmed"
        if all(receipt["process"]["stop_status"] == "confirmed" for receipt in receipts)
        else "unconfirmed",
    )
    return result
