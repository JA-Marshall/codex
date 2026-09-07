"""Private contract scenarios and expected observations, never mounted for a candidate."""


def view(id, **fields):
    return dict(id=id, payload={}, priority=0, dependencies=[], max_attempts=3,
                ready_at=0, state="pending", attempts=0, worker=None, lease_until=None, **fields)


def job(id, **fields):
    result = view(id)
    result.update(fields)
    return result


def ok(value):
    return {"ok": value}


ERROR = {"error": "ValueError"}


def step(op, **args):
    return {"op": op, "args": args}


def scenario(name, steps, expected):
    return {"name": name, "steps": steps, "expected": expected}


CASES = [
    scenario("empty", [step("submit", jobs=[]), step("get", id="missing"), step("list"), step("claim", worker="w", now=0, lease_seconds=5)], [ok([]), ok(None), ok([]), ok(None)]),
    scenario("durable_views", [step("submit", jobs=[{"id":"z","payload":{"nested":[1,True,None,"é"]}}, {"id":"a"}]), step("list")],
             [ok([job("z",payload={"nested":[1,True,None,"é"]}),job("a")]),ok([job("a"),job("z",payload={"nested":[1,True,None,"é"]})])]),
    scenario("priority_and_ties", [step("submit",jobs=[{"id":"b","priority":2},{"id":"a","priority":2},{"id":"high","priority":3},{"id":"later","priority":99,"ready_at":10}])]
             +[step("claim",worker="w",now=0,lease_seconds=5)]*4,
             [ok([job("b",priority=2),job("a",priority=2),job("high",priority=3),job("later",priority=99,ready_at=10)])]
             +[ok(job(id,priority=p,state="running",attempts=1,worker="w",lease_until=5)) for id,p in [("high",3),("a",2),("b",2)]]+[ok(None)]),
    scenario("dependency_diamond", [step("submit",jobs=[{"id":"d","dependencies":["b","c","b"]},{"id":"c","dependencies":["a"]},{"id":"b","dependencies":["a"]},{"id":"a"}]),
              step("claim",worker="w",now=0,lease_seconds=10),step("complete",id="a",worker="w",attempt=1,now=1),step("claim",worker="w",now=1,lease_seconds=10),step("claim",worker="v",now=1,lease_seconds=10),step("claim",worker="x",now=1,lease_seconds=10)],
             [ok([job("d",dependencies=["b","c"]),job("c",dependencies=["a"]),job("b",dependencies=["a"]),job("a")]),ok(job("a",state="running",attempts=1,worker="w",lease_until=10)),ok(job("a",state="succeeded",attempts=1)),ok(job("b",dependencies=["a"],state="running",attempts=1,worker="w",lease_until=11)),ok(job("c",dependencies=["a"],state="running",attempts=1,worker="v",lease_until=11)),ok(None)]),
    scenario("expiry_boundary", [step("submit",jobs=[{"id":"a"}]),step("claim",worker="w",now=0,lease_seconds=5),step("recover",now=4),step("recover",now=5),step("recover",now=8),step("get",id="a")],
             [ok([job("a")]),ok(job("a",state="running",attempts=1,worker="w",lease_until=5)),ok([]),ok(["a"]),ok([]),ok(job("a",attempts=1,ready_at=5))]),
    scenario("same_worker_stale_attempt", [step("submit",jobs=[{"id":"a"}]),step("claim",worker="w",now=0,lease_seconds=5),step("claim",worker="w",now=5,lease_seconds=5),step("complete",id="a",worker="w",attempt=1,now=6),step("complete",id="a",worker="w",attempt=2,now=6)],
             [ok([job("a")]),ok(job("a",state="running",attempts=1,worker="w",lease_until=5)),ok(job("a",state="running",attempts=2,worker="w",lease_until=10,ready_at=5)),ERROR,ok(job("a",state="succeeded",attempts=2,ready_at=5))]),
    scenario("retry_delay_and_limit", [step("submit",jobs=[{"id":"a","max_attempts":2}]),step("claim",worker="w",now=0,lease_seconds=10),step("fail",id="a",worker="w",attempt=1,now=1,retry_delay=3),step("claim",worker="w",now=3,lease_seconds=10),step("claim",worker="v",now=4,lease_seconds=10),step("fail",id="a",worker="v",attempt=2,now=5),step("claim",worker="x",now=100,lease_seconds=10)],
             [ok([job("a",max_attempts=2)]),ok(job("a",max_attempts=2,state="running",attempts=1,worker="w",lease_until=10)),ok(job("a",max_attempts=2,attempts=1,ready_at=4)),ok(None),ok(job("a",max_attempts=2,attempts=2,ready_at=4,state="running",worker="v",lease_until=14)),ok(job("a",max_attempts=2,attempts=2,ready_at=4,state="failed")),ok(None)]),
    scenario("exhausted_expiry_blocks_dependent", [step("submit",jobs=[{"id":"a","max_attempts":1},{"id":"b","dependencies":["a"]}]),step("claim",worker="w",now=0,lease_seconds=2),step("claim",worker="v",now=2,lease_seconds=2),step("list")],
             [ok([job("a",max_attempts=1),job("b",dependencies=["a"])]),ok(job("a",max_attempts=1,state="running",attempts=1,worker="w",lease_until=2)),ok(None),ok([job("a",max_attempts=1,state="failed",attempts=1),job("b",dependencies=["a"])])]),
    scenario("idempotency_after_retry", [step("submit",jobs=[{"id":"a"}]),step("claim",worker="w",now=0,lease_seconds=10),step("fail",id="a",worker="w",attempt=1,now=1,retry_delay=5),step("submit",jobs=[{"id":"a"}]),step("submit",jobs=[{"id":"new"},{"id":"a","priority":1}]),step("get",id="new")],
             [ok([job("a")]),ok(job("a",state="running",attempts=1,worker="w",lease_until=10)),ok(job("a",attempts=1,ready_at=6)),ok([job("a",attempts=1,ready_at=6)]),ERROR,ok(None)]),
    scenario("invalid_completion_no_recovery", [step("submit",jobs=[{"id":"a"}]),step("claim",worker="w",now=0,lease_seconds=5),step("complete",id="a",worker="v",attempt=1,now=1),step("complete",id="a",worker="w",attempt=1,now=5),step("get",id="a")],
             [ok([job("a")]),ok(job("a",state="running",attempts=1,worker="w",lease_until=5)),ERROR,ERROR,ok(job("a",state="running",attempts=1,worker="w",lease_until=5))]),
]

