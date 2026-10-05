"""Reader/close races exercised without relying on thread scheduling luck."""

import pytest

from openai_codex._message_router import MessageRouter
from openai_codex.client import CodexClient
from openai_codex.errors import TransportClosedError


def test_turn_registered_after_transport_failure_does_not_wait_forever():
    router = MessageRouter()
    router.fail_all(TransportClosedError("closed during turn/start"))
    router.register_turn("late-turn")
    with pytest.raises(TransportClosedError):
        router.next_turn_notification("late-turn")
    assert isinstance(
        router.create_response_waiter("late-request").get_nowait(), TransportClosedError
    )


def test_reader_registers_turn_before_caller_can_miss_early_events(monkeypatch):
    client = CodexClient()
    waiter = client._router.create_response_waiter("request")
    messages = iter(
        [
            {"id": "request", "result": {"turn": {"id": "turn"}}},
            {"method": "item/testing", "params": {"turnId": "turn"}},
        ]
    )
    monkeypatch.setattr(client, "_read_message", lambda: next(messages))
    client._reader_loop()
    assert waiter.get_nowait() == {"turn": {"id": "turn"}}
    client.register_turn_notifications("turn")
    assert client.next_turn_notification("turn").method == "item/testing"
