"""Pin the shared Muse relay and check readiness without making model requests."""

import hashlib
import http.client
import json
from pathlib import Path
from urllib.parse import urlsplit


def sha256(path):
    with path.open("rb") as stream:
        return hashlib.file_digest(stream, "sha256").hexdigest()


def endpoint(base_url):
    parsed = urlsplit(base_url)
    if (
        parsed.scheme != "http"
        or parsed.hostname != "127.0.0.1"
        or not parsed.port
        or parsed.username
        or parsed.password
        or parsed.query
        or parsed.fragment
        or parsed.path != "/v1"
    ):
        raise ValueError("campaign provider service must use http://127.0.0.1:PORT/v1")
    return parsed


def freeze_service(path, config):
    provider = config.get("model_providers", {}).get(config.get("model_provider"), {})
    is_muse = str(config.get("model", "")).startswith("muse-")
    if path is None:
        if is_muse:
            raise ValueError(
                "Muse campaigns require --provider-service for the shared limiter"
            )
        return None, {}
    path = path.resolve(strict=True)
    with path.open("rb") as stream:
        data = stream.read(65537)
    if len(data) > 65536:
        raise ValueError("provider service receipt exceeds size limit")
    service = json.loads(data)
    base_url = service["base_url"]
    endpoint(base_url)
    rate = service["requests_per_minute"]
    if (
        service.get("schema_version") != 1
        or type(rate) is not int
        or not 1 <= rate <= 100
        or provider.get("base_url") != base_url
        or service.get("upstream") != "https://api.meta.ai/v1"
    ):
        raise ValueError("provider profile does not match the shared Muse limiter")
    directory = Path(service["proxy_directory"]).resolve(strict=True)
    if directory != path.parent:
        raise ValueError("provider service receipt must belong to its proxy directory")
    sources = service["source_sha256"]
    if set(sources) != {"provider_proxy.py", "provider_rate_limit.py"}:
        raise ValueError("provider service source inventory is incomplete")
    pins = {str(path): hashlib.sha256(data).hexdigest()}
    for name, expected in sources.items():
        source = directory / name
        if source.is_symlink() or sha256(source) != expected:
            raise ValueError("provider service source changed: " + name)
        pins[str(source)] = expected
    return {
        "receipt": str(path),
        "base_url": base_url,
        "requests_per_minute": rate,
        "upstream": service["upstream"],
        "source_commit": service.get("source_commit"),
    }, pins


def check_service(manifest):
    service = manifest.get("provider_service")
    if service is None:
        if str(manifest.get("requested_model", "")).startswith("muse-"):
            raise ValueError("Muse campaign has no pinned shared provider service")
        return
    parsed = endpoint(service["base_url"])
    connection = http.client.HTTPConnection(parsed.hostname, parsed.port, timeout=3)
    try:
        connection.request("GET", "/health")
        response = connection.getresponse()
        body = response.read(4097)
        if response.status != 200 or len(body) > 4096:
            raise ValueError("shared provider service is unavailable")
        health = json.loads(body)
        if (
            health.get("status") != "ready"
            or type(health.get("requests_per_minute")) is not int
            or health["requests_per_minute"] != service["requests_per_minute"]
        ):
            raise ValueError(
                "shared provider service readiness or rate differs from campaign"
            )
    finally:
        connection.close()