for name, bad in [
    ("unknown", [{"id":"valid"},{"id":"b","dependencies":["absent"]}]),
    ("cycle", [{"id":"a","dependencies":["b"]},{"id":"b","dependencies":["a"]}]),
    ("self", [{"id":"a","dependencies":["a"]}]),
    ("duplicate", [{"id":"a"},{"id":"a"}]),
    ("bool_priority", [{"id":"a","priority":True}]),
    ("bool_attempts", [{"id":"a","max_attempts":True}]),
    ("negative_ready", [{"id":"a","ready_at":-1}]),
    ("empty_id", [{"id":""}]),
    ("numeric_id", [{"id":1}]),
    ("unknown_field", [{"id":"a","unknown":1}]),
    ("payload_array", [{"id":"a","payload":[]}]),
    ("nonfinite_payload", [{"id":"a","payload":{"value":float('nan')}}]),
    ("dependencies_string", [{"id":"a","dependencies":"x"}]),
    ("attempts_limit", [{"id":"a","max_attempts":101}]),
    ("batch_object", {"id":"a"}),
]:
    CASES.append(scenario("rollback_"+name,[step("submit",jobs=bad),step("list")],[ERROR,ok([])]))

CASES.append(scenario("invalid_claim_no_recovery", [step("submit",jobs=[{"id":"a"}]),step("claim",worker="w",now=0,lease_seconds=2),step("claim",worker="",now=3,lease_seconds=2),step("claim",worker="v",now=True,lease_seconds=2),step("claim",worker="v",now=3,lease_seconds=0),step("get",id="a")],
    [ok([job("a")]),ok(job("a",state="running",attempts=1,worker="w",lease_until=2)),ERROR,ERROR,ERROR,ok(job("a",state="running",attempts=1,worker="w",lease_until=2))]))

CLI_INVALID = [b'{', b'[]', b'\xff', b'{"op":"unknown"}', b'{"op":"list","extra":1}', b'{"op":"claim"}', b'{"op":"__getattribute__","name":"db_path"}']

CASES.append(scenario("json_type_idempotency", [step("submit",jobs=[{"id":"a","payload":{"v":1}}]),step("submit",jobs=[{"id":"a","payload":{"v":True}}]),step("get",id="a")],
    [ok([job("a",payload={"v":1})]),ERROR,ok(job("a",payload={"v":1}))]))
CASES.append(scenario("terminal_and_invalid_fail", [step("submit",jobs=[{"id":"a"}]),step("claim",worker="w",now=0,lease_seconds=5),step("fail",id="a",worker="w",attempt=1,now=1,retry_delay=True),step("complete",id="a",worker="w",attempt=1,now=1),step("complete",id="a",worker="w",attempt=1,now=2),step("claim",worker="x",now=9,lease_seconds=5)],
    [ok([job("a")]),ok(job("a",state="running",attempts=1,worker="w",lease_until=5)),ERROR,ok(job("a",state="succeeded",attempts=1)),ERROR,ok(None)]))
