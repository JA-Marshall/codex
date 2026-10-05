"""Bounded Zen attempts before Meta; never replay an opened response stream."""

import http.client
import json
import math
import time
from urllib.parse import urlsplit

from provider_rate_limit import Cancelled, retry_after


class ZenProvider:
    def __init__(self, upstream, key, attempts=2, timeout=30):
        endpoint = urlsplit(upstream)
        if (
            endpoint.scheme not in ("https", "http")
            or not endpoint.hostname
            or endpoint.username
            or endpoint.password
            or endpoint.query
            or endpoint.fragment
            or (
                endpoint.scheme == "http"
                and endpoint.hostname not in ("127.0.0.1", "localhost")
            )
        ):
            raise ValueError("Zen endpoint must be HTTPS (or loopback HTTP for tests)")
        if not key or any(c in key for c in "\r\n"):
            raise ValueError("Zen credential is missing or malformed")
        if type(attempts) is not int or not 1 <= attempts <= 3:
            raise ValueError("Zen attempts must be from 1 to 3")
        if not math.isfinite(timeout) or not 0 < timeout <= 300:
            raise ValueError("Zen timeout must be from 0 to 300 seconds")
        self.endpoint, self.key, self.attempts, self.timeout = (
            endpoint,
            key,
            attempts,
            timeout,
        )
        self.blocked_until = 0

    def open(self, path, body, headers, cancelled, journal, request_id):
        # Zen does not expose Meta's compaction route or every Meta model.
        if path != "/v1/responses":
            return None
        try:
            payload = json.loads(body)
        except (ValueError, UnicodeDecodeError):
            return None
        if not isinstance(payload, dict):
            return None
        model = payload.get("model")
        aliases = {
            "muse-spark-1.3-contributor": "muse-spark-1.3-contributor-free",
            "muse-spark-1.2-contributor": "muse-spark-1.2-contributor-free",
            "muse-spark-1.3": "muse-spark-1.3",
            "muse-spark-1.2": "muse-spark-1.2",
        }
        if not isinstance(model, str) or model not in aliases:
            return None
        if time.monotonic() < self.blocked_until:
            return None
        payload["model"] = aliases[model]
        zen_body = json.dumps(payload).encode()
        zen_headers = {
            k: v
            for k, v in headers.items()
            if k.lower()
            not in ("authorization", "content-length", "x-api-key", "api-key")
        }
        zen_headers["Authorization"] = "Bearer " + self.key
        zen_headers["Content-Length"] = str(len(zen_body))
        endpoint = self.endpoint
        connection_type = (
            http.client.HTTPSConnection
            if endpoint.scheme == "https"
            else http.client.HTTPConnection
        )
        for attempt in range(self.attempts):
            if cancelled():
                raise Cancelled()
            connection = connection_type(
                endpoint.hostname, endpoint.port, timeout=self.timeout
            )
            journal.event(
                "provider_attempt",
                request_id=request_id,
                provider="zen",
                attempt=attempt + 1,
            )
            delay = min(2**attempt, 2)
            try:
                connection.request(
                    "POST",
                    endpoint.path.rstrip("/") + "/responses",
                    body=zen_body,
                    headers=zen_headers,
                )
                response = connection.getresponse()
                status = response.status
                if status not in (401, 402, 403, 404, 408, 429) and status < 500:
                    # Ownership transfers to the streaming caller, even for invalid requests.
                    return connection, response
                journal.event(
                    "provider_rejected",
                    request_id=request_id,
                    provider="zen",
                    status=status,
                )
                if status in (401, 402, 403, 404):
                    self.blocked_until = time.monotonic() + 60
                    connection.close()
                    break
                if response.getheader("Retry-After"):
                    delay = retry_after(response.getheader("Retry-After"))
                    self.blocked_until = time.monotonic() + delay
                connection.close()
                if delay > 2:
                    break
            except (OSError, http.client.HTTPException):
                connection.close()
                journal.event(
                    "provider_unreachable", request_id=request_id, provider="zen"
                )
            if attempt + 1 < self.attempts:
                deadline = time.monotonic() + delay
                while time.monotonic() < deadline:
                    if cancelled():
                        raise Cancelled()
                    time.sleep(min(0.1, max(0, deadline - time.monotonic())))
        journal.event("provider_failover", request_id=request_id, provider="meta")
        return None
