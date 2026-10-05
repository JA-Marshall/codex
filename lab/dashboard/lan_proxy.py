#!/usr/bin/env python3
"""Expose read-only dashboard views to one LAN through a fixed loopback upstream."""

import argparse
from http.client import HTTPConnection, HTTPException
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from ipaddress import IPv4Address, IPv4Network
import re
from urllib.parse import urlsplit

STATIC_PATHS = {"/", "/app.js", "/style.css", "/api/campaigns"}
CAMPAIGN_PATH = re.compile(r"/api/campaigns/[A-Za-z0-9][A-Za-z0-9._-]{0,159}\Z")
RESPONSE_HEADERS = (
    "Content-Type",
    "Cache-Control",
    "Content-Security-Policy",
    "X-Content-Type-Options",
)
MAX_RESPONSE_BYTES = 16 * 1024 * 1024


def make_proxy(listen_address, subnet, port=8787, upstream_port=8787):
    address = IPv4Address(listen_address)
    network = IPv4Network(subnet, strict=False)
    if address not in network:
        raise ValueError("The listening address must belong to the allowed subnet")

    class Handler(BaseHTTPRequestHandler):
        def setup(self):
            super().setup()
            self.connection.settimeout(15)

        def do_HEAD(self):
            self.do_GET()

        def do_GET(self):
            hosts = self.headers.get_all("Host", [])
            if IPv4Address(self.client_address[0]) not in network or (
                len(hosts) != 1
                or hosts[0]
                not in (str(address), f"{address}:{self.server.server_port}")
            ):
                self.send_error(403)
                return
            try:
                target = urlsplit(self.path)
            except ValueError:
                self.send_error(404)
                return
            if (
                target.scheme
                or target.netloc
                or (
                    target.path not in STATIC_PATHS
                    and not CAMPAIGN_PATH.fullmatch(target.path)
                )
            ):
                self.send_error(404)
                return
            upstream = HTTPConnection("127.0.0.1", upstream_port, timeout=10)
            try:
                upstream.request(
                    self.command, target.path, headers={"Host": "localhost"}
                )
                response = upstream.getresponse()
                payload = response.read(MAX_RESPONSE_BYTES + 1)
                if len(payload) > MAX_RESPONSE_BYTES:
                    raise ValueError("Upstream response is too large")
                length = (
                    int(response.getheader("Content-Length", "0"))
                    if self.command == "HEAD"
                    else len(payload)
                )
                if length < 0:
                    raise ValueError("Invalid upstream response length")
                status = response.status
                headers = {
                    header: response.getheader(header) for header in RESPONSE_HEADERS
                }
            except (OSError, HTTPException, ValueError):
                self.send_error(502, "The local dashboard is unavailable")
                return
            finally:
                upstream.close()
            self.send_response(status)
            for header, value in headers.items():
                if value is not None:
                    self.send_header(header, value)
            self.send_header("Content-Length", str(length))
            self.end_headers()
            if self.command != "HEAD":
                self.wfile.write(payload)

        def reject_write(self):
            self.send_response(405)
            self.send_header("Allow", "GET, HEAD")
            self.send_header("Content-Length", "0")
            self.end_headers()

        do_POST = do_PUT = do_PATCH = do_DELETE = do_OPTIONS = reject_write

        def log_message(self, *_args):
            pass

    return ThreadingHTTPServer((str(address), port), Handler)


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--listen-address", required=True, type=IPv4Address)
    parser.add_argument("--subnet", required=True)
    parser.add_argument("--port", type=int, default=8787)
    parser.add_argument("--upstream-port", type=int, default=8787)
    args = parser.parse_args()
    address = args.listen_address
    if not address.is_private or address.is_loopback or address.is_unspecified:
        parser.error("--listen-address must be a private LAN IPv4 address")
    try:
        network = IPv4Network(args.subnet, strict=False)
        if address not in network:
            raise ValueError("Listening address is outside --subnet")
    except ValueError as error:
        parser.error(str(error))
    with make_proxy(address, network, args.port, args.upstream_port) as server:
        print(
            f"Read-only LAN dashboard: http://{address}:{server.server_port}",
            flush=True,
        )
        try:
            server.serve_forever()
        except KeyboardInterrupt:
            pass


if __name__ == "__main__":
    main()
