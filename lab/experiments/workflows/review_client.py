"""Authenticated host-only broker client. Credentials never enter candidate input."""

import json
from urllib.error import HTTPError
from urllib.parse import urlsplit
from urllib.request import Request, urlopen


class ReviewClient:
    def __init__(self, origin, token):
        parts = urlsplit(origin)
        if parts.scheme != "http" or parts.hostname != "127.0.0.1" or parts.path not in ("", "/"):
            raise ValueError("explicit loopback broker origin required")
        self.origin, self.token = origin.rstrip("/"), token

    def call(self, operation, **payload):
        request = Request(self.origin + "/runner/" + operation,
                          data=json.dumps(payload).encode(),
                          headers={"Content-Type": "application/json", "Authorization": "Bearer " + self.token})
        try:
            with urlopen(request, timeout=2) as response:
                return json.load(response)["result"]
        except HTTPError as error:
            if error.code in (400, 403, 409):
                raise RuntimeError("broker rejected runner operation") from None
            raise
